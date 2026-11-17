"""Telegram notifications."""

from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass, field
from typing import Iterable

from curl_cffi import requests

from .config import parse_chat_ids
from .models import Job

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 3800


class NotificationError(RuntimeError):
    def __init__(self, message: str, sent_ids: list[str] | None = None) -> None:
        super().__init__(message)
        self.sent_ids = sent_ids or []


@dataclass
class NotificationResult:
    sent_ids: list[str] = field(default_factory=list)
    messages: int = 0


def _job_block(job: Job) -> str:
    title = html.escape(job.title or "Untitled job")
    lines = [f"<b>{title}</b>"]
    if job.company:
        lines.append(f"🏢 {html.escape(job.company)}")
    if job.location:
        lines.append(f"📍 {html.escape(job.location)}")
    if job.salary:
        lines.append(f"💰 {html.escape(job.salary)}")
    meta = " · ".join(
        value
        for value in (job.listing_date_display or job.posted_display, job.work_types)
        if value
    )
    if meta:
        lines.append(f"🕒 {html.escape(meta)}")
    if job.url:
        lines.append(f'<a href="{html.escape(job.url, quote=True)}">Open job</a>')
    return "\n".join(lines)


def build_messages(
    jobs: Iterable[Job],
    *,
    header: str | None = None,
    max_chars: int = MAX_MESSAGE_CHARS,
) -> list[tuple[str, list[str]]]:
    """Group jobs into Telegram-sized HTML messages.

    Returns (message_text, job_ids) pairs so callers can mark only delivered jobs.
    """
    job_list = list(jobs)
    if not job_list:
        return []
    header = header or f"<b>JobStreetracer</b> · {len(job_list)} new job(s)"
    messages: list[tuple[str, list[str]]] = []
    current = header
    current_ids: list[str] = []

    for job in job_list:
        block = _job_block(job)
        separator = "\n\n" if current else ""
        if len(current) + len(separator) + len(block) > max_chars and current_ids:
            messages.append((current, current_ids))
            current = "<b>JobStreetracer</b> · continued"
            current_ids = []
            separator = "\n\n"
        if len(block) > max_chars:
            block = block[: max_chars - 20] + "…"
        current += separator + block
        current_ids.append(job.id)

    if current_ids:
        messages.append((current, current_ids))
    return messages


class TelegramNotifier:
    def __init__(
        self,
        token: str = "",
        chat_ids: str | list[str] = "",
        *,
        topic_id: str = "",
        dry_run: bool = False,
        timeout: float = 20.0,
    ) -> None:
        self.token = token.strip()
        if isinstance(chat_ids, str):
            self.chat_ids = parse_chat_ids(chat_ids)
        else:
            self.chat_ids = [str(chat_id).strip() for chat_id in chat_ids if str(chat_id).strip()]
        self.topic_id = topic_id.strip()
        self.dry_run = dry_run
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_ids)

    def send_jobs(self, jobs: list[Job], *, header: str | None = None) -> NotificationResult:
        if not jobs:
            return NotificationResult()
        if self.dry_run:
            for message, _ in build_messages(jobs, header=header):
                print(message)
                print()
            return NotificationResult(
                sent_ids=[job.id for job in jobs], messages=1
            )
        if not self.configured:
            raise NotificationError(
                "Telegram is not configured: set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID (or TELEGRAM_CHAT_IDS) in .env"
            )

        result = NotificationResult()
        for message, ids in build_messages(jobs, header=header):
            for chat_id in self.chat_ids:
                try:
                    self._send_message(message, chat_id=chat_id)
                except NotificationError as exc:
                    raise NotificationError(str(exc), sent_ids=result.sent_ids) from exc
            result.sent_ids.extend(ids)
            result.messages += 1
            time.sleep(0.4)
        return result

    def _send_message(self, text: str, *, chat_id: str, retry: bool = True) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if self.topic_id:
            payload["message_thread_id"] = int(self.topic_id)
        try:
            response = requests.post(
                f"{TELEGRAM_API}/bot{self.token}/sendMessage",
                json=payload,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise NotificationError(
                f"Telegram request failed for chat {chat_id}: {exc}"
            ) from exc

        if response.status_code == 429 and retry:
            try:
                retry_after = int(response.json().get("parameters", {}).get("retry_after", 3))
            except Exception:
                retry_after = 3
            time.sleep(min(retry_after, 30))
            return self._send_message(text, chat_id=chat_id, retry=False)

        if response.status_code >= 400:
            description = response.text[:300]
            try:
                description = response.json().get("description", description)
            except Exception:
                pass
            raise NotificationError(
                f"Telegram rejected the message for chat {chat_id}: {description}"
            )

    def get_me(self) -> dict:
        response = requests.get(
            f"{TELEGRAM_API}/bot{self.token}/getMe", timeout=self.timeout
        )
        if response.status_code >= 400:
            raise NotificationError(f"getMe failed: HTTP {response.status_code}")
        return response.json().get("result", {})

    def get_chat(self, chat_id: str) -> dict:
        response = requests.get(
            f"{TELEGRAM_API}/bot{self.token}/getChat",
            params={"chat_id": chat_id},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            description = response.text[:200]
            try:
                description = response.json().get("description", description)
            except Exception:
                pass
            raise NotificationError(
                f"getChat failed for {chat_id}: {description}"
            )
        return response.json().get("result", {})
