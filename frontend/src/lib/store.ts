import { create } from "zustand"
import type { User } from "./types"

export interface WorkspaceScope {
  type: "document" | "collection"
  id: string
  name: string
  status?: "pending" | "processing" | "ready" | "failed"
}

interface AppStore {
  user: User | null
  isLoading: boolean
  setUser: (user: User | null) => void
  setLoading: (v: boolean) => void
  scope: WorkspaceScope | null
  setScope: (scope: WorkspaceScope | null) => void
  activeTab: "chat" | "summarise" | "quiz"
  setActiveTab: (tab: "chat" | "summarise" | "quiz") => void
}

export const useAuthStore = create<AppStore>((set) => ({
  user: null,
  isLoading: true,
  setUser: (user) => set({ user }),
  setLoading: (isLoading) => set({ isLoading }),
  scope: null,
  setScope: (scope) => set({ scope }),
  activeTab: "chat",
  setActiveTab: (activeTab) => set({ activeTab }),
}))
