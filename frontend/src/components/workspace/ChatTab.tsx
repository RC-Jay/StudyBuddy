"use client"

import { useState, useEffect, useRef } from "react"
import { Send, Plus, Loader2, ChevronDown, MessageSquare } from "lucide-react"
import api from "@/lib/api"
import type { ChatSession, ChatMessage } from "@/lib/types"

interface Props {
  scopeType: "document" | "collection"
  scopeId: string
}

export function ChatTab({ scopeType, scopeId }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false

    api.get<ChatSession[]>("/chat/sessions").then(async ({ data }) => {
      if (cancelled) return
      const scoped = data.filter(
        (s) => s.scope_type === scopeType && s.scope_id === scopeId
      )
      setSessions(scoped)
      if (scoped.length > 0) {
        const { data: msgData } = await api.get<{ messages: ChatMessage[] }>(
          `/chat/sessions/${scoped[0].id}`
        )
        if (!cancelled) {
          setActiveSession(scoped[0])
          setMessages(msgData.messages)
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [scopeId, scopeType])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function openSession(session: ChatSession) {
    const { data } = await api.get<{ messages: ChatMessage[] }>(
      `/chat/sessions/${session.id}`
    )
    setActiveSession(session)
    setMessages(data.messages)
    setShowHistory(false)
  }

  async function createSession() {
    const { data } = await api.post<ChatSession>("/chat/sessions", {
      scope_type: scopeType,
      scope_id: scopeId,
    })
    setSessions((prev) => [data, ...prev])
    setActiveSession(data)
    setMessages([])
  }

  async function sendMessage() {
    if (!input.trim() || !activeSession || streaming) return
    const text = input.trim()
    setInput("")

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      citations: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setStreaming(true)

    const assistantMsg: ChatMessage = {
      id: Date.now().toString() + "-a",
      role: "assistant",
      content: "",
      citations: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, assistantMsg])

    const token = api.defaults.headers?.common?.["Authorization"]
      ?.toString()
      .replace("Bearer ", "")
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/chat/sessions/${activeSession.id}/messages`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ content: text }),
      }
    )

    const reader = res.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) {
      setStreaming(false)
      return
    }

    let finalCitations: ChatMessage["citations"] = null
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      const lines = decoder.decode(value).split("\n")
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        try {
          const payload = JSON.parse(line.slice(6))
          if (payload.delta) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: m.content + payload.delta }
                  : m
              )
            )
          }
          if (payload.done) finalCitations = payload.citations
        } catch {
          // ignore malformed SSE lines
        }
      }
    }

    if (finalCitations) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id ? { ...m, citations: finalCitations } : m
        )
      )
    }
    setStreaming(false)
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Session bar */}
      <div className="flex items-center justify-between border-b border-gray-100 bg-white px-4 py-2">
        <div className="relative">
          {activeSession ? (
            <button
              onClick={() => setShowHistory((v) => !v)}
              className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span className="max-w-[200px] truncate">
                {activeSession.title || "Untitled chat"}
              </span>
              {sessions.length > 1 && <ChevronDown className="h-3 w-3" />}
            </button>
          ) : (
            <span className="text-sm text-gray-400">No chat session</span>
          )}

          {showHistory && sessions.length > 1 && (
            <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-lg border border-gray-200 bg-white shadow-lg">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => openSession(s)}
                  className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 ${
                    activeSession?.id === s.id ? "bg-indigo-50 text-indigo-700" : "text-gray-700"
                  }`}
                >
                  <p className="truncate font-medium">{s.title || "Untitled chat"}</p>
                  <p className="text-xs text-gray-400">{s.message_count} messages</p>
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={createSession}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 hover:text-indigo-600"
        >
          <Plus className="h-3.5 w-3.5" />
          New chat
        </button>
      </div>

      {!activeSession ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center text-gray-400">
            <MessageSquare className="mx-auto mb-3 h-10 w-10 opacity-20" />
            <p className="text-sm">Start a conversation about this document</p>
            <button
              onClick={createSession}
              className="mt-4 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              New chat
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${
                    msg.role === "user"
                      ? "bg-indigo-600 text-white"
                      : "bg-white ring-1 ring-gray-200 text-gray-800"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {msg.citations.map((c, i) => (
                        <span
                          key={i}
                          className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
                        >
                          {c.document}
                          {c.page ? ` p.${c.page}` : ""}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {streaming && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-gray-200">
                  <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-gray-200 bg-white p-4">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    sendMessage()
                  }
                }}
                rows={1}
                placeholder="Ask about this document…"
                className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || streaming}
                className="rounded-lg bg-indigo-600 p-2 text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
