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


def test_send_jobs_partial_failure_reports_delivered_ids(monkeypatch) -> None:
    """When chat 222 rejects the first message (after chat 111 got it), the ids
    for that message must appear in sent_ids so the runner marks them notified
    and the next run doesn't re-send them to chat 111."""
    notifier = TelegramNotifier("token", ["111", "222"])

    def fake_send(text: str, *, chat_id: str, retry: bool = True) -> None:
        if chat_id == "222" and "Job A" in text:
            raise NotificationError("recipient blocked the bot")

    monkeypatch.setattr(notifier, "_send_message", fake_send)
    monkeypatch.setattr("jobstreetracer.notify.time.sleep", lambda _: None)

    # Force one message per job so msg1 (Job A) fails only on chat 222
    # after chat 111 already received it.
    import jobstreetracer.notify as notify_mod

    def split_messages(jobs, **kwargs):
        return [(f"<b>msg</b>\n<b>{job.title}</b>", [job.id]) for job in jobs]

    monkeypatch.setattr(notify_mod, "build_messages", split_messages)

    job1 = make_job("A", title="Job A")
    job2 = make_job("B", title="Job B")
    with pytest.raises(NotificationError) as exc_info:
        notifier.send_jobs([job1, job2])
    assert exc_info.value.sent_ids == ["A"]


def test_build_messages_truncation_produces_valid_html() -> None:
    """Truncated blocks must stay parseable Telegram HTML: no cut tag/entity."""
    from html.parser import HTMLParser

    class TagChecker(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=False)
            self.stack: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag not in ("br", "img"):
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()

    jobs = [make_job("1", "X" * 400), make_job("2", "Y" * 400)]
    messages = build_messages(jobs, max_chars=300)
    assert all(len(text) <= 300 for text, _ in messages)
    for text, _ in messages:
        checker = TagChecker()
        checker.feed(text)
        assert checker.stack == [], f"unbalanced tags in {text!r}"
        # entity-safe: no dangling '&' fragment
        import re

        assert not re.search(r"&(?!amp;|lt;|gt;|quot;|#\d+;)", text)


def test_send_jobs_does_not_mark_on_partial_failure(monkeypatch) -> None:
    notifier = TelegramNotifier("token", ["111", "222"])

    def fake_send(text: str, *, chat_id: str, retry: bool = True) -> None:
        raise NotificationError("recipient blocked the bot")

    monkeypatch.setattr(notifier, "_send_message", fake_send)
    monkeypatch.setattr("jobstreetracer.notify.time.sleep", lambda _: None)

    with pytest.raises(NotificationError) as exc_info:
        notifier.send_jobs([make_job("1")])
    # Chat 111 may have received it before the failure on 222; over-marking
    # is preferred over re-sending duplicates, so the message's ids are
    # included regardless of which chat failed.
    assert exc_info.value.sent_ids == ["1"]


def test_build_messages_large_single_job_respects_max_chars() -> None:
    jobs = [make_job("1", "First"), make_job("2", "A" * 5000)]
    messages = build_messages(jobs, max_chars=300)

    assert all(len(text) <= 300 for text, _ in messages)
    ids = [job_id for _, job_ids in messages for job_id in job_ids]
    assert ids == ["1", "2"]
