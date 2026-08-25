import { useCallback, useEffect, useMemo, useState } from "react";
import {
  REMINDER_TEMPLATES,
  actionBadge,
  actionBadgeTitle,
  buildOpencodeCommand,
  deleteReminder,
  fetchActionLogs,
  fetchFireworksGlobal,
  fetchPaused,
  fetchReminderStats,
  fetchReminders,
  formatInterval,
  formatLogTime,
  isTauriRuntime,
  kindEmoji,
  kindLabel,
  parseWeekdays,
  renderTaskSummary,
  ruleToForm,
  scheduleSummary,
  setFireworksGlobal,
  skipTaskOnce,
  triggerReminderNow,
  upsertReminder,
  validateReminderInput,
  weekdaysToJson,
  type ActionLogPage,
  type ActionType,
  type ReminderInput,
  type ReminderKind,
  type ReminderRule,
  type ReminderStat,
  type ScheduleKind,
} from "../lib/reminders";
import { t, useLangStore } from "../lib/i18n";
import { pluginEnabled, usePluginStore } from "../lib/plugin-store";

/**
 * 定时任务页（v2 M4，V2-DESIGN §4.7；原 Reminders.tsx 改名重构）：
 * - 一张列表：动作徽标（💧 notify / ⚡ exec，title 说明）+ 名称 + 调度摘要
 *   （每 30 分钟 · 09:00-18:00 / 每天 09:00 / 周三、五 09:00 / 一次 · 08-25 21:00）
 *   + 启用开关 + 行操作（编辑/试一试/跳过本次/删除两步确认）；todo 派生行
 *   保持 M2 展示（可见惰性 + 📋 徽标）；
 * - 表单按 action_type 条件显隐（完整重做）：notify = kind/文案/调度三分支/
 *   烟花；exec = 任务名/opencode 例程模板块/command 等宽多行/cwd/超时/调度；
 * - Rust validate 权威 + 前端同规则预检（v1 模式）；
 * - 执行历史区（折叠面板）：action_logs 倒序分页 50 条/页 + 状态过滤 + 状态
 *   色点 + 展开 output_tail（等宽）+ scheduled_at 与 started_at 差（补跑延迟）。
 * - i18n：tasks.* 命名空间（reminders.* 存量保留复用）。
 */

const KINDS: { id: ReminderKind; labelKey: string }[] = [
  { id: "hydration", labelKey: "reminders.kind.hydration" },
  { id: "rest", labelKey: "reminders.kind.rest" },
  { id: "custom", labelKey: "reminders.kind.custom" },
];

/** 模板键（与 REMINDER_TEMPLATES 按序对应；label 经 t() 本地化）。 */
const TEMPLATE_KEYS = ["reminders.tpl.hydration", "reminders.tpl.rest1", "reminders.tpl.rest2"];

/** 调度三分支（§4.7）。 */
const SCHEDULE_KINDS: { id: ScheduleKind; labelKey: string }[] = [
  { id: "interval", labelKey: "tasks.schedule.interval" },
  { id: "daily", labelKey: "tasks.schedule.daily" },
  { id: "once", labelKey: "tasks.schedule.once" },
];

/** exec 表单的独立状态（command 等 → 序列化进 action_params 提交）。 */
interface ExecFormState {
  command: string;
  cwd: string;
  timeoutMinutes: number;
  /** opencode 模板块的指令 + --auto（模板拼接辅助态）。 */
  tplInstruction: string;
  tplAuto: boolean;
}

function emptyForm(): ReminderInput {
  return {
    kind: "hydration",
    label: t(TEMPLATE_KEYS[0]),
    interval_minutes: 30,
    start_time: null,
    end_time: null,
    enabled: true,
    use_fireworks: false,
    action_type: "notify",
    action_params: null,
    schedule_kind: "interval",
    schedule_at: null,
    schedule_weekdays: null,
  };
}

function emptyExec(): ExecFormState {
  return { command: "", cwd: "", timeoutMinutes: 10, tplInstruction: "", tplAuto: false };
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

/** exec 表单态 → action_params JSON（timeout 恒写——模板与手写同构）。 */
function execParamsJson(exec: ExecFormState): string {
  return JSON.stringify({
    command: exec.command,
    ...(exec.cwd.trim() ? { cwd: exec.cwd.trim() } : {}),
    timeout_minutes: exec.timeoutMinutes,
    ...(exec.tplAuto ? { opencode_auto: true } : {}),
  });
}

/** action_params JSON → exec 表单态（编辑回填）。 */
function execFromParams(params: string | null): ExecFormState {
  const base = emptyExec();
  if (!params) return base;
  try {
    const p = JSON.parse(params) as Record<string, unknown>;
    return {
      command: typeof p.command === "string" ? p.command : "",
      cwd: typeof p.cwd === "string" ? p.cwd : "",
      timeoutMinutes:
        typeof p.timeout_minutes === "number" && p.timeout_minutes >= 1 && p.timeout_minutes <= 120
          ? p.timeout_minutes
          : 10,
      tplInstruction: "",
      tplAuto: p.opencode_auto === true,
    };
  } catch {
    return base;
  }
}

/** once 时刻 "YYYY-MM-DDTHH:MM" → datetime-local input 值。 */
function onceToLocalInput(at: string | null | undefined): string {
  return at ?? "";
}

export default function Tasks() {
  const [rules, setRules] = useState<ReminderRule[] | null>(null);
  const [stats, setStats] = useState<ReminderStat[] | null>(null);
  const [fireworksGlobal, setFwGlobal] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ReminderRule | null>(null);
  const [form, setForm] = useState<ReminderInput>(emptyForm);
  const [exec, setExec] = useState<ExecFormState>(emptyExec);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** 两步删除确认：第一次点"删除"变为"确认删除？"，3s 内再点才执行。 */
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  /** 执行历史区（§4.7）：折叠面板 + 分页 + 规则过滤。 */
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<ActionLogPage | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyFilter, setHistoryFilter] = useState<number | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const lang = useLangStore((s) => s.lang); // M8 i18n：语言变化时本页文案重渲染
  // v2 M2：todo 派生行的「已停用（插件关闭）」徽标数据源（TC-UI-07-3）
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

  const loadHistory = useCallback(async (page: number, filter: number | null) => {
    try {
      const p = await fetchActionLogs(filter, page);
      setHistory(p);
      setHistoryError(null);
    } catch (e) {
      setHistoryError(
        t("tasks.history.loadFail", { msg: e instanceof Error ? e.message : String(e) }),
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (historyOpen) void loadHistory(historyPage, historyFilter);
  }, [historyOpen, historyPage, historyFilter, loadHistory]);

  /** CRUD 后调度器已在 Rust 侧 reload，前端刷新展示即可（TC-RM-07）。 */
  const refresh = () => {
    void load();
    if (historyOpen) void loadHistory(historyPage, historyFilter);
  };

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const save = async () => {
    // 提交形态：exec 的 command/cwd/timeout 序列化进 action_params
    const payload: ReminderInput =
      form.action_type === "exec"
        ? { ...form, action_params: execParamsJson(exec) }
        : { ...form, action_params: null };
    const err = validateReminderInput(payload);
    if (err) {
      setFormError(err);
      return;
    }
    setFormError(null);
    try {
      await upsertReminder(editing?.id ?? null, { ...payload, label: payload.label.trim() });
      setEditing(null);
      setForm(emptyForm());
      setExec(emptyExec());
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
        setExec(emptyExec());
      }
      if (historyFilter === r.id) setHistoryFilter(null);
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

  /** 跳过本次（§4.3）：即时推进 next_due，不触发不记录。 */
  const skipOnce = async (r: ReminderRule) => {
    try {
      await skipTaskOnce(r.id);
      showToast(t("tasks.skipDone"));
      refresh();
    } catch (e) {
      showToast(t("tasks.skipFail", { msg: e instanceof Error ? e.message : String(e) }));
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

  /** opencode 例程模板（§4.6）：一键拼 command（--auto 随 checkbox；不用 --dir）。 */
  const applyOpencodeTemplate = () => {
    const name = form.label.trim() || t("tasks.form.namePlaceholder");
    setExec((e) => ({ ...e, command: buildOpencodeCommand(name, e.tplInstruction, e.tplAuto) }));
    setFormError(null);
  };

  const startEdit = (r: ReminderRule) => {
    setEditing(r);
    setForm(ruleToForm(r));
    setExec(execFromParams(r.action_params));
    setFormError(null);
  };

  const setKind = (kind: ReminderKind) => {
    setForm((f) => {
      // 文案还是模板默认值时跟随 kind 换默认文案；用户改过则保留
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

  /** 调度类型切换：清无关字段（P2-6 同 Rust normalize）。 */
  const setScheduleKind = (kind: ScheduleKind) => {
    setForm((f) => ({
      ...f,
      schedule_kind: kind,
      schedule_at: null,
      schedule_weekdays: null,
      // 回到 interval 时恢复合法间隔（daily/once 行 interval 恒 0）
      interval_minutes: kind === "interval" ? (f.interval_minutes >= 1 ? f.interval_minutes : 30) : 0,
      // 切离 interval 时清时间窗（防遗留窗口卡住 in_window 误 skipped）
      start_time: kind === "interval" ? f.start_time : null,
      end_time: kind === "interval" ? f.end_time : null,
    }));
  };

  /** 动作类型切换（notify ↔ exec）：清调度无关态 + exec 默认间隔调度。 */
  const setActionType = (action: ActionType) => {
    setForm((f) => ({
      ...f,
      action_type: action,
      action_params: null,
      // exec 不消费时间窗（表单不提供；Rust normalize 双保险清空）
      start_time: action === "exec" ? null : f.start_time,
      end_time: action === "exec" ? null : f.end_time,
      use_fireworks: action === "exec" ? false : f.use_fireworks,
    }));
    if (action === "exec") setExec(emptyExec());
  };

  const weekdays = parseWeekdays(form.schedule_weekdays);
  const toggleWeekday = (day: number) => {
    const next = weekdays.includes(day)
      ? weekdays.filter((d) => d !== day)
      : [...weekdays, day];
    setForm((f) => ({ ...f, schedule_weekdays: weekdaysToJson(next) }));
  };

  /**
   * 表单提交/取消按钮组（用户 2026-08-25 二次裁定：**不占独立动作行**，
   * 并入实际渲染的最后一行字段行右端——表单按 action_type/schedule_kind
   * 条件显隐，末行随分支变化：once｜interval+exec → 调度行；interval+notify
   * → 时间窗行；daily → 星期行；todo 编辑态无字段行 → margin-left:auto 在
   * flex-column 表单内天然右对齐。accent 非默认色保持上一轮方案）。
   */
  const formActions = (
    <div className="task-form-actions">
      <button className="seg primary" onClick={() => void save()}>
        {editing ? t("reminders.form.save") : t("reminders.form.create")}
      </button>
      {editing && (
        <button
          className="seg"
          onClick={() => {
            setEditing(null);
            setForm(emptyForm());
            setExec(emptyExec());
            setFormError(null);
          }}
        >
          {t("reminders.form.cancel")}
        </button>
      )}
    </div>
  );

  if (error) {
    return <div className="token-error">{error}</div>;
  }
  if (!rules) {
    return <p className="token-empty">{t("reminders.loading")}</p>;
  }

  const totalPages = history ? Math.max(1, Math.ceil(history.total / history.page_size)) : 1;

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

      {/* 任务列表（一张：notify/exec/todo 派生行同列） */}
      <section className="token-section">
        <h3>{t("tasks.rules.title", { n: rules.length })}</h3>
        {rules.length === 0 && <p className="token-empty">{t("reminders.rules.empty")}</p>}
        <ul className="reminder-list">
          {rules.map((r) => (
            <li key={r.id} className={r.enabled ? "reminder-item" : "reminder-item disabled"}>
              <span className="task-badge" title={actionBadgeTitle(r)}>
                {actionBadge(r)}
              </span>
              {r.kind !== "todo" && (
                <span className="reminder-kind">{kindEmoji(r.kind)} {kindLabel(r.kind)}</span>
              )}
              {/* v2 M2：禁用插件的 todo 派生行加「已停用」徽标（可见但惰性） */}
              {r.kind === "todo" && todoPluginDisabled && (
                <span className="reminder-plugin-off">{t("plugins.disabledBadge")}</span>
              )}
              <span className="reminder-label" title={r.label}>
                {r.label}
              </span>
              {/* 调度摘要（§4.7）：todo 派生行保持 M2 截止展示 */}
              {r.kind === "todo" ? (
                <span className="reminder-meta" title={r.start_time ?? undefined}>
                  {t("reminders.due", {
                    ts: (r.todo_due_at ?? r.start_time ?? "").replace("T", " ") || t("reminders.dueNone"),
                  })}
                </span>
              ) : (
                <span className="reminder-meta">{scheduleSummary(r)}</span>
              )}
              <span
                className="reminder-meta"
                title={r.last_skipped_at ?? r.last_triggered_at ?? t("reminders.lastNever")}
              >
                {r.last_triggered_at
                  ? t("reminders.last", { ts: formatLogTime(r.last_triggered_at) })
                  : r.last_skipped_at
                    ? t("reminders.lastNever")
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
              {r.kind === "todo" && (
                <label className="reminder-check compact" title={t("reminders.fireworksOverride")}>
                  <input
                    type="checkbox"
                    checked={r.use_fireworks}
                    onChange={(e) => void quickToggle(r, { use_fireworks: e.target.checked })}
                  />
                  {t("reminders.fireworks")}
                </label>
              )}
              <span className="reminder-actions">
                <button className="seg" onClick={() => void test(r)}>
                  {t("reminders.test")}
                </button>
                {/* 跳过本次：仅 v2 任务行（todo 派生一次性无"下次"语义） */}
                {r.kind !== "todo" && (
                  <button className="seg" onClick={() => void skipOnce(r)}>
                    {t("tasks.skip")}
                  </button>
                )}
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

      {/* 新建 / 编辑表单（按 action_type 条件显隐，§4.7 完整重做） */}
      <section className="token-section">
        <h3>
          {editing
            ? t("reminders.form.editTitle", { n: editing.id })
            : t("reminders.form.newTitle")}
        </h3>
        <div className="reminder-form">
          {/* M4 P2 ②：编辑 todo 派生规则时锁类型/间隔/时刻 */}
          {form.kind === "todo" && (
            <p className="reminder-hint">{t("reminders.form.todoHint")}</p>
          )}
          {form.kind !== "todo" && (
            <>
              {/* 动作类型分段（notify/exec；用户 2026-08-25 裁定去图标——
                  徽标仅保留在列表行） */}
              <div className="token-seg" role="tablist" aria-label={t("tasks.actionType")}>
                {(["notify", "exec"] as ActionType[]).map((a) => (
                  <button
                    key={a}
                    className={form.action_type === a ? "seg active" : "seg"}
                    onClick={() => setActionType(a)}
                  >
                    {t(`tasks.action.${a}`)}
                  </button>
                ))}
              </div>

              {/* notify 快捷模板（仅 notify 动作） */}
              {form.action_type === "notify" && (
                <div className="reminder-templates">
                  {templates.map((tpl) => (
                    <button key={tpl.label} className="seg" onClick={() => applyTemplate(tpl)}>
                      {tpl.label}（{formatInterval(tpl.interval_minutes)}）
                    </button>
                  ))}
                </div>
              )}

              {/* opencode 例程模板块（仅 exec，§4.6） */}
              {form.action_type === "exec" && (
                <div className="task-tpl-block">
                  <div className="task-tpl-title">{t("tasks.tpl.title")}</div>
                  <p className="reminder-hint">{t("tasks.tpl.hint")}</p>
                  <textarea
                    className="task-textarea"
                    rows={2}
                    placeholder={t("tasks.form.instruction")}
                    value={exec.tplInstruction}
                    onChange={(e) => setExec((x) => ({ ...x, tplInstruction: e.target.value }))}
                  />
                  <div className="task-tpl-row">
                    <label className={`reminder-check${exec.tplAuto ? " danger-check" : ""}`}>
                      <input
                        type="checkbox"
                        checked={exec.tplAuto}
                        onChange={(e) => {
                          const auto = e.target.checked;
                          setExec((x) => {
                            // 已用模板拼过 command：--auto 增删同步进 command
                            const cmd = x.command.includes("opencode run")
                              ? buildOpencodeCommand(form.label || "task", x.tplInstruction, auto)
                              : x.command;
                            return { ...x, tplAuto: auto, command: cmd };
                          });
                        }}
                      />
                      {t("tasks.tpl.auto")}
                    </label>
                    <button className="seg primary" onClick={applyOpencodeTemplate}>
                      {t("tasks.tpl.title")}
                    </button>
                  </div>
                  {exec.tplAuto && (
                    <p className="task-danger-hint">{t("tasks.tpl.autoHint")}</p>
                  )}
                </div>
              )}

              <div className="reminder-form-row">
                {form.action_type === "notify" && (
                  <label>
                    {t("reminders.form.type")}
                    <select
                      value={form.kind}
                      onChange={(e) => setKind(e.target.value as ReminderKind)}
                    >
                      {KINDS.map((k) => (
                        <option key={k.id} value={k.id}>
                          {t(k.labelKey)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="grow">
                  {form.action_type === "exec" ? t("tasks.form.name") : t("reminders.form.label")}
                  <input
                    type="text"
                    value={form.label}
                    maxLength={140}
                    placeholder={
                      form.action_type === "exec"
                        ? t("tasks.form.namePlaceholder")
                        : t("reminders.form.labelPlaceholder")
                    }
                    onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                  />
                </label>
              </div>

              {/* exec 专属字段（§4.7：command 等宽多行 / cwd / 超时） */}
              {form.action_type === "exec" && (
                <>
                  <label className="task-command-label">
                    {t("tasks.form.command")}
                    <textarea
                      className="task-textarea mono"
                      rows={3}
                      value={exec.command}
                      maxLength={2000}
                      onChange={(e) => setExec((x) => ({ ...x, command: e.target.value }))}
                    />
                  </label>
                  <div className="reminder-form-row">
                    <label className="grow">
                      {t("tasks.form.cwd")}
                      <input
                        type="text"
                        value={exec.cwd}
                        placeholder="/path/to/project"
                        onChange={(e) => setExec((x) => ({ ...x, cwd: e.target.value }))}
                      />
                    </label>
                    <label>
                      {t("tasks.form.timeout")}
                      <input
                        type="number"
                        min={1}
                        max={120}
                        value={exec.timeoutMinutes}
                        onChange={(e) =>
                          setExec((x) => ({ ...x, timeoutMinutes: Number(e.target.value) || 10 }))
                        }
                      />
                    </label>
                  </div>
                </>
              )}

              {/* 调度三分支（notify/exec 共用；§4.2 weekly 并入 daily 过滤） */}
              <div className="reminder-form-row">
                <div className="token-seg" role="tablist">
                  {SCHEDULE_KINDS.map((k) => (
                    <button
                      key={k.id}
                      className={(form.schedule_kind ?? "interval") === k.id ? "seg active" : "seg"}
                      onClick={() => setScheduleKind(k.id)}
                    >
                      {t(k.labelKey)}
                    </button>
                  ))}
                </div>
                {(form.schedule_kind ?? "interval") === "interval" && (
                  <label>
                    {t("reminders.form.interval")}
                    <input
                      type="number"
                      min={1}
                      max={1440}
                      value={form.interval_minutes}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, interval_minutes: Number(e.target.value) || 0 }))
                      }
                    />
                  </label>
                )}
                {(form.schedule_kind ?? "interval") === "daily" && (
                  <label>
                    {t("tasks.schedule.at")}
                    <input
                      type="time"
                      value={form.schedule_at ?? ""}
                      onChange={(e) => setForm((f) => ({ ...f, schedule_at: e.target.value || null }))}
                    />
                  </label>
                )}
                {(form.schedule_kind ?? "interval") === "once" && (
                  <label>
                    {t("tasks.schedule.datetime")}
                    <input
                      type="datetime-local"
                      value={onceToLocalInput(form.schedule_at)}
                      onChange={(e) => {
                        // datetime-local 值 "YYYY-MM-DDTHH:MM"——与存储格式一致
                        setForm((f) => ({ ...f, schedule_at: e.target.value || null }));
                      }}
                    />
                  </label>
                )}
                <label className="reminder-check">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                  />
                  {t("reminders.enabled")}
                </label>
                {form.action_type === "notify" && (
                  <label className="reminder-check">
                    <input
                      type="checkbox"
                      checked={form.use_fireworks}
                      onChange={(e) => setForm((f) => ({ ...f, use_fireworks: e.target.checked }))}
                    />
                    {t("reminders.form.fireworksMode")}
                  </label>
                )}
                {/* 调度行是末行的分支（once / interval+exec——后面无窗口/星期行）：
                    按钮并入本行右端 */}
                {((form.schedule_kind ?? "interval") === "once" ||
                  ((form.schedule_kind ?? "interval") === "interval" &&
                    form.action_type === "exec")) &&
                  formActions}
              </div>

              {/* interval + notify 的时间窗（v1 字段；daily/once/exec 不显示）——
                  该分支的末行：按钮并入右端 */}
              {(form.schedule_kind ?? "interval") === "interval" &&
                form.action_type === "notify" && (
                  <div className="reminder-form-row">
                    <label>
                      {t("reminders.form.start")}
                      <input
                        type="time"
                        value={form.start_time ?? ""}
                        onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value || null }))}
                      />
                    </label>
                    <label>
                      {t("reminders.form.end")}
                      <input
                        type="time"
                        value={form.end_time ?? ""}
                        onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value || null }))}
                      />
                    </label>
                    {formActions}
                  </div>
                )}

              {/* daily 的星期过滤（不勾 = 每天）——该分支的末行：按钮并入右端 */}
              {(form.schedule_kind ?? "interval") === "daily" && (
                <div className="task-weekdays">
                  <span className="task-weekdays-label">{t("tasks.schedule.weekdays")}</span>
                  {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                    <label key={d} className="task-weekday-check">
                      <input type="checkbox" checked={weekdays.includes(d)} onChange={() => toggleWeekday(d)} />
                      {t(`tasks.weekday.${d}`)}
                    </label>
                  ))}
                  {formActions}
                </div>
              )}

              {form.action_type === "notify" &&
                (form.schedule_kind ?? "interval") === "interval" &&
                form.start_time &&
                form.end_time &&
                form.start_time > form.end_time && (
                  <p className="reminder-hint">
                    {t("reminders.form.crossMidnight", { start: form.start_time, end: form.end_time })}
                  </p>
                )}
            </>
          )}
          {formError && <p className="reminder-form-error">{formError}</p>}
          {/* todo 编辑态：无字段行（锁定表单只留提示）——按钮组 margin-left:auto
              在 flex-column 表单内天然右对齐（其余分支按钮已并入各自末行） */}
          {form.kind === "todo" && formActions}
        </div>
      </section>

      {/* 执行历史区（§4.7 折叠面板：action_logs 倒序分页 + 过滤 + 展开） */}
      <section className="token-section">
        <h3>
          <button
            className="seg task-history-toggle"
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen((v) => !v)}
          >
            {historyOpen ? "▾" : "▸"} {t("tasks.history.title")}
          </button>
        </h3>
        {historyOpen && (
          <div className="task-history">
            <div className="task-history-controls">
              <select
                value={historyFilter ?? ""}
                onChange={(e) => {
                  setHistoryFilter(e.target.value ? Number(e.target.value) : null);
                  setHistoryPage(1);
                }}
              >
                <option value="">{t("tasks.history.filterAll")}</option>
                {rules
                  .filter((r) => r.action_type === "exec")
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {actionBadge(r)} {r.label}
                    </option>
                  ))}
              </select>
              <span className="reminder-meta">
                {t("tasks.history.page", {
                  page: history?.page ?? 1,
                  pages: totalPages,
                  total: history?.total ?? 0,
                })}
              </span>
              <button
                className="seg"
                disabled={(history?.page ?? 1) <= 1}
                onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
              >
                {t("tasks.history.prev")}
              </button>
              <button
                className="seg"
                disabled={(history?.page ?? 1) >= totalPages}
                onClick={() => setHistoryPage((p) => p + 1)}
              >
                {t("tasks.history.next")}
              </button>
            </div>
            {historyError && <p className="reminder-form-error">{historyError}</p>}
            {history && history.rows.length === 0 && (
              <p className="token-empty">{t("tasks.history.empty")}</p>
            )}
            <ul className="task-history-list">
              {history?.rows.map((log) => {
                // 补跑延迟：scheduled_at 与 started_at 差（秒）
                const delaySec =
                  log.scheduled_at && log.started_at
                    ? Math.max(
                        0,
                        Math.round(
                          (new Date(log.started_at).getTime() - new Date(log.scheduled_at).getTime()) / 1000,
                        ),
                      )
                    : 0;
                return (
                  <li key={log.id} className="task-history-item">
                    <button
                      className="task-history-row"
                      onClick={() => setExpandedLog((cur) => (cur === log.id ? null : log.id))}
                    >
                      <span className={`task-status-dot status-${log.status}`} aria-label={log.status} />
                      <span className="task-history-time">{formatLogTime(log.started_at)}</span>
                      <span className="task-badge">{log.action_type === "exec" ? "⚡" : "💧"}</span>
                      <span className="task-history-summary">
                        {renderTaskSummary(log.summary, log.exit_code)}
                      </span>
                      <span className="task-history-status">{t(`tasks.status.${log.status}`)}</span>
                    </button>
                    {expandedLog === log.id && (
                      <div className="task-history-detail">
                        {delaySec > 0 && (
                          <p className="reminder-meta">
                            {t("tasks.history.delay", { sec: delaySec })}
                          </p>
                        )}
                        <p className="task-detail-label">{t("tasks.history.output")}</p>
                        <pre className="task-output mono">
                          {log.output_tail ?? "—"}
                        </pre>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      {/* 历史统计（TC-RM-13，notify 记账） */}
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
