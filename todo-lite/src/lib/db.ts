import Database from "@tauri-apps/plugin-sql";
import type {
  ListGroup,
  NavTarget,
  RepeatRule,
  Section,
  SmartListId,
  SortMode,
  Tag,
  Task,
  TaskWithTags,
  TodoList,
} from "../types";
import { addDaysToDateStr, computeNextOccurrence, shiftDateTimeStr, toDateStr, toDateTimeStr } from "./repeat";

let db: Database | null = null;

export async function getDb(): Promise<Database> {
  if (!db) {
    db = await Database.load("sqlite:todo-lite.db");
  }
  return db;
}

export async function initDb(): Promise<void> {
  const d = await getDb();
  await d.execute(
    "DELETE FROM tasks WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', '-30 days')",
  );
}

export async function cleanupDeletedTasks(): Promise<void> {
  const d = await getDb();
  await d.execute(
    "DELETE FROM tasks WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', '-30 days')",
  );
}

// ---------- list groups ----------

export async function getListGroups(): Promise<ListGroup[]> {
  const d = await getDb();
  return d.select<ListGroup[]>("SELECT * FROM list_groups ORDER BY sort_order");
}

export async function createListGroup(name: string): Promise<ListGroup> {
  const d = await getDb();
  const rows = await d.select<{ max: number | null }[]>("SELECT MAX(sort_order) AS max FROM list_groups");
  const order = (rows[0]?.max ?? 0) + 1;
  const r = await d.execute("INSERT INTO list_groups (name, sort_order) VALUES (?, ?)", [name, order]);
  return { id: Number(r.lastInsertId), name, sort_order: order };
}

export async function renameListGroup(id: number, name: string): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE list_groups SET name = ? WHERE id = ?", [name, id]);
}

export async function deleteListGroup(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE lists SET group_id = NULL WHERE group_id = ?", [id]);
  await d.execute("DELETE FROM list_groups WHERE id = ?", [id]);
}

// ---------- lists ----------

export async function getLists(): Promise<TodoList[]> {
  const d = await getDb();
  return d.select<TodoList[]>("SELECT * FROM lists ORDER BY sort_order");
}

export async function createList(name: string, color: string, groupId: number | null): Promise<TodoList> {
  const d = await getDb();
  const rows = await d.select<{ max: number | null }[]>("SELECT MAX(sort_order) AS max FROM lists");
  const order = (rows[0]?.max ?? 0) + 1;
  const r = await d.execute(
    "INSERT INTO lists (name, color, group_id, sort_order) VALUES (?, ?, ?, ?)",
    [name, color, groupId, order],
  );
  return {
    id: Number(r.lastInsertId),
    name,
    color,
    icon: null,
    group_id: groupId,
    sort_order: order,
    created_at: toDateTimeStr(new Date()),
  };
}

export async function updateList(
  id: number,
  patch: { name?: string; color?: string; icon?: string | null; group_id?: number | null },
): Promise<void> {
  const d = await getDb();
  const fields: string[] = [];
  const values: unknown[] = [];
  for (const [k, v] of Object.entries(patch)) {
    fields.push(`${k} = ?`);
    values.push(v === undefined ? null : v);
  }
  if (!fields.length) return;
  values.push(id);
  await d.execute(`UPDATE lists SET ${fields.join(", ")} WHERE id = ?`, values);
}

export async function deleteList(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("DELETE FROM lists WHERE id = ?", [id]);
}

// ---------- sections ----------

export async function getSections(listId: number): Promise<Section[]> {
  const d = await getDb();
  return d.select<Section[]>("SELECT * FROM sections WHERE list_id = ? ORDER BY sort_order", [listId]);
}

export async function createSection(listId: number, name: string): Promise<Section> {
  const d = await getDb();
  const rows = await d.select<{ max: number | null }[]>(
    "SELECT MAX(sort_order) AS max FROM sections WHERE list_id = ?",
    [listId],
  );
  const order = (rows[0]?.max ?? 0) + 1;
  const r = await d.execute("INSERT INTO sections (list_id, name, sort_order) VALUES (?, ?, ?)", [
    listId,
    name,
    order,
  ]);
  return { id: Number(r.lastInsertId), list_id: listId, name, sort_order: order };
}

export async function renameSection(id: number, name: string): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE sections SET name = ? WHERE id = ?", [name, id]);
}

export async function deleteSection(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE tasks SET section_id = NULL WHERE section_id = ?", [id]);
  await d.execute("DELETE FROM sections WHERE id = ?", [id]);
}

// ---------- tags ----------

export async function getTags(): Promise<Tag[]> {
  const d = await getDb();
  return d.select<Tag[]>("SELECT * FROM tags ORDER BY name");
}

export async function createTag(name: string, color: string): Promise<Tag> {
  const d = await getDb();
  const r = await d.execute("INSERT INTO tags (name, color) VALUES (?, ?)", [name, color]);
  return { id: Number(r.lastInsertId), name, color };
}

export async function deleteTag(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("DELETE FROM task_tags WHERE tag_id = ?", [id]);
  await d.execute("DELETE FROM tags WHERE id = ?", [id]);
}

// ---------- tasks ----------

export async function getTasks(filter: {
  nav: NavTarget;
  showCompleted: boolean;
  sortMode: SortMode;
  search?: string;
}): Promise<TaskWithTags[]> {
  const { nav, showCompleted, sortMode, search } = filter;
  const isDeletedView = nav.kind === "deleted";
  const where: string[] = [isDeletedView ? "t.deleted_at IS NOT NULL" : "t.deleted_at IS NULL"];
  const params: unknown[] = [];

  if (search) {
    where.push("t.title LIKE ?");
    params.push(`%${search}%`);
    if (!isDeletedView) where.push("t.completed_at IS NULL");
  } else if (!isDeletedView) {
    where.push("t.parent_id IS NULL");
  }

  if (search) {
    // 全局搜索：跨所有列表/智能列表匹配
  } else if (nav.kind === "list") {
    where.push("t.list_id = ?");
    params.push(nav.listId);
    if (!showCompleted) where.push("t.completed_at IS NULL");
  } else if (nav.kind === "smart") {
    applySmartList(nav.id, where, params);
  }

  if (search) where.push("t.completed_at IS NULL");

  const orderBy = ORDER_BY[sortMode] ?? ORDER_BY.manual;
  const effectiveSort =
    nav.kind === "smart" && (nav.id === "planned" || nav.id === "scheduled")
      ? "ORDER BY t.due_date, t.sort_order"
      : orderBy;
  const d = await getDb();
  const tasks = await d.select<Task[]>(
    `SELECT t.*, 
       (SELECT COUNT(*) FROM tasks c WHERE c.parent_id = t.id AND c.deleted_at IS NULL) AS subtask_count,
       (SELECT COUNT(*) FROM tasks c WHERE c.parent_id = t.id AND c.deleted_at IS NULL AND c.completed_at IS NOT NULL) AS subtask_done
     FROM tasks t WHERE ${where.join(" AND ")} ${effectiveSort}`,
    params,
  );
  return attachTags(tasks);
}

function applySmartList(id: SmartListId, where: string[], params: unknown[]): void {
  const today = toDateStr(new Date());
  switch (id) {
    case "my-day":
      where.push("t.my_day_date = ? AND t.completed_at IS NULL");
      params.push(today);
      break;
    case "important":
      where.push("t.flagged = 1 AND t.completed_at IS NULL");
      break;
    case "planned":
      where.push("t.due_date IS NOT NULL AND t.completed_at IS NULL");
      break;
    case "scheduled":
      where.push("t.reminder_at IS NOT NULL AND t.completed_at IS NULL");
      break;
    case "no-date":
      where.push("t.due_date IS NULL AND t.completed_at IS NULL");
      break;
    case "completed":
      where.push("t.completed_at IS NOT NULL");
      break;
    case "all":
      where.push("t.completed_at IS NULL");
      break;
  }
}

const ORDER_BY: Record<SortMode, string> = {
  manual: "ORDER BY t.sort_order",
  priority: "ORDER BY t.priority DESC, t.sort_order",
  due: "ORDER BY COALESCE(t.due_date, '9999-99-99'), t.sort_order",
  created: "ORDER BY t.created_at DESC",
  alpha: "ORDER BY t.title COLLATE NOCASE",
};

async function attachTags(tasks: Task[]): Promise<TaskWithTags[]> {
  if (!tasks.length) return tasks as TaskWithTags[];
  const ids = tasks.map((t) => t.id);
  const placeholders = ids.map(() => "?").join(",");
  const d = await getDb();
  const rows = await d.select<{ task_id: number; id: number; name: string; color: string }[]>(
    `SELECT tt.task_id, t.id, t.name, t.color FROM task_tags tt
     JOIN tags t ON t.id = tt.tag_id WHERE tt.task_id IN (${placeholders})`,
    ids,
  );
  const byTask = new Map<number, Tag[]>();
  for (const r of rows) {
    const list = byTask.get(r.task_id) ?? [];
    list.push({ id: r.id, name: r.name, color: r.color });
    byTask.set(r.task_id, list);
  }
  return tasks.map((t) => ({ ...t, tags: byTask.get(t.id) ?? [] }));
}

export async function createTask(input: {
  listId: number | null;
  sectionId?: number | null;
  title: string;
  myDay?: boolean;
}): Promise<TaskWithTags> {
  const d = await getDb();
  const orderRows = await d.select<{ max: number | null }[]>(
    "SELECT MAX(sort_order) AS max FROM tasks WHERE list_id IS ? AND parent_id IS NULL",
    [input.listId],
  );
  const order = (orderRows[0]?.max ?? 0) + 1;
  const myDay = input.myDay ? toDateStr(new Date()) : null;
  const r = await d.execute(
    `INSERT INTO tasks (list_id, section_id, title, my_day_date, sort_order)
     VALUES (?, ?, ?, ?, ?)`,
    [input.listId, input.sectionId ?? null, input.title, myDay, order],
  );
  const rows = await d.select<Task[]>("SELECT * FROM tasks WHERE id = ?", [Number(r.lastInsertId)]);
  return { ...rows[0], tags: [] };
}

export async function updateTask(id: number, patch: Partial<Task>): Promise<void> {
  const d = await getDb();
  const fields: string[] = [];
  const values: unknown[] = [];
  for (const [k, v] of Object.entries(patch)) {
    if (k === "id") continue;
    fields.push(`${k} = ?`);
    values.push(v === undefined ? null : v);
  }
  if (!fields.length) return;
  fields.push("updated_at = datetime('now')");
  values.push(id);
  await d.execute(`UPDATE tasks SET ${fields.join(", ")} WHERE id = ?`, values);
}

export async function deleteTask(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE tasks SET deleted_at = datetime('now') WHERE id = ?", [id]);
  await d.execute("UPDATE tasks SET deleted_at = datetime('now') WHERE parent_id = ?", [id]);
}

export async function restoreTask(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE tasks SET deleted_at = NULL WHERE id = ?", [id]);
  await d.execute("UPDATE tasks SET deleted_at = NULL WHERE parent_id = ?", [id]);
}

export async function purgeTask(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("DELETE FROM tasks WHERE id = ?", [id]);
}

export async function purgeAllDeleted(): Promise<void> {
  const d = await getDb();
  await d.execute("DELETE FROM tasks WHERE deleted_at IS NOT NULL");
}

export async function toggleComplete(task: Task): Promise<void> {
  const d = await getDb();
  if (task.completed_at) {
    await d.execute("UPDATE tasks SET completed_at = NULL, updated_at = datetime('now') WHERE id = ?", [
      task.id,
    ]);
    return;
  }
  if (task.repeat_rule) {
    const rule = JSON.parse(task.repeat_rule) as RepeatRule;
    const from = new Date();
    const next = computeNextOccurrence(rule, from);
    await d.execute(
      `UPDATE tasks SET
         due_date = ?, due_time = ?, reminder_at = ?, my_day_date = NULL,
         completed_at = NULL, updated_at = datetime('now')
       WHERE id = ?`,
      [
        addDaysToDateStr(task.due_date, Math.round((next.getTime() - from.getTime()) / 86400000)) ?? toDateStr(next),
        task.due_time,
        shiftDateTimeStr(task.reminder_at, from, next),
        task.id,
      ],
    );
    return;
  }
  await d.execute("UPDATE tasks SET completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?", [
    task.id,
  ]);
}

export async function setTaskTags(taskId: number, tagIds: number[]): Promise<void> {
  const d = await getDb();
  await d.execute("DELETE FROM task_tags WHERE task_id = ?", [taskId]);
  for (const tagId of tagIds) {
    await d.execute("INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)", [taskId, tagId]);
  }
}

export async function reorderTasks(orderedIds: number[]): Promise<void> {
  const d = await getDb();
  for (let i = 0; i < orderedIds.length; i++) {
    await d.execute("UPDATE tasks SET sort_order = ? WHERE id = ?", [i + 1, orderedIds[i]]);
  }
}

export async function getTaskCount(): Promise<number> {
  const d = await getDb();
  const rows = await d.select<{ n: number }[]>(
    "SELECT COUNT(*) AS n FROM tasks WHERE deleted_at IS NULL AND completed_at IS NULL",
  );
  return rows[0]?.n ?? 0;
}

// ---------- subtasks ----------

export async function getTaskById(id: number): Promise<TaskWithTags | null> {
  const d = await getDb();
  const rows = await d.select<Task[]>(
    `SELECT t.*,
       (SELECT COUNT(*) FROM tasks c WHERE c.parent_id = t.id AND c.deleted_at IS NULL) AS subtask_count,
       (SELECT COUNT(*) FROM tasks c WHERE c.parent_id = t.id AND c.deleted_at IS NULL AND c.completed_at IS NOT NULL) AS subtask_done
     FROM tasks t WHERE t.id = ? AND t.deleted_at IS NULL`,
    [id],
  );
  if (!rows.length) return null;
  const [tagged] = await attachTags(rows);
  return tagged;
}

export async function getSubtasks(parentId: number): Promise<Task[]> {
  const d = await getDb();
  return d.select<Task[]>(
    "SELECT * FROM tasks WHERE parent_id = ? AND deleted_at IS NULL ORDER BY sort_order",
    [parentId],
  );
}

export async function createSubtask(parentId: number, title: string): Promise<Task> {
  const d = await getDb();
  const rows = await d.select<{ max: number | null }[]>(
    "SELECT MAX(sort_order) AS max FROM tasks WHERE parent_id = ?",
    [parentId],
  );
  const order = (rows[0]?.max ?? 0) + 1;
  const r = await d.execute(
    "INSERT INTO tasks (parent_id, title, sort_order) VALUES (?, ?, ?)",
    [parentId, title, order],
  );
  const created = await d.select<Task[]>("SELECT * FROM tasks WHERE id = ?", [Number(r.lastInsertId)]);
  return created[0];
}

export async function toggleSubtask(task: Task): Promise<void> {
  const d = await getDb();
  if (task.completed_at) {
    await d.execute("UPDATE tasks SET completed_at = NULL, updated_at = datetime('now') WHERE id = ?", [
      task.id,
    ]);
  } else {
    await d.execute("UPDATE tasks SET completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?", [
      task.id,
    ]);
  }
}

export async function deleteSubtask(id: number): Promise<void> {
  const d = await getDb();
  await d.execute("UPDATE tasks SET deleted_at = datetime('now') WHERE id = ?", [id]);
}

export async function getTaskTags(taskId: number): Promise<Tag[]> {
  const d = await getDb();
  return d.select<Tag[]>(
    "SELECT t.* FROM task_tags tt JOIN tags t ON t.id = tt.tag_id WHERE tt.task_id = ? ORDER BY t.name",
    [taskId],
  );
}
