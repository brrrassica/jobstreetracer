import { useEffect, useState } from "react";
import { formatDate, relativeTime } from "../feed";
import { JOB_STATUSES, STATUS_LABELS, type Job, type JobStatus } from "../types";

interface Props {
  job: Job;
  onClose: () => void;
  onUpdate: (job: Job) => void;
}

function sanitizeHtml(html: string): string {
  if (!html) return "";
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script,style,iframe,object,embed,link,meta,form").forEach((node) => node.remove());
  doc.querySelectorAll("*").forEach((element) => {
    for (const attr of [...element.attributes]) {
      const name = attr.name.toLowerCase();
      const value = attr.value.trim().toLowerCase();
      if (name.startsWith("on") || (name === "href" && value.startsWith("javascript:"))) {
        element.removeAttribute(attr.name);
      }
    }
    if (element.tagName === "A") {
      element.setAttribute("target", "_blank");
      element.setAttribute("rel", "noopener noreferrer");
    }
  });
  return doc.body.innerHTML;
}

export function JobDetail({ job, onClose, onUpdate }: Props) {
  const [tagDraft, setTagDraft] = useState("");
  const [notes, setNotes] = useState(job.tracking.notes);

  useEffect(() => {
    setNotes(job.tracking.notes);
  }, [job.id, job.tracking.notes]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const patchTracking = (patch: Partial<Job["tracking"]>) => {
    onUpdate({
      ...job,
      tracking: { ...job.tracking, ...patch, updatedAt: new Date().toISOString() },
    });
  };

  const addTag = () => {
    const tag = tagDraft.trim();
    if (!tag || job.tracking.tags.includes(tag)) {
      setTagDraft("");
      return;
    }
    patchTracking({ tags: [...job.tracking.tags, tag] });
    setTagDraft("");
  };

  return (
    <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={job.title}>
        <header className="drawer-head">
          <div>
            <div className="drawer-badges">
              {job.isNew && <span className="badge badge-new">New</span>}
              {job.isFeatured && <span className="badge badge-muted">Featured</span>}
              {job.isVerified && <span className="badge badge-good">Verified</span>}
            </div>
            <h2>{job.title}</h2>
            <p className="muted">
              {[job.company, job.location].filter(Boolean).join(" · ") || "Unknown company"}
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div className="drawer-actions">
          {job.url && (
            <a className="btn btn-primary" href={job.url} target="_blank" rel="noreferrer">
              Open on JobStreet ↗
            </a>
          )}
          {job.applyUrl && job.applyUrl !== job.url && (
            <a className="btn" href={job.applyUrl} target="_blank" rel="noreferrer">
              Apply ↗
            </a>
          )}
          <button
            className="btn"
            onClick={() => patchTracking({ seen: true })}
            disabled={job.tracking.seen}
          >
            {job.tracking.seen ? "Reviewed" : "Mark reviewed"}
          </button>
        </div>

        <dl className="meta-grid">
          <div>
            <dt>Status</dt>
            <dd>
              <select
                value={job.tracking.status}
                onChange={(event) => patchTracking({ status: event.target.value as JobStatus })}
              >
                {JOB_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            </dd>
          </div>
          <div>
            <dt>Salary</dt>
            <dd>{job.salary || "—"}</dd>
          </div>
          <div>
            <dt>Posted</dt>
            <dd>{job.listingDateDisplay || job.postedDisplay || formatDate(job.listingDate)}</dd>
          </div>
          <div>
            <dt>First seen</dt>
            <dd>
              {formatDate(job.firstSeen)} <span className="muted">({relativeTime(job.firstSeen)})</span>
            </dd>
          </div>
          <div>
            <dt>Work</dt>
            <dd>{[job.workTypes, job.workArrangement].filter(Boolean).join(" · ") || "—"}</dd>
          </div>
          <div>
            <dt>Classification</dt>
            <dd>{[job.classification, job.subclassification].filter(Boolean).join(" · ") || "—"}</dd>
          </div>
          <div>
            <dt>Search</dt>
            <dd>{job.searchName || "—"}</dd>
          </div>
          <div>
            <dt>Expires</dt>
            <dd>{job.expiresAt ? formatDate(job.expiresAt) : "—"}</dd>
          </div>
        </dl>

        <section className="drawer-section">
          <h3>Tags</h3>
          <div className="tag-row">
            {job.tracking.tags.map((tag) => (
              <button
                key={tag}
                className="tag tag-removable"
                onClick={() => patchTracking({ tags: job.tracking.tags.filter((value) => value !== tag) })}
                title="Remove tag"
              >
                {tag} ✕
              </button>
            ))}
          </div>
          <div className="inline-form">
            <input
              placeholder="Add a tag (e.g. remote, backend)"
              value={tagDraft}
              onChange={(event) => setTagDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addTag();
                }
              }}
            />
            <button className="btn btn-small" onClick={addTag}>
              Add
            </button>
          </div>
        </section>

        <section className="drawer-section">
          <h3>Notes</h3>
          <textarea
            rows={4}
            placeholder="Recruiter, referral, interview notes…"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
          <div className="inline-form end">
            <button
              className="btn btn-small"
              onClick={() => patchTracking({ notes })}
              disabled={notes === job.tracking.notes}
            >
              Save notes
            </button>
          </div>
        </section>

        <section className="drawer-section">
          <h3>Description</h3>
          {job.descriptionHtml ? (
            <div
              className="description"
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(job.descriptionHtml) }}
            />
          ) : job.descriptionText ? (
            <div className="description pre">{job.descriptionText}</div>
          ) : (
            <p className="muted">
              No description cached. Run the scraper with detail enrichment enabled, then sync the feed.
            </p>
          )}
        </section>
      </aside>
    </div>
  );
}
