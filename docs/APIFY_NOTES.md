# Apify research notes

`apify-client` 3.4.0 was installed in `.venv` for research:

```bash
.venv/bin/pip install "apify-client>=3"
```

It is an optional `research` extra in `pyproject.toml`; the scraper does not
import it at runtime.

## What the Apify Store offers

Store search (public, no token):

```bash
curl 'https://api.apify.com/v2/store?search=jobstreet&limit=50'
```

Dozens of JobStreet actors exist, e.g.:

| Actor | Countries | Pricing model |
| --- | --- | --- |
| `blackfalcondata/jobstreet-scraper` | MY, SG, ID, PH | $0.002 per result + start |
| `scrapersdelight/jobstreet-jobs-scraper` | MY, SG, ID, PH | $0.0002 per job / detail / new job |
| `memo23/jobstreet-scraper` | SEA incl. jobsDB | ~$0.0009 per result + start |
| `shahidirfan/JobStreet-Scraper` | JobStreet | pay per result |

Actor metadata is public:

```bash
curl 'https://api.apify.com/v2/acts/blackfalcondata~jobstreet-scraper'
curl 'https://api.apify.com/v2/acts/scrapersdelight~jobstreet-jobs-scraper'
```

## Verify yourself

```bash
.venv/bin/python research/apify_probe.py
```

This lists 112 JobStreet actors and their public pricing (via `apify-client`,
no token needed). Every one with visible pricing uses `PAY_PER_EVENT`.

## Conclusion

No Apify actor is free/libre. They are hosted, paid, per-result services that
hide the underlying calls. Their descriptions explicitly mention the SEEK API,
which is the same endpoint this project uses directly:

```
GET https://id.jobstreet.com/api/jobsearch/v5/search
```

The Apify client is therefore not part of the runtime path. The free option is
to call JobStreet's own endpoint politely, which is what `jobstreetracer` does.
