import { useCallback, useEffect, useMemo, useState } from "react";
import {
  completeTodo,
  composeDue,
  deleteTodo,
  fetchPlugins,
  fetchTodos,
  formatDue,
  formatTodoTime,
  priorityLabel,
  reorderTodos,
  splitDue,
  upsertTodo,
  validateTodoInput,
  dueHasTime,
  isTauriRuntime,
  type PluginInfo,
  type TodoInput,
  type TodoItem,
} from "../../lib/todos";
import { t, useLangStore } from "../../lib/i18n";

/**
 * Todo 插件页（内置 built-in-todo，DESIGN §8，TC-TD-01/02/04/05）：
 * - 列表按 sort_order 排序（↑↓ 重排立即生效，TC-TD-02）；
 * - CRUD：title/notes/priority(0-3)/due(date+可选 time)/remind_before/tags；
 * - 完成勾选：completed_at 写入 + 派生提醒级联删（Rust 侧）；waving/气泡
 *   由 pet 窗口监听 `todo://completed` 呈现（TC-TD-04/05）；
 * - 头部展示插件 manifest 信息（TC-TD-01：manifest 与 plugins 表核对入口）；
 * - 派生提醒说明：due 带时间且提前提醒>0 → reminders 表 kind='todo' 单次行
 *   （TC-TD-03/08；remind_before=0 → 完全无提醒）。
 * - M8 i18n：全部文案经 t() 随当前语言。
 */

interface FormState {
  title: string;
  notes: string;
  priority: number;
  dueDate: string;
  dueTime: string;
  remindBefore: number;
  tags: string;
}

const EMPTY_FORM: FormState = {
  title: "",
  notes: "",
  priority: 0,
  dueDate: "",
  dueTime: "",
  remindBefore: 5,
  tags: "",
};

function itemToForm(t: TodoItem): FormState {
  const { date, time } = splitDue(t.due_date);
  return {
    title: t.title,
    notes: t.notes ?? "",
    priority: t.priority,
    dueDate: date,
    dueTime: time,
    remindBefore: t.remind_before_minutes,
    tags: t.tags.join(", "),
  };
}

function formToInput(f: FormState, sortOrder: number): TodoInput {
  return {
    title: f.title.trim(),
    notes: f.notes.trim() || null,
    priority: f.priority,
    due_date: composeDue(f.dueDate, f.dueTime),
    remind_before_minutes: f.remindBefore,
    sort_order: sortOrder,
    tags: f.tags
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean),
  };
}

export default function Todo() {
  useLangStore((s) => s.lang); // M8 i18n：语言变化时本页文案重渲染
  const [items, setItems] = useState<TodoItem[] | null>(null);
  const [plugins, setPlugins] = useState<PluginInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<TodoItem | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** 两步删除确认（与 Reminders 同模式）。 */
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!isTauriRuntime()) {
      setError(t("todo.needApp"));
      return;
    }
    try {
      const [todos, pls] = await Promise.all([fetchTodos(), fetchPlugins()]);
      setItems(todos);
      setPlugins(pls);
      setError(null);
    } catch (e) {
      setError(t("todo.loadFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const refresh = () => void load();

  const save = async () => {
    const input = formToInput(form, editing?.sort_order ?? (items?.length ?? 0));
    const err = validateTodoInput(input);
    if (err) {
      setFormError(err);
      return;
    }
    setFormError(null);
    try {
      await upsertTodo(editing?.id ?? null, input);
      setEditing(null);
      setForm(EMPTY_FORM);
      refresh();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async (item: TodoItem) => {
    if (confirmDeleteId !== item.id) {
      setConfirmDeleteId(item.id);
      setTimeout(() => {
        setConfirmDeleteId((cur) => (cur === item.id ? null : cur));
      }, 3000);
      return;
    }
    setConfirmDeleteId(null);
    try {
      await deleteTodo(item.id);
      if (editing?.id === item.id) {
        setEditing(null);
        setForm(EMPTY_FORM);
      }
      refresh();
    } catch (e) {
      showToast(t("todo.toast.deleteFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  };

  /** 完成/取消完成：完成时派生提醒级联删 + 宠物 waving（Rust 事件广播）。 */
  const toggleComplete = async (item: TodoItem) => {
    try {
      await completeTodo(item.id, item.completed_at === null);
      refresh();
    } catch (e) {
      showToast(t("todo.toast.updateFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  };

  const move = async (item: TodoItem, dir: -1 | 1) => {
    if (!items) return;
    const i = items.findIndex((x) => x.id === item.id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j], next[i]];
    try {
      setItems(await reorderTodos(next.map((x) => x.id)));
    } catch (e) {
      showToast(t("todo.toast.reorderFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  };

  const startEdit = (item: TodoItem) => {
    setEditing(item);
    setForm(itemToForm(item));
    setFormError(null);
  };

  const todoPlugin = plugins?.find((p) => p.id === "built-in-todo") ?? null;
  /** 今日完成数（展示；权威统计在 Rust 完成事件里）。 */
  const doneToday = useMemo(() => {
    if (!items) return 0;
    const p = (n: number) => String(n).padStart(2, "0");
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
    const localDate = (ts: string) => {
      const d = new Date(ts);
      return Number.isNaN(d.getTime())
        ? null
        : `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    };
    return items.filter((t) => t.completed_at && localDate(t.completed_at) === todayStr)
      .length;
  }, [items]);

  if (error) {
    return <div className="token-error">{error}</div>;
  }
  if (!items) {
    return <p className="token-empty">{t("todo.loading")}</p>;
  }

  const openCount = items.filter((t) => t.completed_at === null).length;

  return (
    <div className="todo-plugin">
      {/* 插件 manifest 信息（TC-TD-01：manifest + plugins 表核对入口） */}
      <div className="todo-plugin-meta">
        {todoPlugin ? (
          <span>
            {t("todo.plugin.prefix")} <strong>{todoPlugin.name}</strong>（{todoPlugin.id} v{todoPlugin.version}
            ，manifest v{todoPlugin.manifest_version}）
            {todoPlugin.enabled
              ? ` · ${t("todo.plugin.enabled")}`
              : ` · ${t("todo.plugin.disabled")}`}
            {" "}&middot; {t("todo.plugin.permissions")}:{" "}
            {todoPlugin.permissions.join(", ")}
          </span>
        ) : (
          <span>{t("todo.plugin.loading")}</span>
        )}
      </div>

      <section className="token-section">
        <h3>{t("todo.tasks.title", { open: openCount, done: doneToday })}</h3>
        {items.length === 0 && (
          <p className="token-empty">{t("todo.tasks.empty")}</p>
        )}
        <ul className="todo-list">
          {items.map((item, idx) => (
            <li
              key={item.id}
              className={item.completed_at ? "todo-item done" : "todo-item"}
            >
              <label
                className="todo-check"
                title={item.completed_at ? t("todo.uncomplete") : t("todo.complete")}
              >
                <input
                  type="checkbox"
                  checked={item.completed_at !== null}
                  onChange={() => void toggleComplete(item)}
                />
              </label>
              <span className="todo-main">
                <span className="todo-title" title={item.title}>
                  {item.title}
                </span>
                {item.notes && <span className="todo-notes">{item.notes}</span>}
                <span className="todo-meta">
                  <span className={`todo-priority p${item.priority}`}>
                    {priorityLabel(item.priority)}
                  </span>
                  <span
                    title={
                      dueHasTime(item.due_date)
                        ? t("todo.form.dueTimeTitle")
                        : t("todo.form.dueTitle")
                    }
                  >
                    🕒 {formatDue(item.due_date)}
                  </span>
                  {item.completed_at === null && item.remind_before_minutes > 0 && dueHasTime(item.due_date) && (
                    <span title={t("todo.form.remindBeforeTitle")}>
                      🔔 {t("todo.form.remindBeforeNote", { n: item.remind_before_minutes })}
                    </span>
                  )}
                  {item.tags.length > 0 && (
                    <span className="todo-tags">
                      {item.tags.map((g) => (
                        <code key={g}>{g}</code>
                      ))}
                    </span>
                  )}
                  {item.completed_at && <span>✅ {formatTodoTime(item.completed_at)}</span>}
                </span>
              </span>
              <span className="todo-actions">
                <button
                  className="seg"
                  disabled={idx === 0}
                  onClick={() => void move(item, -1)}
                  title={t("todo.moveUp")}
                >
                  ↑
                </button>
                <button
                  className="seg"
                  disabled={idx === items.length - 1}
                  onClick={() => void move(item, 1)}
                  title={t("todo.moveDown")}
                >
                  ↓
                </button>
                <button className="seg" onClick={() => startEdit(item)}>
                  {t("todo.edit")}
                </button>
                <button
                  className="seg danger"
                  onClick={() => void remove(item)}
                  title={confirmDeleteId === item.id ? t("todo.deleteHint") : t("todo.delete")}
                >
                  {confirmDeleteId === item.id ? t("todo.deleteConfirm") : t("todo.delete")}
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* 新建 / 编辑表单（R2 P2-2：容器复用 reminder-form——M2 控件规格基线
          32px/2px 边框/禁用态挂在该选择器下，todo-form 无规则致 UA 默认渲染） */}
      <section className="token-section">
        <h3>
          {editing ? t("todo.form.editTitle", { n: editing.id }) : t("todo.form.newTitle")}
        </h3>
        <div className="reminder-form">
          <div className="reminder-form-row">
            <label className="grow">
              {t("todo.form.title")}
              <input
                type="text"
                value={form.title}
                maxLength={140}
                placeholder={t("todo.form.titlePlaceholder")}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </label>
            <label>
              {t("todo.form.priority")}
              <select
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
              >
                <option value={0}>{t("todo.priority.0")}</option>
                <option value={1}>{t("todo.priority.1")}</option>
                <option value={2}>{t("todo.priority.2")}</option>
                <option value={3}>{t("todo.priority.3")}</option>
              </select>
            </label>
          </div>
          <div className="reminder-form-row">
            <label>
              {t("todo.form.dueDate")}
              <input
                type="date"
                value={form.dueDate}
                onChange={(e) => setForm((f) => ({ ...f, dueDate: e.target.value }))}
              />
            </label>
            <label>
              {t("todo.form.dueTime")}
              <input
                type="time"
                value={form.dueTime}
                onChange={(e) => setForm((f) => ({ ...f, dueTime: e.target.value }))}
              />
            </label>
            <label>
              {t("todo.form.remindBefore")}
              <input
                type="number"
                min={0}
                max={10080}
                value={form.remindBefore}
                onChange={(e) =>
                  setForm((f) => ({ ...f, remindBefore: Number(e.target.value) || 0 }))
                }
              />
            </label>
            <label className="grow">
              {t("todo.form.tags")}
              <input
                type="text"
                value={form.tags}
                placeholder={t("todo.form.tagsPlaceholder")}
                onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
              />
            </label>
          </div>
          <div className="reminder-form-row">
            <label className="grow">
              {t("todo.form.notes")}
              <input
                type="text"
                value={form.notes}
                maxLength={2000}
                placeholder={t("todo.form.notesPlaceholder")}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </label>
          </div>
          <p className="reminder-hint">{t("todo.form.hint")}</p>
          {formError && <p className="reminder-form-error">{formError}</p>}
          <div className="reminder-form-actions">
            <button className="seg primary" onClick={() => void save()}>
              {editing ? t("todo.form.save") : t("todo.form.create")}
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
                {t("todo.form.cancel")}
              </button>
            )}
          </div>
        </div>
      </section>

      {toast && <div className="reminder-toast">{toast}</div>}
    </div>
  );
}
