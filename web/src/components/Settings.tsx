import { useEffect, useRef, useState } from "react";
import { relativeTime } from "../feed";
import type { Job, Run, Search, Settings as SettingsType } from "../types";
import { permissionState } from "../notify";

interface Props {
  settings: SettingsType;
  jobs: Job[];
  searches: Search[];
  runs: Run[];
  canInstall: boolean;
  syncing: boolean;
  onSave: (settings: SettingsType) => void;
  onSync: () => void;
  onRefresh: () => void;
  onImportText: (text: string, importSearches: boolean) => void;
  onExportBackup: (includeSecrets: boolean) => void;
  onExportConfig: () => void;
  onClearJobs: () => void;
  onClearAll: () => void;
  onInstall: () => void;
  onRequestNotifications: () => void;
  onTestTelegram: (text: string, telegram: SettingsType["telegram"], bridgeUrl: string) => Promise<string>;
  onToast: (message: string, error?: boolean) => void;
}

export function Settings({
  settings,
  jobs,
  searches,
  runs,
  canInstall,
  syncing,
  onSave,
  onSync,
  onRefresh,
  onImportText,
  onExportBackup,
  onExportConfig,
  onClearJobs,
  onClearAll,
  onInstall,
  onRequestNotifications,
  onTestTelegram,
  onToast,
}: Props) {
  const [draft, setDraft] = useState(settings);
  const [showToken, setShowToken] = useState(false);
  const [importSearches, setImportSearches] = useState(true);
  const [includeSecrets, setIncludeSecrets] = useState(false);
  const [bridgeStatus, setBridgeStatus] = useState("");
  const [testText, setTestText] = useState("JobStreetracer test message ✅");
  const [testing, setTesting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => setDraft(settings), [settings]);

  const patch = (value: Partial<SettingsType>) => setDraft((current) => ({ ...current, ...value }));
  const patchTelegram = (value: Partial<SettingsType["telegram"]>) =>
    setDraft((current) => ({ ...current, telegram: { ...current.telegram, ...value } }));

  const checkBridge = async () => {
    const base = draft.bridgeUrl.trim().replace(/\/+$/, "");
    if (!base) {
      setBridgeStatus("Set a bridge URL first.");
      return;
    }
    try {
      const response = await fetch(`${base}/api/health`, { cache: "no-store" });
      const data = (await response.json()) as { ok?: boolean; version?: string };
      setBridgeStatus(
        response.ok && data.ok ? `Bridge online (v${data.version ?? "?"})` : `Bridge error: HTTP ${response.status}`,
      );
    } catch (error) {
      setBridgeStatus(`Bridge unreachable: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const save = () => {
    onSave({
      ...draft,
      feedUrl: draft.feedUrl.trim(),
      bridgeUrl: draft.bridgeUrl.trim().replace(/\/+$/, ""),
      pollMinutes: Math.max(1, Number(draft.pollMinutes) || 5),
    });
    onToast("Settings saved.");
  };

  const testTelegram = async () => {
    setTesting(true);
    try {
      const result = await onTestTelegram(testText, draft.telegram, draft.bridgeUrl);
      onToast(result);
    } catch (error) {
      onToast(error instanceof Error ? error.message : String(error), true);
    } finally {
      setTesting(false);
    }
  };

  const permission = permissionState();

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Local configuration</p>
          <h1>Settings</h1>
          <p className="subtitle">
            Everything here stays in this browser profile. Nothing is published to GitHub Pages.
          </p>
        </div>
        <div className="head-actions">
          <button className="btn btn-primary" onClick={save}>
            Save settings
          </button>
        </div>
      </header>

      <section className="panel settings-section">
        <div className="panel-head">
          <h2>Data source</h2>
          <span className="muted">last sync {relativeTime(settings.lastSyncAt)}</span>
        </div>
        <p className="muted">
          The PWA is static. Use the local bridge for live data and “run scraper now”, or point at any JSON
          feed / <code>data/feed.json</code> URL. Importing a file always works.
        </p>
        <div className="form-grid">
          <label className="field">
            <span>Bridge URL</span>
            <input
              value={draft.bridgeUrl}
              placeholder="http://127.0.0.1:8765"
              onChange={(event) => patch({ bridgeUrl: event.target.value })}
            />
            <small>
              Start it with <code>jobstreetracer bridge --static web/dist --open</code>. Keep it on
              127.0.0.1.
            </small>
          </label>
          <label className="field">
            <span>Feed URL (optional override)</span>
            <input
              value={draft.feedUrl}
              placeholder="http://127.0.0.1:8765/api/feed or https://…/feed.json"
              onChange={(event) => patch({ feedUrl: event.target.value })}
            />
            <small>When empty, the bridge's <code>/api/feed</code> is used.</small>
          </label>
          <label className="field">
            <span>Poll interval (minutes)</span>
            <input
              type="number"
              min={1}
              value={draft.pollMinutes}
              onChange={(event) => patch({ pollMinutes: Number(event.target.value) })}
            />
            <small>Only runs while the app is open or resident in the browser.</small>
          </label>
        </div>
        <div className="inline-form">
          <button className="btn btn-small" onClick={checkBridge}>
            Check bridge
          </button>
          <button className="btn btn-small" onClick={onSync} disabled={syncing}>
            Sync now
          </button>
          <button className="btn btn-small" onClick={onRefresh} disabled={syncing || !draft.bridgeUrl}>
            Run scraper
          </button>
          {bridgeStatus && <span className="muted">{bridgeStatus}</span>}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={draft.mirrorSearches}
            onChange={(event) => patch({ mirrorSearches: event.target.checked })}
          />
          Mirror search definitions from each feed sync (overwrites local edits to those searches)
        </label>
        {settings.lastSyncError && <p className="form-error">{settings.lastSyncError}</p>}
      </section>

      <section className="panel settings-section">
        <div className="panel-head">
          <h2>Notifications & startup</h2>
          <span className="badge badge-muted">{permission}</span>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={draft.notificationsEnabled}
            onChange={(event) => patch({ notificationsEnabled: event.target.checked })}
          />
          Show an OS toast when a sync finds new listings
        </label>
        <div className="inline-form">
          <button className="btn btn-small" onClick={onRequestNotifications} disabled={permission === "granted"}>
            {permission === "granted" ? "Permission granted" : "Request permission"}
          </button>
          {canInstall && (
            <button className="btn btn-small" onClick={onInstall}>
              Install app
            </button>
          )}
        </div>
        <details className="help">
          <summary>Keep alerts running while logged in</summary>
          <p>
            Install the app, then let Chromium start it on login and keep background apps running. On Linux,
            add the installed app to your desktop session's autostart. On Windows, use{" "}
            <code>shell:startup</code> with the installed app shortcut. This keeps a normal app process open
            (not a system service), so toasts stop if you fully quit the browser.
          </p>
          <p>
            For guaranteed scraping while the app is closed, run the bridge on login too (for example an
            autostart entry for <code>jobstreetracer bridge</code>) or keep the CLI scheduler/systemd timer.
          </p>
        </details>
      </section>

      <section className="panel settings-section">
        <div className="panel-head">
          <h2>Telegram</h2>
          <span className="muted">stored locally</span>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Bot token</span>
            <div className="inline-form">
              <input
                type={showToken ? "text" : "password"}
                autoComplete="off"
                value={draft.telegram.token}
                placeholder="123456:ABC…"
                onChange={(event) => patchTelegram({ token: event.target.value })}
              />
              <button className="btn btn-small" onClick={() => setShowToken((value) => !value)}>
                {showToken ? "Hide" : "Show"}
              </button>
            </div>
          </label>
          <label className="field">
            <span>Chat ids</span>
            <input
              value={draft.telegram.chatIds}
              placeholder="123456789, 987654321"
              onChange={(event) => patchTelegram({ chatIds: event.target.value })}
            />
            <small>Comma, semicolon or whitespace separated.</small>
          </label>
          <label className="field">
            <span>Topic id (optional)</span>
            <input
              value={draft.telegram.topicId}
              placeholder="Forum topic id"
              onChange={(event) => patchTelegram({ topicId: event.target.value })}
            />
          </label>
        </div>
        <div className="inline-form">
          <input value={testText} onChange={(event) => setTestText(event.target.value)} />
          <button className="btn btn-small" onClick={testTelegram} disabled={testing}>
            {testing ? "Sending…" : "Send test"}
          </button>
        </div>
        <p className="muted small">
          Direct browser calls to Telegram are often blocked by CORS. If the test fails, configure the bridge
          URL above; the app relays through localhost instead. The token is never included in exports unless
          you opt in below.
        </p>
      </section>

      <section className="panel settings-section">
        <div className="panel-head">
          <h2>Import & export</h2>
          <span className="muted">
            {jobs.length} jobs · {searches.length} searches
          </span>
        </div>
        <div className="button-row">
          <button className="btn" onClick={() => fileInput.current?.click()}>
            Import JSONL / JSON feed
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".json,.jsonl,application/json"
            hidden
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              const text = await file.text();
              onImportText(text, importSearches);
              event.target.value = "";
            }}
          />
          <label className="check">
            <input
              type="checkbox"
              checked={importSearches}
              onChange={(event) => setImportSearches(event.target.checked)}
            />
            Import searches too
          </label>
        </div>
        <div className="button-row">
          <button className="btn" onClick={onExportConfig} disabled={searches.length === 0}>
            Export config.toml
          </button>
          <button className="btn" onClick={() => onExportBackup(includeSecrets)}>
            Export backup JSON
          </button>
          <label className="check">
            <input
              type="checkbox"
              checked={includeSecrets}
              onChange={(event) => setIncludeSecrets(event.target.checked)}
            />
            Include Telegram token
          </label>
        </div>
        <div className="button-row">
          <button
            className="btn btn-danger-ghost"
            onClick={() => {
              if (confirm("Remove all cached listings? Searches and settings stay.")) onClearJobs();
            }}
          >
            Clear listings
          </button>
          <button
            className="btn btn-danger"
            onClick={() => {
              if (
                confirm(
                  "Erase all JobStreetracer data in this browser, including searches, tracking notes and the Telegram token?",
                )
              )
                onClearAll();
            }}
          >
            Erase all local data
          </button>
        </div>
      </section>

      <section className="panel settings-section">
        <div className="panel-head">
          <h2>About</h2>
          <span className="muted">runs {runs.length} cached</span>
        </div>
        <p className="muted">
          Unofficial personal tool. JobStreet's endpoints are undocumented and can change. This app only
          filters data you already imported or fetched from your own bridge. Job data and tokens are not
          committed to the repo or published to Pages.
        </p>
        <p className="muted small">
          <a href="https://github.com/brrrassica/jobstreetracer" target="_blank" rel="noreferrer">
            github.com/brrrassica/jobstreetracer
          </a>{" "}
          · PWA base <code>/jobstreetracer/</code>
        </p>
      </section>
    </div>
  );
}
