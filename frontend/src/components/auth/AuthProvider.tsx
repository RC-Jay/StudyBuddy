"use client"

import { useEffect } from "react"
import { refreshSession } from "@/lib/auth"
import { useAuthStore } from "@/lib/store"

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setUser, setLoading } = useAuthStore()

  useEffect(() => {
    refreshSession()
      .then((user) => setUser(user))
      .finally(() => setLoading(false))
  }, [setUser, setLoading])

  return <>{children}</>
}
