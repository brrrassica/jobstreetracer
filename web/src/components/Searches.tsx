import { useState } from "react";
import { slug } from "../feed";
import type { Search } from "../types";
import { Modal } from "./Modal";

interface Props {
  searches: Search[];
  onSave: (search: Search, previousName?: string) => void;
  onDelete: (name: string) => void;
  onExport: () => void;
}

function blankSearch(): Search {
  return {
    name: "",
    keywords: "",
    where: "",
    sort: "Relevance",
    daterange: 14,
    worktype: "",
    pageSize: 30,
    maxPages: 3,
    maxJobs: 0,
    enrich: true,
    enabled: true,
    notifyOnFirstRun: false,
  };
}

export function Searches({ searches, onSave, onDelete, onExport }: Props) {
  const [editing, setEditing] = useState<Search | null>(null);
  const [originalName, setOriginalName] = useState<string | undefined>(undefined);
  const [error, setError] = useState("");

  const save = () => {
    if (!editing) return;
    const keywords = editing.keywords.trim();
    if (!keywords && !editing.where) {
      setError("Add keywords or a location so the search has something to match.");
      return;
    }
    const name = editing.name.trim() || slug(`${keywords}-${editing.where}`);
    if (searches.some((search) => search.name === name && search.name !== originalName)) {
      setError(`A search named “${name}” already exists. Pick another name.`);
      return;
    }
    const cleaned: Search = {
      ...editing,
      name,
      keywords,
      where: editing.where.trim(),
      pageSize: Math.max(1, Math.min(100, Math.round(editing.pageSize) || 30)),
      maxPages: Math.max(1, Math.round(editing.maxPages) || 3),
      maxJobs: Math.max(0, Math.round(editing.maxJobs) || 0),
      daterange: editing.daterange && editing.daterange > 0 ? editing.daterange : null,
    };
    onSave(cleaned, originalName);
    setEditing(null);
    setOriginalName(undefined);
    setError("");
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">{searches.filter((search) => search.enabled).length} enabled</p>
          <h1>Saved searches</h1>
          <p className="subtitle">
            These definitions are the app's source of truth. Export them as TOML for the Python CLI whenever
            you need parity.
          </p>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={onExport} disabled={searches.length === 0}>
            Export config.toml
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              setOriginalName(undefined);
              setEditing(blankSearch());
            }}
          >
            New search
          </button>
        </div>
      </header>

      {searches.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">＋</div>
          <h3>No saved searches</h3>
          <p>Create one here, or sync a feed from the CLI to import its existing searches.</p>
          <button
            className="btn btn-primary"
            onClick={() => {
              setOriginalName(undefined);
              setEditing(blankSearch());
            }}
          >
            Create the first search
          </button>
        </div>
      ) : (
        <div className="search-grid">
          {searches.map((search) => (
            <article className={`search-card ${search.enabled ? "" : "is-disabled"}`} key={search.name}>
              <header>
                <div>
                  <h3>{search.name}</h3>
                  <p className="muted">
                    {search.keywords || "all jobs"}
                    {search.where ? ` · ${search.where}` : ""}
                  </p>
                </div>
                <label className="switch" title={search.enabled ? "Enabled" : "Disabled"}>
                  <input
                    type="checkbox"
                    checked={search.enabled}
                    onChange={(event) => onSave({ ...search, enabled: event.target.checked })}
                  />
                  <span />
                </label>
              </header>
              <dl className="search-facts">
                <div>
                  <dt>Sort</dt>
                  <dd>{search.sort}</dd>
                </div>
                <div>
                  <dt>Posted</dt>
                  <dd>{search.daterange ? `≤ ${search.daterange}d` : "any"}</dd>
                </div>
                <div>
                  <dt>Pages</dt>
                  <dd>
                    {search.maxPages} × {search.pageSize}
                  </dd>
                </div>
                <div>
                  <dt>Notify first run</dt>
                  <dd>{search.notifyOnFirstRun ? "yes" : "no"}</dd>
                </div>
              </dl>
              <footer>
                <button
                  className="btn btn-small"
                  onClick={() => {
                    setOriginalName(search.name);
                    setEditing({ ...search });
                  }}
                >
                  Edit
                </button>
                <button
                  className="btn btn-small btn-danger-ghost"
                  onClick={() => {
                    if (confirm(`Delete “${search.name}” from the PWA? The CLI config is not touched.`)) {
                      onDelete(search.name);
                    }
                  }}
                >
                  Delete
                </button>
              </footer>
            </article>
          ))}
        </div>
      )}

      {editing && (
        <Modal
          title={editing.name ? `Edit ${editing.name}` : "New search"}
          onClose={() => {
            setEditing(null);
            setOriginalName(undefined);
            setError("");
          }}
          wide
        >
          <div className="form-grid">
            <label className="field">
              <span>Name</span>
              <input
                value={editing.name}
                placeholder={`auto: ${slug(`${editing.keywords || "search"}-${editing.where}`)}`}
                onChange={(event) => setEditing({ ...editing, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Keywords</span>
              <input
                value={editing.keywords}
                placeholder={'"data engineer" OR "backend engineer"'}
                onChange={(event) => setEditing({ ...editing, keywords: event.target.value })}
              />
              <small>
                Quote phrases for exact matches. Uppercase OR/AND only work inside quoted phrases on
                JobStreet.
              </small>
            </label>
            <label className="field">
              <span>Where</span>
              <input
                value={editing.where}
                placeholder="Jakarta"
                onChange={(event) => setEditing({ ...editing, where: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Sort</span>
              <select
                value={editing.sort}
                onChange={(event) => setEditing({ ...editing, sort: event.target.value })}
              >
                <option value="Relevance">Relevance</option>
                <option value="ListedDate">Listed date</option>
              </select>
            </label>
            <label className="field">
              <span>Max age (days)</span>
              <input
                type="number"
                min={0}
                value={editing.daterange ?? ""}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    daterange: event.target.value ? Number(event.target.value) : null,
                  })
                }
              />
            </label>
            <label className="field">
              <span>Work type</span>
              <input
                value={editing.worktype}
                placeholder="e.g. full-time"
                onChange={(event) => setEditing({ ...editing, worktype: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Page size</span>
              <input
                type="number"
                min={1}
                max={100}
                value={editing.pageSize}
                onChange={(event) => setEditing({ ...editing, pageSize: Number(event.target.value) })}
              />
            </label>
            <label className="field">
              <span>Max pages</span>
              <input
                type="number"
                min={1}
                value={editing.maxPages}
                onChange={(event) => setEditing({ ...editing, maxPages: Number(event.target.value) })}
              />
            </label>
            <label className="field">
              <span>Max jobs (0 = unlimited)</span>
              <input
                type="number"
                min={0}
                value={editing.maxJobs}
                onChange={(event) => setEditing({ ...editing, maxJobs: Number(event.target.value) })}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={editing.enrich}
                onChange={(event) => setEditing({ ...editing, enrich: event.target.checked })}
              />
              Fetch full descriptions
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={editing.enabled}
                onChange={(event) => setEditing({ ...editing, enabled: event.target.checked })}
              />
              Enabled
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={editing.notifyOnFirstRun}
                onChange={(event) =>
                  setEditing({ ...editing, notifyOnFirstRun: event.target.checked })
                }
              />
              Notify on first baseline
            </label>
          </div>
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button
              className="btn"
              onClick={() => {
                setEditing(null);
                setOriginalName(undefined);
              }}
            >
              Cancel
            </button>
            <button className="btn btn-primary" onClick={save}>
              Save search
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
