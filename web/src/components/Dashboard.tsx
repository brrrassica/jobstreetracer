import { relativeTime, sortJobs } from "../feed";
import { STATUS_LABELS, type Job, type Run, type Search, type Settings } from "../types";

interface Props {
  jobs: Job[];
  searches: Search[];
  runs: Run[];
  settings: Settings;
  syncing: boolean;
  onSync: () => void;
  onRefresh: () => void;
  onNavigate: (view: string) => void;
  onSelect: (job: Job) => void;
  onSetup: () => void;
}

export function Dashboard({
  jobs,
  searches,
  runs,
  settings,
  syncing,
  onSync,
  onRefresh,
  onNavigate,
  onSelect,
  onSetup,
}: Props) {
  const newJobs = jobs.filter((job) => job.isNew);
  const activeSearches = searches.filter((search) => search.enabled);
  const applied = jobs.filter((job) => job.tracking.status === "applied").length;
  const shortlisted = jobs.filter((job) => job.tracking.status === "shortlisted").length;
  const recent = sortJobs(jobs, "newest").slice(0, 6);
  const source = settings.feedUrl || settings.bridgeUrl;
  const lastRun = runs[0];

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">JobStreet Indonesia radar</p>
          <h1>Dashboard</h1>
          <p className="subtitle">
            Local-first listings, saved searches and alerts. Last sync {relativeTime(settings.lastSyncAt)}.
          </p>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={onSetup}>Setup wizard</button>
          <button className="btn" onClick={onSync} disabled={syncing || !source}>
            {syncing ? "Syncing…" : "Sync feed"}
          </button>
          <button className="btn btn-primary" onClick={onRefresh} disabled={syncing || !settings.bridgeUrl}>
            {syncing ? "Working…" : "Run scraper now"}
          </button>
        </div>
      </header>

      {!source && (
        <div className="notice">
          <strong>No feed configured yet.</strong> Use the setup wizard to connect the local bridge, choose a
          feed, and enable autostart in a few clicks. You can also configure everything manually in Settings or
          import a JSONL export.
          <div className="notice-actions">
            <button className="btn btn-small btn-primary" onClick={onSetup}>
              Open setup wizard
            </button>
            <button className="btn btn-small" onClick={() => onNavigate("settings")}>
              Open settings
            </button>
          </div>
        </div>
      )}

      {settings.lastSyncError && (
        <div className="notice notice-error">
          <strong>Last sync failed:</strong> {settings.lastSyncError}
        </div>
      )}

      <div className="stat-grid">
        <button className="stat" onClick={() => onNavigate("listings?new=1")}>
          <span className="stat-label">New matches</span>
          <strong className="stat-value accent">{newJobs.length}</strong>
          <span className="stat-foot">unreviewed listings</span>
        </button>
        <button className="stat" onClick={() => onNavigate("listings")}>
          <span className="stat-label">Cached listings</span>
          <strong className="stat-value">{jobs.length}</strong>
          <span className="stat-foot">{activeSearches.length} active searches</span>
        </button>
        <button className="stat" onClick={() => onNavigate("listings?status=shortlisted")}>
          <span className="stat-label">Shortlisted</span>
          <strong className="stat-value">{shortlisted}</strong>
          <span className="stat-foot">saved for later</span>
        </button>
        <button className="stat" onClick={() => onNavigate("listings?status=applied")}>
          <span className="stat-label">Applied</span>
          <strong className="stat-value">{applied}</strong>
          <span className="stat-foot">in your pipeline</span>
        </button>
      </div>

      <div className="split">
        <section className="panel">
          <div className="panel-head">
            <h2>Latest listings</h2>
            <button className="link-btn" onClick={() => onNavigate("listings")}>
              View all →
            </button>
          </div>
          {recent.length === 0 ? (
            <p className="muted pad">Nothing cached yet. Sync a feed or import an export.</p>
          ) : (
            <div className="job-list">
              {recent.map((job) => (
                <button className="job-row" key={job.id} onClick={() => onSelect(job)}>
                  <div className="job-row-main">
                    <span className="job-title">
                      {job.isNew && <span className="dot" aria-label="new" />}
                      {job.title}
                    </span>
                    <span className="job-meta">
                      {[job.company, job.location, job.salary].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                  <span className="job-when">{relativeTime(job.firstSeen)}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Searches</h2>
            <button className="link-btn" onClick={() => onNavigate("searches")}>
              Manage →
            </button>
          </div>
          {searches.length === 0 ? (
            <p className="muted pad">No saved searches yet.</p>
          ) : (
            <div className="search-summary">
              {searches.map((search) => {
                const count = jobs.filter((job) => job.searchName === search.name).length;
                return (
                  <div className="search-line" key={search.name}>
                    <div>
                      <span className={search.enabled ? "enabled-dot" : "disabled-dot"} />
                      <strong>{search.name}</strong>
                      <span className="muted"> · {search.keywords || "all jobs"}</span>
                    </div>
                    <span className="muted">{count}</span>
                  </div>
                );
              })}
            </div>
          )}
          {lastRun && (
            <div className="run-note">
              Last run {relativeTime(lastRun.startedAt)}: scanned {lastRun.scanned}, new {lastRun.newJobs},
              errors {lastRun.errors}.
            </div>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Pipeline snapshot</h2>
          <span className="muted">tracking is stored only in this browser</span>
        </div>
        <div className="status-grid">
          {(["inbox", "shortlisted", "applied", "interview", "offer", "rejected"] as const).map((status) => {
            const count = jobs.filter((job) => job.tracking.status === status).length;
            return (
              <button
                key={status}
                className="status-card"
                onClick={() => onNavigate(`listings?status=${status}`)}
              >
                <span>{STATUS_LABELS[status]}</span>
                <strong>{count}</strong>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
