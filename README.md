# JobStreetracer

A polite JobStreet Indonesia scraper + cron scheduler with SQLite dedupe and
Telegram alerts. Focused on `id.jobstreet.com`.

It talks directly to JobStreet's own SEEK-backed JSON search API, then enriches
new jobs from their detail pages. No Apify account, no API key, no third-party
service.

> **Unofficial.** This uses a public web endpoint that JobStreet does not
> document or guarantee. It can change or block requests at any time. Check
> JobStreet's terms before using it, keep the request rate low, and use it for
> personal job hunting rather than republishing their data.

## PWA (GitHub Pages)

The repo also ships an installable Progressive Web App at:

**https://brrrassica.github.io/jobstreetracer/**

It is a local-first dashboard for the data the Python scraper produces: saved
search terms, a filterable/sortable listing cache, job detail with notes/tags and
an application pipeline, Telegram settings, and optional OS toasts for new
matches. See [docs/PWA.md](docs/PWA.md) for the feed schema, bridge API,
IndexedDB layout, notification guarantees, and troubleshooting.

The Pages site is static, so it cannot scrape JobStreet by itself. Open the
**Setup wizard** in the app for guided configuration (detect/connect bridge,
choose a feed, request notifications, and enable autostart). Pick one of these
data paths:

1. **Local bridge (recommended, no daemon):**
   ```bash
   cd ~/projects/jobstreetracer
   .venv/bin/jobstreetracer setup --enable-autostart
   .venv/bin/jobstreetracer bridge --static web/dist --open
   ```
   The wizard can detect the bridge at `http://127.0.0.1:8765`, save the feed,
   and toggle login autostart with one click when connected. The bridge exposes
   `/api/feed`, `/api/refresh` (run one scrape now), `/api/telegram` (CORS-safe
   relay), and setup endpoints for status/autostart. Bind it to localhost only.
   If the bridge is not installed yet, the wizard shows a copyable bootstrap
   command.
2. **Published feed:** `jobstreetracer publish --out data/feed.json`, then point
   the PWA's Settings/wizard at a URL that serves that JSON. Keep private job
   data out of the public repo/Pages site.
3. **Manual import:** export with `jobstreetracer export` and use
   *Settings → Import JSONL / JSON feed* in the PWA.

The PWA stores searches, listings, tracking notes, settings and the Telegram bot
token in this browser profile (IndexedDB). It never writes to the repo or Pages.
Chrome/Chromium can install it from the toolbar or **Settings → Install app**.

### Notifications and “run at boot”

The installed app polls the configured feed while it is running and shows an OS
toast for newly seen job IDs. For alerts while logged in, let Chromium/your
desktop start the installed app on login and keep background apps running. This
is a normal app process, not a system service; toasts stop if you fully quit the
browser. For guaranteed scraping while everything is closed, keep the Python
scheduler/timer or the bridge running (autostart entry), or rely on Telegram.

Autostart the bridge (so “run scraper now” and feeds work after login):

- **One click (when bridge is running):** open the PWA Setup wizard and enable
  autostart, or run `jobstreetracer setup --enable-autostart`.
- **Linux (manual):** copy `deploy/jobstreetracer-bridge.desktop` to
  `~/.config/autostart/` and adjust the path if needed.
- **Windows (manual):** put a shortcut to `deploy\jobstreetracer-bridge.cmd` in
  `shell:startup` (Win+R → type `shell:startup`). It starts minimized.
- **macOS:** `jobstreetracer setup --enable-autostart` writes a LaunchAgent plist.

These configure user-session startup (no elevation). If you need a true boot-time
service before login, use an elevated system service (e.g. the Linux template in
`deploy/jobstreetracer.service` or a Windows scheduled task "At startup").

The installed PWA itself can also be allowed to start on login, depending on
Chromium/OS settings; keep it open (minimized) for periodic feed polling and OS
toasts.


Telegram calls made directly from the browser are often blocked by CORS. Set the
bridge URL in Settings to relay **Send test** and job messages through
`/api/telegram`. The token is kept locally and is omitted from exports unless you
opt in.


## Install

```bash
cd ~/projects/jobstreetracer
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Quick start

```bash
.venv/bin/jobstreetracer init          # creates config.toml and .env
$EDITOR config.toml                    # set keywords/location
$EDITOR .env                           # Telegram token + chat id
.venv/bin/jobstreetracer doctor
.venv/bin/jobstreetracer run --dry-run # scrape now, print alerts
.venv/bin/jobstreetracer run           # scrape now, send alerts
```

The first run of each search establishes a **silent baseline**: existing matches
are stored but not sent. Later runs only notify job IDs that have never been
seen before. Use `run --notify-first-run` if you want the initial backlog sent.

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather), run `/newbot`, and copy the token.
2. Send any message to your new bot.
3. Get your chat id:

   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result'][0]['message']['chat']['id'])"
   ```

4. Put both values in `.env`:

   ```dotenv
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=123456789,987654321
   ```

For multiple recipients, put comma-separated chat ids in `TELEGRAM_CHAT_ID` (or
use `TELEGRAM_CHAT_IDS`). Every job is sent to every recipient; a job is marked
notified only after all recipients accept the message.

For a group topic, also set `TELEGRAM_TOPIC_ID`.

Without Telegram credentials the scraper still runs and stores jobs; they stay
un-notified and are sent later once credentials are configured.

## Schedule it

### Option A — built-in cron scheduler

```bash
.venv/bin/jobstreetracer schedule          # uses schedule/timezone from config.toml
.venv/bin/jobstreetracer schedule --run-now
.venv/bin/jobstreetracer schedule --cron "*/30 * * * *" --timezone Asia/Jakarta
```

Runs in the foreground. Keep it alive with systemd, tmux, or a process manager.

### Option B — systemd timer

```bash
sudo cp deploy/jobstreetracer.service deploy/jobstreetracer.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobstreetracer.timer
systemctl list-timers jobstreetracer.timer
```

The unit assumes the project lives at `/home/sam/projects/jobstreetracer`.
Edit the paths if needed.

### Option C — plain cron

```cron
*/15 * * * * cd /home/sam/projects/jobstreetracer && flock -n /tmp/jobstreetracer.lock .venv/bin/jobstreetracer run >> data/cron.log 2>&1
```

Pick one scheduler, not all three.

## Commands

| Command | Purpose |
| --- | --- |
| `jobstreetracer init` | Create `config.toml` / `.env` from templates |
| `jobstreetracer run` | Scrape once, store, notify |
| `jobstreetracer schedule` | Run forever on a cron expression |
| `jobstreetracer search "data engineer" --where Jakarta` | Ad-hoc search, prints a table |
| `jobstreetracer search ... --json --details 1` | JSON output with full description |
| `jobstreetracer jobs --limit 20` | Show recent stored jobs |
| `jobstreetracer stats` | Database and last-run stats |
| `jobstreetracer export --format csv --out data/jobs.csv` | Export everything |
| `jobstreetracer publish --out data/feed.json` | Export a PWA feed (searches + jobs + runs) |
| `jobstreetracer bridge --static web/dist` | Localhost feed/refresh/Telegram endpoints for the PWA |
| `jobstreetracer setup --enable-autostart` | Check bridge readiness and configure login autostart |
| `jobstreetracer doctor` | Check config, API, and Telegram |

Useful flags for `run`:

```bash
--search NAME      # only run one configured search (repeatable)
--max-pages N      # override page cap
--no-enrich        # skip per-job detail fetches (faster)
--no-notify        # store only
--dry-run          # print Telegram messages, send nothing, mark nothing
--json             # machine-readable run summary
-v                 # debug logging
```

## Configuration

`config.toml`:

```toml
[app]
locale = "en-ID"
site_key = "ID-Main"
delay_seconds = 1.0
timeout_seconds = 30
enrich_details = true
output_dir = "data"
db_path = "data/jobs.db"
notify_max_jobs = 40
schedule = "*/15 * * * *"
timezone = "Asia/Jakarta"
notify_on_first_run = false   # silent baseline on a search's first run

[[search]]
name = "data-engineer-jakarta"
keywords = '"data engineer"'   # quotes = exact phrase
where = "Jakarta"
sort = "Relevance"      # or "ListedDate" for newest-first
daterange = 14          # days
page_size = 30          # API accepts up to 100
max_pages = 3
enrich = true
enabled = true
```

Notes:

- `keywords` uses JobStreet's normal search semantics, which are broad (they can
  match words in the ad body, not just the title). Wrap a phrase in quotes
  (`'"data engineer"'` in TOML, or `'"data engineer"'` on the CLI) for an exact
  phrase, which is much more precise. `Relevance` gives the best precision;
  `ListedDate` gives the freshest but noisier list.
- Boolean operators only work with quoted phrases and uppercase operators, e.g.
  `'"IoT Lead" OR "AI Manager"'`. Unquoted `IoT Lead OR AI Manager` is treated
  as loose keywords and returns noise. See
  [docs/ENDPOINTS.md](docs/ENDPOINTS.md#boolean-query-syntax).
- `where` accepts a city/region, e.g. `Jakarta`, `Bandung`, `Surabaya`.
- `daterange` filters by listing age.
- `max_jobs = 0` means unlimited (still bounded by `max_pages`).
- Relative paths resolve against the config file's directory.
- Environment variables override Telegram, DB, output dir, schedule, timezone,
  and delay settings. See `.env.example`.

## Output

Each run that finds new jobs writes a snapshot to
`data/runs/YYYYMMDD-HHMMSS-nanoseconds.jsonl`. Every job record includes title,
company, location, salary, dates, classification, work type, URL, and the full
description when enriched. Runs with no new jobs skip the snapshot.

SQLite (`data/jobs.db`) keeps:

- `jobs` — one row per JobStreet job ID, with `first_seen`, `last_seen`,
  `notified_at`, and the normalized fields.
- `runs` — one row per scrape run.

Dedupe is by JobStreet job ID, so the same job appearing in multiple searches is
only notified once.

## How it works

1. `GET /api/jobsearch/v5/search` for each configured search, paginated.
2. Upsert results into SQLite. On a search's first run, existing matches are
   marked notified silently; afterwards only unseen IDs are alerts.
3. Fetch `https://id.jobstreet.com/id/job/<id>` for new jobs (and retry any
   missing descriptions) and parse the rendered detail page.
4. Write a JSONL snapshot of the full result set (archive, not alerts).
5. Send pending **unseen** jobs to Telegram in batches; mark them notified only
   after a successful API response.

### New-only behaviour

The search endpoint ignores `newSince` and `isnew`; it always returns the whole
match set. "New" is therefore determined locally by JobStreet job ID in SQLite:

- First run of a search: seed the backlog silently.
- Later runs: notify only IDs that were not already stored.
- `notify_on_first_run = true` in `[app]` (or per `[[search]]`) restores the old
  behaviour of sending the initial backlog too.
- `jobstreetracer run --notify-first-run` does the same for one run.

This means a 15-minute poll does not re-send the same jobs, even though the API
returns them every time.

See [docs/ENDPOINTS.md](docs/ENDPOINTS.md) for the endpoint map and
[docs/APIFY_NOTES.md](docs/APIFY_NOTES.md) for the Apify research notes.

## Project layout

```
src/jobstreetracer/
  client.py     # HTTP client, retries, throttling
  parsing.py    # search-item + detail-page parsing
  store.py      # SQLite dedupe and run history
  notify.py     # Telegram formatting + delivery
  runner.py     # one scrape run
  scheduler.py  # APScheduler cron loop
  publish.py    # JSON feed for the PWA
  bridge.py     # localhost feed/refresh/Telegram bridge
  cli.py        # command line
web/            # Vite + React + TypeScript PWA (GitHub Pages)
tests/          # offline unit tests
research/       # apify-client store/pricing probe
deploy/         # systemd units, crontab, PWA bridge autostart
docs/           # endpoint notes + PWA guide
.github/        # CI (ruff + pytest + PWA build) and Pages deploy
```

## Develop and deploy the PWA

```bash
cd web
npm install
npm run dev      # http://127.0.0.1:5173/jobstreetracer/
npm run build    # static output in web/dist
```

The Pages workflow (`.github/workflows/pages.yml`) builds `web/` and deploys it
with the official Pages actions. The repository is public and Pages is enabled
with **Source: GitHub Actions**. The app is built with base
`/jobstreetracer/`, so keep the repository name or update `vite.config.ts` and the
manifest/`index.html` paths together.

See [`web/README.md`](web/README.md) for the frontend quick start and
[`docs/PWA.md`](docs/PWA.md) for the full PWA guide.


## Limits and etiquette

- Default delay is 1 request/second. Do not lower it aggressively.
- 15-minute polling is about 96 runs/day. With a small result set that is roughly
  96 search requests/day, plus detail fetches only when a new job appears. That
  is far below what a browser session generates.
- No published rate limit is known and no `429` has been observed. The practical
  risk is Cloudflare bot detection, not a quota. The client rotates browser
  fingerprints, backs off on `403`/`429`/`5xx`, and cron uses `flock` to prevent
  overlapping runs.
- Each additional `[[search]]` adds roughly 96 search requests/day at this
  interval; keep the 1-second delay if you add many.
- The API page size cap observed is 100; this project caps at 100.
- Cloudflare may challenge non-browser TLS fingerprints. The client uses
  `curl_cffi` browser impersonation, which is why plain `curl`/`requests` gets
  a 403 while this works.
- If JobStreet changes its markup or query parameters, update
  `docs/ENDPOINTS.md` and the selectors in `parsing.py`.
- JobStreet may rate-limit or block; back off rather than retrying harder.

## License

MIT © 2026 JobStreetracer contributors. See [LICENSE](LICENSE).

This is an unofficial personal project, not affiliated with JobStreet or SEEK.
JobStreet data remains subject to JobStreet's terms; do not republish it.

