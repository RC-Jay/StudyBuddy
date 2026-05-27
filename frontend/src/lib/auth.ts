import api, { setAccessToken } from "./api"
import type { User } from "./types"

export async function loginWithGoogle(idToken: string): Promise<User> {
  const { data } = await api.post("/auth/google", { credential: idToken })
  setAccessToken(data.access_token)
  return data.user
}

export async function loginWithLinkedIn(code: string): Promise<User> {
  const { data } = await api.post("/auth/linkedin", { credential: code })
  setAccessToken(data.access_token)
  return data.user
}

export function initiateLinkedInLogin(): void {
  const clientId = process.env.NEXT_PUBLIC_LINKEDIN_CLIENT_ID
  const redirectUri = encodeURIComponent(
    process.env.NEXT_PUBLIC_LINKEDIN_REDIRECT_URI ?? `${window.location.origin}/auth/callback`
  )
  const scope = encodeURIComponent("openid profile email")
  window.location.href = `https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=${clientId}&redirect_uri=${redirectUri}&scope=${scope}&state=linkedin`
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
