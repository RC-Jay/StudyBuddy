"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { GoogleLogin } from "@react-oauth/google"
import { initiateLinkedInLogin, loginWithGoogle } from "@/lib/auth"
import { useAuthStore } from "@/lib/store"

export default function LoginPage() {
  const router = useRouter()
  const setUser = useAuthStore((s) => s.setUser)
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-indigo-600">StudyBuddy</h1>
          <p className="mt-2 text-sm text-gray-600">AI-powered study assistant</p>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-sm ring-1 ring-gray-200">
          {error && (
            <div className="mb-6 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          )}

          <div className="flex flex-col items-center gap-3">
            <GoogleLogin
              onSuccess={async (credentialResponse) => {
                setError(null)
                const idToken = credentialResponse.credential
                if (!idToken) {
                  setError("No credential received from Google.")
                  return
                }
                try {
                  const user = await loginWithGoogle(idToken)
                  setUser(user)
                  router.replace("/library")
                } catch (e: unknown) {
                  const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
                  setError(msg || "Sign-in failed. Please try again.")
                }
              }}
              onError={() => setError("Google sign-in was cancelled or failed.")}
              useOneTap
            />

            <div className="flex w-full items-center gap-3">
              <div className="h-px flex-1 bg-gray-200" />
              <span className="text-xs text-gray-400">or</span>
              <div className="h-px flex-1 bg-gray-200" />
            </div>

            <button
              onClick={() => { setError(null); initiateLinkedInLogin() }}
              className="flex w-full items-center justify-center gap-3 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
            >
              <LinkedInIcon />
              Continue with LinkedIn
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function LinkedInIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" fill="#0A66C2">
      <path d="M15.75 0H2.25A2.25 2.25 0 0 0 0 2.25v13.5A2.25 2.25 0 0 0 2.25 18h13.5A2.25 2.25 0 0 0 18 15.75V2.25A2.25 2.25 0 0 0 15.75 0ZM5.625 14.625H3.375V6.75h2.25v7.875ZM4.5 5.85a1.35 1.35 0 1 1 0-2.7 1.35 1.35 0 0 1 0 2.7Zm10.125 8.775h-2.25v-3.713c0-.994-.378-1.587-1.181-1.587-.794 0-1.257.536-1.257 1.587v3.713H7.688V6.75h2.25v1.014c.463-.684 1.194-1.264 2.194-1.264 1.69 0 2.493 1.12 2.493 3.07v5.055Z" />
    </svg>
  )
}
