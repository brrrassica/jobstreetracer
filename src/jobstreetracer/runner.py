"""Orchestration: scrape configured searches, persist, notify."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .client import JobStreetClient
from .config import SearchConfig, load_config
from .models import Job, utc_now
from .notify import NotificationError, TelegramNotifier
from .store import JobStore

log = logging.getLogger(__name__)


@dataclass
class SearchOutcome:
    name: str
    scanned: int = 0
    available: int = 0
    new: int = 0
    seeded: int = 0
    enriched: int = 0
    errors: int = 0


@dataclass
class RunSummary:
    started_at: str
    searches: list[SearchOutcome] = field(default_factory=list)
    notified: int = 0
    snapshots: list[str] = field(default_factory=list)
    errors: int = 0

    @property
    def scanned(self) -> int:
        return sum(item.scanned for item in self.searches)

    @property
    def new_jobs(self) -> int:
        return sum(item.new for item in self.searches)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["scanned"] = self.scanned
        data["new_jobs"] = self.new_jobs
        return data


def write_snapshot(jobs: Iterable[Job], output_dir: Path, started_at: str) -> Path:
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"{time.time_ns() % 1_000_000_000:09d}"
    path = runs_dir / f"{stamp}-{suffix}.jsonl"
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job.to_dict(include_raw=False), ensure_ascii=False) + "\n")
            count += 1
    log.info("wrote %s (%s jobs)", path, count)
    return path


def scrape_search(
    client: JobStreetClient,
    store: JobStore,
    search: SearchConfig,
    *,
    max_pages: int | None = None,
    enrich: bool | None = None,
    notify_first_run: bool | None = None,
    dry_run: bool = False,
) -> tuple[list[Job], SearchOutcome]:
    outcome = SearchOutcome(name=search.name)
    enrich = search.enrich if enrich is None else enrich
    pages = max_pages or search.max_pages

    jobs_by_id: dict[str, Job] = {}
    try:
        for page in client.iter_search(
            search.keywords,
            where=search.where or None,
            page_size=search.page_size,
            sort=search.sort or None,
            daterange=search.daterange,
            worktype=search.worktype or None,
            max_pages=pages,
            max_jobs=search.max_jobs,
        ):
            outcome.available = page.total_count
            for job in page.jobs:
                job.search_name = search.name
                jobs_by_id[job.id] = job
    except Exception as exc:
        outcome.errors += 1
        log.error("[%s] search failed: %s", search.name, exc)

    jobs = list(jobs_by_id.values())
    outcome.scanned = len(jobs)
    if outcome.errors and not jobs:
        return [], outcome
    first_run = store.get_search_state(search.name) is None
    if dry_run:
        existing_ids: set[str] = set()
        ids = list(jobs_by_id)
        for start in range(0, len(ids), 900):
            chunk = ids[start : start + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = store.conn.execute(
                f"SELECT id FROM jobs WHERE id IN ({placeholders})", chunk
            ).fetchall()
            existing_ids.update(row["id"] for row in rows)
        new_jobs = [job for job in jobs if job.id not in existing_ids]
        for job in new_jobs:
            job.is_new = True
    else:
        new_jobs = store.upsert_jobs(jobs)
    outcome.new = len(new_jobs)
    new_ids = {job.id for job in new_jobs}
    log.info(
        "[%s] scanned=%s new=%s available=%s",
        search.name,
        outcome.scanned,
        outcome.new,
        outcome.available,
    )

    should_notify = (
        search.notify_on_first_run if notify_first_run is None else notify_first_run
    )
    if first_run and not should_notify:
        seeded_ids = [job.id for job in new_jobs]
        if not dry_run:
            store.mark_notified(seeded_ids)
        else:
            for job in new_jobs:
                job.is_new = False
        outcome.seeded = len(seeded_ids)
        log.info(
            "[%s] first run: seeded %s existing job(s) silently%s; "
            "future unseen jobs will be notified",
            search.name,
            outcome.seeded,
            " [dry-run]" if dry_run else "",
        )
    elif first_run:
        log.info(
            "[%s] first run: notifying %s existing job(s)",
            search.name,
            outcome.new,
        )
    if not dry_run:
        store.mark_search_run(search.name)

    if enrich and jobs:
        retry_ids = store.ids_missing_detail(jobs_by_id)
        targets = [job for job in jobs if job.id in new_ids or job.id in retry_ids]
        for job in targets:
            try:
                detail = client.get_detail(job)
                if not dry_run:
                    store.update_detail(detail)
                jobs_by_id[job.id] = detail
                outcome.enriched += 1
            except Exception as exc:
                outcome.errors += 1
                log.warning("[%s] detail failed for %s: %s", search.name, job.id, exc)
        if targets:
            log.info("[%s] enriched=%s", search.name, outcome.enriched)

    return list(jobs_by_id.values()), outcome


def run_once(
    config_path: str | Path | None = None,
    *,
    search_names: list[str] | None = None,
    max_pages: int | None = None,
    no_enrich: bool = False,
    no_notify: bool = False,
    dry_run: bool = False,
    notify_first_run: bool | None = None,
) -> RunSummary:
    config = load_config(config_path)
    selected = set(search_names or [])
    searches = [
        item
        for item in config.searches
        if item.enabled and (not selected or item.name in selected)
    ]
    if not searches:
        raise ValueError("no enabled searches matched")
    if selected - {item.name for item in searches}:
        missing = ", ".join(sorted(selected - {item.name for item in searches}))
        raise ValueError(f"unknown search name(s): {missing}")

    store = JobStore(config.db_path)
    client = JobStreetClient(
        locale=config.locale,
        site_key=config.site_key,
        delay_seconds=config.delay_seconds,
        timeout=config.timeout_seconds,
    )
    notifier = TelegramNotifier(
        config.telegram_bot_token,
        config.telegram_chat_ids,
        topic_id=config.telegram_topic_id,
        dry_run=dry_run,
    )

    started_at = utc_now()
    summary = RunSummary(started_at=started_at)
    all_jobs: dict[str, Job] = {}

    try:
        for search in searches:
            log.info("searching: %s (%s)", search.name, search.keywords)
            jobs, outcome = scrape_search(
                client,
                store,
                search,
                max_pages=max_pages,
                enrich=False if no_enrich else None,
                notify_first_run=notify_first_run,
                dry_run=dry_run,
            )
            summary.searches.append(outcome)
            summary.errors += outcome.errors
            for job in jobs:
                previous = all_jobs.get(job.id)
                if previous and previous.is_new and not job.is_new:
                    job.is_new = True
                all_jobs[job.id] = job

        if all_jobs and summary.new_jobs > 0:
            if dry_run:
                log.info("dry-run; snapshot skipped")
            else:
                snapshot = write_snapshot(all_jobs.values(), config.output_dir, started_at)
                summary.snapshots.append(str(snapshot))
        elif all_jobs:
            log.info("no new jobs; snapshot skipped")

        if no_notify:
            log.info("notifications disabled (--no-notify); jobs stay pending")
        elif not notifier.configured and not dry_run:
            log.warning(
                "Telegram not configured; jobs stay pending. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (or TELEGRAM_CHAT_IDS) in .env"
            )
        else:
            if dry_run:
                # Mirror the real run's selection: stored-but-unnotified jobs
                # (backlog, oldest first) plus genuinely new ones, capped like
                # get_unnotified.
                unnotified = store.unnotified_ids()
                backlog = sorted(
                    (job for job in all_jobs.values() if job.id in unnotified),
                    key=lambda job: job.first_seen,
                )
                fresh = [job for job in all_jobs.values() if job.is_new]
                pending = (backlog + fresh)[: config.notify_max_jobs]
            else:
                pending = store.get_unnotified(limit=config.notify_max_jobs)
            if pending:
                try:
                    result = notifier.send_jobs(pending)
                except NotificationError as exc:
                    summary.errors += 1
                    if exc.sent_ids and not dry_run:
                        store.mark_notified(exc.sent_ids)
                    summary.notified += len(exc.sent_ids)
                    log.error("Telegram notification failed: %s", exc)
                else:
                    if not dry_run:
                        store.mark_notified(result.sent_ids)
                    summary.notified = len(result.sent_ids)
                    log.info(
                        "notified %s job(s) in %s message(s)",
                        len(result.sent_ids),
                        result.messages,
                    )
            else:
                log.info("no pending jobs to notify")

        if not dry_run:
            store.record_run(
                started_at=started_at,
                searches=len(summary.searches),
                scanned=summary.scanned,
                new_jobs=summary.new_jobs,
                notified=summary.notified,
                errors=summary.errors,
            )
    finally:
        store.close()

    return summary
