import { create } from "zustand";
import type { NavTarget, SortMode, Task, TaskWithTags } from "../types";
import * as db from "../lib/db";

interface TaskState {
  tasks: TaskWithTags[];
  loading: boolean;
  error: string | null;
  load: (opts: {
    nav: NavTarget;
    showCompleted: boolean;
    sortMode: SortMode;
    search?: string;
  }) => Promise<void>;
  addTask: (input: { listId: number | null; title: string; sectionId?: number | null; myDay?: boolean }) => Promise<TaskWithTags>;
  updateTask: (id: number, patch: Partial<Task>) => Promise<void>;
  toggleComplete: (task: Task) => Promise<void>;
  deleteTask: (id: number) => Promise<void>;
  restoreTask: (id: number) => Promise<void>;
  purgeTask: (id: number) => Promise<void>;
  purgeAllDeleted: () => Promise<void>;
  setTags: (taskId: number, tagIds: number[]) => Promise<void>;
  reorder: (orderedIds: number[]) => Promise<void>;
  updateLocal: (id: number, patch: Partial<Task>) => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  loading: false,
  error: null,

  load: async (opts) => {
    set({ loading: true, error: null });
    try {
      const tasks = await db.getTasks(opts);
      set({ tasks, loading: false });
    } catch (e) {
      console.error("load tasks failed", e);
      set({ tasks: [], loading: false, error: String(e) });
    }
  },

  addTask: async (input) => {
    const task = await db.createTask(input);
    set({ tasks: [...get().tasks, task] });
    return task;
  },

  updateTask: async (id, patch) => {
    await db.updateTask(id, patch);
    get().updateLocal(id, patch);
  },

  updateLocal: (id, patch) => {
    set({
      tasks: get().tasks.map((t) =>
        t.id === id ? { ...t, ...patch, updated_at: new Date().toISOString() } : t,
      ),
    });
  },

  toggleComplete: async (task) => {
    await db.toggleComplete(task);
    set({ tasks: get().tasks.filter((t) => t.id !== task.id) });
  },

  deleteTask: async (id) => {
    await db.deleteTask(id);
    set({ tasks: get().tasks.filter((t) => t.id !== id) });
  },

  restoreTask: async (id) => {
    await db.restoreTask(id);
    set({ tasks: get().tasks.filter((t) => t.id !== id) });
  },

  purgeTask: async (id) => {
    await db.purgeTask(id);
    set({ tasks: get().tasks.filter((t) => t.id !== id) });
  },

  purgeAllDeleted: async () => {
    await db.purgeAllDeleted();
    set({ tasks: [] });
  },

  setTags: async (taskId, tagIds) => {
    await db.setTaskTags(taskId, tagIds);
  },

  reorder: async (orderedIds) => {
    await db.reorderTasks(orderedIds);
    set({
      tasks: orderedIds
        .map((id) => get().tasks.find((t) => t.id === id))
        .filter((t): t is TaskWithTags => t !== undefined),
    });
  },
}));
