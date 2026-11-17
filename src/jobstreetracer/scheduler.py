"""Cron-style scheduler backed by APScheduler."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .runner import run_once

log = logging.getLogger(__name__)

JOB_ID = "jobstreetracer"


def build_trigger(expression: str, timezone: str) -> CronTrigger:
    """Parse a crontab expression into an APScheduler cron trigger."""
    return CronTrigger.from_crontab(expression, timezone=timezone)


def run_tick(
    config_path: str | Path | None,
    *,
    on_summary: Callable[[object], None] | None = None,
) -> bool:
    """Run one scrape cycle, logging (never raising) any failure.

    Returns ``True`` when the run completed without an exception, ``False``
    otherwise. ``on_summary`` is called with the run summary when the cycle
    succeeds, which lets callers (and tests) observe the result.
    """
    try:
        summary = run_once(config_path)
    except Exception:
        log.exception("scheduled run failed")
        return False
    log.info(
        "run complete: scanned=%s new=%s notified=%s errors=%s",
        summary.scanned,
        summary.new_jobs,
        summary.notified,
        summary.errors,
    )
    if on_summary is not None:
        on_summary(summary)
    return True


def build_scheduler(
    config_path: str | Path | None,
    *,
    cron: str | None = None,
    timezone: str | None = None,
    scheduler_cls: type[BlockingScheduler] | None = None,
) -> BlockingScheduler:
    """Construct a (not yet started) scheduler wired to :func:`run_tick`.

    Reads defaults from the config file unless ``cron``/``timezone`` override
    them. Exposed separately from :func:`serve` so it can be exercised in tests
    without blocking on ``start()``.
    """
    from .config import load_config

    config = load_config(config_path)
    expression = cron or config.schedule
    tz = timezone or config.timezone
    cls = scheduler_cls or BlockingScheduler
    trigger = build_trigger(expression, tz)
    scheduler = cls(timezone=tz)
    scheduler.add_job(
        lambda: run_tick(config_path),
        trigger,
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    log.info("scheduler configured: cron=%r timezone=%s", expression, tz)
    return scheduler


def serve(
    config_path: str | Path | None,
    *,
    cron: str | None = None,
    timezone: str | None = None,
    run_now: bool = False,
) -> None:
    scheduler = build_scheduler(config_path, cron=cron, timezone=timezone)
    if run_now:
        log.info("running once before waiting for the schedule")
        run_tick(config_path)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")
