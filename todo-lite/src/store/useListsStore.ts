import { create } from "zustand";
import type { ListGroup, Section, Tag, TodoList } from "../types";
import * as db from "../lib/db";

interface ListsState {
  groups: ListGroup[];
  lists: TodoList[];
  tags: Tag[];
  sectionsByList: Record<number, Section[]>;
  loading: boolean;
  loadAll: () => Promise<void>;
  addList: (name: string, color: string, groupId: number | null) => Promise<TodoList>;
  renameList: (id: number, name: string) => Promise<void>;
  deleteList: (id: number) => Promise<void>;
  addGroup: (name: string) => Promise<void>;
  deleteGroup: (id: number) => Promise<void>;
  reloadSections: (listId: number) => Promise<void>;
  addSection: (listId: number, name: string) => Promise<void>;
  deleteSection: (id: number, listId: number) => Promise<void>;
  addTag: (name: string, color: string) => Promise<Tag>;
  deleteTag: (id: number) => Promise<void>;
}

export const useListsStore = create<ListsState>((set, get) => ({
  groups: [],
  lists: [],
  tags: [],
  sectionsByList: {},
  loading: false,

  loadAll: async () => {
    set({ loading: true });
    const [groups, lists, tags] = await Promise.all([
      db.getListGroups(),
      db.getLists(),
      db.getTags(),
    ]);
    set({ groups, lists, tags, loading: false });
  },

  addList: async (name, color, groupId) => {
    const list = await db.createList(name, color, groupId);
    set({ lists: [...get().lists, list] });
    return list;
  },

  renameList: async (id, name) => {
    await db.updateList(id, { name });
    set({ lists: get().lists.map((l) => (l.id === id ? { ...l, name } : l)) });
  },

  deleteList: async (id) => {
    await db.deleteList(id);
    set({ lists: get().lists.filter((l) => l.id !== id) });
  },

  addGroup: async (name) => {
    const group = await db.createListGroup(name);
    set({ groups: [...get().groups, group] });
  },

  deleteGroup: async (id) => {
    await db.deleteListGroup(id);
    set({
      groups: get().groups.filter((g) => g.id !== id),
      lists: get().lists.map((l) => (l.group_id === id ? { ...l, group_id: null } : l)),
    });
  },

  reloadSections: async (listId) => {
    const sections = await db.getSections(listId);
    set({ sectionsByList: { ...get().sectionsByList, [listId]: sections } });
  },

  addSection: async (listId, name) => {
    const section = await db.createSection(listId, name);
    set({
      sectionsByList: {
        ...get().sectionsByList,
        [listId]: [...(get().sectionsByList[listId] ?? []), section],
      },
    });
  },

  deleteSection: async (id, listId) => {
    await db.deleteSection(id);
    set({
      sectionsByList: {
        ...get().sectionsByList,
        [listId]: (get().sectionsByList[listId] ?? []).filter((s) => s.id !== id),
      },
    });
  },

  addTag: async (name, color) => {
    const tag = await db.createTag(name, color);
    set({ tags: [...get().tags, tag] });
    return tag;
  },

  deleteTag: async (id) => {
    await db.deleteTag(id);
    set({ tags: get().tags.filter((t) => t.id !== id) });
  },
}));
