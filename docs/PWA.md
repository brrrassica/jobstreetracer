# PWA guide

The web app in [`web/`](../web) is a static, installable Progressive Web App.
It is deployed to GitHub Pages at:

<https://brrrassica.github.io/jobstreetracer/>

It is a **local-first dashboard**, not a second scraper. GitHub Pages cannot run
Python, bypass Cloudflare, or read your SQLite database, so the Python CLI (or a
local bridge) supplies the data.

## Architecture

```
┌──────────────────────────────┐        ┌───────────────────────────────┐
│ Python CLI / scheduler       │        │ Browser PWA (GitHub Pages)    │
│                              │        │                               │
│ JobStreet API ──► SQLite     │        │ IndexedDB                     │
│                      │       │        │  ├─ searches                  │
│                      ▼       │  feed  │  ├─ jobs + tracking           │
│              `publish` ──────┼───────►│  ├─ runs                      │
│           or `bridge`        │        │  ├─ settings (incl. Telegram) │
│                      │       │        │  └─ meta                      │
│                      └───────┼───────►│ Service worker (app shell)    │
│  POST /api/refresh ◄─────────┼────────│ Notifications / badge         │
└──────────────────────────────┘        └───────────────────────────────┘
```

There are three supported data paths:

| Path | How | Best for |
| --- | --- | --- |
| Local bridge | `jobstreetracer bridge --static web/dist` | Live feed + “Run scraper now” + CORS-safe Telegram |
| Published feed | `jobstreetracer publish --out data/feed.json`, served from a private URL | Read-only sync without a running bridge |
| Manual import | `jobstreetracer export`, then Settings → Import | Fully offline / one-off snapshots |

> **Privacy:** the Pages site is public, but it ships only the app shell. Do not
> commit `data/`, `config.toml`, `.env`, feeds, tokens, or exported backups. They
> are ignored by `.gitignore` and are never part of the Pages build.

## Features

- Saved search terms with the same fields as `config.toml`.
- Browsable local listing cache with text, search, status, location and tag
  filters; sorting by newest/oldest/title/company/salary.
- Job detail drawer with sanitized description, notes, tags, and an application
  pipeline (`inbox → shortlisted → applied → interview → offer / rejected /
  archived`).
- Telegram token/chat/topic settings stored locally; test-send and “send new
  listings” actions. Direct browser calls may be blocked by CORS; the bridge
  relays when configured.
- OS notifications for newly seen job IDs while the app is running, plus app
  badge support.
- JSONL/JSON feed import, JSON backup export, and `config.toml` export for CLI
  parity.
- Offline app shell and cached listings via a service worker.

## Feed format

`jobstreetracer publish` and `GET /api/feed` return schema version `1`:

```json
{
  "schema": 1,
  "generated_at": "2026-11-17T10:00:00+00:00",
  "app": {
    "version": "0.1.0",
    "locale": "en-ID",
    "site_key": "ID-Main",
    "schedule": "*/15 * * * *",
    "timezone": "Asia/Jakarta",
    "stats": { "total_jobs": 19, "unnotified": 3, "new_today": 1, "last_run": {} }
  },
  "searches": [
    {
      "name": "data-engineer-jakarta",
      "keywords": "\"data engineer\"",
      "where": "Jakarta",
      "sort": "Relevance",
      "daterange": 14,
      "worktype": "",
      "page_size": 30,
      "max_pages": 3,
      "max_jobs": 0,
      "enrich": true,
      "enabled": true,
      "notify_on_first_run": false
    }
  ],
  "search_state": {
    "data-engineer-jakarta": {
      "first_run_at": "2026-11-01T00:00:00+00:00",
      "last_run_at": "2026-11-17T10:00:00+00:00",
      "baseline_at": "2026-11-01T00:00:00+00:00"
    }
  },
  "runs": [
    {
      "id": 12,
      "started_at": "2026-11-17T10:00:00+00:00",
      "finished_at": "2026-11-17T10:00:04+00:00",
      "searches": 1,
      "scanned": 19,
      "new_jobs": 1,
      "notified": 1,
      "errors": 0
    }
  ],
  "jobs": [
    {
      "id": "123456789",
      "title": "Data Engineer",
      "company": "Example",
      "location": "Jakarta",
      "salary": "Rp 10.000.000 per month",
      "listing_date": "2026-11-16T00:00:00Z",
      "listing_date_display": "1d ago",
      "work_types": "Full time",
      "work_arrangement": "On-site",
      "classification": "Information & Communication Technology",
      "url": "https://id.jobstreet.com/id/job/123456789",
      "apply_url": "",
      "description_html": "<p>…</p>",
      "description_text": "…",
      "first_seen": "2026-11-17T10:00:00+00:00",
      "last_seen": "2026-11-17T10:00:00+00:00",
      "search_name": "data-engineer-jakarta",
      "is_featured": false,
      "is_verified": true
    }
  ]
}
```

`--no-descriptions` omits the description fields to keep the feed small. Import
accepts this object, a bare JSON array of jobs, or JSONL (one job per line). The
app merges by job id, keeps local tracking data, and retains cached jobs missing
from a later feed.

## Local storage

IndexedDB database `jobstreetracer` (version 1):

| Store | Key | Contents |
| --- | --- | --- |
| `jobs` | `id` | Normalized listing + `tracking { status, notes, tags, seen, updatedAt }` |
| `searches` | `name` | PWA-edited search definitions |
| `runs` | `key` (`startedAt::id`) | Recent run summaries |
| `settings` | `key` (`app`) | Feed/bridge URLs, poll interval, notification prefs, Telegram |
| `meta` | `key` | `feedBaseline` flag used to keep the first sync silent |

The first feed import is a **silent baseline** (`feedBaseline`); only jobs that
appear in later syncs are flagged as new. Clearing all local data resets the
baseline.

## Search editor ↔ config.toml

The PWA is the editor of record for its own searches. Export them with
**Searches → Export config.toml** and paste into the CLI config, or enable
**Mirror search definitions from each feed sync** in Settings to let the CLI win
on every sync.

PWA field ↔ TOML field:

| PWA | TOML |
| --- | --- |
| Name | `name` |
| Keywords | `keywords` |
| Where | `where` |
| Sort | `sort` |
| Max age (days) | `daterange` |
| Work type | `worktype` |
| Page size | `page_size` |
| Max pages | `max_pages` |
| Max jobs | `max_jobs` |
| Fetch full descriptions | `enrich` |
| Enabled | `enabled` |
| Notify on first baseline | `notify_on_first_run` |

## Local bridge API

`jobstreetracer bridge` binds to `127.0.0.1` by default and is deliberately not a
system daemon. It serves:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | `{ "ok": true, "version": "…" }` |
| `GET` | `/api/setup/status` | Setup/readiness info (paths, command, autostart state) |
| `GET` | `/api/feed` | Current feed JSON |
| `POST` | `/api/refresh` | Run one scrape cycle; optional `{ "search": ["name"], "max_pages": 3, "no_enrich": true, "no_notify": false }` |
| `POST` | `/api/telegram` | Relay `{ token, chat_ids, topic_id, text }` to Telegram |
| `POST` | `/api/setup/autostart` | `{ "enabled": true|false, "method"?: "auto" }` — enable/disable user-session autostart |
| `GET` | `/jobstreetracer/…` | Built PWA (when `--static web/dist` is passed) |

POST requests require the `X-JSR-Bridge: 1` header. CORS allows
`https://brrrassica.github.io` and loopback origins, and responds to Chrome's
Private Network Access preflight. The bridge has no authentication and must stay
bound to localhost.

## Setup wizard and autostart

The PWA includes a **Setup wizard** (Dashboard/Settings) that can probe for a
local bridge, save feed/bridge settings, request notification permission, and
toggle autostart when connected.

CLI helpers:

- `jobstreetracer setup` — show readiness (config/static/command/autostart)
- `jobstreetracer setup --enable-autostart` / `--disable-autostart`
- `jobstreetracer setup --install-command` — print a bootstrap command

Autostart targets user-session startup (no elevation): Linux desktop autostart
(or `--method linux-user-service`), Windows current-user Run entry, macOS
LaunchAgent. For true boot-time startup before login, use an elevated system
service (e.g. `deploy/jobstreetracer.service` on Linux or a Windows scheduled
task "At startup"). Manual templates remain in `deploy/`:

- Linux: `deploy/jobstreetracer-bridge.desktop` → `~/.config/autostart/`
- Windows: shortcut `deploy\jobstreetracer-bridge.cmd` → `shell:startup`

## Notifications: what is guaranteed

- **App open (foreground):** each sync diffs job IDs, fires a Notification API
  toast for new ones, and updates the app badge.
- **App minimized / resident browser:** usually works while Chromium is running,
  but OS power saving and background throttling apply.
- **App/browser fully closed:** no toast from the static PWA. Use Telegram (CLI
  or bridge), or keep a companion process running.

The app is a normal installed web app, not a service/daemon; “run at boot”
means letting Chromium start the installed app on login and keep background
apps running.

## Development

```bash
cd web
npm install
npm run dev       # http://127.0.0.1:5173/jobstreetracer/
npm test          # feed merge/parse/export unit tests
npm run build     # web/dist
```

Useful local preview with live data:

```bash
cd ..
.venv/bin/jobstreetracer publish --out data/feed.json --pretty
.venv/bin/jobstreetracer bridge --static web/dist --open
```

## Deployment

`.github/workflows/pages.yml` builds `web/` and deploys `web/dist` with the
official GitHub Pages actions whenever `main` changes. In the repository:

1. **Settings → Pages → Source:** GitHub Actions.
2. Build base is `/jobstreetracer/` (`web/vite.config.ts`). If you rename the
   repo, update the base, the manifest `start_url`/`scope`, and the workflow
   path assumptions together.
3. The site is public; only app shell assets are uploaded.

## Troubleshooting

- **Install button missing:** serve over HTTPS (or localhost), confirm
  `manifest.webmanifest` loads without errors, and check the service worker in
  DevTools → Application. Chrome's install criteria need the manifest, 192/512
  icons, `start_url`, `display: standalone`, and an activated service worker with
  a fetch handler.
- **Old UI after deploy:** the service worker caches the shell. Reload; the next
  activation clears old `jsr-*` caches. If needed, unregister the service worker
  in DevTools and reload.
- **Bridge unreachable from the published site:** check it is running on
  `http://127.0.0.1:8765`, the URL is exact, and the origin is
  `https://brrrassica.github.io`. Chrome may preflight localhost requests; the
  bridge sends `Access-Control-Allow-Private-Network: true`.
- **Telegram test fails with CORS/network:** set the Bridge URL; the bridge
  relays Telegram server-side from your machine. Direct browser sends are
  best-effort.
- **No notifications:** grant permission from Settings; check OS/Chromium
  notification settings and whether the app/browser is still running.
- **“No feed configured”:** set a Bridge URL or Feed URL, or import a JSON/JSONL
  export. A relative `data/feed.json` path resolves against the app origin (and
  is not served by GitHub Pages).
- **Feed sync imported searches unexpectedly:** disable
  **Mirror search definitions from each feed sync** and keep the PWA as the
  editor of record.

## Security notes

- The Telegram bot token is stored in this browser origin's IndexedDB. It is not
  encrypted at rest beyond browser profile protections. Use a dedicated bot and
  lock your OS account; do not include the token in shared backups.
- The PWA never scrapes JobStreet directly and never publishes job data.
- The bridge can trigger scrapes and send Telegram messages. Keep it on
  `127.0.0.1`; do not expose it on a LAN or the internet.
- JobStreet's endpoints are unofficial. Keep request rates polite and check
  their terms.
