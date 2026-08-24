import { useCallback, useEffect, useMemo, useState } from "react";
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
import { t, useLangStore } from "../lib/i18n";
import { pluginEnabled, usePluginStore } from "../lib/plugin-store";

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
 * - M8 i18n：全部文案经 t()；A4（M4 P2⑥ 清偿）：全局烟花开关写失败不再
 *   静默吞——console.error + toast 提示 + 回读真实值。
 */

const KINDS: { id: ReminderKind; labelKey: string }[] = [
  { id: "hydration", labelKey: "reminders.kind.hydration" },
  { id: "rest", labelKey: "reminders.kind.rest" },
  { id: "custom", labelKey: "reminders.kind.custom" },
];

/** 模板键（与 REMINDER_TEMPLATES 按序对应；label 经 t() 本地化）。 */
const TEMPLATE_KEYS = ["reminders.tpl.hydration", "reminders.tpl.rest1", "reminders.tpl.rest2"];

function emptyForm(): ReminderInput {
  return {
    kind: "hydration",
    label: t(TEMPLATE_KEYS[0]),
    interval_minutes: 30,
    start_time: null,
    end_time: null,
    enabled: true,
    use_fireworks: false,
  };
}

/** 当前语言的模板列表（label 本地化；kind/interval 取 REMINDER_TEMPLATES 权威值）。 */
function templatesHere() {
  return REMINDER_TEMPLATES.map((tpl, i) => ({
    ...tpl,
    label: t(TEMPLATE_KEYS[i]),
  }));
}

/**
 * "文案仍是模板默认值"判定：跨语言收集 zh/en 两套模板文案——切换语言后
 * 旧语言的默认文案也能被识别为"模板值"，kind 切换跟随逻辑不误判为用户改过。
 */
function allTemplateLabels(): Set<string> {
  const labels = new Set<string>();
  for (const tpl of REMINDER_TEMPLATES) labels.add(tpl.label);
  for (const key of TEMPLATE_KEYS) {
    labels.add(t(key, undefined, "zh"));
    labels.add(t(key, undefined, "en"));
  }
  return labels;
}

export default function Reminders() {
  const [rules, setRules] = useState<ReminderRule[] | null>(null);
  const [stats, setStats] = useState<ReminderStat[] | null>(null);
  const [fireworksGlobal, setFwGlobal] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ReminderRule | null>(null);
  const [form, setForm] = useState<ReminderInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** 两步删除确认：第一次点"删除"变为"确认删除？"，3s 内再点才执行。 */
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const lang = useLangStore((s) => s.lang); // M8 i18n：语言变化时本页文案重渲染
  // v2 M2：todo 派生行的「已停用（插件关闭）」徽标数据源（TC-UI-07-3；
  // 禁用即惰性——行可见但不再触发，用户不疑惑「我的 todo 提醒去哪了」）
  const plugins = usePluginStore((s) => s.plugins);
  const todoPluginDisabled = !pluginEnabled(plugins, "built-in-todo");

  const load = useCallback(async () => {
    if (!isTauriRuntime()) {
      setError(t("reminders.needApp"));
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
      setError(t("reminders.loadFail", { msg: e instanceof Error ? e.message : String(e) }));
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
      setForm(emptyForm());
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
        setForm(emptyForm());
      }
      refresh();
    } catch (e) {
      showToast(t("reminders.toast.deleteFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  };

  const quickToggle = async (r: ReminderRule, patch: Partial<ReminderInput>) => {
    try {
      await upsertReminder(r.id, { ...ruleToForm(r), ...patch });
      refresh();
    } catch (e) {
      showToast(t("reminders.toast.updateFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  };

  const test = async (r: ReminderRule) => {
    try {
      const status = await triggerReminderNow(r.id);
      if (status === "fired") showToast(t("reminders.toast.fired", { label: r.label }));
      else if (status === "dedup") showToast(t("reminders.toast.dedup"));
      else showToast(t("reminders.toast.paused"));
    } catch (e) {
      showToast(t("reminders.toast.triggerFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  };

  /** A4（M4 P2⑥ 清偿）：全局烟花开关写失败不再静默——报错 + toast + 回读真实值。 */
  const toggleFireworksGlobal = (enabled: boolean) => {
    setFwGlobal(enabled);
    void setFireworksGlobal(enabled)
      .then(refresh)
      .catch((e) => {
        console.error("[pulsepet] set fireworks global failed:", e);
        showToast(
          t("reminders.toast.fwGlobalFail", { msg: e instanceof Error ? e.message : String(e) }),
        );
        refresh(); // 回读权威值，撤销本地乐观态
      });
  };

  const templates = useMemo(templatesHere, [lang]);

  const applyTemplate = (tpl: (typeof templates)[number]) => {
    setForm((f) => ({
      ...f,
      kind: tpl.kind,
      label: tpl.label,
      interval_minutes: tpl.interval_minutes,
    }));
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
      //（模板默认值跨语言识别：见 allTemplateLabels）
      const isTemplate = allTemplateLabels().has(f.label);
      const tpl = templates.find((x) => x.kind === kind);
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
    return <p className="token-empty">{t("reminders.loading")}</p>;
  }

  return (
    <div className="reminders">
      {/* 全局区：烟花总开关 + 暂停状态提示（TC-RM-11/08） */}
      <div className="reminder-toolbar">
        <label className="reminder-check">
          <input
            type="checkbox"
            checked={fireworksGlobal}
            onChange={(e) => toggleFireworksGlobal(e.target.checked)}
          />
          {t("reminders.fwGlobal")}
        </label>
        {paused && <span className="reminder-paused-badge">{t("reminders.pausedBadge")}</span>}
      </div>

      {/* 规则列表 */}
      <section className="token-section">
        <h3>{t("reminders.rules.title", { n: rules.length })}</h3>
        {rules.length === 0 && <p className="token-empty">{t("reminders.rules.empty")}</p>}
        <ul className="reminder-list">
          {rules.map((r) => (
            <li key={r.id} className={r.enabled ? "reminder-item" : "reminder-item disabled"}>
              <span className="reminder-kind" title={r.kind}>
                {kindEmoji(r.kind)} {kindLabel(r.kind)}
              </span>
              {/* v2 M2：禁用插件的 todo 派生行加「已停用」徽标（可见但惰性） */}
              {r.kind === "todo" && todoPluginDisabled && (
                <span className="reminder-plugin-off">{t("plugins.disabledBadge")}</span>
              )}
              <span className="reminder-label" title={r.label}>
                {r.label}
              </span>
              <span className="reminder-meta">{formatInterval(r.interval_minutes)}</span>
              {/* M7：todo 派生规则展示截止时刻（start_time 为绝对时刻非窗口） */}
              {r.kind === "todo" ? (
                <span className="reminder-meta" title={r.start_time ?? undefined}>
                  {t("reminders.due", {
                    ts: (r.todo_due_at ?? r.start_time ?? "").replace("T", " ") || t("reminders.dueNone"),
                  })}
                </span>
              ) : (
                <span className="reminder-meta">{formatWindow(r.start_time, r.end_time)}</span>
              )}
              <span className="reminder-meta" title={r.last_triggered_at ?? t("reminders.lastNever")}>
                {r.last_triggered_at
                  ? t("reminders.last", { ts: formatLogTime(r.last_triggered_at) })
                  : t("reminders.lastNever")}
              </span>
              <label
                className="reminder-check compact"
                title={r.enabled ? t("reminders.enabledOn") : t("reminders.enabledOff")}
              >
                <input
                  type="checkbox"
                  checked={r.enabled}
                  onChange={(e) => void quickToggle(r, { enabled: e.target.checked })}
                />
                {t("reminders.enabled")}
              </label>
              <label className="reminder-check compact" title={t("reminders.fireworksOverride")}>
                <input
                  type="checkbox"
                  checked={r.use_fireworks}
                  onChange={(e) => void quickToggle(r, { use_fireworks: e.target.checked })}
                />
                {t("reminders.fireworks")}
              </label>
              <span className="reminder-actions">
                <button className="seg" onClick={() => void test(r)}>
                  {t("reminders.test")}
                </button>
                <button className="seg" onClick={() => startEdit(r)}>
                  {t("reminders.edit")}
                </button>
                <button
                  className="seg danger"
                  onClick={() => void remove(r)}
                  title={confirmDeleteId === r.id ? t("reminders.deleteHint") : t("reminders.delete")}
                >
                  {confirmDeleteId === r.id ? t("reminders.deleteConfirm") : t("reminders.delete")}
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* 新建 / 编辑表单 */}
      <section className="token-section">
        <h3>
          {editing
            ? t("reminders.form.editTitle", { n: editing.id })
            : t("reminders.form.newTitle")}
        </h3>
        <div className="reminder-form">
          {/* M4 P2 ②（M7 清偿）：编辑 todo 派生规则时锁类型/间隔/窗口
              （kind 不得被改写、interval=0 与绝对 start_time 原样保留） */}
          {form.kind === "todo" && (
            <p className="reminder-hint">{t("reminders.form.todoHint")}</p>
          )}
          {form.kind !== "todo" && (
            <div className="reminder-templates">
              {templates.map((tpl) => (
                <button key={tpl.label} className="seg" onClick={() => applyTemplate(tpl)}>
                  {tpl.label}（{formatInterval(tpl.interval_minutes)}）
                </button>
              ))}
            </div>
          )}
          <div className="reminder-form-row">
            <label>
              {t("reminders.form.type")}
              <select
                value={form.kind}
                disabled={form.kind === "todo"}
                onChange={(e) => setKind(e.target.value as ReminderKind)}
              >
                {form.kind === "todo" && (
                  <option value="todo">{t("reminders.kind.todoDerived")}</option>
                )}
                {KINDS.map((k) => (
                  <option key={k.id} value={k.id}>
                    {t(k.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className="grow">
              {t("reminders.form.label")}
              <input
                type="text"
                value={form.label}
                maxLength={140}
                placeholder={t("reminders.form.labelPlaceholder")}
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              />
            </label>
          </div>
          <div className="reminder-form-row">
            <label>
              {t("reminders.form.interval")}
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
              {t("reminders.form.start")}
              <input
                type="time"
                disabled={form.kind === "todo"}
                value={form.start_time ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value || null }))}
              />
            </label>
            <label>
              {t("reminders.form.end")}
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
              {t("reminders.enabled")}
            </label>
            <label className="reminder-check">
              <input
                type="checkbox"
                checked={form.use_fireworks}
                onChange={(e) => setForm((f) => ({ ...f, use_fireworks: e.target.checked }))}
              />
              {t("reminders.form.fireworksMode")}
            </label>
          </div>
          {form.kind !== "todo" &&
            form.start_time &&
            form.end_time &&
            form.start_time > form.end_time && (
              <p className="reminder-hint">
                {t("reminders.form.crossMidnight", { start: form.start_time, end: form.end_time })}
              </p>
            )}
          {formError && <p className="reminder-form-error">{formError}</p>}
          <div className="reminder-form-actions">
            <button className="seg primary" onClick={() => void save()}>
              {editing ? t("reminders.form.save") : t("reminders.form.create")}
            </button>
            {editing && (
              <button
                className="seg"
                onClick={() => {
                  setEditing(null);
                  setForm(emptyForm());
                  setFormError(null);
                }}
              >
                {t("reminders.form.cancel")}
              </button>
            )}
          </div>
        </div>
      </section>

      {/* 历史统计（TC-RM-13） */}
      <section className="token-section">
        <h3>{t("reminders.stats.title")}</h3>
        {(!stats || stats.length === 0) && (
          <p className="token-empty">{t("reminders.stats.empty")}</p>
        )}
        <ul className="reminder-stats">
          {stats?.map((s) => (
            <li key={s.kind}>
              <span className="reminder-kind">
                {kindEmoji(s.kind)} {kindLabel(s.kind)}
              </span>
              <span className="reminder-meta">{t("reminders.stats.today", { n: s.today })}</span>
              <span className="reminder-meta">{t("reminders.stats.total", { n: s.total })}</span>
            </li>
          ))}
        </ul>
      </section>

      {toast && <div className="reminder-toast">{toast}</div>}
    </div>
  );
}
