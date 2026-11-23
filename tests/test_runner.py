from __future__ import annotations

from jobstreetracer.config import SearchConfig
from jobstreetracer.models import Job, SearchPage
from jobstreetracer.runner import scrape_search
from jobstreetracer.store import JobStore


class FakeClient:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def iter_search(self, keywords, **kwargs):
        yield SearchPage(
            jobs=list(self.jobs),
            total_count=len(self.jobs),
            page=1,
            page_size=30,
        )

    def get_detail(self, job: Job) -> Job:
        return job


def make_job(job_id: str) -> Job:
    return Job(
        id=job_id,
        title=f"Job {job_id}",
        company="Acme",
        url=f"https://id.jobstreet.com/id/job/{job_id}",
        listing_date="2026-11-05T00:00:00Z",
    )


def search(name: str = "test", **kwargs) -> SearchConfig:
    return SearchConfig(name=name, keywords='"x"', enrich=False, **kwargs)


def test_first_run_seeds_silently_then_alerts_new_jobs(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        client = FakeClient([make_job("1"), make_job("2")])
        _, first = scrape_search(client, store, search())
        assert first.new == 2
        assert first.seeded == 2
        assert store.get_unnotified() == []
        assert store.get_search_state("test") is not None

        client.jobs = [make_job("1"), make_job("2"), make_job("3")]
        _, second = scrape_search(client, store, search())
        assert second.new == 1
        assert second.seeded == 0
        assert [job.id for job in store.get_unnotified()] == ["3"]
    finally:
        store.close()


def test_notify_first_run_keeps_backlog_pending(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        client = FakeClient([make_job("1"), make_job("2")])
        _, outcome = scrape_search(
            client, store, search(name="fresh"), notify_first_run=True
        )
        assert outcome.seeded == 0
        assert {job.id for job in store.get_unnotified()} == {"1", "2"}
    finally:
        store.close()


def test_first_run_state_is_per_search(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        client = FakeClient([make_job("1")])
        scrape_search(client, store, search(name="one"))
        assert store.get_search_state("one") is not None
        assert store.get_search_state("two") is None

        client.jobs = [make_job("2")]
        _, outcome = scrape_search(client, store, search(name="two"))
        assert outcome.seeded == 1
        assert store.get_search_state("two") is not None
    finally:
        store.close()


def test_partial_pagination_failure_preserves_fetched_jobs(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        class PartialFailClient:
            def iter_search(self, *args, **kwargs):
                yield SearchPage(
                    jobs=[make_job("1")],
                    total_count=2,
                    page=1,
                    page_size=1,
                )
                raise RuntimeError("network down")

            def get_detail(self, job):
                return job

        jobs, outcome = scrape_search(PartialFailClient(), store, search())
        assert outcome.errors == 1
        assert outcome.scanned == 1
        assert {job.id for job in jobs} == {"1"}
        assert outcome.seeded == 1
        assert store.get_unnotified() == []
        assert store.get_search_state("test") is not None
    finally:
        store.close()


def test_pagination_failure_with_no_jobs_does_not_mark_state(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        class FailClient:
            def iter_search(self, *args, **kwargs):
                raise RuntimeError("boom")
                yield  # pragma: no cover

            def get_detail(self, job):
                return job

        jobs, outcome = scrape_search(FailClient(), store, search())
        assert jobs == []
        assert outcome.errors == 1
        assert outcome.scanned == 0
        assert store.get_search_state("test") is None
    finally:
        store.close()


def test_dry_run_first_run_does_not_seed_or_mark_state(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    try:
        client = FakeClient([make_job("1"), make_job("2")])
        jobs, outcome = scrape_search(client, store, search(), dry_run=True)
        assert outcome.new == 2
        assert outcome.seeded == 2
        assert [job.id for job in store.get_unnotified()] == []
        assert store.get_search_state("test") is None
        assert store.stats()["total_jobs"] == 0

        _, real = scrape_search(client, store, search())
        assert real.new == 2
        assert real.seeded == 2
        assert store.get_unnotified() == []
        assert store.get_search_state("test") is not None

        client.jobs = [make_job("1"), make_job("2"), make_job("3")]
        _, after = scrape_search(client, store, search())
        assert after.new == 1
        assert [job.id for job in store.get_unnotified()] == ["3"]
    finally:
        store.close()
