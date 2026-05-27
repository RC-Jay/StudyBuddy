"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { loginWithLinkedIn } from "@/lib/auth"
import { useAuthStore } from "@/lib/store"

function CallbackHandler() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setUser = useAuthStore((s) => s.setUser)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const code = searchParams.get("code")
    const errorParam = searchParams.get("error")

    if (errorParam || !code) {
      const msg = errorParam
        ? "Sign-in was cancelled or denied."
        : "No authorization code received."
      Promise.resolve().then(() => setError(msg))
      return
    }

    loginWithLinkedIn(code)
      .then((user) => {
        setUser(user)
        router.replace("/library")
      })
      .catch((e: unknown) => {
        const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
        setError(msg || "Sign-in failed. Please try again.")
      })
  }, [searchParams, setUser, router])

  if (error) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center gap-4 px-4">
        <div className="rounded-lg bg-red-50 px-6 py-4 text-sm text-red-700">{error}</div>
        <a href="/login" className="text-sm text-indigo-600 hover:underline">
          Back to sign in
        </a>
      </div>
    )
  }

  return (
    <div className="flex min-h-full items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
    </div>
  )
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-full items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  )
}
