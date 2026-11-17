"""HTML and JSON parsing helpers for JobStreet pages."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString

from .models import Job


class ParseError(RuntimeError):
    pass


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def html_to_text(html: str) -> str:
    """Convert a job description fragment to readable plain text.

    Keeps paragraph breaks and turns list items into "- item" lines.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert(0, NavigableString("- "))
    for tag in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr"]):
        tag.append(NavigableString("\n"))
    text = soup.get_text("", strip=False)
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out).strip()


def _automation_text(soup: BeautifulSoup, name: str) -> str:
    el = soup.select_one(f'[data-automation="{name}"]')
    return _clean(el.get_text(" ", strip=True)) if el else ""


def _json_regex(html: str, pattern: str) -> str:
    match = re.search(pattern, html)
    return match.group(1) if match else ""


def parse_job_detail(html: str, fallback: Job) -> Job:
    """Extract a full job record from a JobStreet detail page.

    Selectors are data-automation attributes used by the rendered page. If the
    page is a block/challenge page the required title marker is missing and a
    ParseError is raised so the caller can keep the search-result record.
    """
    soup = BeautifulSoup(html, "html.parser")
    if not soup.select_one('[data-automation="jobDetailsPage"]'):
        raise ParseError("job detail page marker not found (blocked or changed layout)")

    title = _automation_text(soup, "job-detail-title")
    if not title:
        raise ParseError("job title not found on detail page")

    description_el = soup.select_one('[data-automation="jobAdDetails"]')
    description_html = description_el.decode_contents() if description_el else ""
    description_text = html_to_text(description_html)

    classification = _automation_text(soup, "job-detail-classifications")
    expires_at = _json_regex(
        html,
        r'"expiresAt":\{"__typename":"SeekDateTime","dateTimeUtc":"([^"]+)"',
    )
    posted_display = _json_regex(html, r'"postedTime":"([^"]+)"')
    verified_match = re.search(r'"isVerified":(true|false)', html)
    linkout_match = re.search(r'"isLinkOut":(true|false)', html)

    updates: dict[str, Any] = {
        "title": title or fallback.title,
        "company": _automation_text(soup, "advertiser-name") or fallback.company,
        "location": _automation_text(soup, "job-detail-location") or fallback.location,
        "salary": _automation_text(soup, "job-detail-salary") or fallback.salary,
        "work_types": _automation_text(soup, "job-detail-work-type") or fallback.work_types,
        "classification": classification or fallback.classification,
        "description_html": description_html,
        "description_text": description_text,
        "expires_at": expires_at,
        "posted_display": posted_display or fallback.posted_display,
        "apply_url": fallback.url.rstrip("/") + "/apply" if fallback.url else "",
    }
    if verified_match:
        updates["is_verified"] = verified_match.group(1) == "true"
    if linkout_match:
        updates["is_link_out"] = linkout_match.group(1) == "true"

    return dataclasses.replace(fallback, **updates)
