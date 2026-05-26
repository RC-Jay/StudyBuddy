import api, { setAccessToken } from "./api"
import type { User } from "./types"

export async function requestOtp(phone: string): Promise<{ debug_token?: string }> {
  const { data } = await api.post("/auth/otp/request", { phone })
  return data
}

export async function loginWithOtp(phone: string, otp: string): Promise<User> {
  const { data } = await api.post("/auth/login/otp", { phone, otp })
  setAccessToken(data.access_token)
  return data.user
}

export async function loginWithPassword(phone: string, password: string): Promise<User> {
  const { data } = await api.post("/auth/login/password", { phone, password })
  setAccessToken(data.access_token)
  return data.user
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout")
  setAccessToken(null)
}

export async function refreshSession(): Promise<User | null> {
  try {
    const { data } = await api.post("/auth/refresh")
    setAccessToken(data.access_token)
    return data.user
  } catch {
    return null
  }
}
