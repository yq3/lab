import { useCallback, useEffect, useState } from "react";
import {
  REMINDER_TEMPLATES,
  deleteReminder,
  fetchFireworksGlobal,
  fetchPaused,
  fetchReminderStats,
  fetchReminders,
  formatInterval,
  formatLogTime,
  formatWindow,
  isTauriRuntime,
  kindEmoji,
  kindLabel,
  ruleToForm,
  setFireworksGlobal,
  triggerReminderNow,
  upsertReminder,
  validateReminderInput,
  type ReminderInput,
  type ReminderKind,
  type ReminderRule,
  type ReminderStat,
} from "../lib/reminders";

/**
 * 提醒配置页（DESIGN §5.4 / §10.2 M4，TC-RM-07/11/13/14）：
 * - 规则 CRUD（增/改/删 + 启用/烟花快捷开关），写 `reminders` 表并即时
 *   reload 调度器（Rust 侧 CRUD 命令内置，无需重启 App）；
 * - 全局烟花开关（app_state；TC-RM-11：全局关 + 单条勾选 → 该条仍放烟花）；
 * - 内置模板一键套用（喝水/休息/站立，文案可改，TC-RM-14 自定义文案）；
 * - "试一试"手动触发（受 3 分钟去重与全局暂停约束）；
 * - 历史统计（reminder_logs 按 kind 聚合今日/累计，TC-RM-13）；
 * - M4 P2 ②（M7 清偿）：todo 派生规则不再降级 custom——快捷开关/编辑保留
 *   kind='todo' 与 interval=0（表单对 todo 只开放 文案/启用/烟花），不丢
 *   source_todo_id（Rust update 不触碰该列）。
 */

const KINDS: { id: ReminderKind; label: string }[] = [
  { id: "hydration", label: "喝水" },
  { id: "rest", label: "休息" },
  { id: "custom", label: "自定义" },
];

const EMPTY_FORM: ReminderInput = {
  kind: "hydration",
  label: "该喝水啦 💧",
  interval_minutes: 30,
  start_time: null,
  end_time: null,
  enabled: true,
  use_fireworks: false,
};

export default function Reminders() {
  const [rules, setRules] = useState<ReminderRule[] | null>(null);
  const [stats, setStats] = useState<ReminderStat[] | null>(null);
  const [fireworksGlobal, setFwGlobal] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ReminderRule | null>(null);
  const [form, setForm] = useState<ReminderInput>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** 两步删除确认：第一次点"删除"变为"确认删除？"，3s 内再点才执行。 */
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!isTauriRuntime()) {
      setError("提醒配置需要在 PulsePet App（Tauri）内使用");
      return;
    }
    try {
      const [rs, st, fw, pa] = await Promise.all([
        fetchReminders(),
        fetchReminderStats(),
        fetchFireworksGlobal(),
        fetchPaused(),
      ]);
      setRules(rs);
      setStats(st);
      setFwGlobal(fw);
      setPaused(pa);
      setError(null);
    } catch (e) {
      setError(`读取提醒配置失败：${e instanceof Error ? e.message : String(e)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** CRUD 后调度器已在 Rust 侧 reload，前端刷新展示即可（TC-RM-07）。 */
  const refresh = () => void load();

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const save = async () => {
    const err = validateReminderInput(form);
    if (err) {
      setFormError(err);
      return;
    }
    setFormError(null);
    try {
      await upsertReminder(editing?.id ?? null, { ...form, label: form.label.trim() });
      setEditing(null);
      setForm(EMPTY_FORM);
      refresh();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async (r: ReminderRule) => {
    // wry/WKWebView 无 window.confirm 原生对话框（E2E 实测返回假值）→ 应用内两步确认
    if (confirmDeleteId !== r.id) {
      setConfirmDeleteId(r.id);
      setTimeout(() => {
        setConfirmDeleteId((cur) => (cur === r.id ? null : cur));
      }, 3000);
      return;
    }
    setConfirmDeleteId(null);
    try {
      await deleteReminder(r.id);
      if (editing?.id === r.id) {
        setEditing(null);
        setForm(EMPTY_FORM);
      }
      refresh();
    } catch (e) {
      showToast(`删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const quickToggle = async (r: ReminderRule, patch: Partial<ReminderInput>) => {
    try {
      await upsertReminder(r.id, { ...ruleToForm(r), ...patch });
      refresh();
    } catch (e) {
      showToast(`更新失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const test = async (r: ReminderRule) => {
    try {
      const status = await triggerReminderNow(r.id);
      if (status === "fired") showToast(`已触发「${r.label}」`);
      else if (status === "dedup") showToast("3 分钟内已触发过，去重拦截（TC-RM-05）");
      else showToast("所有提醒已暂停（托盘「暂停所有提醒」），恢复后再试");
    } catch (e) {
      showToast(`触发失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const applyTemplate = (t: (typeof REMINDER_TEMPLATES)[number]) => {
    setForm((f) => ({ ...f, kind: t.kind, label: t.label, interval_minutes: t.interval_minutes }));
    setFormError(null);
  };

  const startEdit = (r: ReminderRule) => {
    setEditing(r);
    setForm(ruleToForm(r));
    setFormError(null);
  };

  const setKind = (kind: ReminderKind) => {
    setForm((f) => {
      // 文案还是模板默认值时跟随 kind 换默认文案；用户改过则保留
      const isTemplate = REMINDER_TEMPLATES.some((t) => t.label === f.label);
      const tpl = REMINDER_TEMPLATES.find((t) => t.kind === kind);
      return {
        ...f,
        kind,
        label: isTemplate && tpl ? tpl.label : f.label,
        interval_minutes: isTemplate && tpl ? tpl.interval_minutes : f.interval_minutes,
      };
    });
  };

  if (error) {
    return <div className="token-error">{error}</div>;
  }
  if (!rules) {
    return <p className="token-empty">读取提醒配置…</p>;
  }

  return (
    <div className="reminders">
      {/* 全局区：烟花总开关 + 暂停状态提示（TC-RM-11/08） */}
      <div className="reminder-toolbar">
        <label className="reminder-check">
          <input
            type="checkbox"
            checked={fireworksGlobal}
            onChange={(e) => {
              setFwGlobal(e.target.checked);
              void setFireworksGlobal(e.target.checked).then(refresh).catch(() => {});
            }}
          />
          全局烟花模式（未单独勾选的提醒也升级为烟花）
        </label>
        {paused && <span className="reminder-paused-badge">已暂停所有提醒（托盘可恢复）</span>}
      </div>

      {/* 规则列表 */}
      <section className="token-section">
        <h3>提醒规则（{rules.length}）</h3>
        {rules.length === 0 && (
          <p className="token-empty">还没有提醒规则，从下方模板或表单新建一条吧。</p>
        )}
        <ul className="reminder-list">
          {rules.map((r) => (
            <li key={r.id} className={r.enabled ? "reminder-item" : "reminder-item disabled"}>
              <span className="reminder-kind" title={r.kind}>
                {kindEmoji(r.kind)} {kindLabel(r.kind)}
              </span>
              <span className="reminder-label" title={r.label}>
                {r.label}
              </span>
              <span className="reminder-meta">{formatInterval(r.interval_minutes)}</span>
              {/* M7：todo 派生规则展示截止时刻（start_time 为绝对时刻非窗口） */}
              {r.kind === "todo" ? (
                <span className="reminder-meta" title={r.start_time ?? undefined}>
                  截止 {(r.todo_due_at ?? r.start_time ?? "").replace("T", " ") || "—"}
                </span>
              ) : (
                <span className="reminder-meta">{formatWindow(r.start_time, r.end_time)}</span>
              )}
              <span className="reminder-meta" title={r.last_triggered_at ?? "从未触发"}>
                上次 {formatLogTime(r.last_triggered_at)}
              </span>
              <label className="reminder-check compact" title={r.enabled ? "启用中" : "已停用"}>
                <input
                  type="checkbox"
                  checked={r.enabled}
                  onChange={(e) => void quickToggle(r, { enabled: e.target.checked })}
                />
                启用
              </label>
              <label className="reminder-check compact" title="单条烟花覆盖（TC-RM-11）">
                <input
                  type="checkbox"
                  checked={r.use_fireworks}
                  onChange={(e) => void quickToggle(r, { use_fireworks: e.target.checked })}
                />
                烟花
              </label>
              <span className="reminder-actions">
                <button className="seg" onClick={() => void test(r)}>
                  试一试
                </button>
                <button className="seg" onClick={() => startEdit(r)}>
                  编辑
                </button>
                <button
                  className="seg danger"
                  onClick={() => void remove(r)}
                  title={confirmDeleteId === r.id ? "再次点击确认删除" : "删除"}
                >
                  {confirmDeleteId === r.id ? "确认删除？" : "删除"}
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* 新建 / 编辑表单 */}
      <section className="token-section">
        <h3>{editing ? `编辑提醒 #${editing.id}` : "新建提醒"}</h3>
        <div className="reminder-form">
          {/* M4 P2 ②（M7 清偿）：编辑 todo 派生规则时锁类型/间隔/窗口
              （kind 不得被改写、interval=0 与绝对 start_time 原样保留） */}
          {form.kind === "todo" && (
            <p className="reminder-hint">
              📋 Todo 派生提醒（单次，由 Todo 插件管理类型/间隔/时刻——在 Todo 页改任务的
              截止或提前提醒即可）。此处仅可调整文案、启用与烟花；改动会随任务下次保存被
              任务标题覆盖。
            </p>
          )}
          {form.kind !== "todo" && (
            <div className="reminder-templates">
              {REMINDER_TEMPLATES.map((t) => (
                <button key={t.label} className="seg" onClick={() => applyTemplate(t)}>
                  {t.label}（{formatInterval(t.interval_minutes)}）
                </button>
              ))}
            </div>
          )}
          <div className="reminder-form-row">
            <label>
              类型
              <select
                value={form.kind}
                disabled={form.kind === "todo"}
                onChange={(e) => setKind(e.target.value as ReminderKind)}
              >
                {form.kind === "todo" && <option value="todo">待办（派生）</option>}
                {KINDS.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="grow">
              文案（气泡显示，纯文本 1-140 字符）
              <input
                type="text"
                value={form.label}
                maxLength={140}
                placeholder="如：该喝水啦 💧"
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              />
            </label>
          </div>
          <div className="reminder-form-row">
            <label>
              间隔（分钟，1-1440）
              <input
                type="number"
                min={1}
                max={1440}
                disabled={form.kind === "todo"}
                value={form.interval_minutes}
                onChange={(e) =>
                  setForm((f) => ({ ...f, interval_minutes: Number(e.target.value) || 0 }))
                }
              />
            </label>
            <label>
              起始（留空 = 全天）
              <input
                type="time"
                disabled={form.kind === "todo"}
                value={form.start_time ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value || null }))}
              />
            </label>
            <label>
              结束（留空 = 全天）
              <input
                type="time"
                disabled={form.kind === "todo"}
                value={form.end_time ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value || null }))}
              />
            </label>
            <label className="reminder-check">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              启用
            </label>
            <label className="reminder-check">
              <input
                type="checkbox"
                checked={form.use_fireworks}
                onChange={(e) => setForm((f) => ({ ...f, use_fireworks: e.target.checked }))}
              />
              烟花模式
            </label>
          </div>
          {form.kind !== "todo" &&
            form.start_time &&
            form.end_time &&
            form.start_time > form.end_time && (
              <p className="reminder-hint">
                跨午夜窗口：仅在 [{form.start_time}, 24:00) ∪ [00:00, {form.end_time}) 内触发（TC-RM-06）
              </p>
            )}
          {formError && <p className="reminder-form-error">{formError}</p>}
          <div className="reminder-form-actions">
            <button className="seg primary" onClick={() => void save()}>
              {editing ? "保存修改" : "新建"}
            </button>
            {editing && (
              <button
                className="seg"
                onClick={() => {
                  setEditing(null);
                  setForm(EMPTY_FORM);
                  setFormError(null);
                }}
              >
                取消编辑
              </button>
            )}
          </div>
        </div>
      </section>

      {/* 历史统计（TC-RM-13） */}
      <section className="token-section">
        <h3>历史统计（reminder_logs）</h3>
        {(!stats || stats.length === 0) && <p className="token-empty">暂无提醒记录。</p>}
        <ul className="reminder-stats">
          {stats?.map((s) => (
            <li key={s.kind}>
              <span className="reminder-kind">
                {kindEmoji(s.kind)} {kindLabel(s.kind)}
              </span>
              <span className="reminder-meta">今日 {s.today} 次</span>
              <span className="reminder-meta">累计 {s.total} 次</span>
            </li>
          ))}
        </ul>
      </section>

      {toast && <div className="reminder-toast">{toast}</div>}
    </div>
  );
}
