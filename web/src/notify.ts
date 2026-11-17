import type { Job } from "./types";

const BASE = import.meta.env.BASE_URL;

export function notificationsSupported(): boolean {
  return typeof Notification !== "undefined";
}

export function permissionState(): NotificationPermission | "unsupported" {
  if (!notificationsSupported()) return "unsupported";
  return Notification.permission;
}

export async function requestNotificationPermission(): Promise<NotificationPermission | "unsupported"> {
  if (!notificationsSupported()) return "unsupported";
  if (Notification.permission === "granted") return "granted";
  return Notification.requestPermission();
}

export async function showNewJobsNotification(jobs: Job[], maxItems = 5): Promise<void> {
  if (jobs.length === 0 || !notificationsSupported()) return;
  if (Notification.permission !== "granted") return;
  const shown = jobs.slice(0, maxItems);
  const more = jobs.length - shown.length;
  const lines = shown.map((job) => {
    const meta = [job.company, job.location].filter(Boolean).join(" · ");
    return meta ? `${job.title} — ${meta}` : job.title;
  });
  const body = lines.join("\n") + (more > 0 ? `\n…and ${more} more` : "");
  const registration = await navigator.serviceWorker?.ready.catch(() => null);
  if (registration) {
    await registration.showNotification(
      jobs.length === 1 ? "New job match" : `${jobs.length} new job matches`,
      {
        body,
        icon: `${BASE}icons/icon-192.png`,
        badge: `${BASE}icons/icon-192.png`,
        tag: "jobstreetracer-new-jobs",
        data: { url: `${BASE}#/listings?new=1` },
      },
    );
  } else {
    new Notification(`${jobs.length} new job matches`, {
      body,
      icon: `${BASE}icons/icon-192.png`,
    });
  }
}

export async function updateAppBadge(count: number): Promise<void> {
  const nav = navigator as Navigator & {
    setAppBadge?: (value?: number) => Promise<void>;
    clearAppBadge?: () => Promise<void>;
  };
  try {
    if (count > 0) await nav.setAppBadge?.(count);
    else await nav.clearAppBadge?.();
  } catch {
    // Badging is best-effort and unsupported in some contexts.
  }
}
