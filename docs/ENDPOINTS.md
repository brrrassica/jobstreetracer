# JobStreet Indonesia endpoint map

Verified against `id.jobstreet.com` on 2026-11-05. JobStreet is powered by SEEK
and exposes a Next.js frontend backed by JSON endpoints and a GraphQL gateway.

All requests below need a browser-like TLS fingerprint. Plain `curl` and
`requests` get `HTTP/2 403` with `cf-mitigated: challenge` from Cloudflare.
`curl_cffi` with `impersonate="chrome"` works.

## 1. Search (used)

```
GET https://id.jobstreet.com/api/jobsearch/v5/search
```

Query parameters confirmed working:

| Param | Example | Notes |
| --- | --- | --- |
| `siteKey` | `ID-Main` | Indonesia market |
| `sourcesystem` | `houston` | SEEK search backend |
| `keywords` | `data engineer` | Broad match, including ad body |
| `where` | `Jakarta` | Optional location |
| `page` | `1` | 1-based |
| `pageSize` | `30` | Up to `100` observed |
| `locale` | `en-ID` | `id-ID` also available |
| `sortmode` | `Relevance` / `ListedDate` | Default relevance; date is noisier |
| `daterange` | `7` | Days since listing |
| `worktype` | e.g. `242` | Optional SEEK work-type id |

Other parameters seen in the wild but not required: `classification`,
`subclassification`, `salaryrange`, `isnew`, `event`, `include`.

Example:

```python
from curl_cffi import requests

r = requests.get(
    "https://id.jobstreet.com/api/jobsearch/v5/search",
    params={
        "siteKey": "ID-Main",
        "sourcesystem": "houston",
        "keywords": '"data engineer"',
        "where": "Jakarta",
        "page": 1,
        "pageSize": 30,
        "locale": "en-ID",
        "sortmode": "Relevance",
    },
    impersonate="chrome",
)
print(r.json())
```

Response shape:

```json
{
  "data": [
    {
      "id": "95582087",
      "title": "Data Engineer — Enterprise Data Integration",
      "advertiser": {"id": "60894404", "description": "PT Global Solusindo Kompudata"},
      "classifications": [{
        "classification": {"id": "6281", "description": "Information & Communication Technology"},
        "subclassification": {"id": "6286", "description": "Database Development & Administration"}
      }],
      "locations": [{"label": "Central Jakarta, Jakarta", "countryCode": "ID"}],
      "salaryLabel": "Rp 6.000.000 – Rp 7.500.000 per month",
      "listingDate": "2026-10-29T09:37:55Z",
      "listingDateDisplay": "6d ago",
      "teaser": "Build and implement enterprise data integration solutions...",
      "workTypes": ["Full time"],
      "workArrangements": {"data": [{"id": "1", "label": {"text": "On-site"}}]},
      "roleId": "data-engineer",
      "isFeatured": false
    }
  ],
  "totalCount": 911,
  "info": {"timeTaken": 65, "source": "JobSearch-sm", "newSince": 1793860490},
  "solMetadata": {
    "requestToken": "...",
    "keywords": "data engineer",
    "sortMode": "RELEVANCE",
    "pageSize": 30,
    "pageNumber": 1,
    "totalJobCount": 911
  },
  "searchParams": {"keywords": "data engineer", "page": "1", "pagesize": "30"},
  "facets": {}
}
```

Pagination: increment `page`; stop when `data` is empty or
`page * pageSize >= totalCount`. `totalCount` is the number of matching jobs and
can vary between runs.

## 2. Job detail (used for enrichment)

```
GET https://id.jobstreet.com/id/job/<jobId>
```

Returns server-rendered HTML (also works without the `/id` prefix). Important
`data-automation` selectors:

| Field | Selector |
| --- | --- |
| Title | `[data-automation="job-detail-title"]` |
| Company | `[data-automation="advertiser-name"]` |
| Location | `[data-automation="job-detail-location"]` |
| Salary | `[data-automation="job-detail-salary"]` |
| Work type | `[data-automation="job-detail-work-type"]` |
| Classification | `[data-automation="job-detail-classifications"]` |
| Full description | `[data-automation="jobAdDetails"]` |
| Apply link | `[data-automation="job-detail-apply"]` |

Additional structured values are embedded in the page's script payload:

- `"expiresAt":{"__typename":"SeekDateTime","dateTimeUtc":"..."}`
- `"postedTime":"6d ago"`
- `"isVerified":true`
- `"isLinkOut":false`

There is no `__NEXT_DATA__` or JSON-LD `JobPosting` object; the HTML and the
embedded script state are the useful sources.

## 3. GraphQL gateway (not used)

```
POST https://id.jobstreet.com/graphql
```

Returns a valid GraphQL error when sent an empty body:

```json
{"errors":[{"message":"GraphQL operations must contain a non-empty `query` or a `persistedQuery` extension.", ...}]}
```

The frontend uses this for parts of the job detail page via persisted queries.
We do not need it because the detail HTML already contains everything. It is a
fallback if the markup changes.

## 4. Search result page (not used)

```
GET https://id.jobstreet.com/id/jobs?keywords=...
```

Server-rendered HTML. Useful for debugging what a browser sees, but the JSON
endpoint above is cheaper and more stable.

## Boolean query syntax

The search engine does support boolean logic, but the syntax is picky. Verified
behaviour:

| Query | Result |
| --- | --- |
| `IoT Lead OR IoT Manager OR AI Manager` | 189 loose matches — operators ignored |
| `"IoT Lead" OR "IoT Manager" OR "AI Manager"` | 2 — correct union |
| `"IoT Lead" "AI Manager"` | 0 — adjacent phrases are implicitly ANDed |
| `"IoT Lead" AND "AI Manager"` | 0 — explicit AND works |
| `"IoT Lead" OR "AI Manager"` | 2 — OR works |
| `"IoT Lead" NOT "AI Manager"` | 1 — NOT works |
| `"IoT Lead" -"AI Manager"` | 0 — minus does *not* work |
| `"IoT Lead" or "AI Manager"` | 3 — lowercase `or` is ignored |

Rules of thumb:

1. Quote every phrase.
2. Use uppercase `AND`, `OR`, `NOT`.
3. Adjacent quoted phrases default to AND.
4. Expect occasional false positives when OR-ing multiple phrases. Dedupe is by
   job ID, but there is no relevance-score cutoff.

## Behaviour notes

- `sortmode=Relevance` gives the most precise ordering.
- `sortmode=ListedDate` orders the same broad match set by date; expect
  loosely-related titles near the top because keyword matching includes ad body
  text.
- `totalCount` can be surprisingly large for common keywords (e.g. `data
  engineer` returned 2,429 at one point and 911 at another). Treat counts as
  approximate.
- Detail page location text is sometimes localized differently from the search
  response (`Central Jakarta, Jakarta` vs `Jakarta Pusat, Jakarta Raya`).
- The search endpoint did not require cookies in testing. Detail pages worked
  with the same browser-impersonating session.
- `newSince` and `isnew` query parameters are ignored; the API always returns
  the full match set. Use local ID dedupe for new-only alerts.
- If a challenge appears, rotate the browser profile, warm up on `/id/jobs`,
  and back off. Do not hammer it.
