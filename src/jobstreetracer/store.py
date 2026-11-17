"""SQLite persistence: dedupe jobs, track notification state, record runs."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import Job, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    company_id TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    salary TEXT NOT NULL DEFAULT '',
    listing_date TEXT NOT NULL DEFAULT '',
    listing_date_display TEXT NOT NULL DEFAULT '',
    posted_display TEXT NOT NULL DEFAULT '',
    teaser TEXT NOT NULL DEFAULT '',
    work_types TEXT NOT NULL DEFAULT '',
    work_arrangement TEXT NOT NULL DEFAULT '',
    classification TEXT NOT NULL DEFAULT '',
    subclassification TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    role_id TEXT NOT NULL DEFAULT '',
    is_featured INTEGER NOT NULL DEFAULT 0,
    is_verified INTEGER,
    is_link_out INTEGER,
    description_html TEXT NOT NULL DEFAULT '',
    description_text TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL DEFAULT '',
    apply_url TEXT NOT NULL DEFAULT '',
    search_name TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '{}',
    notified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs(notified_at);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    searches INTEGER NOT NULL DEFAULT 0,
    scanned INTEGER NOT NULL DEFAULT 0,
    new_jobs INTEGER NOT NULL DEFAULT 0,
    notified INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS search_state (
    name TEXT PRIMARY KEY,
    first_run_at TEXT NOT NULL,
    last_run_at TEXT NOT NULL,
    baseline_at TEXT NOT NULL
);
"""

FIELDS = [
    "id",
    "first_seen",
    "last_seen",
    "title",
    "company",
    "company_id",
    "location",
    "salary",
    "listing_date",
    "listing_date_display",
    "posted_display",
    "teaser",
    "work_types",
    "work_arrangement",
    "classification",
    "subclassification",
    "url",
    "role_id",
    "is_featured",
    "is_verified",
    "is_link_out",
    "description_html",
    "description_text",
    "expires_at",
    "apply_url",
    "search_name",
    "raw_json",
    "notified_at",
]


def _bool_int(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _row_to_job(row: sqlite3.Row) -> Job:
    try:
        raw = json.loads(row["raw_json"] or "{}")
    except json.JSONDecodeError:
        raw = {}
    return Job(
        id=row["id"],
        title=row["title"],
        company=row["company"],
        company_id=row["company_id"],
        location=row["location"],
        salary=row["salary"],
        listing_date=row["listing_date"],
        listing_date_display=row["listing_date_display"],
        posted_display=row["posted_display"],
        teaser=row["teaser"],
        work_types=row["work_types"],
        work_arrangement=row["work_arrangement"],
        classification=row["classification"],
        subclassification=row["subclassification"],
        url=row["url"],
        role_id=row["role_id"],
        is_featured=bool(row["is_featured"]),
        is_verified=None if row["is_verified"] is None else bool(row["is_verified"]),
        is_link_out=None if row["is_link_out"] is None else bool(row["is_link_out"]),
        description_html=row["description_html"],
        description_text=row["description_text"],
        expires_at=row["expires_at"],
        apply_url=row["apply_url"],
        search_name=row["search_name"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        is_new=False,
        raw=raw,
    )


class JobStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- writes --------------------------------------------------------
    def upsert_jobs(self, jobs: Iterable[Job]) -> list[Job]:
        """Insert unseen jobs; refresh seen ones. Returns the unseen jobs."""
        now = utc_now()
        new_jobs: list[Job] = []
        with self.conn:
            for job in jobs:
                existing = self.conn.execute(
                    "SELECT id FROM jobs WHERE id = ?", (job.id,)
                ).fetchone()
                job.last_seen = now
                job.raw = job.raw or {}
                if existing is None:
                    job.first_seen = now
                    job.is_new = True
                    self._insert(job)
                    new_jobs.append(job)
                else:
                    job.is_new = False
                    self._refresh(job)
        return new_jobs

    def _insert(self, job: Job) -> None:
        values = {
            "id": job.id,
            "first_seen": job.first_seen,
            "last_seen": job.last_seen,
            "title": job.title,
            "company": job.company,
            "company_id": job.company_id,
            "location": job.location,
            "salary": job.salary,
            "listing_date": job.listing_date,
            "listing_date_display": job.listing_date_display,
            "posted_display": job.posted_display,
            "teaser": job.teaser,
            "work_types": job.work_types,
            "work_arrangement": job.work_arrangement,
            "classification": job.classification,
            "subclassification": job.subclassification,
            "url": job.url,
            "role_id": job.role_id,
            "is_featured": _bool_int(job.is_featured),
            "is_verified": _bool_int(job.is_verified),
            "is_link_out": _bool_int(job.is_link_out),
            "description_html": job.description_html,
            "description_text": job.description_text,
            "expires_at": job.expires_at,
            "apply_url": job.apply_url,
            "search_name": job.search_name,
            "raw_json": json.dumps(job.raw, ensure_ascii=False),
            "notified_at": None,
        }
        placeholders = ", ".join("?" for _ in FIELDS)
        columns = ", ".join(FIELDS)
        self.conn.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
            [values[name] for name in FIELDS],
        )

    def _refresh(self, job: Job) -> None:
        # Never blank out fields that a lighter search response did not carry.
        self.conn.execute(
            """
            UPDATE jobs SET
                last_seen = ?,
                title = COALESCE(NULLIF(?, ''), title),
                company = COALESCE(NULLIF(?, ''), company),
                company_id = COALESCE(NULLIF(?, ''), company_id),
                location = COALESCE(NULLIF(?, ''), location),
                salary = COALESCE(NULLIF(?, ''), salary),
                listing_date = COALESCE(NULLIF(?, ''), listing_date),
                listing_date_display = COALESCE(NULLIF(?, ''), listing_date_display),
                posted_display = COALESCE(NULLIF(?, ''), posted_display),
                teaser = COALESCE(NULLIF(?, ''), teaser),
                work_types = COALESCE(NULLIF(?, ''), work_types),
                work_arrangement = COALESCE(NULLIF(?, ''), work_arrangement),
                classification = COALESCE(NULLIF(?, ''), classification),
                subclassification = COALESCE(NULLIF(?, ''), subclassification),
                url = COALESCE(NULLIF(?, ''), url),
                role_id = COALESCE(NULLIF(?, ''), role_id),
                is_featured = ?,
                is_verified = COALESCE(?, is_verified),
                is_link_out = COALESCE(?, is_link_out),
                description_html = COALESCE(NULLIF(?, ''), description_html),
                description_text = COALESCE(NULLIF(?, ''), description_text),
                expires_at = COALESCE(NULLIF(?, ''), expires_at),
                apply_url = COALESCE(NULLIF(?, ''), apply_url),
                search_name = COALESCE(NULLIF(?, ''), search_name),
                raw_json = ?
            WHERE id = ?
            """,
            (
                job.last_seen,
                job.title,
                job.company,
                job.company_id,
                job.location,
                job.salary,
                job.listing_date,
                job.listing_date_display,
                job.posted_display,
                job.teaser,
                job.work_types,
                job.work_arrangement,
                job.classification,
                job.subclassification,
                job.url,
                job.role_id,
                _bool_int(job.is_featured),
                _bool_int(job.is_verified),
                _bool_int(job.is_link_out),
                job.description_html,
                job.description_text,
                job.expires_at,
                job.apply_url,
                job.search_name,
                json.dumps(job.raw, ensure_ascii=False),
                job.id,
            ),
        )

    def update_detail(self, job: Job) -> None:
        """Refresh enriched detail fields for an existing job."""
        with self.conn:
            self.conn.execute(
                """
                UPDATE jobs SET
                    title = COALESCE(NULLIF(?, ''), title),
                    company = COALESCE(NULLIF(?, ''), company),
                    location = COALESCE(NULLIF(?, ''), location),
                    salary = COALESCE(NULLIF(?, ''), salary),
                    work_types = COALESCE(NULLIF(?, ''), work_types),
                    classification = COALESCE(NULLIF(?, ''), classification),
                    description_html = COALESCE(NULLIF(?, ''), description_html),
                    description_text = COALESCE(NULLIF(?, ''), description_text),
                    expires_at = COALESCE(NULLIF(?, ''), expires_at),
                    posted_display = COALESCE(NULLIF(?, ''), posted_display),
                    apply_url = COALESCE(NULLIF(?, ''), apply_url),
                    is_verified = COALESCE(?, is_verified),
                    is_link_out = COALESCE(?, is_link_out),
                    last_seen = ?
                WHERE id = ?
                """,
                (
                    job.title,
                    job.company,
                    job.location,
                    job.salary,
                    job.work_types,
                    job.classification,
                    job.description_html,
                    job.description_text,
                    job.expires_at,
                    job.posted_display,
                    job.apply_url,
                    _bool_int(job.is_verified),
                    _bool_int(job.is_link_out),
                    utc_now(),
                    job.id,
                ),
            )

    def mark_notified(self, job_ids: Iterable[str]) -> None:
        ids = list(job_ids)
        if not ids:
            return
        now = utc_now()
        with self.conn:
            self.conn.executemany(
                "UPDATE jobs SET notified_at = ? WHERE id = ?",
                [(now, job_id) for job_id in ids],
            )

    def get_search_state(self, name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM search_state WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def mark_search_run(self, name: str) -> None:
        now = utc_now()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO search_state (name, first_run_at, last_run_at, baseline_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET last_run_at = excluded.last_run_at
                """,
                (name, now, now, now),
            )

    def record_run(
        self,
        *,
        started_at: str,
        searches: int,
        scanned: int,
        new_jobs: int,
        notified: int,
        errors: int,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO runs
                    (started_at, finished_at, searches, scanned, new_jobs, notified, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (started_at, utc_now(), searches, scanned, new_jobs, notified, errors),
            )

    # -- reads ---------------------------------------------------------
    def ids_missing_detail(self, job_ids: Iterable[str]) -> set[str]:
        ids = list(job_ids)
        missing: set[str] = set()
        for start in range(0, len(ids), 900):
            chunk = ids[start : start + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.conn.execute(
                f"SELECT id FROM jobs WHERE id IN ({placeholders}) AND description_text = ''",
                chunk,
            ).fetchall()
            missing.update(row["id"] for row in rows)
        return missing

    def get_unnotified(self, limit: int = 40) -> list[Job]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE notified_at IS NULL ORDER BY first_seen ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def recent_jobs(self, limit: int = 20, *, only_new: bool = False) -> list[Job]:
        where = "WHERE notified_at IS NULL" if only_new else ""
        rows = self.conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY first_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        total = self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        unnotified = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE notified_at IS NULL"
        ).fetchone()[0]
        today = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE date(first_seen) = date('now')"
        ).fetchone()[0]
        last_run = self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "total_jobs": total,
            "unnotified": unnotified,
            "new_today": today,
            "last_run": dict(last_run) if last_run else None,
        }

    def all_jobs(self) -> list[Job]:
        rows = self.conn.execute(
            "SELECT * FROM jobs ORDER BY first_seen DESC"
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (max(1, limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def all_search_state(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM search_state").fetchall()
        return {row["name"]: dict(row) for row in rows}

    def export(self, path: str | Path, *, fmt: str = "jsonl", only_new: bool = False) -> int:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        where = "WHERE notified_at IS NULL" if only_new else ""
        rows = self.conn.execute(f"SELECT * FROM jobs {where} ORDER BY first_seen ASC").fetchall()
        jobs = [_row_to_job(row) for row in rows]
        if fmt == "jsonl":
            with target.open("w", encoding="utf-8") as handle:
                for job in jobs:
                    handle.write(json.dumps(job.to_dict(include_raw=False), ensure_ascii=False) + "\n")
        elif fmt == "csv":
            fieldnames = list(Job.__dataclass_fields__)
            fieldnames.remove("raw")
            with target.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for job in jobs:
                    writer.writerow(job.to_dict(include_raw=False))
        else:
            raise ValueError(f"unsupported export format: {fmt}")
        return len(jobs)
