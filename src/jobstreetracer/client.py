"""HTTP client for the JobStreet Indonesia web API.

JobStreet is powered by SEEK. The site's own search endpoint is a free,
keyless JSON API. It is unofficial: it can change, rate-limit, or start
requiring a browser challenge at any time.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Iterator

from curl_cffi import requests

from .models import Job, SearchPage
from .parsing import parse_job_detail

log = logging.getLogger(__name__)

BASE_URL = "https://id.jobstreet.com"
SEARCH_PATH = "/api/jobsearch/v5/search"
MAX_PAGE_SIZE = 100


class JobStreetError(RuntimeError):
    pass


class BlockedError(JobStreetError):
    pass


class ApiError(JobStreetError):
    pass


class JobStreetClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        locale: str = "en-ID",
        site_key: str = "ID-Main",
        delay_seconds: float = 1.0,
        timeout: float = 30.0,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.site_key = site_key
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.session = requests.Session()
        self._last_request = 0.0
        self._impersonation = "chrome"
        self._impersonations = ["chrome", "safari", "edge"]

    # -- low level -----------------------------------------------------
    def _throttle(self) -> None:
        if self.delay_seconds <= 0:
            return
        wait = self.delay_seconds - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def _headers(self, *, accept: str, referer: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "Accept-Language": "en-ID,en;q=0.9,id;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def _warm_up(self) -> None:
        """Visit a normal page so the session has fresh cookies."""
        try:
            self.session.get(
                f"{self.base_url}/id/jobs",
                impersonate=self._impersonation,
                timeout=self.timeout,
                headers=self._headers(accept="text/html"),
            )
        except Exception as exc:  # pragma: no cover - best effort only
            log.debug("warm-up failed: %s", exc)

    def _request(
        self,
        method: str,
        url: str,
        *,
        accept: str = "application/json",
        referer: str | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                response = self.session.request(
                    method,
                    url,
                    impersonate=self._impersonation,
                    timeout=self.timeout,
                    headers=self._headers(accept=accept, referer=referer),
                    **kwargs,
                )
            except Exception as exc:
                last_error = exc
                log.warning("request error (%s/%s): %s", attempt, self.max_retries, exc)
                if attempt == self.max_retries:
                    break
                time.sleep(min(2 ** attempt + random.random(), 30))
                continue

            self._last_request = time.monotonic()
            challenged = response.status_code == 403 or response.headers.get(
                "cf-mitigated"
            ) == "challenge"
            if not challenged and response.status_code not in (429, 500, 502, 503, 504):
                if response.status_code >= 400:
                    raise ApiError(f"HTTP {response.status_code} for {url}")
                return response

            last_error = (
                BlockedError(f"HTTP {response.status_code} challenge for {url}")
                if challenged
                else ApiError(f"HTTP {response.status_code} for {url}")
            )
            log.warning(
                "blocked/server error (%s/%s): %s",
                attempt,
                self.max_retries,
                last_error,
            )
            if attempt == self.max_retries:
                break
            if challenged:
                self._impersonation = self._impersonations[
                    attempt % len(self._impersonations)
                ]
                self._warm_up()
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), 30))
            else:
                time.sleep(min(2 ** attempt + random.random(), 30))

        raise BlockedError(str(last_error)) if isinstance(
            last_error, BlockedError
        ) else JobStreetError(str(last_error))

    # -- public API ----------------------------------------------------
    def search(
        self,
        keywords: str = "",
        *,
        where: str | None = None,
        page: int = 1,
        page_size: int = 30,
        sort: str | None = "Relevance",
        daterange: int | None = None,
        worktype: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> SearchPage:
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        params: dict[str, Any] = {
            "siteKey": self.site_key,
            "sourcesystem": "houston",
            "keywords": keywords,
            "page": max(1, int(page)),
            "pageSize": page_size,
            "locale": self.locale,
        }
        if where:
            params["where"] = where
        if sort:
            params["sortmode"] = sort
        if daterange:
            params["daterange"] = int(daterange)
        if worktype:
            params["worktype"] = worktype
        if extra:
            params.update(extra)

        response = self._request(
            "GET",
            f"{self.base_url}{SEARCH_PATH}",
            params=params,
            referer=f"{self.base_url}/id/jobs",
        )
        try:
            data = response.json()
        except Exception as exc:
            raise ApiError(f"search response was not JSON: {exc}") from exc

        items = data.get("data") or []
        jobs = [
            Job.from_search(item, base_url=self.base_url, search_name="")
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]
        total = int(data.get("totalCount") or 0)
        return SearchPage(
            jobs=jobs,
            total_count=total,
            page=page,
            page_size=page_size,
            raw=data,
        )

    def iter_search(
        self,
        keywords: str = "",
        *,
        max_pages: int = 3,
        max_jobs: int = 0,
        **kwargs: Any,
    ) -> Iterator[SearchPage]:
        """Yield pages newest-first, stopping on exhaustion or caps."""
        seen: set[str] = set()
        yielded = 0
        for page in range(1, max(1, max_pages) + 1):
            result = self.search(keywords, page=page, **kwargs)
            remaining = max_jobs - yielded if max_jobs else None
            if remaining is not None and remaining <= 0:
                break
            fresh = [job for job in result.jobs if job.id not in seen]
            if remaining is not None:
                fresh = fresh[:remaining]
            for job in fresh:
                seen.add(job.id)
            result.jobs = fresh
            yielded += len(fresh)
            yield result

            if len(fresh) == 0:
                break
            if result.total_count and page * result.page_size >= result.total_count:
                break
            if max_jobs and yielded >= max_jobs:
                break

    def get_detail(self, job: Job) -> Job:
        url = job.url or f"{self.base_url}/id/job/{job.id}"
        response = self._request(
            "GET",
            url,
            accept="text/html",
            referer=f"{self.base_url}/id/jobs",
        )
        return parse_job_detail(response.text, job)
