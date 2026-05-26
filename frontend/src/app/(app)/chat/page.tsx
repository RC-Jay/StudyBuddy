"use client"

import { useState, useEffect, useRef } from "react"
import { Send, Plus, Loader2 } from "lucide-react"
import api from "@/lib/api"
import type { ChatSession, ChatMessage, Document, Collection } from "@/lib/types"

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [docs, setDocs] = useState<Document[]>([])
  const [collections, setCollections] = useState<Collection[]>([])
  const [showNewChat, setShowNewChat] = useState(false)
  const [scopeType, setScopeType] = useState<"document" | "collection">("document")
  const [scopeId, setScopeId] = useState("")
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get<ChatSession[]>("/chat/sessions").then(({ data }) => setSessions(data))
    api.get<Document[]>("/documents").then(({ data }) => setDocs(data.filter((d) => d.processing_status === "ready")))
    api.get<Collection[]>("/collections").then(({ data }) => setCollections(data))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function openSession(session: ChatSession) {
    const { data } = await api.get<{ messages: ChatMessage[] }>(`/chat/sessions/${session.id}`)
    setActiveSession(session)
    setMessages(data.messages)
    setShowNewChat(false)
  }

  async function createSession() {
    if (!scopeId) return
    const { data } = await api.post<ChatSession>("/chat/sessions", { scope_type: scopeType, scope_id: scopeId })
    setSessions((prev) => [data, ...prev])
    setActiveSession(data)
    setMessages([])
    setShowNewChat(false)
  }

  async function sendMessage() {
    if (!input.trim() || !activeSession || streaming) return
    const text = input.trim()
    setInput("")
    const userMsg: ChatMessage = { id: Date.now().toString(), role: "user", content: text, citations: null, created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, userMsg])
    setStreaming(true)

    const assistantMsg: ChatMessage = { id: Date.now().toString() + "-a", role: "assistant", content: "", citations: null, created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, assistantMsg])

    const token = api.defaults.headers?.common?.["Authorization"]?.toString().replace("Bearer ", "")
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/chat/sessions/${activeSession.id}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      credentials: "include",
      body: JSON.stringify({ content: text }),
    })

    const reader = res.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) { setStreaming(false); return }

    let finalCitations: ChatMessage["citations"] = null
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      const lines = decoder.decode(value).split("\n")
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        const payload = JSON.parse(line.slice(6))
        if (payload.delta) {
          setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? { ...m, content: m.content + payload.delta } : m))
        }
        if (payload.done) finalCitations = payload.citations
      }
    }
    if (finalCitations) {
      setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? { ...m, citations: finalCitations } : m))
    }
    setStreaming(false)
  }

  return (
    <div className="flex h-full">
      {/* Session list */}
      <aside className="flex w-56 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <span className="text-sm font-medium text-gray-700">Chats</span>
          <button onClick={() => setShowNewChat(true)} className="rounded-lg p-1 text-indigo-600 hover:bg-indigo-50"><Plus className="h-4 w-4" /></button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessions.map((s) => (
            <button key={s.id} onClick={() => openSession(s)} className={`w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 ${activeSession?.id === s.id ? "bg-indigo-50 text-indigo-700" : "text-gray-700"}`}>
              <p className="truncate font-medium">{s.title || `Chat ${s.scope_type}`}</p>
              <p className="text-xs text-gray-400">{s.message_count} messages</p>
            </button>
          ))}
        </div>
      </aside>

      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {showNewChat ? (
          <div className="flex flex-1 items-center justify-center p-8">
            <div className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <h2 className="font-semibold text-gray-900">New Chat</h2>
              <div>
                <label className="block text-sm font-medium text-gray-700">Scope</label>
                <select value={scopeType} onChange={(e) => { setScopeType(e.target.value as "document" | "collection"); setScopeId("") }} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none">
                  <option value="document">Single Document</option>
                  <option value="collection">Collection</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">{scopeType === "document" ? "Document" : "Collection"}</label>
                <select value={scopeId} onChange={(e) => setScopeId(e.target.value)} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none">
                  <option value="">Select…</option>
                  {scopeType === "document"
                    ? docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)
                    : collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <button onClick={createSession} disabled={!scopeId} className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                Start Chat
              </button>
            </div>
          </div>
        ) : !activeSession ? (
          <div className="flex flex-1 items-center justify-center text-gray-400">
            <p className="text-sm">Select a chat or start a new one</p>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.map((msg) => (
                <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${msg.role === "user" ? "bg-indigo-600 text-white" : "bg-white ring-1 ring-gray-200 text-gray-800"}`}>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {msg.citations.map((c, i) => (
                          <span key={i} className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">
                            {c.document}{c.page ? ` p.${c.page}` : ""}
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
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
                  rows={1}
                  placeholder="Ask about your documents…"
                  className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <button onClick={sendMessage} disabled={!input.trim() || streaming} className="rounded-lg bg-indigo-600 p-2 text-white hover:bg-indigo-700 disabled:opacity-50">
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
