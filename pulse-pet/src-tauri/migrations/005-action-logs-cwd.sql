-- 迁移 005（routine-exec.md Part C，2026-08-30）：执行上下文增补。
-- +cwd 快照列：执行历史的快照字段集合演进为 任务名/命令/工作目录——
--   「当时在哪个目录执行」此前无处可见（action_params 现值违背时点快照语义）。
-- −executed_command：与 command 恒同值（命令串逐字节原样传给 sh/powershell，
--   目录经进程属性 current_dir 生效、不进命令串）——冗余列删除，表结构
--   反映真实语义。004→005 存量行该列与 command 同值，删除零信息损失。
ALTER TABLE action_logs ADD COLUMN cwd TEXT;
ALTER TABLE action_logs DROP COLUMN executed_command;
