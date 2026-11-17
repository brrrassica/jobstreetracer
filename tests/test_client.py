from __future__ import annotations

from jobstreetracer.client import JobStreetClient
from jobstreetracer.models import Job, SearchPage


def make_job(job_id: str) -> Job:
    return Job(id=job_id, title=f"Job {job_id}")


def test_iter_search_respects_max_jobs_exactly() -> None:
    client = JobStreetClient(delay_seconds=0)
    pages = {
        1: SearchPage(jobs=[make_job("1"), make_job("2"), make_job("3")], total_count=9, page=1, page_size=3),
        2: SearchPage(jobs=[make_job("4"), make_job("5"), make_job("6")], total_count=9, page=2, page_size=3),
    }

    def fake_search(keywords, *, page=1, **kwargs):
        return pages[page]

    client.search = fake_search  # type: ignore[method-assign]
    jobs = [job for result in client.iter_search("x", max_pages=3, max_jobs=4) for job in result.jobs]
    assert [job.id for job in jobs] == ["1", "2", "3", "4"]


def test_iter_search_dedupes_across_pages() -> None:
    client = JobStreetClient(delay_seconds=0)
    pages = {
        1: SearchPage(jobs=[make_job("1"), make_job("2")], total_count=4, page=1, page_size=2),
        2: SearchPage(jobs=[make_job("2"), make_job("3")], total_count=4, page=2, page_size=2),
    }

    def fake_search(keywords, *, page=1, **kwargs):
        return pages[page]

    client.search = fake_search  # type: ignore[method-assign]
    jobs = [job for result in client.iter_search("x", max_pages=2) for job in result.jobs]
    assert [job.id for job in jobs] == ["1", "2", "3"]
