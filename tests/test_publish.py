from __future__ import annotations

import json

from jobstreetracer.config import load_config
from jobstreetracer.models import Job
from jobstreetracer.publish import build_feed, write_feed
from jobstreetracer.store import JobStore


def _config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[app]
db_path = "data/jobs.db"

[[search]]
name = "test-search"
keywords = '"data engineer"'
where = "Jakarta"
enabled = true
""",
        encoding="utf-8",
    )
    return load_config(cfg)


def _job(job_id: str) -> Job:
    return Job(
        id=job_id,
        title=f"Job {job_id}",
        company="Acme",
        location="Jakarta",
        description_text="A job description",
        url=f"https://id.jobstreet.com/id/job/{job_id}",
    )


def test_build_feed_includes_searches_and_jobs(tmp_path) -> None:
    config = _config(tmp_path)
    store = JobStore(config.db_path)
    try:
        store.upsert_jobs([_job("1")])
        store.mark_search_run("test-search")
    finally:
        store.close()

    feed = build_feed(config)
    assert feed["schema"] == 1
    assert feed["searches"][0]["name"] == "test-search"
    assert feed["searches"][0]["keywords"] == '"data engineer"'
    assert [job["id"] for job in feed["jobs"]] == ["1"]
    assert feed["jobs"][0]["description_text"] == "A job description"
    assert feed["search_state"]["test-search"]["first_run_at"]
    assert feed["app"]["stats"]["total_jobs"] == 1


def test_write_feed_can_omit_descriptions(tmp_path) -> None:
    config = _config(tmp_path)
    store = JobStore(config.db_path)
    try:
        store.upsert_jobs([_job("1")])
    finally:
        store.close()

    target, feed = write_feed(
        config, tmp_path / "out" / "feed.json", include_descriptions=False
    )
    assert target.exists()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["jobs"][0]["description_text"] == ""
    assert written["jobs"][0]["description_html"] == ""
    assert "raw" not in written["jobs"][0]
