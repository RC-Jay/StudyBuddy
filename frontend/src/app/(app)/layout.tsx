"use client"

import { useEffect } from "react"
import { useRouter, usePathname } from "next/navigation"
import Link from "next/link"
import { BookOpen, FolderOpen, MessageSquare, ClipboardList, FileText, LogOut } from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { logout } from "@/lib/auth"

const nav = [
  { href: "/library", label: "Library", icon: BookOpen },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/quiz", label: "Quiz", icon: ClipboardList },
  { href: "/summaries", label: "Summaries", icon: FileText },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuthStore()
  const router = useRouter()
  const pathname = usePathname()
  const setUser = useAuthStore((s) => s.setUser)

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login")
  }, [user, isLoading, router])

  if (isLoading || !user) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
      </div>
    )
  }

  async function handleLogout() {
    await logout()
    setUser(null)
    router.replace("/login")
  }

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="flex w-56 flex-col bg-white shadow-sm ring-1 ring-gray-200">
        <div className="px-4 py-5">
          <span className="text-xl font-bold text-indigo-600">StudyBuddy</span>
        </div>
        <nav className="flex-1 space-y-1 px-2">
          {nav.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                pathname.startsWith(href)
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-gray-200 p-4">
          <p className="truncate text-xs font-medium text-gray-700">{user.display_name}</p>
          <p className="truncate text-xs text-gray-500">{user.email}</p>
          <button
            onClick={handleLogout}
            className="mt-3 flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-700"
          >
            <LogOut className="h-3 w-3" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">{children}</main>
    </div>
  )
}
