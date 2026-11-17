"""Publish a PWA-friendly JSON feed from the local database.

The GitHub Pages PWA is static and cannot scrape JobStreet itself. This module
turns the CLI's SQLite state into a portable snapshot that the installed app can
import (file) or poll (local bridge / private URL).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .config import AppConfig
from .models import utc_now
from .store import JobStore

FEED_SCHEMA = 1


def _search_payload(config: AppConfig) -> list[dict[str, Any]]:
    return [
        {
            "name": search.name,
            "keywords": search.keywords,
            "where": search.where,
            "sort": search.sort,
            "daterange": search.daterange,
            "worktype": search.worktype,
            "page_size": search.page_size,
            "max_pages": search.max_pages,
            "max_jobs": search.max_jobs,
            "enrich": search.enrich,
            "enabled": search.enabled,
            "notify_on_first_run": search.notify_on_first_run,
        }
        for search in config.searches
    ]


def build_feed(
    config: AppConfig,
    *,
    include_descriptions: bool = True,
    run_limit: int = 20,
) -> dict[str, Any]:
    """Build the feed object shared by ``publish`` and the local bridge."""
    store = JobStore(config.db_path)
    try:
        jobs = [job.to_dict(include_raw=False) for job in store.all_jobs()]
        runs = store.recent_runs(run_limit)
        search_state = store.all_search_state()
        stats = store.stats()
    finally:
        store.close()

    if not include_descriptions:
        for job in jobs:
            job["description_html"] = ""
            job["description_text"] = ""
            job.pop("raw", None)

    return {
        "schema": FEED_SCHEMA,
        "generated_at": utc_now(),
        "app": {
            "version": __version__,
            "locale": config.locale,
            "site_key": config.site_key,
            "schedule": config.schedule,
            "timezone": config.timezone,
            "stats": stats,
        },
        "searches": _search_payload(config),
        "search_state": search_state,
        "runs": runs,
        "jobs": jobs,
    }


def write_feed(
    config: AppConfig,
    path: str | Path,
    *,
    include_descriptions: bool = True,
    pretty: bool = False,
    run_limit: int = 20,
) -> tuple[Path, dict[str, Any]]:
    feed = build_feed(
        config, include_descriptions=include_descriptions, run_limit=run_limit
    )
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(feed, indent=2, ensure_ascii=False)
    else:
        text = json.dumps(feed, separators=(",", ":"), ensure_ascii=False)
    target.write_text(text + "\n", encoding="utf-8")
    return target, feed
