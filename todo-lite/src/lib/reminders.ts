import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from "@tauri-apps/plugin-notification";
import { getDb } from "./db";
import { toDateTimeStr } from "./repeat";

const NOTIFIED_KEY = "todo-lite:notified-reminders";

function loadNotified(): Set<number> {
  try {
    const raw = localStorage.getItem(NOTIFIED_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as number[];
    return new Set(arr.slice(-200));
  } catch {
    return new Set();
  }
}

function saveNotified(s: Set<number>): void {
  localStorage.setItem(NOTIFIED_KEY, JSON.stringify(Array.from(s).slice(-200)));
}

export async function checkReminders(): Promise<void> {
  let granted = await isPermissionGranted();
  if (!granted) {
    const res = await requestPermission();
    if (res !== "granted") return;
    granted = true;
  }
  if (!granted) return;

  const now = new Date();
  const windowStart = new Date(now.getTime() - 90 * 1000);
  const d = await getDb();
  const rows = await d.select<{ id: number; title: string }[]>(
    `SELECT id, title FROM tasks
     WHERE deleted_at IS NULL AND completed_at IS NULL
       AND reminder_at IS NOT NULL AND reminder_at <= ? AND reminder_at >= ?`,
    [toDateTimeStr(now), toDateTimeStr(windowStart)],
  );
  if (!rows.length) return;

  const notified = loadNotified();
  for (const r of rows) {
    if (notified.has(r.id)) continue;
    sendNotification({ title: "todo-lite", body: r.title });
    notified.add(r.id);
  }
  saveNotified(notified);
}

export function startReminderLoop(): void {
  void checkReminders();
  const timer = setInterval(() => void checkReminders(), 30_000);
  window.addEventListener("beforeunload", () => clearInterval(timer));
}
