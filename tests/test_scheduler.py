from __future__ import annotations

from types import SimpleNamespace

from jobstreetracer import scheduler
from jobstreetracer.scheduler import build_scheduler, build_trigger, run_tick, serve


def write_config(tmp_path, *, schedule="*/15 * * * *", timezone="Asia/Jakarta"):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""
[app]
schedule = "{schedule}"
timezone = "{timezone}"

[[search]]
name = "test"
keywords = "python"
""",
        encoding="utf-8",
    )
    return cfg


class FakeScheduler:
    def __init__(self, timezone=None):
        self.timezone = timezone
        self.jobs = []
        self.started = False
        self.start_exc = None

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append((func, trigger, kwargs))

    def start(self):
        self.started = True
        if self.start_exc is not None:
            raise self.start_exc


def test_build_trigger_parses_crontab(tmp_path) -> None:
    trigger = build_trigger("*/15 * * * *", "UTC")
    # APScheduler computes a concrete next-fire time for a valid expression.
    assert trigger is not None


def test_run_tick_success_calls_summary(tmp_path, monkeypatch) -> None:
    summary = SimpleNamespace(scanned=3, new_jobs=1, notified=1, errors=0)
    seen = {}

    def fake_run_once(config_path):
        seen["config_path"] = config_path
        return summary

    monkeypatch.setattr(scheduler, "run_once", fake_run_once)

    results = []
    ok = run_tick("cfg.toml", on_summary=results.append)

    assert ok is True
    assert seen["config_path"] == "cfg.toml"
    assert results == [summary]


def test_run_tick_swallows_exception(tmp_path, monkeypatch) -> None:
    def boom(config_path):
        raise RuntimeError("network down")

    monkeypatch.setattr(scheduler, "run_once", boom)

    called = []
    ok = run_tick("cfg.toml", on_summary=called.append)

    # A failing cycle must not raise (it would kill the blocking scheduler)
    assert ok is False
    assert called == []


def test_build_scheduler_uses_config_defaults(tmp_path, monkeypatch) -> None:
    cfg = write_config(tmp_path, schedule="0 * * * *", timezone="Asia/Jakarta")
    monkeypatch.setattr(scheduler, "BlockingScheduler", FakeScheduler)

    sched = build_scheduler(cfg)

    assert sched.timezone == "Asia/Jakarta"
    assert len(sched.jobs) == 1
    func, trigger, kwargs = sched.jobs[0]
    assert kwargs["id"] == scheduler.JOB_ID
    assert kwargs["coalesce"] is True
    # The job body is a callable closure, not run at build time.
    assert callable(func)


def test_build_scheduler_overrides(tmp_path, monkeypatch) -> None:
    cfg = write_config(tmp_path, schedule="0 * * * *", timezone="Asia/Jakarta")
    monkeypatch.setattr(scheduler, "BlockingScheduler", FakeScheduler)

    sched = build_scheduler(cfg, cron="*/5 * * * *", timezone="UTC")

    assert sched.timezone == "UTC"


def test_build_scheduler_job_runs_tick(tmp_path, monkeypatch) -> None:
    cfg = write_config(tmp_path)
    monkeypatch.setattr(scheduler, "BlockingScheduler", FakeScheduler)
    ticks = []
    monkeypatch.setattr(
        scheduler, "run_tick", lambda config_path: ticks.append(config_path) or True
    )

    sched = build_scheduler(cfg)
    func, _trigger, _kwargs = sched.jobs[0]
    func()

    assert ticks == [cfg]


def test_serve_run_now_ticks_before_start(tmp_path, monkeypatch) -> None:
    cfg = write_config(tmp_path)
    ticks = []
    monkeypatch.setattr(scheduler, "run_tick", lambda cp: ticks.append(cp) or True)
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "build_scheduler", lambda *a, **k: fake)

    serve(cfg, run_now=True)

    assert ticks == [cfg]
    assert fake.started is True


def test_serve_without_run_now_does_not_tick(tmp_path, monkeypatch) -> None:
    cfg = write_config(tmp_path)
    ticks = []
    monkeypatch.setattr(scheduler, "run_tick", lambda cp: ticks.append(cp) or True)
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "build_scheduler", lambda *a, **k: fake)

    serve(cfg)

    assert ticks == []
    assert fake.started is True


def test_serve_swallows_keyboard_interrupt(tmp_path, monkeypatch) -> None:
    cfg = write_config(tmp_path)
    monkeypatch.setattr(scheduler, "run_tick", lambda cp: True)
    fake = FakeScheduler()
    fake.start_exc = KeyboardInterrupt
    monkeypatch.setattr(scheduler, "build_scheduler", lambda *a, **k: fake)

    # Should return cleanly rather than propagate the interrupt.
    serve(cfg)

    assert fake.started is True
