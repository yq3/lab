import { create } from "zustand";
import type { NavTarget, SortMode } from "../types";

export type Theme = "light" | "dark" | "system";

interface UIState {
  nav: NavTarget;
  showCompleted: boolean;
  sortMode: SortMode;
  search: string;
  searchFocus: number;
  searchOpen: boolean;
  quickAddFocus: number;
  selectedTaskId: number | null;
  detailOpen: boolean;
  detailBump: number;
  theme: Theme;
  setNav: (nav: NavTarget) => void;
  toggleShowCompleted: () => void;
  setSortMode: (mode: SortMode) => void;
  setSearch: (q: string) => void;
  focusSearch: () => void;
  closeSearch: () => void;
  focusQuickAdd: () => void;
  selectTask: (id: number | null, open?: boolean) => void;
  toggleDetail: (open?: boolean) => void;
  cycleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const THEME_ORDER: Theme[] = ["system", "light", "dark"];

export const useUIStore = create<UIState>((set) => ({
  nav: { kind: "smart", id: "my-day" },
  showCompleted: false,
  sortMode: "manual",
  search: "",
  searchFocus: 0,
  searchOpen: false,
  quickAddFocus: 0,
  selectedTaskId: null,
  detailOpen: false,
  detailBump: 0,
  theme: "system",

  setNav: (nav) => set({ nav, selectedTaskId: null, detailOpen: false, search: "", searchOpen: false }),
  toggleShowCompleted: () => set((s) => ({ showCompleted: !s.showCompleted })),
  setSortMode: (mode) => set({ sortMode: mode }),
  setSearch: (q) => set({ search: q, searchOpen: true }),
  focusSearch: () => set((s) => ({ searchFocus: s.searchFocus + 1, searchOpen: true })),
  closeSearch: () => set({ search: "", searchOpen: false }),
  focusQuickAdd: () => set((s) => ({ quickAddFocus: s.quickAddFocus + 1, detailOpen: false })),
  selectTask: (id, open = true) =>
    set((s) => ({
      selectedTaskId: id,
      detailOpen: open,
      detailBump: id !== null && id === s.selectedTaskId ? s.detailBump + 1 : s.detailBump,
    })),
  toggleDetail: (open) => set((s) => ({ detailOpen: open ?? !s.detailOpen })),
  cycleTheme: () =>
    set((s) => ({
      theme: THEME_ORDER[(THEME_ORDER.indexOf(s.theme) + 1) % THEME_ORDER.length],
    })),
  setTheme: (theme) => set({ theme }),
}));
