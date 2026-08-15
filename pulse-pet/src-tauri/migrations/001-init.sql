-- 001 初始化表结构（DESIGN §5.4 / §8.2 / §8.1）
CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  interval_minutes INTEGER NOT NULL,
  start_time TEXT,
  end_time TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  use_fireworks INTEGER NOT NULL DEFAULT 0,
  last_triggered_at TEXT,
  source_todo_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reminder_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reminder_id INTEGER NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
  triggered_at TEXT NOT NULL,
  acked_at TEXT,
  dismissed_via TEXT
);

CREATE TABLE IF NOT EXISTS todos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  notes TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  due_date TEXT,
  remind_before_minutes INTEGER NOT NULL DEFAULT 5,
  remind_last_triggered_at TEXT,
  completed_at TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS todo_tags (
  todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  PRIMARY KEY (todo_id, tag)
);

CREATE TABLE IF NOT EXISTS plugins (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  manifest_version INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
