import type { RepeatRule } from "../types";

function toDateParts(s: string): { y: number; m: number; d: number } {
  const [y, m, d] = s.split("-").map(Number);
  return { y, m, d };
}

function nextWeekday(d: Date): Date {
  const next = new Date(d);
  do {
    next.setDate(next.getDate() + 1);
  } while (next.getDay() === 0 || next.getDay() === 6);
  return next;
}

export function computeNextOccurrence(rule: RepeatRule, from: Date): Date {
  switch (rule.type) {
    case "daily":
      return addDays(from, 1);
    case "weekdays":
      return nextWeekday(from);
    case "weekly":
      return addDays(from, 7);
    case "monthly": {
      const d = new Date(from);
      const target = new Date(d.getFullYear(), d.getMonth() + 1, 1);
      const dom = Math.min(d.getDate(), new Date(d.getFullYear(), d.getMonth() + 2, 0).getDate());
      target.setDate(dom);
      return target;
    }
    case "yearly": {
      const d = new Date(from);
      return new Date(d.getFullYear() + 1, d.getMonth(), d.getDate());
    }
  }
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

export function toDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function toDateTimeStr(d: Date): string {
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${toDateStr(d)} ${h}:${min}:00`;
}

export function addDaysToDateStr(dateStr: string | null, n: number): string | null {
  if (!dateStr) return null;
  const { y, m, d } = toDateParts(dateStr);
  return toDateStr(addDays(new Date(y, m - 1, d), n));
}

export function shiftDateTimeStr(dtStr: string | null, from: Date, to: Date): string | null {
  if (!dtStr) return null;
  const { y, m, d } = toDateParts(dtStr.slice(0, 10));
  const time = dtStr.slice(11);
  const base = new Date(y, m - 1, d);
  const diff = to.getTime() - from.getTime();
  return toDateStr(new Date(base.getTime() + diff)) + " " + time;
}
