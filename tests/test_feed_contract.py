"""Contract test: a feed written by ``publish.py`` parses through the PWA.

The web side consumes ``web/tests/fixtures/feed.json`` (see
``web/src/feed.contract.test.ts``). This module is the other half of that
contract: it regenerates the feed with the current Python schema and asserts the
committed fixture still matches, so backend schema drift that the PWA parser
would not handle fails CI here rather than silently in the browser.

Refresh the fixture after an intentional schema change with::

    pytest tests/test_feed_contract.py --update-fixtures
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobstreetracer import publish, store as store_module
from jobstreetracer.config import load_config
from jobstreetracer.models import Job
from jobstreetracer.publish import build_feed
from jobstreetracer.store import JobStore

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "web" / "tests" / "fixtures" / "feed.json"

FROZEN = "2026-01-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin time so the fixture is byte-stable across runs.

    ``store`` and ``publish`` each do ``from .models import utc_now`` and bind a
    module-local reference, so patching ``models.utc_now`` alone would have no
    effect. Patch the references these modules actually call.
    """
    monkeypatch.setattr(store_module, "utc_now", lambda: FROZEN)
    monkeypatch.setattr(publish, "utc_now", lambda: FROZEN)


def _make_job(job_id: str) -> Job:
    return Job(
        id=job_id,
        title=f"Senior Data Engineer {job_id}",
        company="Acme Corp",
        company_id=f"co-{job_id}",
        location="Jakarta Selatan, Jakarta",
        salary="Rp 20.000.000 - Rp 30.000.000",
        listing_date="2026-01-01T00:00:00Z",
        listing_date_display="1 day ago",
        posted_display="1d ago",
        teaser="Join our data platform team building petabyte pipelines.",
        work_types="Full time",
        work_arrangement="Hybrid",
        classification="Information & Communication Technology",
        subclassification="Data Science & Machine Learning",
        url=f"https://id.jobstreet.com/id/job/{job_id}",
        role_id="12345",
        is_featured=job_id == "1",
        is_verified=True,
        is_link_out=False,
        description_text=f"A rich description for job {job_id} with keywords and responsibilities.",
        description_html=f"<p>A rich description for job {job_id}.</p>",
        expires_at="2026-02-01T00:00:00Z",
        apply_url=f"https://id.jobstreet.com/apply/{job_id}",
        search_name="contract-search",
    )


def _seed_store(store: JobStore) -> None:
    jobs = [_make_job("1"), _make_job("2")]
    jobs[1].description_text = ""  # second job stays unenriched
    jobs[1].description_html = ""
    store.upsert_jobs(jobs)
    store.update_detail(jobs[0])  # exercise the enrichment path too
    store.mark_search_run("contract-search")
    store.record_run(
        started_at="2025-12-31T23:00:00+00:00",
        searches=1,
        scanned=2,
        new_jobs=2,
        notified=0,
        errors=0,
    )
    # one notified job so the feed carries a non-null notified_at for the PWA
    store.mark_notified(["1"])


def _build_feed(config_path: Path) -> dict:
    config = load_config(config_path)
    return build_feed(config)


@pytest.fixture()
def feed(tmp_path: Path) -> dict:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[app]
locale = "en-ID"
site_key = "ID-Main"
db_path = "data/jobs.db"

[[search]]
name = "contract-search"
keywords = '"data engineer"'
where = "Jakarta"
sort = "Date"
daterange = 14
page_size = 30
max_pages = 3
enrich = true
enabled = true
""",
        encoding="utf-8",
    )
    config = load_config(cfg)
    store = JobStore(config.db_path)
    try:
        _seed_store(store)
    finally:
        store.close()
    return _build_feed(cfg)


def _normalize(payload: object) -> object:
    """Strip volatile values, keep the shape (keys + value types)."""
    if isinstance(payload, dict):
        return {key: _normalize(value) for key, value in sorted(payload.items())}
    if isinstance(payload, list):
        return [_normalize(item) for item in payload]
    return type(payload).__name__


def test_feed_shape_matches_pwa_fixture(feed: dict, request: pytest.FixtureRequest) -> None:
    generated = json.dumps(feed, indent=2, ensure_ascii=False) + "\n"

    if request.config.getoption("--update-fixtures"):
        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE_PATH.write_text(generated, encoding="utf-8")
        pytest.skip("regenerated web/tests/fixtures/feed.json")

    assert FIXTURE_PATH.exists(), (
        f"missing contract fixture at {FIXTURE_PATH}; "
        "run: pytest tests/test_feed_contract.py --update-fixtures"
    )
    committed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert _normalize(committed) == _normalize(feed), (
        "publish.py schema drifted from the committed PWA fixture; "
        "update the web parser and regenerate with --update-fixtures"
    )
    # also assert the exact bytes so the fixture stays reproducible
    assert FIXTURE_PATH.read_text(encoding="utf-8") == generated


def test_feed_jobs_use_snake_case_keys(feed: dict) -> None:
    # the PWA parser reads these exact keys; guard the contract explicitly
    expected = {
        "id",
        "title",
        "company",
        "company_id",
        "location",
        "salary",
        "listing_date",
        "teaser",
        "work_types",
        "url",
        "is_featured",
        "description_text",
        "search_name",
    }
    for job in feed["jobs"]:
        assert expected.issubset(job.keys())
        assert "raw" not in job
