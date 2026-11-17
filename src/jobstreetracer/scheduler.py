"""Cron-style scheduler backed by APScheduler."""

from __future__ import annotations

import logging
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .runner import run_once

log = logging.getLogger(__name__)


def serve(
    config_path: str | Path | None,
    *,
    cron: str | None = None,
    timezone: str | None = None,
    run_now: bool = False,
) -> None:
    from .config import load_config

    config = load_config(config_path)
    expression = cron or config.schedule
    tz = timezone or config.timezone
    trigger = CronTrigger.from_crontab(expression, timezone=tz)
    scheduler = BlockingScheduler(timezone=tz)

    def tick() -> None:
        try:
            summary = run_once(config_path)
            log.info(
                "run complete: scanned=%s new=%s notified=%s errors=%s",
                summary.scanned,
                summary.new_jobs,
                summary.notified,
                summary.errors,
            )
        except Exception:
            log.exception("scheduled run failed")

    scheduler.add_job(
        tick,
        trigger,
        id="jobstreetracer",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    log.info("scheduler started: cron=%r timezone=%s", expression, tz)
    if run_now:
        log.info("running once before waiting for the schedule")
        tick()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")
