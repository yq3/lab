import type { TaskWithTags } from "../types";
import { CheckIcon, ClockIcon, FlagIcon, ListIcon, TrashIcon } from "./Icons";

export function formatDueDate(dueDate: string): string {
  const today = new Date();
  const d = new Date(dueDate + "T00:00:00");
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "今天";
  if (diff === 1) return "明天";
  if (diff === -1) return "昨天";
  if (diff > 1 && diff < 7) return `${diff} 天后`;
  if (diff < -1 && diff > -7) return `${-diff} 天前`;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

export function isOverdue(task: TaskWithTags): boolean {
  if (!task.due_date || task.completed_at) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(task.due_date + "T00:00:00") < today;
}

interface Props {
  task: TaskWithTags;
  selected: boolean;
  onSelect: (id: number) => void;
  onToggleComplete: (task: TaskWithTags) => void;
  onDelete?: (task: TaskWithTags) => void;
}

export function TaskItem({ task, selected, onSelect, onToggleComplete, onDelete }: Props) {
  const due = task.due_date ? formatDueDate(task.due_date) : null;
  const overdue = isOverdue(task);

  return (
    <div
      className={`task-item ${selected ? "selected" : ""}`}
      onClick={() => onSelect(task.id)}
    >
      {task.priority > 0 && <span className={`priority-dot p${task.priority}`} />}
      <div
        className={`check-circle ${task.completed_at ? "checked" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          onToggleComplete(task);
        }}
        title={task.completed_at ? "标记为未完成" : "完成任务"}
      >
        <CheckIcon width={12} height={12} />
      </div>
      <div className="task-body">
        <div className={`task-title ${task.completed_at ? "completed" : ""}`}>{task.title}</div>
        <div className="task-sub">
          {due && <span className={`sub-item ${overdue ? "overdue" : ""}`}>{due}</span>}
          {task.due_time && <span className="sub-item">{task.due_time}</span>}
          {task.reminder_at && (
            <span className="sub-item">
              <ClockIcon width={12} height={12} />
              {task.reminder_at.slice(11, 16)}
            </span>
          )}
          {task.subtask_count ? (
            <span className="sub-item">
              <ListIcon width={12} height={12} />
              {task.subtask_done}/{task.subtask_count}
            </span>
          ) : null}
          {task.flagged === 1 && (
            <span className="sub-item flag">
              <FlagIcon width={12} height={12} />
            </span>
          )}
          {task.tags.map((t) => (
            <span key={t.id} className="tag-pill" style={{ background: t.color }}>
              {t.name}
            </span>
          ))}
        </div>
      </div>
      {onDelete && (
        <button
          className="task-delete"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(task);
          }}
          title="删除任务"
        >
          <TrashIcon width={14} height={14} />
        </button>
      )}
    </div>
  );
}
