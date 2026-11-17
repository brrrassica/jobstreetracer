# JobStreetracer PWA

Vite + React + TypeScript frontend for the JobStreetracer dashboard. It is an
installable offline-first PWA deployed to GitHub Pages at
<https://brrrassica.github.io/jobstreetracer/>.

The full design, feed schema, bridge API, storage layout, notification limits and
troubleshooting guide live in [`../docs/PWA.md`](../docs/PWA.md).

## Quick start

```bash
npm install
npm run dev      # http://127.0.0.1:5173/jobstreetracer/
```

For live local data, start the Python bridge from the repository root:

```bash
.venv/bin/jobstreetracer bridge --static web/dist --open
```

## Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server (base path `/jobstreetracer/`) |
| `npm test` | Vitest feed parsing/merge/export tests |
| `npm run build` | Typecheck and emit `dist/` |
| `npm run preview` | Preview the production build |
| `npm run typecheck` | TypeScript only |

## Layout

```
public/
  manifest.webmanifest   # install metadata, icons, shortcuts
  sw.js                  # app-shell cache, offline fallback, notification clicks
  icons/                 # 192/512 + maskable PNGs, favicon
src/
  main.tsx               # React root + service-worker registration
  App.tsx                # routing, sync/polling, notifications, data actions
  db.ts                  # IndexedDB stores and settings
  feed.ts                # feed parsing, merging, TOML/salary/export helpers
  notify.ts              # Notification API + app badge
  telegram.ts            # direct/Bridge Telegram sending
  components/            # Dashboard, Listings, JobDetail, Searches, Settings
  styles.css             # theme and responsive layout
```

## Data and privacy

- Listings, searches, tracking notes and the Telegram token stay in this browser
  profile's IndexedDB. Nothing is sent to GitHub Pages after the app shell loads.
- The app shell is public; do not place private job data, feeds, `.env` or tokens
  in `public/` or anywhere committed.
- The first feed import is a silent baseline; subsequent syncs flag unseen IDs.

## Deploy

Pushing `main` triggers `.github/workflows/pages.yml`, which runs `npm ci`,
`npm run build`, and deploys `dist/` via the official Pages actions. Keep the
Vite base, manifest `start_url`/`scope` and repository name in sync if you rename
the project.
