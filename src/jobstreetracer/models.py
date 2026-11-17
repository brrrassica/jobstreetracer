"""Data models shared by the scraper, store, and notifier."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _join(values: list[str]) -> str:
    seen: list[str] = []
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            seen.append(value)
    return " | ".join(seen)


@dataclass
class Job:
    """A normalized JobStreet listing.

    Search results provide most fields; detail pages add the description,
    expiry, and verification state.
    """

    id: str
    title: str
    company: str = ""
    company_id: str = ""
    location: str = ""
    salary: str = ""
    listing_date: str = ""
    listing_date_display: str = ""
    posted_display: str = ""
    teaser: str = ""
    work_types: str = ""
    work_arrangement: str = ""
    classification: str = ""
    subclassification: str = ""
    url: str = ""
    role_id: str = ""
    is_featured: bool = False
    is_verified: bool | None = None
    is_link_out: bool | None = None
    description_html: str = ""
    description_text: str = ""
    expires_at: str = ""
    apply_url: str = ""
    search_name: str = ""
    first_seen: str = ""
    last_seen: str = ""
    is_new: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_search(cls, item: dict[str, Any], *, base_url: str, search_name: str) -> "Job":
        advertiser = item.get("advertiser") or {}
        classifications = item.get("classifications") or []
        first_class = classifications[0] if classifications else {}
        classification = (first_class.get("classification") or {}).get("description") or ""
        subclassification = (first_class.get("subclassification") or {}).get("description") or ""

        locations = [
            loc.get("label", "")
            for loc in (item.get("locations") or [])
            if isinstance(loc, dict)
        ]
        work_types = [wt for wt in (item.get("workTypes") or []) if isinstance(wt, str)]
        arrangements = [
            ((arr.get("label") or {}).get("text") or "")
            for arr in ((item.get("workArrangements") or {}).get("data") or [])
            if isinstance(arr, dict)
        ]

        job_id = str(item.get("id") or "")
        return cls(
            id=job_id,
            title=(item.get("title") or "").strip(),
            company=(advertiser.get("description") or "").strip(),
            company_id=str(advertiser.get("id") or ""),
            location=_join(locations),
            salary=(item.get("salaryLabel") or "").strip(),
            listing_date=(item.get("listingDate") or "").strip(),
            listing_date_display=(item.get("listingDateDisplay") or "").strip(),
            teaser=(item.get("teaser") or "").strip(),
            work_types=_join(work_types),
            work_arrangement=_join(arrangements),
            classification=classification,
            subclassification=subclassification,
            url=f"{base_url}/id/job/{job_id}" if job_id else "",
            role_id=(item.get("roleId") or "").strip(),
            is_featured=bool(item.get("isFeatured")),
            search_name=search_name,
            raw=item,
        )

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data.pop("raw", None)
        return data


@dataclass
class SearchPage:
    jobs: list[Job]
    total_count: int
    page: int
    page_size: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
