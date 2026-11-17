from __future__ import annotations

import pytest

from jobstreetracer.models import Job
from jobstreetracer.parsing import ParseError, html_to_text, parse_job_detail

SEARCH_ITEM = {
    "id": "123456",
    "title": "Senior Data Engineer",
    "advertiser": {"id": "99", "description": "Acme Data"},
    "classifications": [
        {
            "classification": {"id": "6281", "description": "Information & Communication Technology"},
            "subclassification": {"id": "6286", "description": "Database Development & Administration"},
        }
    ],
    "locations": [
        {"label": "Central Jakarta, Jakarta"},
        {"label": "Central Jakarta, Jakarta"},
        {"label": "Remote"},
    ],
    "workTypes": ["Full time", "Contract"],
    "workArrangements": {"data": [{"id": "1", "label": {"text": "On-site"}}]},
    "salaryLabel": "Rp 10.000.000 per month",
    "listingDate": "2026-11-01T00:00:00Z",
    "listingDateDisplay": "4d ago",
    "teaser": "Build pipelines",
    "isFeatured": False,
    "roleId": "data-engineer",
}

DETAIL_HTML = """
<html><body>
<div data-automation="jobDetailsPage">
  <h1 data-automation="job-detail-title">Senior Data Engineer</h1>
  <span data-automation="advertiser-name">Acme Data</span>
  <span data-automation="job-detail-location">Jakarta, Indonesia</span>
  <span data-automation="job-detail-salary">Rp 10.000.000 per month</span>
  <span data-automation="job-detail-work-type">Full time</span>
  <a data-automation="job-detail-classifications">Information &amp; Communication Technology</a>
  <div data-automation="jobAdDetails">
    <p>Build reliable pipelines.</p>
    <ul><li>SQL</li><li>Python</li></ul>
  </div>
  <script>
    {"expiresAt":{"__typename":"SeekDateTime","dateTimeUtc":"2026-12-01T00:00:00.000Z"},
     "postedTime":"4d ago","isVerified":true,"isLinkOut":false}
  </script>
</div>
</body></html>
"""


def test_from_search_normalizes_fields() -> None:
    job = Job.from_search(SEARCH_ITEM, base_url="https://id.jobstreet.com", search_name="test")
    assert job.id == "123456"
    assert job.company == "Acme Data"
    assert job.location == "Central Jakarta, Jakarta | Remote"
    assert job.work_types == "Full time | Contract"
    assert job.work_arrangement == "On-site"
    assert job.classification == "Information & Communication Technology"
    assert job.subclassification == "Database Development & Administration"
    assert job.url == "https://id.jobstreet.com/id/job/123456"
    assert job.search_name == "test"


def test_parse_detail_enriches_job() -> None:
    job = Job.from_search(SEARCH_ITEM, base_url="https://id.jobstreet.com", search_name="test")
    detail = parse_job_detail(DETAIL_HTML, job)
    assert detail.title == "Senior Data Engineer"
    assert detail.company == "Acme Data"
    assert detail.location == "Jakarta, Indonesia"
    assert detail.work_types == "Full time"
    assert detail.expires_at == "2026-12-01T00:00:00.000Z"
    assert detail.posted_display == "4d ago"
    assert detail.is_verified is True
    assert detail.is_link_out is False
    assert detail.apply_url == "https://id.jobstreet.com/id/job/123456/apply"
    assert "Build reliable pipelines." in detail.description_text
    assert "- SQL" in detail.description_text
    assert "- Python" in detail.description_text


def test_parse_detail_rejects_challenge_page() -> None:
    job = Job.from_search(SEARCH_ITEM, base_url="https://id.jobstreet.com", search_name="test")
    with pytest.raises(ParseError):
        parse_job_detail("<html><body>Cloudflare challenge</body></html>", job)


def test_html_to_text_collapses_blank_lines() -> None:
    text = html_to_text("<p>A</p><p></p><p>B</p><br><ul><li>C</li></ul>")
    assert "A" in text and "B" in text and "- C" in text
    assert "\n\n\n" not in text
