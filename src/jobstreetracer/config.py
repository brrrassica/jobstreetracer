"""Configuration loading (TOML + environment overrides)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_CONFIG_NAME = "config.toml"

CONFIG_TEMPLATE = """\
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
notify_on_first_run = false

[[search]]
name = "data-engineer-jakarta"
keywords = '"data engineer"'   # quotes = exact phrase (much less noise)
where = "Jakarta"
sort = "Relevance"
daterange = 14
page_size = 30
max_pages = 3
enrich = true
enabled = true
"""


class ConfigError(RuntimeError):
    pass


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "search"


def parse_chat_ids(value: str) -> list[str]:
    """Accept one id or a comma/semicolon/whitespace separated list."""
    return [part for part in re.split(r"[,;\s]+", value or "") if part]


@dataclass
class SearchConfig:
    name: str
    keywords: str
    where: str = ""
    sort: str = "Relevance"
    daterange: int | None = None
    worktype: str = ""
    page_size: int = 30
    max_pages: int = 3
    max_jobs: int = 0
    enrich: bool = True
    enabled: bool = True
    notify_on_first_run: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, default_enrich: bool = True,
                  default_notify_first_run: bool = False) -> "SearchConfig":
        keywords = str(data.get("keywords") or "").strip()
        where = str(data.get("where") or "").strip()
        name = str(data.get("name") or "").strip() or _slug(f"{keywords}-{where}")
        daterange = data.get("daterange")
        return cls(
            name=name,
            keywords=keywords,
            where=where,
            sort=str(data.get("sort") or "Relevance"),
            daterange=int(daterange) if daterange not in (None, "", 0) else None,
            worktype=str(data.get("worktype") or "").strip(),
            page_size=max(1, min(int(data.get("page_size") or 30), 100)),
            max_pages=max(1, int(data.get("max_pages") or 3)),
            max_jobs=max(0, int(data.get("max_jobs") or 0)),
            enrich=bool(data.get("enrich", default_enrich)),
            enabled=bool(data.get("enabled", True)),
            notify_on_first_run=bool(
                data.get("notify_on_first_run", default_notify_first_run)
            ),
        )


@dataclass
class AppConfig:
    path: Path
    searches: list[SearchConfig] = field(default_factory=list)
    locale: str = "en-ID"
    site_key: str = "ID-Main"
    delay_seconds: float = 1.0
    timeout_seconds: float = 30.0
    enrich_details: bool = True
    output_dir: Path = Path("data")
    db_path: Path = Path("data/jobs.db")
    notify_max_jobs: int = 40
    schedule: str = "*/15 * * * *"
    timezone: str = "Asia/Jakarta"
    notify_on_first_run: bool = False
    telegram_bot_token: str = ""
    telegram_chat_ids: list[str] = field(default_factory=list)
    telegram_topic_id: str = ""

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_ids)


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_config(path: str | Path | None = None) -> AppConfig:
    configured = path or os.environ.get("JOBSTREETRACER_CONFIG") or DEFAULT_CONFIG_NAME
    config_path = Path(configured).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(
            f"config not found: {config_path}\n"
            "Run `jobstreetracer init` to create one, or copy config.example.toml."
        )

    load_dotenv(config_path.parent / ".env", override=False)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    app = data.get("app") or {}
    if not isinstance(app, dict):
        raise ConfigError("[app] must be a table")

    default_enrich = bool(app.get("enrich_details", True))
    default_notify_first_run = bool(app.get("notify_on_first_run", False))
    raw_searches = data.get("search", data.get("searches", []))
    if isinstance(raw_searches, dict):
        raw_searches = [raw_searches]
    if not isinstance(raw_searches, list):
        raise ConfigError("[[search]] must be an array of tables")

    searches = [
        SearchConfig.from_dict(
            item,
            default_enrich=default_enrich,
            default_notify_first_run=default_notify_first_run,
        )
        for item in raw_searches
        if isinstance(item, dict)
    ]
    if not searches:
        raise ConfigError("no [[search]] blocks found in config")

    base = config_path.parent
    output_dir = _resolve(
        base, os.environ.get("JOBSTREETRACER_OUTPUT_DIR") or app.get("output_dir", "data")
    )
    db_path = _resolve(
        base, os.environ.get("JOBSTREETRACER_DB") or app.get("db_path", output_dir / "jobs.db")
    )

    delay = os.environ.get("JOBSTREETRACER_DELAY") or app.get("delay_seconds", 1.0)
    raw_chat_ids = (
        os.environ.get("TELEGRAM_CHAT_IDS")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or ""
    )
    return AppConfig(
        path=config_path,
        searches=searches,
        locale=str(app.get("locale") or "en-ID"),
        site_key=str(app.get("site_key") or "ID-Main"),
        delay_seconds=max(0.0, float(delay)),
        timeout_seconds=max(1.0, float(app.get("timeout_seconds", 30))),
        enrich_details=default_enrich,
        output_dir=output_dir,
        db_path=db_path,
        notify_max_jobs=max(1, int(app.get("notify_max_jobs", 40))),
        schedule=os.environ.get("JOBSTREETRACER_SCHEDULE")
        or str(app.get("schedule") or "*/15 * * * *"),
        timezone=os.environ.get("JOBSTREETRACER_TIMEZONE")
        or str(app.get("timezone") or "Asia/Jakarta"),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_ids=parse_chat_ids(raw_chat_ids),
        telegram_topic_id=os.environ.get("TELEGRAM_TOPIC_ID", "").strip(),
    )


def write_default_config(path: str | Path, *, force: bool = False) -> Path:
    target = Path(path).expanduser().resolve()
    if target.exists() and not force:
        raise ConfigError(f"refusing to overwrite existing {target} (use --force)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    return target
