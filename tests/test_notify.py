from __future__ import annotations

import pytest

from jobstreetracer.models import Job
from jobstreetracer.notify import NotificationError, TelegramNotifier, build_messages


def make_job(job_id: str, title: str = "Data Engineer") -> Job:
    return Job(
        id=job_id,
        title=title,
        company="Acme & Sons",
        location="Jakarta",
        salary="Rp 10.000.000",
        listing_date_display="4d ago",
        work_types="Full time",
        url=f"https://id.jobstreet.com/id/job/{job_id}",
    )


def test_build_messages_chunks_and_covers_all_jobs() -> None:
    jobs = [make_job(str(i), f"Job {i}") for i in range(80)]
    messages = build_messages(jobs, max_chars=1200)
    assert len(messages) > 1
    assert all(len(text) <= 1200 for text, _ in messages)
    ids = [job_id for _, job_ids in messages for job_id in job_ids]
    assert ids == [str(i) for i in range(80)]


def test_build_messages_escapes_html_and_links() -> None:
    job = make_job("1", title="<Data> & Engineer")
    job.company = "A < B"
    messages = build_messages([job])
    text, ids = messages[0]
    assert ids == ["1"]
    assert "&lt;Data&gt; &amp; Engineer" in text
    assert "A &lt; B" in text
    assert 'href="https://id.jobstreet.com/id/job/1"' in text


def test_build_messages_empty() -> None:
    assert build_messages([]) == []


def test_send_jobs_fans_out_to_every_chat(monkeypatch) -> None:
    notifier = TelegramNotifier("token", ["111", "222"])
    calls: list[str] = []

    def fake_send(text: str, *, chat_id: str, retry: bool = True) -> None:
        calls.append(chat_id)

    monkeypatch.setattr(notifier, "_send_message", fake_send)
    monkeypatch.setattr("jobstreetracer.notify.time.sleep", lambda _: None)

    result = notifier.send_jobs([make_job("1")])
    assert calls == ["111", "222"]
    assert result.sent_ids == ["1"]
    assert result.messages == 1


def test_send_jobs_does_not_mark_on_partial_failure(monkeypatch) -> None:
    notifier = TelegramNotifier("token", ["111", "222"])

    def fake_send(text: str, *, chat_id: str, retry: bool = True) -> None:
        if chat_id == "222":
            raise NotificationError("recipient blocked the bot")

    monkeypatch.setattr(notifier, "_send_message", fake_send)
    monkeypatch.setattr("jobstreetracer.notify.time.sleep", lambda _: None)

    with pytest.raises(NotificationError) as exc_info:
        notifier.send_jobs([make_job("1")])
    assert exc_info.value.sent_ids == []
