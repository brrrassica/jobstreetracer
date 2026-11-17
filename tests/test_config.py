from __future__ import annotations

from jobstreetracer.config import load_config


def test_load_config_resolves_paths_and_search(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[app]
output_dir = "out"
db_path = "state/jobs.db"
delay_seconds = 0
notify_max_jobs = 5

[[search]]
name = "test"
keywords = "data engineer"
where = "Jakarta"
max_pages = 2
daterange = 7
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("JOBSTREETRACER_DB", raising=False)
    monkeypatch.delenv("JOBSTREETRACER_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    config = load_config(cfg)
    assert config.path == cfg.resolve()
    assert config.output_dir == (tmp_path / "out").resolve()
    assert config.db_path == (tmp_path / "state/jobs.db").resolve()
    assert config.delay_seconds == 0
    assert len(config.searches) == 1
    search = config.searches[0]
    assert search.name == "test"
    assert search.daterange == 7
    assert search.max_pages == 2
    assert search.sort == "Relevance"
    assert config.telegram_enabled is False
    assert config.telegram_chat_ids == []


def test_env_overrides_db(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[app]
db_path = "state/jobs.db"
[[search]]
keywords = "python"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JOBSTREETRACER_DB", "override/jobs.db")
    config = load_config(cfg)
    assert config.db_path == (tmp_path / "override/jobs.db").resolve()
    assert config.searches[0].name == "python"


def test_multiple_telegram_chat_ids(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[[search]]
keywords = "python"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_CHAT_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111, 222;333")
    config = load_config(cfg)
    assert config.telegram_chat_ids == ["111", "222", "333"]
    assert config.telegram_enabled is False  # no token set
