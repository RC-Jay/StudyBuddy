import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"
import type { TocItem, User } from "./types"

export interface WorkspaceScope {
  type: "document" | "collection"
  id: string
  name: string
  status?: "pending" | "processing" | "summarising" | "ready" | "failed"
  doc_type?: "book" | "research_paper" | "video"
  expected_summary_count?: number
  toc?: TocItem[] | null
  thumbnail_url?: string | null
}

interface AppStore {
  user: User | null
  isLoading: boolean
  setUser: (user: User | null) => void
  setLoading: (v: boolean) => void
  scope: WorkspaceScope | null
  setScope: (scope: WorkspaceScope | null) => void
  activeTab: "chat" | "summarise" | "quiz" | "documents"
  setActiveTab: (tab: "chat" | "summarise" | "quiz" | "documents") => void
}

export const useAuthStore = create<AppStore>()(
  persist(
    (set) => ({
      user: null,
      isLoading: true,
      setUser: (user) => set({ user }),
      setLoading: (isLoading) => set({ isLoading }),
      scope: null,
      setScope: (scope) => set({ scope }),
      activeTab: "chat",
      setActiveTab: (activeTab) => set({ activeTab }),
    }),
    {
      name: "studybuddy-workspace",
      storage: createJSONStorage(() => sessionStorage),
      // Only persist workspace navigation state, not auth (managed by refresh cookie)
      partialize: (state) => ({
        scope: state.scope,
        activeTab: state.activeTab,
      }),
    }
  )
)
