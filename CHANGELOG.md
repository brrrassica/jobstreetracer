# Changelog

All notable changes to JobStreetracer are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-17

First stable release. The full feature set developed pre-tag is described
below; the feed schema is frozen at this tag (schema version `1`).

### Added

- **Scraper core**: direct client for JobStreet Indonesia's SEEK-backed JSON
  search API (`client.py`) with `curl_cffi` browser impersonation, request
  throttling, and automatic backoff on `403`/`429`/`5xx`.
- **Detail enrichment**: new jobs are enriched from their rendered detail
  pages, with retry of any missing descriptions (`parsing.py`).
- **Storage**: SQLite store with dedupe by JobStreet job ID and per-run
  history (`store.py`); JSONL run snapshots under `data/runs/`.
- **Silent baseline**: the first run of each search seeds existing matches
  without notifying; later runs alert only on unseen job IDs (`runner.py`).
- **Telegram alerts**: multi-chat recipients, group-topic support, and a
  per-run batch cap (`notify.py`).
- **Scheduling**: built-in cron loop via APScheduler (`scheduler.py`) plus
  systemd timer and crontab templates (`deploy/`).
- **CLI**: `init`, `run`, `schedule`, `search`, `jobs`, `stats`, `export`,
  `publish`, `bridge`, `setup`, `doctor` (`cli.py`).
- **PWA**: installable React + Vite Progressive Web App deployed to GitHub
  Pages — IndexedDB local store, feed import, filter/sort listings, job
  detail with notes/tags/application pipeline, setup wizard, and OS toasts
  for newly seen job IDs (`web/`).
- **Localhost bridge**: `/api/feed`, `/api/refresh`, `/api/telegram`,
  `/api/health`, `/api/setup/status`, and `/api/setup/autostart` endpoints
  for the PWA (`bridge.py`, `setup.py`); user-session autostart on
  Linux/Windows/macOS.
- **Feed publishing**: versioned JSON feed for the PWA via
  `jobstreetracer publish` (`publish.py`).
- **CI**: `ruff` lint + `pytest` matrix on Python 3.11–3.13, PWA `npm test`
  and build, and GitHub Pages deployment (`.github/workflows/`).
- **Docs**: PWA guide, JobStreet endpoint map, Apify research notes
  (`docs/`).

### Distribution

- Install from the git tag: `pip install
  "jobstreetracer @ git+https://github.com/brrrassica/jobstreetracer@v0.1.0"`.
  PyPI publication is explicitly not planned (see README).

[0.1.0]: https://github.com/brrrassica/jobstreetracer/releases/tag/v0.1.0
