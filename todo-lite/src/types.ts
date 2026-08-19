export type Priority = 0 | 1 | 2 | 3;

export interface ListGroup {
  id: number;
  name: string;
  sort_order: number;
}

export interface TodoList {
  id: number;
  name: string;
  color: string;
  icon: string | null;
  group_id: number | null;
  sort_order: number;
  created_at: string;
}

export interface Section {
  id: number;
  list_id: number;
  name: string;
  sort_order: number;
}

export interface Tag {
  id: number;
  name: string;
  color: string;
}

export interface RepeatRule {
  type: "daily" | "weekdays" | "weekly" | "monthly" | "yearly";
}

export interface Task {
  id: number;
  list_id: number | null;
  section_id: number | null;
  parent_id: number | null;
  title: string;
  notes: string | null;
  priority: Priority;
  flagged: 0 | 1;
  my_day_date: string | null;
  due_date: string | null;
  due_time: string | null;
  reminder_at: string | null;
  repeat_rule: string | null;
  sort_order: number;
  completed_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskWithTags extends Task {
  tags: Tag[];
  subtask_count?: number;
  subtask_done?: number;
}

export type TaskFilter = {
  listId?: number;
  smartList?: SmartListId;
  search?: string;
  showCompleted?: boolean;
};

export type SmartListId =
  | "my-day"
  | "important"
  | "planned"
  | "scheduled"
  | "no-date"
  | "completed"
  | "all";

export type NavTarget =
  | { kind: "list"; listId: number }
  | { kind: "smart"; id: SmartListId }
  | { kind: "deleted" };

export type SortMode = "manual" | "priority" | "due" | "created" | "alpha";
