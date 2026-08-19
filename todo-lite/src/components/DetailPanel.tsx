import { useCallback, useEffect, useRef, useState } from "react";
import { useTaskStore } from "../store/useTaskStore";
import { useUIStore } from "../store/useUIStore";
import { useListsStore } from "../store/useListsStore";
import * as db from "../lib/db";
import { toDateStr } from "../lib/repeat";
import type { Priority, RepeatRule, Task, TaskWithTags } from "../types";
import { CheckIcon, ClockIcon, FlagIcon, SunIcon, TrashIcon } from "./Icons";

const PRIORITIES: { value: Priority; label: string }[] = [
  { value: 0, label: "无" },
  { value: 1, label: "低" },
  { value: 2, label: "中" },
  { value: 3, label: "高" },
];

const REPEATS: { value: string; label: string }[] = [
  { value: "", label: "不重复" },
  { value: "daily", label: "每天" },
  { value: "weekdays", label: "每个工作日" },
  { value: "weekly", label: "每周" },
  { value: "monthly", label: "每月" },
  { value: "yearly", label: "每年" },
];

function nextMonday(): Date {
  const d = new Date();
  const day = d.getDay();
  const diff = day === 0 ? 1 : 8 - day;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + diff);
}

function formatTimeRange(reminderAt: string | null): string {
  if (!reminderAt) return "";
  const d = new Date(reminderAt.replace(" ", "T"));
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const label = sameDay ? "今天" : `${d.getMonth() + 1}月${d.getDate()}日`;
  return `${label} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function DetailPanel() {
  const { selectedTaskId, detailOpen, toggleDetail, detailBump } = useUIStore();
  const { updateTask, toggleComplete, deleteTask, setTags } = useTaskStore();
  const { tags: allTags, addTag } = useListsStore();

  const [task, setTask] = useState<TaskWithTags | null>(null);
  const [subtasks, setSubtasks] = useState<Task[]>([]);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [newSubtask, setNewSubtask] = useState("");
  const [showTagPicker, setShowTagPicker] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [reminderDate, setReminderDate] = useState("");
  const [reminderTime, setReminderTime] = useState("09:00");
  const notesTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    if (!selectedTaskId) return;
    const [t, subs] = await Promise.all([db.getTaskById(selectedTaskId), db.getSubtasks(selectedTaskId)]);
    setTask(t);
    setSubtasks(subs);
    if (t?.reminder_at) {
      setReminderDate(t.reminder_at.slice(0, 10));
      setReminderTime(t.reminder_at.slice(11, 16));
    }
  }, [selectedTaskId]);

  useEffect(() => {
    if (detailOpen && selectedTaskId) {
      refresh();
      setEditingTitle(false);
      setShowTagPicker(false);
      setNotesDraft("");
      setNewSubtask("");
    }
  }, [detailOpen, selectedTaskId, detailBump, refresh]);

  useEffect(() => {
    if (!detailOpen || !task) return;
    setNotesDraft(task.notes ?? "");
  }, [task?.notes, detailOpen]);

  if (!detailOpen || !task) return null;

  const apply = async (patch: Partial<Task>) => {
    await updateTask(task.id, patch);
    await refresh();
  };

  const saveTitle = async () => {
    setEditingTitle(false);
    const t = titleDraft.trim();
    if (t && t !== task.title) await apply({ title: t });
  };

  const saveNotes = async (value: string) => {
    if (value !== (task.notes ?? "")) await apply({ notes: value || null });
  };

  const onNotesChange = (value: string) => {
    setNotesDraft(value);
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesTimer.current = setTimeout(() => void saveNotes(value), 400);
  };

  const setPriority = (p: Priority) => apply({ priority: p });

  const setDueDate = (d: string | null) => apply({ due_date: d });

  const setReminder = async () => {
    const t = reminderTime || "09:00";
    await apply({ reminder_at: `${reminderDate} ${t}:00` });
  };

  const clearReminder = () => apply({ reminder_at: null });

  const setRepeat = (type: string) =>
    apply({ repeat_rule: type ? (JSON.stringify({ type }) as string) : null });

  const toggleFlag = () => apply({ flagged: task.flagged === 1 ? 0 : 1 });

  const toggleMyDay = () => {
    const today = toDateStr(new Date());
    apply({ my_day_date: task.my_day_date ? null : today });
  };

  const addSubtask = async () => {
    const t = newSubtask.trim();
    if (!t) return;
    await db.createSubtask(task.id, t);
    setNewSubtask("");
    await refresh();
  };

  const toggleSub = async (sub: Task) => {
    await db.toggleSubtask(sub);
    await refresh();
  };

  const removeSub = async (sub: Task) => {
    await db.deleteSubtask(sub.id);
    await refresh();
  };

  const toggleTag = async (tagId: number) => {
    const has = task.tags.some((t) => t.id === tagId);
    const next = has ? task.tags.filter((t) => t.id !== tagId).map((t) => t.id) : [...task.tags.map((t) => t.id), tagId];
    await setTags(task.id, next);
    await refresh();
  };

  const createNewTag = async () => {
    const name = newTagName.trim();
    if (!name) return;
    const tag = await addTag(name, "#64748b");
    await setTags(task.id, [...task.tags.map((t) => t.id), tag.id]);
    setNewTagName("");
    setShowTagPicker(false);
    await refresh();
  };

  const removeTask = async () => {
    await deleteTask(task.id);
    toggleDetail(false);
  };

  const onPanelClick = (e: React.MouseEvent) => {
    const el = e.target as HTMLElement;
    if (
      el.closest(
        "input, textarea, select, button, label, .check-circle, .subtask-item, .detail-task-title, .tag-pill, .tag-option, .reminder-text",
      )
    ) {
      return;
    }
    toggleDetail(false);
  };

  const subtaskDone = subtasks.filter((s) => s.completed_at).length;

  return (
    <aside className="detail-panel" onClick={onPanelClick}>
      <div className="detail-head">
        <span className="detail-title">任务详情</span>
        <button className="detail-close" onClick={() => toggleDetail(false)} title="关闭">
          ✕
        </button>
      </div>

      {editingTitle ? (
        <input
          className="detail-title-input"
          value={titleDraft}
          autoFocus
          onChange={(e) => setTitleDraft(e.target.value)}
          onBlur={saveTitle}
          onKeyDown={(e) => e.key === "Enter" && saveTitle()}
        />
      ) : (
        <div
          className={`detail-task-title ${task.completed_at ? "completed" : ""}`}
          onClick={() => {
            setTitleDraft(task.title);
            setEditingTitle(true);
          }}
          title="点击编辑"
        >
          {task.title}
        </div>
      )}

      <div className="detail-actions">
        <button className={`detail-btn ${task.my_day_date ? "active" : ""}`} onClick={toggleMyDay}>
          <SunIcon width={14} height={14} />
          我的某天
        </button>
        <button className={`detail-btn ${task.flagged ? "active" : ""}`} onClick={toggleFlag}>
          <FlagIcon width={14} height={14} />
          旗标
        </button>
        <button
          className={`detail-btn ${task.completed_at ? "active" : ""}`}
          onClick={async () => {
            await toggleComplete(task);
            toggleDetail(false);
          }}
        >
          <CheckIcon width={14} height={14} />
          完成
        </button>
      </div>

      <div className="detail-section">
        <label>优先级</label>
        <div className="priority-row">
          {PRIORITIES.map((p) => (
            <button
              key={p.value}
              className={`detail-btn ${task.priority === p.value ? `active p${p.value}` : ""}`}
              onClick={() => setPriority(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="detail-section">
        <label>截止日期</label>
        <div className="due-row">
          <button className="detail-btn" onClick={() => setDueDate(toDateStr(new Date()))}>
            今天
          </button>
          <button
            className="detail-btn"
            onClick={() => setDueDate(toDateStr(new Date(Date.now() + 86400000)))}
          >
            明天
          </button>
          <button className="detail-btn" onClick={() => setDueDate(toDateStr(nextMonday()))}>
            下周
          </button>
          {task.due_date && (
            <button className="detail-btn danger" onClick={() => setDueDate(null)}>
              清除
            </button>
          )}
        </div>
        <div className="due-row">
          <input
            type="date"
            value={task.due_date ?? ""}
            onChange={(e) => setDueDate(e.target.value || null)}
          />
          <input
            type="time"
            value={task.due_time ?? ""}
            onChange={(e) => apply({ due_time: e.target.value || null })}
          />
        </div>
      </div>

      <div className="detail-section">
        <label>提醒</label>
        {task.reminder_at ? (
          <div className="due-row">
            <span className="reminder-text">{formatTimeRange(task.reminder_at)}</span>
            <button className="detail-btn" onClick={clearReminder}>
              清除提醒
            </button>
          </div>
        ) : (
          <div className="due-row">
            <input type="date" value={reminderDate} onChange={(e) => setReminderDate(e.target.value)} />
            <input type="time" value={reminderTime} onChange={(e) => setReminderTime(e.target.value)} />
            <button
              className="detail-btn"
              onClick={setReminder}
              disabled={!reminderDate}
              title="设置提醒"
            >
              <ClockIcon width={14} height={14} />
            </button>
          </div>
        )}
      </div>

      <div className="detail-section">
        <label>重复</label>
        <select
          className="detail-select"
          value={task.repeat_rule ? ((JSON.parse(task.repeat_rule) as RepeatRule).type ?? "") : ""}
          onChange={(e) => setRepeat(e.target.value)}
        >
          {REPEATS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      <div className="detail-section">
        <label>标签</label>
        <div className="tag-row">
          {task.tags.map((t) => (
            <span key={t.id} className="tag-pill" style={{ background: t.color }}>
              {t.name}
              <button className="tag-remove" onClick={() => toggleTag(t.id)}>
                ✕
              </button>
            </span>
          ))}
          <button className="detail-btn small" onClick={() => setShowTagPicker(!showTagPicker)}>
            + 标签
          </button>
        </div>
        {showTagPicker && (
          <div className="tag-picker">
            {allTags.map((t) => (
              <label key={t.id} className="tag-option">
                <input
                  type="checkbox"
                  checked={task.tags.some((x) => x.id === t.id)}
                  onChange={() => toggleTag(t.id)}
                />
                <span className="tag-pill" style={{ background: t.color }}>
                  {t.name}
                </span>
              </label>
            ))}
            <div className="tag-new">
              <input
                type="text"
                placeholder="新标签名称"
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && createNewTag()}
              />
              <button className="detail-btn small" onClick={createNewTag}>
                创建
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="detail-section">
        <label>备注</label>
        <textarea
          className="notes-input"
          rows={4}
          placeholder="添加备注…"
          value={notesDraft}
          onChange={(e) => onNotesChange(e.target.value)}
          onBlur={() => saveNotes(notesDraft)}
        />
      </div>

      <div className="detail-section">
        <label>
          子任务 {subtasks.length > 0 && `(${subtaskDone}/${subtasks.length})`}
        </label>
        <div className="subtask-list">
          {subtasks.map((s) => (
            <div key={s.id} className="subtask-item">
              <div
                className={`check-circle small ${s.completed_at ? "checked" : ""}`}
                onClick={() => toggleSub(s)}
              >
                <CheckIcon width={10} height={10} />
              </div>
              <span className={`subtask-title ${s.completed_at ? "completed" : ""}`}>{s.title}</span>
              <button className="icon-btn" onClick={() => removeSub(s)} title="删除子任务">
                <TrashIcon width={12} height={12} />
              </button>
            </div>
          ))}
        </div>
        <div className="subtask-add">
          <input
            type="text"
            placeholder="添加子任务…"
            value={newSubtask}
            onChange={(e) => setNewSubtask(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addSubtask()}
          />
        </div>
      </div>

      <div className="detail-footer">
        {task.my_day_date && (
          <button className="detail-btn" onClick={toggleMyDay}>
            从我的某天移除
          </button>
        )}
        <button className="detail-btn danger" onClick={removeTask}>
          <TrashIcon width={14} height={14} />
          删除任务
        </button>
      </div>
    </aside>
  );
}
