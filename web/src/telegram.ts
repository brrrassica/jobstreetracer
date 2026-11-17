import type { Job, TelegramSettings } from "./types";

export interface TelegramResult {
  delivered: string[];
  errors: { chat_id: string; error: string }[];
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function parseChatIds(value: string): string[] {
  return value
    .split(/[,;\s]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function buildJobMessage(jobs: Job[], header?: string): string {
  const lines = [header ?? `<b>JobStreetracer</b> · ${jobs.length} job(s)`, ""];
  for (const job of jobs) {
    lines.push(`<b>${escapeHtml(job.title)}</b>`);
    if (job.company) lines.push(`🏢 ${escapeHtml(job.company)}`);
    if (job.location) lines.push(`📍 ${escapeHtml(job.location)}`);
    if (job.salary) lines.push(`💰 ${escapeHtml(job.salary)}`);
    const meta = [job.listingDateDisplay || job.postedDisplay, job.workTypes].filter(Boolean).join(" · ");
    if (meta) lines.push(`🕒 ${escapeHtml(meta)}`);
    if (job.url) lines.push(`<a href="${escapeHtml(job.url)}">Open job</a>`);
    lines.push("");
  }
  return lines.join("\n").trim();
}

function bridgeBase(bridgeUrl: string): string {
  return bridgeUrl.trim().replace(/\/+$/, "");
}

export async function sendTelegram(
  telegram: TelegramSettings,
  text: string,
  bridgeUrl = "",
): Promise<TelegramResult> {
  const token = telegram.token.trim();
  const chatIds = parseChatIds(telegram.chatIds);
  if (!token) throw new Error("Telegram bot token is empty.");
  if (chatIds.length === 0) throw new Error("Add at least one Telegram chat id.");
  if (!text.trim()) throw new Error("Message text is empty.");

  if (bridgeBase(bridgeUrl)) {
    const response = await fetch(`${bridgeBase(bridgeUrl)}/api/telegram`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-JSR-Bridge": "1" },
      body: JSON.stringify({
        token,
        chat_ids: chatIds,
        topic_id: telegram.topicId.trim(),
        text,
      }),
    });
    const data = (await response.json().catch(() => ({}))) as Partial<TelegramResult> & {
      error?: string;
    };
    if (!response.ok && !data.errors) {
      throw new Error(data.error || `Bridge returned HTTP ${response.status}.`);
    }
    return {
      delivered: data.delivered ?? [],
      errors: data.errors ?? (data.error ? [{ chat_id: "bridge", error: data.error }] : []),
    };
  }

  const delivered: string[] = [];
  const errors: TelegramResult["errors"] = [];
  for (const chatId of chatIds) {
    try {
      const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          text,
          parse_mode: "HTML",
          disable_web_page_preview: true,
          ...(telegram.topicId.trim() ? { message_thread_id: Number(telegram.topicId.trim()) } : {}),
        }),
      });
      const data = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        description?: string;
      };
      if (response.ok && data.ok) delivered.push(chatId);
      else errors.push({ chat_id: chatId, error: data.description || `HTTP ${response.status}` });
    } catch (error) {
      errors.push({
        chat_id: chatId,
        error:
          error instanceof Error
            ? `${error.message} (browsers usually block direct Telegram calls via CORS; set a Bridge URL)`
            : String(error),
      });
    }
  }
  return { delivered, errors };
}
