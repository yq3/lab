-- 002（M7，DESIGN §8/§5.4 / TC-TD-07/08）：
-- 1) reminders 增加 todo_due_at：todo 派生提醒的截止时刻（due_date 原值），
--    供触发时计算"还有 X 分钟要完成「任务名」"的 X（调度器单一数据源，不回查 todos）。
-- 2) reminder_logs 去掉对 reminders 的 ON DELETE CASCADE：todo 删除/完成时级联删
--    reminders 行，但历史日志保留（TC-TD-07：级联仅作用于 reminders 行）。
ALTER TABLE reminders ADD COLUMN todo_due_at TEXT;

CREATE TABLE reminder_logs_m7 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reminder_id INTEGER NOT NULL,
  triggered_at TEXT NOT NULL,
  acked_at TEXT,
  dismissed_via TEXT
);
INSERT INTO reminder_logs_m7 (id, reminder_id, triggered_at, acked_at, dismissed_via)
  SELECT id, reminder_id, triggered_at, acked_at, dismissed_via FROM reminder_logs;
DROP TABLE reminder_logs;
ALTER TABLE reminder_logs_m7 RENAME TO reminder_logs;
