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

/**
 * Todo 插件页（内置 built-in-todo，DESIGN §8，TC-TD-01/02/04/05）：
 * - 列表按 sort_order 排序（↑↓ 重排立即生效，TC-TD-02）；
 * - CRUD：title/notes/priority(0-3)/due(date+可选 time)/remind_before/tags；
 * - 完成勾选：completed_at 写入 + 派生提醒级联删（Rust 侧）；waving/气泡
 *   由 pet 窗口监听 `todo://completed` 呈现（TC-TD-04/05）；
 * - 头部展示插件 manifest 信息（TC-TD-01：manifest 与 plugins 表核对入口）；
 * - 派生提醒说明：due 带时间且提前提醒>0 → reminders 表 kind='todo' 单次行
 *   （TC-TD-03/08；remind_before=0 → 完全无提醒）。
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
      setError("Todo 需要在 PulsePet App（Tauri）内使用");
      return;
    }
    try {
      const [todos, pls] = await Promise.all([fetchTodos(), fetchPlugins()]);
      setItems(todos);
      setPlugins(pls);
      setError(null);
    } catch (e) {
      setError(`读取 Todo 失败：${e instanceof Error ? e.message : String(e)}`);
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

  const remove = async (t: TodoItem) => {
    if (confirmDeleteId !== t.id) {
      setConfirmDeleteId(t.id);
      setTimeout(() => {
        setConfirmDeleteId((cur) => (cur === t.id ? null : cur));
      }, 3000);
      return;
    }
    setConfirmDeleteId(null);
    try {
      await deleteTodo(t.id);
      if (editing?.id === t.id) {
        setEditing(null);
        setForm(EMPTY_FORM);
      }
      refresh();
    } catch (e) {
      showToast(`删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  /** 完成/取消完成：完成时派生提醒级联删 + 宠物 waving（Rust 事件广播）。 */
  const toggleComplete = async (t: TodoItem) => {
    try {
      await completeTodo(t.id, t.completed_at === null);
      refresh();
    } catch (e) {
      showToast(`更新失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const move = async (t: TodoItem, dir: -1 | 1) => {
    if (!items) return;
    const i = items.findIndex((x) => x.id === t.id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j], next[i]];
    try {
      setItems(await reorderTodos(next.map((x) => x.id)));
    } catch (e) {
      showToast(`重排失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const startEdit = (t: TodoItem) => {
    setEditing(t);
    setForm(itemToForm(t));
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
    return <p className="token-empty">读取 Todo…</p>;
  }

  const openCount = items.filter((t) => t.completed_at === null).length;

  return (
    <div className="todo-plugin">
      {/* 插件 manifest 信息（TC-TD-01：manifest + plugins 表核对入口） */}
      <div className="todo-plugin-meta">
        {todoPlugin ? (
          <span>
            插件 <strong>{todoPlugin.name}</strong>（{todoPlugin.id} v{todoPlugin.version}
            ，manifest v{todoPlugin.manifest_version}）
            {todoPlugin.enabled ? " · 已启用" : " · 已停用"} · 权限：{" "}
            {todoPlugin.permissions.join(", ")}
          </span>
        ) : (
          <span>内置 Todo 插件（manifest 读取中…）</span>
        )}
      </div>

      <section className="token-section">
        <h3>
          任务（未完成 {openCount} · 今日已完成 {doneToday}）
        </h3>
        {items.length === 0 && (
          <p className="token-empty">还没有任务，从下方表单新建一个吧。</p>
        )}
        <ul className="todo-list">
          {items.map((t, idx) => (
            <li
              key={t.id}
              className={t.completed_at ? "todo-item done" : "todo-item"}
            >
              <label className="todo-check" title={t.completed_at ? "取消完成" : "完成"}>
                <input
                  type="checkbox"
                  checked={t.completed_at !== null}
                  onChange={() => void toggleComplete(t)}
                />
              </label>
              <span className="todo-main">
                <span className="todo-title" title={t.title}>
                  {t.title}
                </span>
                {t.notes && <span className="todo-notes">{t.notes}</span>}
                <span className="todo-meta">
                  <span className={`todo-priority p${t.priority}`}>
                    {priorityLabel(t.priority)}
                  </span>
                  <span title={dueHasTime(t.due_date) ? "截止（带时间，可派生提醒）" : "截止"}>
                    🕒 {formatDue(t.due_date)}
                  </span>
                  {t.completed_at === null && t.remind_before_minutes > 0 && dueHasTime(t.due_date) && (
                    <span title="到点前 N 分钟宠物气泡提醒（reminders kind='todo' 单次）">
                      🔔 提前 {t.remind_before_minutes} 分钟
                    </span>
                  )}
                  {t.tags.length > 0 && (
                    <span className="todo-tags">
                      {t.tags.map((g) => (
                        <code key={g}>{g}</code>
                      ))}
                    </span>
                  )}
                  {t.completed_at && <span>✅ {formatTodoTime(t.completed_at)}</span>}
                </span>
              </span>
              <span className="todo-actions">
                <button
                  className="seg"
                  disabled={idx === 0}
                  onClick={() => void move(t, -1)}
                  title="上移（sort_order 重排立即生效）"
                >
                  ↑
                </button>
                <button
                  className="seg"
                  disabled={idx === items.length - 1}
                  onClick={() => void move(t, 1)}
                  title="下移"
                >
                  ↓
                </button>
                <button className="seg" onClick={() => startEdit(t)}>
                  编辑
                </button>
                <button
                  className="seg danger"
                  onClick={() => void remove(t)}
                  title={confirmDeleteId === t.id ? "再次点击确认删除" : "删除"}
                >
                  {confirmDeleteId === t.id ? "确认删除？" : "删除"}
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* 新建 / 编辑表单 */}
      <section className="token-section">
        <h3>{editing ? `编辑任务 #${editing.id}` : "新建任务"}</h3>
        <div className="todo-form">
          <div className="reminder-form-row">
            <label className="grow">
              标题（必填，1-140 字符）
              <input
                type="text"
                value={form.title}
                maxLength={140}
                placeholder="如：交周报"
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </label>
            <label>
              优先级
              <select
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
              >
                <option value={0}>无</option>
                <option value={1}>低</option>
                <option value={2}>中</option>
                <option value={3}>高</option>
              </select>
            </label>
          </div>
          <div className="reminder-form-row">
            <label>
              截止日期
              <input
                type="date"
                value={form.dueDate}
                onChange={(e) => setForm((f) => ({ ...f, dueDate: e.target.value }))}
              />
            </label>
            <label>
              截止时间（可选；带时间才派生提醒）
              <input
                type="time"
                value={form.dueTime}
                onChange={(e) => setForm((f) => ({ ...f, dueTime: e.target.value }))}
              />
            </label>
            <label>
              提前提醒（分钟，0 = 完全无提醒）
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
              标签（逗号分隔）
              <input
                type="text"
                value={form.tags}
                placeholder="如：work, 紧急"
                onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
              />
            </label>
          </div>
          <div className="reminder-form-row">
            <label className="grow">
              备注
              <input
                type="text"
                value={form.notes}
                placeholder="可选"
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </label>
          </div>
          <p className="reminder-hint">
            带时间的截止 + 提前提醒 &gt; 0 → 到点前宠物气泡「还有 X 分钟要完成「任务名」」
            （reminders 派生单次行，TC-TD-03）；提前提醒 = 0 → 完全无提醒（TC-TD-08）。
          </p>
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

      {toast && <div className="reminder-toast">{toast}</div>}
    </div>
  );
}
