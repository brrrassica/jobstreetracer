"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from rich.console import Console
from rich.table import Table

from . import __version__
from .client import JobStreetClient
from .config import ConfigError, load_config, write_default_config
from .models import Job
from .notify import TelegramNotifier
from .runner import run_once
from .scheduler import serve
from .store import JobStore

console = Console()
log = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def _config_or_defaults(path: str | None):
    """Load config for ad-hoc commands, falling back to built-in defaults."""
    try:
        return load_config(path)
    except ConfigError:
        if path:
            raise
        return None


def _client_from_config(config) -> JobStreetClient:
    if config is None:
        return JobStreetClient(delay_seconds=1.0)
    return JobStreetClient(
        locale=config.locale,
        site_key=config.site_key,
        delay_seconds=config.delay_seconds,
        timeout=config.timeout_seconds,
    )


def _print_jobs_table(jobs: list[Job]) -> None:
    table = Table(title=f"JobStreetracer — {len(jobs)} job(s)", show_lines=False)
    table.add_column("Title", overflow="fold", max_width=45)
    table.add_column("Company", overflow="fold", max_width=28)
    table.add_column("Location", overflow="fold", max_width=24)
    table.add_column("Salary", overflow="fold", max_width=24)
    table.add_column("Posted", max_width=10)
    table.add_column("ID", style="dim")
    for job in jobs:
        table.add_row(
            job.title,
            job.company,
            job.location,
            job.salary,
            job.listing_date_display or job.posted_display,
            job.id,
        )
    console.print(table)


def cmd_init(args: argparse.Namespace) -> int:
    target = write_default_config(args.config, force=args.force)
    console.print(f"[green]Created[/green] {target}")
    env_path = target.parent / ".env"
    example = target.parent / ".env.example"
    if example.exists() and not env_path.exists():
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        console.print(f"[green]Created[/green] {env_path}")
    console.print(
        "\nNext:\n"
        "  1. Edit the search blocks in the config.\n"
        "  2. Put your Telegram bot token and chat id in .env.\n"
        "  3. Run: jobstreetracer run --dry-run\n"
        "  4. Schedule: jobstreetracer schedule   (or use cron/systemd)"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose)
    summary = run_once(
        args.config,
        search_names=args.search or None,
        max_pages=args.max_pages,
        no_enrich=args.no_enrich,
        no_notify=args.no_notify,
        dry_run=args.dry_run,
        notify_first_run=True if args.notify_first_run else None,
    )
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
        return 1 if summary.errors else 0

    table = Table(title="JobStreetracer run")
    table.add_column("Search")
    table.add_column("Scanned", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Seeded", justify="right")
    table.add_column("Enriched", justify="right")
    table.add_column("Errors", justify="right")
    for item in summary.searches:
        table.add_row(
            item.name,
            str(item.scanned),
            str(item.new),
            str(item.seeded),
            str(item.enriched),
            str(item.errors),
        )
    console.print(table)
    console.print(
        f"Scanned [bold]{summary.scanned}[/bold], new [bold green]{summary.new_jobs}[/bold green], "
        f"seeded [bold]{sum(item.seeded for item in summary.searches)}[/bold], "
        f"notified [bold]{summary.notified}[/bold], errors [bold]{summary.errors}[/bold]"
    )
    for path in summary.snapshots:
        console.print(f"Snapshot: {path}")
    return 1 if summary.errors else 0


def cmd_schedule(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose)
    serve(
        args.config,
        cron=args.cron,
        timezone=args.timezone,
        run_now=args.run_now,
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose)
    config = _config_or_defaults(args.config)
    client = _client_from_config(config)
    if args.delay is not None:
        client.delay_seconds = max(0.0, args.delay)

    jobs: dict[str, Job] = {}
    pages = args.pages if args.pages else 1
    for page in client.iter_search(
        args.keywords,
        where=args.where or None,
        page_size=args.page_size,
        sort=args.sort or None,
        daterange=args.daterange,
        max_pages=pages,
        max_jobs=args.limit,
    ):
        for job in page.jobs:
            jobs[job.id] = job

    result = list(jobs.values())
    if args.details:
        enriched: list[Job] = []
        for job in result[: args.details]:
            try:
                enriched.append(client.get_detail(job))
                log.info("enriched %s", job.id)
            except Exception as exc:
                log.warning("detail failed for %s: %s", job.id, exc)
                enriched.append(job)
        result[0 : min(args.details, len(result))] = enriched

    if args.json:
        print(json.dumps([job.to_dict(include_raw=False) for job in result], indent=2))
    else:
        _print_jobs_table(result)
        if args.details and result and result[0].description_text:
            console.rule(result[0].title)
            console.print(result[0].description_text[:3000])
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store = JobStore(config.db_path)
    try:
        jobs = store.recent_jobs(args.limit, only_new=args.new)
    finally:
        store.close()
    if args.json:
        print(json.dumps([job.to_dict(include_raw=False) for job in jobs], indent=2))
    else:
        _print_jobs_table(jobs)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store = JobStore(config.db_path)
    try:
        stats = store.stats()
    finally:
        store.close()
    if args.json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        console.print_json(data=stats)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store = JobStore(config.db_path)
    try:
        count = store.export(args.out, fmt=args.format, only_new=args.new_only)
    finally:
        store.close()
    console.print(f"Exported {count} job(s) to {args.out}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose)
    ok = True
    console.print(f"JobStreetracer {__version__}")

    config = _config_or_defaults(args.config)
    if config is None:
        console.print("[yellow]![/yellow] No config.toml found (run: jobstreetracer init)")
        ok = False
    else:
        console.print(f"[green]✓[/green] Config {config.path}")
        console.print(f"  DB: {config.db_path}")
        console.print(f"  Searches: {', '.join(s.name for s in config.searches if s.enabled)}")
        if config.telegram_enabled:
            notifier = TelegramNotifier(
                config.telegram_bot_token, config.telegram_chat_ids
            )
            try:
                me = notifier.get_me()
                console.print(f"[green]✓[/green] Telegram bot @{me.get('username', '?')}")
            except Exception as exc:
                console.print(f"[red]✗[/red] Telegram bot: {exc}")
                ok = False
            for chat_id in config.telegram_chat_ids:
                try:
                    chat = notifier.get_chat(chat_id)
                    name = (
                        chat.get("title")
                        or " ".join(
                            part
                            for part in (chat.get("first_name"), chat.get("last_name"))
                            if part
                        )
                        or chat.get("username")
                        or chat_id
                    )
                    console.print(f"[green]✓[/green] Telegram recipient {chat_id} ({name})")
                except Exception as exc:
                    console.print(f"[red]✗[/red] Telegram recipient {chat_id}: {exc}")
                    ok = False
        else:
            console.print(
                "[yellow]![/yellow] Telegram not configured "
                "(set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"
            )

    try:
        client = _client_from_config(config)
        client.max_retries = 2
        client.delay_seconds = 0
        page = client.search("", page_size=1)
        console.print(f"[green]✓[/green] JobStreet API reachable ({page.total_count:,} total jobs)")
    except Exception as exc:
        console.print(f"[red]✗[/red] JobStreet API: {exc}")
        ok = False

    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobstreetracer",
        description="JobStreet Indonesia scraper with SQLite dedupe and Telegram alerts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", "-c", default=None, help="path to config.toml")
    common.add_argument("-v", "--verbose", action="store_true")

    init = sub.add_parser("init", help="create a starter config.toml")
    init.add_argument("--config", "-c", default="config.toml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    run = sub.add_parser("run", help="scrape once, store, and notify", parents=[common])
    run.add_argument("--search", action="append", help="only run this search (repeatable)")
    run.add_argument("--max-pages", type=int, default=None)
    run.add_argument("--no-enrich", action="store_true", help="skip job detail pages")
    run.add_argument("--no-notify", action="store_true", help="do not send Telegram messages")
    run.add_argument("--dry-run", action="store_true", help="print alerts instead of sending")
    run.add_argument(
        "--notify-first-run",
        action="store_true",
        help="alert on the first run's existing backlog instead of seeding silently",
    )
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    schedule = sub.add_parser(
        "schedule", help="run forever on a cron expression", parents=[common]
    )
    schedule.add_argument("--cron", default=None, help='e.g. "*/15 * * * *"')
    schedule.add_argument("--timezone", default=None, help="e.g. Asia/Jakarta")
    schedule.add_argument("--run-now", action="store_true", help="run once before scheduling")
    schedule.set_defaults(func=cmd_schedule)

    search = sub.add_parser("search", help="ad-hoc search, printed to stdout", parents=[common])
    search.add_argument("keywords", nargs="?", default="")
    search.add_argument("--where", default="")
    search.add_argument("--pages", type=int, default=1)
    search.add_argument("--page-size", type=int, default=30)
    search.add_argument("--sort", default="Relevance")
    search.add_argument("--daterange", type=int, default=None)
    search.add_argument("--limit", type=int, default=0)
    search.add_argument("--details", type=int, default=0, help="enrich first N jobs")
    search.add_argument("--delay", type=float, default=None)
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_search)

    jobs = sub.add_parser("jobs", help="list jobs from the local database", parents=[common])
    jobs.add_argument("--limit", type=int, default=20)
    jobs.add_argument("--new", action="store_true", help="only jobs not yet notified")
    jobs.add_argument("--json", action="store_true")
    jobs.set_defaults(func=cmd_jobs)

    stats = sub.add_parser("stats", help="database stats", parents=[common])
    stats.add_argument("--json", action="store_true")
    stats.set_defaults(func=cmd_stats)

    export = sub.add_parser("export", help="export stored jobs", parents=[common])
    export.add_argument("--out", default="data/export.jsonl")
    export.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    export.add_argument("--new-only", action="store_true")
    export.set_defaults(func=cmd_export)

    doctor = sub.add_parser("doctor", help="check config, API, and Telegram", parents=[common])
    doctor.set_defaults(func=cmd_doctor)

    return parser


def cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 2
    except KeyboardInterrupt:
        console.print("Interrupted")
        return 130


def main() -> None:
    raise SystemExit(cli())
