import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  dbBulkPut,
  dbClear,
  dbDelete,
  dbPut,
  getMeta,
  loadSnapshot,
  saveSettings,
  setMeta,
  type Snapshot,
} from "./db";
import {
  downloadText,
  exportBackup,
  fetchFeedText,
  mergeFeed,
  parseFeedText,
  searchesToToml,
} from "./feed";
import { showNewJobsNotification, updateAppBadge } from "./notify";
import { buildJobMessage, sendTelegram } from "./telegram";
import {
  DEFAULT_SETTINGS,
  type FeedPayload,
  type Job,
  type Run,
  type Search,
  type Settings as SettingsValue,
} from "./types";
import { Dashboard } from "./components/Dashboard";
import { Listings } from "./components/Listings";
import { Searches } from "./components/Searches";
import { Settings } from "./components/Settings";
import { JobDetail } from "./components/JobDetail";

const VIEWS = ["dashboard", "listings", "searches", "settings"] as const;
type View = (typeof VIEWS)[number];

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function parseView(): View {
  const raw = window.location.hash.replace(/^#\/?/, "") || "dashboard";
  const view = raw.split("?")[0] as View;
  return VIEWS.includes(view) ? view : "dashboard";
}

function effectiveFeedUrl(settings: SettingsValue): string {
  const feed = settings.feedUrl.trim();
  if (feed) return feed;
  const bridge = settings.bridgeUrl.trim().replace(/\/+$/, "");
  return bridge ? `${bridge}/api/feed` : "";
}

function bridgeUrl(settings: SettingsValue): string {
  return settings.bridgeUrl.trim().replace(/\/+$/, "");
}

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loadError, setLoadError] = useState("");
  const [view, setView] = useState<View>(parseView);
  const [routeKey, setRouteKey] = useState(window.location.hash);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<{ message: string; error: boolean } | null>(null);
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null);
  const [online, setOnline] = useState(navigator.onLine);

  const snapshotRef = useRef<Snapshot | null>(null);
  const busyRef = useRef(false);
  const autoSyncRef = useRef(false);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  const notify = useCallback((message: string, error = false) => {
    setToast({ message, error });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    void loadSnapshot()
      .then(setSnapshot)
      .catch((error) => {
        console.error("Failed to open local database", error);
        setLoadError(error instanceof Error ? error.message : String(error));
      });
  }, []);

  useEffect(() => {
    const onHash = () => {
      setView(parseView());
      setRouteKey(window.location.hash);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as InstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    const count = snapshot.jobs.filter((job) => job.isNew).length;
    void updateAppBadge(count);
  }, [snapshot]);

  const navigate = useCallback((target: string) => {
    window.location.hash = `#/${target}`;
    setView(parseView());
    setRouteKey(`#/${target}`);
  }, []);

  const applyPayload = useCallback(
    async (payload: FeedPayload, options: { importSearches?: boolean; silent?: boolean }) => {
      const current = snapshotRef.current;
      if (!current) return { added: 0, updated: 0 };
      const baselineDone = await getMeta("feedBaseline");
      const merged = mergeFeed(payload, current.jobs, current.searches, {
        importSearches: options.importSearches,
        baseline: !baselineDone,
      });
      const runMap = new Map<string, Run>([...current.runs, ...merged.runs].map((run) => [run.key, run]));
      const runs = [...runMap.values()].sort((a, b) => b.startedAt.localeCompare(a.startedAt)).slice(0, 50);
      const settings: SettingsValue = {
        ...current.settings,
        lastSyncAt: new Date().toISOString(),
        lastSyncError: "",
      };
      await Promise.all([
        dbBulkPut("jobs", merged.jobs),
        dbBulkPut("runs", runs),
        dbBulkPut("searches", merged.searches),
        saveSettings(settings),
        setMeta("feedBaseline", "1"),
      ]);
      const next: Snapshot = { jobs: merged.jobs, searches: merged.searches, runs, settings };
      setSnapshot(next);
      snapshotRef.current = next;
      const newlyFlagged = merged.added.filter((job) => job.isNew);
      if (
        newlyFlagged.length > 0 &&
        settings.notificationsEnabled &&
        "Notification" in window &&
        Notification.permission === "granted"
      ) {
        await showNewJobsNotification(newlyFlagged, settings.notifyMaxPerToast);
      }
      if (!options.silent) {
        const imported = merged.added.length - newlyFlagged.length;
        const parts = [
          `${newlyFlagged.length} new`,
          imported > 0 ? `${imported} imported` : "",
          `${merged.updated} updated`,
          merged.importedSearches ? `${merged.importedSearches} searches imported` : "",
        ].filter(Boolean);
        notify(`Sync complete: ${parts.join(", ")}.`);
      }
      return { added: merged.added.length, updated: merged.updated };
    },
    [notify],
  );

  const processFeed = useCallback(
    async (url: string, options: { importSearches?: boolean; silent?: boolean }) => {
      const text = await fetchFeedText(url);
      const payload = parseFeedText(text);
      return applyPayload(payload, {
        importSearches:
          options.importSearches ?? snapshotRef.current?.settings.mirrorSearches ?? false,
        silent: options.silent,
      });
    },
    [applyPayload],
  );

  const recordSyncError = useCallback(async (error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    const current = snapshotRef.current;
    if (!current) return;
    const settings = { ...current.settings, lastSyncAt: new Date().toISOString(), lastSyncError: message };
    await saveSettings(settings);
    const next = { ...current, settings };
    snapshotRef.current = next;
    setSnapshot(next);
  }, []);

  const syncNow = useCallback(
    async (options: { silent?: boolean } = {}) => {
      if (busyRef.current) return;
      const current = snapshotRef.current;
      if (!current) return;
      const url = effectiveFeedUrl(current.settings);
      if (!url) {
        if (!options.silent) notify("Set a feed URL or bridge URL in Settings first.", true);
        return;
      }
      busyRef.current = true;
      setSyncing(true);
      try {
        await processFeed(url, { silent: options.silent });
      } catch (error) {
        await recordSyncError(error);
        if (!options.silent) {
          notify(error instanceof Error ? error.message : String(error), true);
        }
      } finally {
        busyRef.current = false;
        setSyncing(false);
      }
    },
    [notify, processFeed, recordSyncError],
  );

  const refreshNow = useCallback(async () => {
    if (busyRef.current) return;
    const current = snapshotRef.current;
    if (!current) return;
    const bridge = bridgeUrl(current.settings);
    if (!bridge) {
      await syncNow();
      return;
    }
    busyRef.current = true;
    setSyncing(true);
    try {
      const response = await fetch(`${bridge}/api/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-JSR-Bridge": "1" },
        body: JSON.stringify({}),
      });
      const data = (await response.json().catch(() => ({}))) as {
        error?: string;
        summary?: { new_jobs?: number; scanned?: number };
      };
      if (!response.ok) throw new Error(data.error || `Bridge returned HTTP ${response.status}.`);
      await processFeed(effectiveFeedUrl(current.settings) || `${bridge}/api/feed`, {});
      if (data.summary) {
        notify(`Scrape finished: scanned ${data.summary.scanned ?? 0}, new ${data.summary.new_jobs ?? 0}.`);
      }
    } catch (error) {
      await recordSyncError(error);
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      busyRef.current = false;
      setSyncing(false);
    }
  }, [notify, processFeed, recordSyncError, syncNow]);

  const source = snapshot ? effectiveFeedUrl(snapshot.settings) : "";
  const syncRef = useRef(syncNow);
  syncRef.current = syncNow;

  useEffect(() => {
    if (!snapshot || autoSyncRef.current) return;
    if (!effectiveFeedUrl(snapshot.settings)) return;
    autoSyncRef.current = true;
    void syncRef.current({ silent: true });
  }, [snapshot]);

  useEffect(() => {
    if (!snapshot || !source) return;
    const minutes = Math.max(1, snapshot.settings.pollMinutes || 5);
    const timer = window.setInterval(() => void syncRef.current({ silent: true }), minutes * 60_000);
    return () => window.clearInterval(timer);
  }, [source, snapshot]);

  const updateJob = useCallback(
    (job: Job) => {
      setSnapshot((current) => {
        if (!current) return current;
        const next = { ...current, jobs: current.jobs.map((item) => (item.id === job.id ? job : item)) };
        snapshotRef.current = next;
        return next;
      });
      void dbPut("jobs", job);
    },
    [],
  );

  const selectJob = useCallback(
    (job: Job) => {
      setSelectedId(job.id);
      if (job.isNew || !job.tracking.seen) {
        updateJob({
          ...job,
          isNew: false,
          tracking: { ...job.tracking, seen: true, updatedAt: new Date().toISOString() },
        });
      }
    },
    [updateJob],
  );

  const saveSearch = useCallback(
    async (search: Search, previousName?: string) => {
      const current = snapshotRef.current;
      if (!current) return;
      const key = previousName ?? search.name;
      const exists = current.searches.some((item) => item.name === key);
      if (previousName && previousName !== search.name) {
        await dbDelete("searches", previousName);
      }
      const searches = exists
        ? current.searches.map((item) => (item.name === key ? search : item))
        : [...current.searches, search];
      await dbBulkPut("searches", searches);
      const next = { ...current, searches };
      snapshotRef.current = next;
      setSnapshot(next);
      notify(`Saved search “${search.name}”.`);
    },
    [notify],
  );

  const deleteSearch = useCallback(
    async (name: string) => {
      const current = snapshotRef.current;
      if (!current) return;
      const searches = current.searches.filter((item) => item.name !== name);
      await dbDelete("searches", name);
      const next = { ...current, searches };
      snapshotRef.current = next;
      setSnapshot(next);
      notify(`Deleted “${name}”.`);
    },
    [notify],
  );

  const saveSettingsValue = useCallback(
    async (settings: SettingsValue) => {
      const current = snapshotRef.current;
      if (!current) return;
      await saveSettings(settings);
      const next = { ...current, settings };
      snapshotRef.current = next;
      setSnapshot(next);
    },
    [],
  );

  const importText = useCallback(
    async (text: string, importSearches: boolean) => {
      try {
        const payload = parseFeedText(text);
        await applyPayload(payload, { importSearches });
      } catch (error) {
        notify(error instanceof Error ? error.message : String(error), true);
      }
    },
    [applyPayload, notify],
  );

  const requestNotifications = useCallback(async () => {
    if (!("Notification" in window)) {
      notify("This browser does not support notifications.", true);
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission === "granted") {
      const current = snapshotRef.current;
      if (current && !current.settings.notificationsEnabled) {
        await saveSettingsValue({ ...current.settings, notificationsEnabled: true });
      }
      notify("Notifications enabled.");
    } else {
      notify("Notification permission was not granted.", true);
    }
  }, [notify, saveSettingsValue]);

  const clearJobs = useCallback(async () => {
    await dbClear("jobs");
    const current = snapshotRef.current;
    if (!current) return;
    const next = { ...current, jobs: [] };
    snapshotRef.current = next;
    setSnapshot(next);
    setSelectedId(null);
    notify("Cached listings cleared.");
  }, [notify]);

  const clearAll = useCallback(async () => {
    await Promise.all(["jobs", "searches", "runs", "settings", "meta"].map((store) => dbClear(store)));
    const next: Snapshot = {
      jobs: [],
      searches: [],
      runs: [],
      settings: { ...DEFAULT_SETTINGS },
    };
    snapshotRef.current = next;
    setSnapshot(next);
    setSelectedId(null);
    notify("All local data erased.");
  }, [notify]);

  const install = useCallback(async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    if (choice.outcome === "accepted") notify("JobStreetracer installed.");
    setInstallPrompt(null);
  }, [installPrompt, notify]);

  const testTelegram = useCallback(
    async (text: string, telegram: SettingsValue["telegram"], bridge: string) => {
      const result = await sendTelegram(telegram, text, bridge);
      if (result.errors.length > 0) {
        throw new Error(
          `Delivered to ${result.delivered.length}; errors: ${result.errors
            .map((item) => `${item.chat_id}: ${item.error}`)
            .join("; ")}`,
        );
      }
      return `Sent to ${result.delivered.length} chat(s).`;
    },
    [],
  );

  const sendJobsToTelegram = useCallback(async (jobs: Job[]) => {
    const current = snapshotRef.current;
    if (!current) return;
    try {
      const result = await sendTelegram(
        current.settings.telegram,
        buildJobMessage(jobs),
        current.settings.bridgeUrl,
      );
      if (result.errors.length > 0) {
        notify(`Telegram: ${result.errors.map((item) => item.error).join("; ")}`, true);
      } else {
        notify(`Sent ${jobs.length} listing(s) to ${result.delivered.length} chat(s).`);
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    }
  }, [notify]);

  const selected = useMemo(
    () => snapshot?.jobs.find((job) => job.id === selectedId) ?? null,
    [snapshot, selectedId],
  );

  if (loadError) {
    return (
      <div className="splash">
        <h1>Could not open the local database</h1>
        <p>{loadError}</p>
        <button className="btn" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="splash">
        <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="" width={72} height={72} />
        <h1>JobStreetracer</h1>
        <p>Opening the local radar…</p>
      </div>
    );
  }

  const newCount = snapshot.jobs.filter((job) => job.isNew).length;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="" width={36} height={36} />
          <div>
            <strong>JobStreetracer</strong>
            <span className="brand-sub">private radar</span>
          </div>
        </div>
        <nav className="nav">
          {VIEWS.map((item) => (
            <button
              key={item}
              className={`nav-item ${view === item ? "active" : ""}`}
              onClick={() => navigate(item)}
            >
              <span className="nav-icon">
                {item === "dashboard" ? "◎" : item === "listings" ? "▤" : item === "searches" ? "⌕" : "⚙"}
              </span>
              <span>{item[0].toUpperCase() + item.slice(1)}</span>
              {item === "listings" && newCount > 0 && <span className="nav-badge">{newCount}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={`conn ${online ? "online" : "offline"}`}>
            {online ? "Online" : "Offline"}
          </span>
          <span className={`conn ${source ? "online" : ""}`}>{source ? "Feed configured" : "No feed"}</span>
          {installPrompt && (
            <button className="btn btn-small" onClick={install}>
              Install app
            </button>
          )}
        </div>
      </aside>

      <main className="main">
        {view === "dashboard" && (
          <Dashboard
            jobs={snapshot.jobs}
            searches={snapshot.searches}
            runs={snapshot.runs}
            settings={snapshot.settings}
            syncing={syncing}
            onSync={() => void syncNow()}
            onRefresh={() => void refreshNow()}
            onNavigate={navigate}
            onSelect={selectJob}
          />
        )}
        {view === "listings" && (
          <Listings key={routeKey} jobs={snapshot.jobs} searches={snapshot.searches} onSelect={selectJob} />
        )}
        {view === "searches" && (
          <Searches
            searches={snapshot.searches}
            onSave={(search, previousName) => void saveSearch(search, previousName)}
            onDelete={(name) => void deleteSearch(name)}
            onExport={() =>
              downloadText("config.toml", searchesToToml(snapshot.searches), "text/plain;charset=utf-8")
            }
          />
        )}
        {view === "settings" && (
          <Settings
            settings={snapshot.settings}
            jobs={snapshot.jobs}
            searches={snapshot.searches}
            runs={snapshot.runs}
            canInstall={Boolean(installPrompt)}
            syncing={syncing}
            onSave={(settings) => void saveSettingsValue(settings)}
            onSync={() => void syncNow()}
            onRefresh={() => void refreshNow()}
            onImportText={(text, importSearches) => void importText(text, importSearches)}
            onExportBackup={(includeSecrets) =>
              downloadText(
                `jobstreetracer-backup-${new Date().toISOString().slice(0, 10)}.json`,
                exportBackup(
                  snapshot.jobs,
                  snapshot.searches,
                  snapshot.runs,
                  snapshot.settings,
                  includeSecrets,
                ),
              )
            }
            onExportConfig={() =>
              downloadText("config.toml", searchesToToml(snapshot.searches), "text/plain;charset=utf-8")
            }
            onClearJobs={() => void clearJobs()}
            onClearAll={() => void clearAll()}
            onInstall={install}
            onRequestNotifications={() => void requestNotifications()}
            onTestTelegram={testTelegram}
            onToast={notify}
          />
        )}
        {selected && (
          <JobDetail
            job={selected}
            onClose={() => setSelectedId(null)}
            onUpdate={updateJob}
          />
        )}
        {snapshot.jobs.length > 0 && snapshot.settings.telegram.token && (
          <div className="fab-wrap">
            <button
              className="fab"
              title="Send the latest new listings to Telegram"
              onClick={() => void sendJobsToTelegram(snapshot.jobs.filter((job) => job.isNew).slice(0, 10))}
              disabled={newCount === 0}
            >
              TG {newCount || ""}
            </button>
          </div>
        )}
      </main>

      {toast && (
        <div className={`toast ${toast.error ? "toast-error" : ""}`} role="status">
          {toast.message}
        </div>
      )}
    </div>
  );
}
