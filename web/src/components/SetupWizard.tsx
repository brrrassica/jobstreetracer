import { useEffect, useMemo, useState } from "react";
import type { Settings as SettingsType } from "../types";
import { Modal } from "./Modal";

interface SetupStatus {
  root: string;
  python: string;
  platform: string;
  static_dir: string;
  config_path: string;
  feed_url: string;
  bridge_url: string;
  pwa_url: string;
  command: string[];
  command_string: string;
  autostart: {
    supported: boolean;
    enabled: boolean;
    method: string;
    path: string;
    command: string;
    detail: string;
    error: string;
  };
}

interface Props {
  open: boolean;
  settings: SettingsType;
  canInstall: boolean;
  onClose: () => void;
  onSaveSettings: (settings: SettingsType) => void;
  onSync: () => void;
  onRequestNotifications: () => void;
  onInstall: () => void;
  onToast: (message: string, error?: boolean) => void;
}

const DEFAULT_BRIDGE = "http://127.0.0.1:8765";

async function probeBridge(base: string): Promise<{ ok: boolean; version?: string }> {
  const url = `${base.replace(/\/+$/, "")}/api/health`;
  try {
    const response = await fetch(url, { cache: "no-store" });
    const data = (await response.json()) as { ok?: boolean; version?: string };
    return { ok: response.ok && Boolean(data.ok), version: data.version };
  } catch {
    return { ok: false };
  }
}

async function fetchSetupStatus(base: string): Promise<SetupStatus | null> {
  try {
    const response = await fetch(`${base.replace(/\/+$/, "")}/api/setup/status`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as SetupStatus;
  } catch {
    return null;
  }
}

function bootstrapCommand(platformHint: string): string {
  const win = platformHint.startsWith("win");
  if (win) {
    return [
      'cd /d "%USERPROFILE%\\projects\\jobstreetracer"',
      "python -m venv .venv",
      ".venv\\Scripts\\pip install -e .",
      ".venv\\Scripts\\jobstreetracer setup --enable-autostart",
      ".venv\\Scripts\\jobstreetracer bridge --static web\\dist --open",
    ].join("\r\n");
  }
  return [
    'cd "$HOME/projects/jobstreetracer"',
    "python3 -m venv .venv",
    ".venv/bin/pip install -e .",
    ".venv/bin/jobstreetracer setup --enable-autostart",
    ".venv/bin/jobstreetracer bridge --static web/dist --open",
  ].join("\n");
}

export function SetupWizard({
  open,
  settings,
  canInstall,
  onClose,
  onSaveSettings,
  onSync,
  onRequestNotifications,
  onInstall,
  onToast,
}: Props) {
  const [step, setStep] = useState(0);
  const [bridgeUrl, setBridgeUrl] = useState(settings.bridgeUrl || DEFAULT_BRIDGE);
  const [feedUrl, setFeedUrl] = useState(settings.feedUrl || "");
  const [probing, setProbing] = useState(false);
  const [bridgeOk, setBridgeOk] = useState(false);
  const [bridgeVersion, setBridgeVersion] = useState("");
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [autostartBusy, setAutostartBusy] = useState(false);
  const [mirrorSearches, setMirrorSearches] = useState(settings.mirrorSearches);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setBridgeUrl(settings.bridgeUrl || DEFAULT_BRIDGE);
    setFeedUrl(settings.feedUrl || "");
    setMirrorSearches(settings.mirrorSearches);
  }, [open, settings.bridgeUrl, settings.feedUrl, settings.mirrorSearches]);

  const base = bridgeUrl.trim().replace(/\/+$/, "");
  const platform = status?.platform ?? (navigator.userAgent.includes("Windows") ? "win32" : "linux");
  const installCmd = bootstrapCommand(platform);

  const detect = async (candidate?: string) => {
    const target = (candidate ?? bridgeUrl).trim().replace(/\/+$/, "") || DEFAULT_BRIDGE;
    setProbing(true);
    try {
      const result = await probeBridge(target);
      setBridgeOk(result.ok);
      setBridgeVersion(result.version ?? "");
      if (result.ok) {
        setBridgeUrl(target);
        const info = await fetchSetupStatus(target);
        setStatus(info);
        if (info?.feed_url && !feedUrl) setFeedUrl("");
        onToast(`Bridge connected${result.version ? ` (v${result.version})` : ""}.`);
      } else {
        setStatus(null);
        onToast("Bridge not reachable at that address.", true);
      }
    } finally {
      setProbing(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    void detect(settings.bridgeUrl || DEFAULT_BRIDGE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const applyConnection = () => {
    const next: SettingsType = {
      ...settings,
      bridgeUrl: base,
      feedUrl: feedUrl.trim(),
      mirrorSearches,
    };
    onSaveSettings(next);
    onToast("Feed and bridge settings saved.");
  };

  const toggleAutostart = async (enabled: boolean) => {
    if (!bridgeOk) {
      onToast("Connect to the local bridge first.", true);
      return;
    }
    setAutostartBusy(true);
    try {
      const response = await fetch(`${base}/api/setup/autostart`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-JSR-Bridge": "1" },
        body: JSON.stringify({ enabled }),
      });
      const data = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        autostart?: SetupStatus["autostart"];
      };
      if (!response.ok || data.error) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      if (data.autostart) {
        setStatus((current) => (current ? { ...current, autostart: data.autostart! } : current));
      } else {
        setStatus(await fetchSetupStatus(base));
      }
      onToast(enabled ? "Autostart enabled." : "Autostart disabled.");
    } catch (error) {
      onToast(error instanceof Error ? error.message : String(error), true);
    } finally {
      setAutostartBusy(false);
    }
  };

  const copy = async (text: string, label = "Copied to clipboard.") => {
    try {
      await navigator.clipboard.writeText(text);
      onToast(label);
    } catch {
      onToast("Could not copy automatically — select and copy the text manually.", true);
    }
  };

  const steps = useMemo(
    () => [
      { id: "bridge", title: "Local bridge" },
      { id: "feed", title: "Feed" },
      { id: "alerts", title: "Alerts" },
      { id: "autostart", title: "Autostart" },
    ],
    [],
  );

  if (!open) return null;

  return (
    <Modal title="Setup wizard" onClose={onClose} wide>
      <div className="wizard">
        <ol className="wizard-steps" aria-label="Setup steps">
          {steps.map((item, index) => (
            <li key={item.id} className={index === step ? "active" : index < step ? "done" : ""}>
              <button className="wizard-step-btn" onClick={() => setStep(index)}>
                <span className="wizard-num">{index + 1}</span>
                {item.title}
              </button>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <section className="wizard-pane">
            <h3>Connect the local bridge</h3>
            <p className="muted">
              The GitHub Pages app is static. The local bridge on your machine provides the feed, can run the
              scraper, and relays Telegram safely. This is a user process, not a system daemon.
            </p>
            <div className="wizard-row">
              <label className="field" style={{ flex: 1 }}>
                <span>Bridge URL</span>
                <input value={bridgeUrl} onChange={(event) => setBridgeUrl(event.target.value)} />
              </label>
              <button className="btn" onClick={() => void detect()} disabled={probing}>
                {probing ? "Checking…" : "Detect"}
              </button>
              <button className="btn" onClick={() => void detect(DEFAULT_BRIDGE)} disabled={probing}>
                Try default
              </button>
            </div>
            <div className={`notice ${bridgeOk ? "" : "notice-warn"}`}>
              {bridgeOk ? (
                <>
                  <strong>Bridge connected.</strong> {bridgeVersion ? `Version ${bridgeVersion}. ` : ""}
                  {status?.pwa_url ? (
                    <>
                      Local PWA: <a href={status.pwa_url}>{status.pwa_url}</a>
                    </>
                  ) : null}
                </>
              ) : (
                <>
                  <strong>Bridge not running.</strong> If you already have the repo set up, start it with the
                  command below. If not, run the bootstrap once (it creates a venv, installs, enables autostart,
                  and starts the bridge).
                </>
              )}
            </div>
            {status?.command_string && (
              <div className="field">
                <span>Start command (detected)</span>
                <textarea readOnly rows={2} value={status.command_string} />
                <div className="inline-form">
                  <button className="btn btn-small" onClick={() => void copy(status.command_string, "Start command copied.")}>Copy</button>
                </div>
              </div>
            )}
            <div className="field">
              <span>Bootstrap / install command</span>
              <textarea readOnly rows={6} value={installCmd} />
              <div className="inline-form">
                <button className="btn btn-small" onClick={() => void copy(installCmd, "Bootstrap command copied.")}>
                  Copy
                </button>
                {canInstall && (
                  <button className="btn btn-small" onClick={onInstall}>
                    Install this app
                  </button>
                )}
              </div>
              <small>
                Run in a terminal. Adjust the project path if needed. On Linux/macOS this uses your user account
                (no sudo). On Windows, run in PowerShell or Command Prompt.
              </small>
            </div>
          </section>
        )}

        {step === 1 && (
          <section className="wizard-pane">
            <h3>Choose your feed</h3>
            <p className="muted">
              The app stores listings locally in this browser. Pick how it receives new data.
            </p>
            <div className="wizard-cards">
              <button
                className={`wizard-card ${bridgeOk ? "recommended" : ""}`}
                onClick={() => {
                  if (bridgeOk && status?.feed_url) setFeedUrl("");
                  setStep(1);
                }}
              >
                <strong>Local bridge feed {bridgeOk ? "(recommended, ready)" : "(recommended)"}</strong>
                <span>
                  Uses <code>{status?.feed_url || `${base}/api/feed`}</code>. Supports one-click refresh and
                  live scraping.
                </span>
              </button>
              <div className="wizard-card">
                <strong>Remote/published feed URL</strong>
                <span>Use a JSON feed you host privately. Avoid publishing personal job data publicly.</span>
                <input
                  placeholder="https://example.com/private/feed.json"
                  value={feedUrl}
                  onChange={(event) => setFeedUrl(event.target.value)}
                />
              </div>
              <div className="wizard-card">
                <strong>Manual import only</strong>
                <span>Leave URLs empty and use Settings → Import JSONL / JSON feed after each run.</span>
                <button
                  className="btn btn-small"
                  onClick={() => {
                    setFeedUrl("");
                    onToast("Manual-import mode selected. Save settings, then import files from Settings.");
                  }}
                >
                  Use manual import
                </button>
              </div>
            </div>
            <label className="field">
              <span>Bridge URL</span>
              <input value={bridgeUrl} onChange={(event) => setBridgeUrl(event.target.value)} />
            </label>
            <label className="field">
              <span>Feed URL override (leave empty to use the bridge feed)</span>
              <input value={feedUrl} onChange={(event) => setFeedUrl(event.target.value)} />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={mirrorSearches}
                onChange={(event) => setMirrorSearches(event.target.checked)}
              />
              Mirror search definitions from feed syncs (CLI/config becomes source of truth)
            </label>
            <div className="inline-form">
              <button className="btn btn-primary" onClick={applyConnection}>
                Save connection
              </button>
              <button
                className="btn"
                onClick={() => {
                  applyConnection();
                  window.setTimeout(() => void onSync(), 0);
                }}
                disabled={!base && !feedUrl.trim()}
              >
                Save & sync
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="wizard-pane">
            <h3>Alerts and notifications</h3>
            <p className="muted">
              New-entry toasts are shown while the app is running and polling. Keep the app open/minimized (and
              allowed to start with your session) for the most reliable alerts.
            </p>
            <div className="notice">
              <strong>Browser notifications:</strong> permission is {typeof Notification !== "undefined" ? Notification.permission : "unsupported"}.
              <div className="inline-form" style={{ marginTop: 8 }}>
                <button className="btn btn-small" onClick={onRequestNotifications}>
                  Request notification permission
                </button>
                {canInstall && (
                  <button className="btn btn-small" onClick={onInstall}>
                    Install app
                  </button>
                )}
              </div>
            </div>
            <div className="notice">
              <strong>Telegram:</strong> configure your bot token and chat id in Settings → Telegram. If direct
              browser sends fail due to CORS, keep the bridge connected so the app can relay through
              <code> /api/telegram</code>.
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="wizard-pane">
            <h3>Start automatically</h3>
            <p className="muted">
              Autostart keeps the local bridge (and your scraper/feed endpoint) available after login. This is a
              normal user-session startup entry, not a system daemon.
            </p>
            {!bridgeOk ? (
              <div className="notice notice-warn">
                Connect to the local bridge in step 1 to enable one-click autostart. You can still copy the
                bootstrap command there — it enables autostart as part of setup.
              </div>
            ) : (
              <>
                <div className="notice">
                  <strong>Status:</strong>{" "}
                  {status?.autostart.enabled ? "enabled" : "disabled"} ({status?.autostart.method || "unknown"})
                  {status?.autostart.path ? (
                    <div className="muted small">Path: {status.autostart.path}</div>
                  ) : null}
                  {status?.autostart.detail ? <div className="muted small">{status.autostart.detail}</div> : null}
                  {status?.autostart.error ? <div className="form-error">{status.autostart.error}</div> : null}
                </div>
                <div className="inline-form">
                  <button
                    className="btn btn-primary"
                    onClick={() => void toggleAutostart(true)}
                    disabled={autostartBusy || Boolean(status?.autostart.enabled)}
                  >
                    {autostartBusy ? "Working…" : "Enable autostart"}
                  </button>
                  <button
                    className="btn"
                    onClick={() => void toggleAutostart(false)}
                    disabled={autostartBusy || !status?.autostart.enabled}
                  >
                    Disable autostart
                  </button>
                  <button className="btn" onClick={() => void detect()} disabled={probing}>
                    Refresh status
                  </button>
                </div>
              </>
            )}
            <details className="help">
              <summary>System boot / elevated options</summary>
              <p>
                Login autostart does not require escalation. If you truly need the bridge before any user login,
                run the CLI with administrator/root privileges and configure a platform service (for example a
                systemd system unit on Linux or a scheduled task "At startup" on Windows). The existing
                <code> deploy/jobstreetracer.service</code> template is a starting point for Linux servers.
              </p>
            </details>
          </section>
        )}

        <div className="wizard-nav">
          <button className="btn" onClick={onClose}>Close</button>
          <div className="spacer" />
          <button className="btn" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
            Back
          </button>
          {step < steps.length - 1 ? (
            <button className="btn btn-primary" onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}>
              Next
            </button>
          ) : (
            <button className="btn btn-primary" onClick={onClose}>
              Done
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
