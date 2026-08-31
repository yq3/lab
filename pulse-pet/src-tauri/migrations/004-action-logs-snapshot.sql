-- 迁移 004（routine-exec.md Part A，2026-08-30）：action_logs +3 快照列。
-- 执行历史 = 执行时点的任务内容快照——任务名/配置命令/实际执行命令
-- 随每次运行落库，规则改名/改命令/删除后历史仍可回查当时内容。
-- label 沿用来源列 reminders.label 同名（快照与来源字段对位）；
-- executed_command 仅 running 写入（skipped 恒 NULL = 未执行）；
-- 存量旧行三列 NULL（前端展示「—（未记录）」）。
ALTER TABLE action_logs ADD COLUMN label TEXT;
ALTER TABLE action_logs ADD COLUMN command TEXT;
ALTER TABLE action_logs ADD COLUMN executed_command TEXT;
