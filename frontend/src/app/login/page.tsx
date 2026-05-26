"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { requestOtp, loginWithOtp, loginWithPassword } from "@/lib/auth"
import { useAuthStore } from "@/lib/store"

const passwordSchema = z.object({ phone: z.string().min(10), password: z.string().min(1) })
const otpRequestSchema = z.object({ phone: z.string().min(10) })
const otpSubmitSchema = z.object({ otp: z.string().length(6) })

type PasswordFields = z.infer<typeof passwordSchema>
type OtpRequestFields = z.infer<typeof otpRequestSchema>
type OtpSubmitFields = z.infer<typeof otpSubmitSchema>

export default function LoginPage() {
  const router = useRouter()
  const setUser = useAuthStore((s) => s.setUser)
  const [mode, setMode] = useState<"password" | "otp-request" | "otp-submit">("password")
  const [phone, setPhone] = useState("")
  const [debugOtp, setDebugOtp] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const pwForm = useForm<PasswordFields>({ resolver: zodResolver(passwordSchema) })
  const otpReqForm = useForm<OtpRequestFields>({ resolver: zodResolver(otpRequestSchema) })
  const otpSubmitForm = useForm<OtpSubmitFields>({ resolver: zodResolver(otpSubmitSchema) })

  async function handlePasswordLogin(data: PasswordFields) {
    setError(null)
    setLoading(true)
    try {
      const user = await loginWithPassword(data.phone, data.password)
      setUser(user)
      router.replace("/library")
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(msg || "Login failed. Check your credentials.")
    } finally {
      setLoading(false)
    }
  }

  async function handleOtpRequest(data: OtpRequestFields) {
    setError(null)
    setLoading(true)
    try {
      const res = await requestOtp(data.phone)
      setPhone(data.phone)
      setDebugOtp(res.debug_token ?? null)
      setMode("otp-submit")
      if (res.debug_token) {
        otpSubmitForm.setValue("otp", res.debug_token)
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(msg || "Failed to send OTP.")
    } finally {
      setLoading(false)
    }
  }

  async function handleOtpSubmit(data: OtpSubmitFields) {
    setError(null)
    setLoading(true)
    try {
      const user = await loginWithOtp(phone, data.otp)
      setUser(user)
      router.replace("/library")
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(msg || "Invalid OTP. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-indigo-600">StudyBuddy</h1>
          <p className="mt-2 text-sm text-gray-600">Sign in with your ChangePay account</p>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-sm ring-1 ring-gray-200">
          {/* Tab switcher */}
          {mode !== "otp-submit" && (
            <div className="mb-6 flex rounded-lg bg-gray-100 p-1">
              <button
                onClick={() => setMode("password")}
                className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${mode === "password" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
              >
                Password
              </button>
              <button
                onClick={() => setMode("otp-request")}
                className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${mode === "otp-request" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
              >
                OTP
              </button>
            </div>
          )}

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          )}

          {mode === "password" && (
            <form onSubmit={pwForm.handleSubmit(handlePasswordLogin)} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Phone number</label>
                <input
                  {...pwForm.register("phone")}
                  placeholder="+917829860000"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Password</label>
                <input
                  {...pwForm.register("password")}
                  type="password"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}

          {mode === "otp-request" && (
            <form onSubmit={otpReqForm.handleSubmit(handleOtpRequest)} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Phone number</label>
                <input
                  {...otpReqForm.register("phone")}
                  placeholder="+917829860000"
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? "Sending OTP…" : "Send OTP"}
              </button>
            </form>
          )}

          {mode === "otp-submit" && (
            <form onSubmit={otpSubmitForm.handleSubmit(handleOtpSubmit)} className="space-y-4">
              <p className="text-sm text-gray-600">
                OTP sent to <span className="font-medium">{phone}</span>
              </p>
              {debugOtp && (
                <div className="rounded-lg bg-yellow-50 px-3 py-2 text-xs text-yellow-800">
                  Staging OTP: <span className="font-mono font-bold">{debugOtp}</span> (pre-filled)
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700">Enter OTP</label>
                <input
                  {...otpSubmitForm.register("otp")}
                  placeholder="123456"
                  maxLength={6}
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-center font-mono text-lg tracking-widest focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? "Verifying…" : "Verify OTP"}
              </button>
              <button type="button" onClick={() => setMode("otp-request")} className="w-full text-sm text-indigo-600 hover:underline">
                ← Back
              </button>
            </form>
          )}

          <p className="mt-6 text-center text-xs text-gray-500">
            Don&apos;t have an account?{" "}
            <a href="https://changepay.in" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">
              Register on ChangePay
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}
