import { useMemo, useState } from "react";
import { matchesText, relativeTime, sortJobs } from "../feed";
import {
  JOB_STATUSES,
  SORT_OPTIONS,
  STATUS_LABELS,
  type Job,
  type JobStatus,
  type Search,
  type SortKey,
} from "../types";

interface Props {
  jobs: Job[];
  searches: Search[];
  onSelect: (job: Job) => void;
}

function initialFilters() {
  const query = window.location.hash.split("?")[1] ?? "";
  const params = new URLSearchParams(query);
  return {
    text: "",
    searchName: params.get("search") ?? "",
    status: (params.get("status") as JobStatus | null) ?? "",
    location: "",
    tag: params.get("tag") ?? "",
    onlyNew: params.get("new") === "1",
    sort: (params.get("sort") as SortKey | null) ?? "newest",
  };
}

export function Listings({ jobs, searches, onSelect }: Props) {
  const [filters, setFilters] = useState(initialFilters);
  const [visible, setVisible] = useState(50);

  const tags = useMemo(() => {
    const values = new Set<string>();
    jobs.forEach((job) => job.tracking.tags.forEach((tag) => values.add(tag)));
    return [...values].sort();
  }, [jobs]);

  const filtered = useMemo(() => {
    const list = jobs.filter((job) => {
      if (filters.onlyNew && !job.isNew) return false;
      if (filters.status && job.tracking.status !== filters.status) return false;
      if (filters.searchName && job.searchName !== filters.searchName) return false;
      if (filters.location && !job.location.toLowerCase().includes(filters.location.toLowerCase())) {
        return false;
      }
      if (filters.tag && !job.tracking.tags.includes(filters.tag)) return false;
      if (!matchesText(job, filters.text)) return false;
      return true;
    });
    return sortJobs(list, filters.sort);
  }, [jobs, filters]);

  const update = (patch: Partial<typeof filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setVisible(50);
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">{jobs.length} cached listings</p>
          <h1>Listings</h1>
          <p className="subtitle">Filter the local cache. Opening a listing marks it reviewed.</p>
        </div>
        <div className="head-actions">
          <button
            className="btn"
            onClick={() =>
              setFilters({
                text: "",
                searchName: "",
                status: "",
                location: "",
                tag: "",
                onlyNew: false,
                sort: "newest",
              })
            }
          >
            Reset filters
          </button>
        </div>
      </header>

      <section className="filter-bar">
        <label className="search-input">
          <span className="sr-only">Search listings</span>
          <input
            type="search"
            placeholder="Search title, company, description, notes…"
            value={filters.text}
            onChange={(event) => update({ text: event.target.value })}
          />
        </label>
        <select value={filters.searchName} onChange={(event) => update({ searchName: event.target.value })}>
          <option value="">All searches</option>
          {searches.map((search) => (
            <option key={search.name} value={search.name}>
              {search.name}
            </option>
          ))}
        </select>
        <select value={filters.status} onChange={(event) => update({ status: event.target.value as JobStatus | "" })}>
          <option value="">Any status</option>
          {JOB_STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="Location"
          value={filters.location}
          onChange={(event) => update({ location: event.target.value })}
        />
        <select value={filters.tag} onChange={(event) => update({ tag: event.target.value })}>
          <option value="">Any tag</option>
          {tags.map((tag) => (
            <option key={tag} value={tag}>
              {tag}
            </option>
          ))}
        </select>
        <select value={filters.sort} onChange={(event) => update({ sort: event.target.value as SortKey })}>
          {SORT_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label className="check">
          <input
            type="checkbox"
            checked={filters.onlyNew}
            onChange={(event) => update({ onlyNew: event.target.checked })}
          />
          Only new
        </label>
      </section>

      <div className="results-line">
        <span>
          {filtered.length} result{filtered.length === 1 ? "" : "s"}
        </span>
        {(filters.text ||
          filters.searchName ||
          filters.status ||
          filters.location ||
          filters.tag ||
          filters.onlyNew) && <span className="muted">filters applied</span>}
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">⌕</div>
          <h3>No listings match</h3>
          <p>Try clearing filters, syncing the feed, or importing a JSONL export.</p>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="job-table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Company</th>
                  <th>Location</th>
                  <th>Salary</th>
                  <th>Posted</th>
                  <th>Status</th>
                  <th>First seen</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, visible).map((job) => (
                  <tr key={job.id} onClick={() => onSelect(job)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && onSelect(job)}>
                    <td>
                      <div className="cell-title">
                        {job.isNew && <span className="dot" />}
                        <span>{job.title}</span>
                      </div>
                      <div className="cell-sub">
                        {[job.classification, job.workTypes].filter(Boolean).join(" · ")}
                      </div>
                      {job.tracking.tags.length > 0 && (
                        <div className="tag-row">
                          {job.tracking.tags.map((tag) => (
                            <span className="tag" key={tag}>
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>{job.company || "—"}</td>
                    <td>{job.location || "—"}</td>
                    <td>{job.salary || "—"}</td>
                    <td>{job.listingDateDisplay || job.postedDisplay || "—"}</td>
                    <td>
                      <span className={`status-pill status-${job.tracking.status}`}>
                        {STATUS_LABELS[job.tracking.status]}
                      </span>
                    </td>
                    <td className="muted">{relativeTime(job.firstSeen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visible < filtered.length && (
            <div className="center">
              <button className="btn" onClick={() => setVisible((value) => value + 50)}>
                Show more ({filtered.length - visible} remaining)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
