from __future__ import annotations

import json

from jobstreetracer.models import Job
from jobstreetracer.store import JobStore


def make_job(job_id: str, title: str = "Data Engineer") -> Job:
    return Job(
        id=job_id,
        title=title,
        company="Acme",
        location="Jakarta",
        salary="Rp 10.000.000",
        listing_date="2026-11-01T00:00:00Z",
        listing_date_display="4d ago",
        url=f"https://id.jobstreet.com/id/job/{job_id}",
        raw={"id": job_id},
    )


def test_upsert_dedupes_and_updates(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        first = store.upsert_jobs([make_job("1"), make_job("2")])
        assert [job.id for job in first] == ["1", "2"]
        assert all(job.first_seen for job in first)

        second = store.upsert_jobs([make_job("2", title="Updated"), make_job("3")])
        assert [job.id for job in second] == ["3"]

        recent = store.recent_jobs(10)
        assert len(recent) == 3
        assert next(job for job in recent if job.id == "2").title == "Updated"
    finally:
        store.close()


def test_detail_update_does_not_blank_search_fields(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        store.upsert_jobs([make_job("1")])
        detail = make_job("1")
        detail.description_text = "Full description"
        detail.expires_at = "2026-12-01T00:00:00Z"
        store.update_detail(detail)
        job = store.recent_jobs(1)[0]
        assert job.description_text == "Full description"
        assert job.company == "Acme"
        assert job.expires_at == "2026-12-01T00:00:00Z"
    finally:
        store.close()


def test_notification_state_and_export(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        store.upsert_jobs([make_job("1"), make_job("2")])
        assert len(store.get_unnotified()) == 2
        store.mark_notified(["1"])
        assert [job.id for job in store.get_unnotified()] == ["2"]

        out = tmp_path / "export.jsonl"
        count = store.export(out)
        assert count == 2
        lines = [json.loads(line) for line in out.read_text().splitlines()]
        assert {line["id"] for line in lines} == {"1", "2"}
        assert "raw" not in lines[0]
    finally:
        store.close()


def test_search_state_tracks_first_and_last_run(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        assert store.get_search_state("test") is None
        store.mark_search_run("test")
        state = store.get_search_state("test")
        assert state is not None
        first = state["first_run_at"]
        assert state["last_run_at"] == first

        store.mark_search_run("test")
        again = store.get_search_state("test")
        assert again["first_run_at"] == first
        assert again["last_run_at"] >= first
    finally:
        store.close()
