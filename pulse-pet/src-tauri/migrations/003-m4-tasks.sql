-- v2 M4：定时任务泛化（V2-DESIGN §4.2）。
-- reminders +7 列（action_type/action_params/schedule_kind/schedule_at/
-- schedule_weekdays/snooze_until/last_skipped_at）+ 新表 action_logs
-- （exec 执行历史；notify 维持 reminder_logs 既有记账，不双写）。
-- v1 存量行自动获默认值（notify / interval），行为零变化；
-- todo 派生行（kind='todo'）不迁移，M7 已验逻辑不动。
ALTER TABLE reminders ADD COLUMN action_type TEXT NOT NULL DEFAULT 'notify';
ALTER TABLE reminders ADD COLUMN action_params TEXT;
ALTER TABLE reminders ADD COLUMN schedule_kind TEXT NOT NULL DEFAULT 'interval';
ALTER TABLE reminders ADD COLUMN schedule_at TEXT;
ALTER TABLE reminders ADD COLUMN schedule_weekdays TEXT;
ALTER TABLE reminders ADD COLUMN snooze_until TEXT;
ALTER TABLE reminders ADD COLUMN last_skipped_at TEXT;

-- exec 执行历史（§4.2）：reminder_id 悬空引用允许（规则删除后历史保留，
-- 同 002 迁移 reminder_logs 语义）；action_type 为冗余快照。
CREATE TABLE action_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reminder_id INTEGER NOT NULL,
  action_type TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL,
  output_tail TEXT,
  exit_code INTEGER,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  scheduled_at TEXT
);
