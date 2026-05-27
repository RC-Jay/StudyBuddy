"use client"

import { useState, useEffect, useRef } from "react"
import Image from "next/image"
import { Upload, Trash2, FileText, Loader2, Plus, FolderOpen, LogOut, ChevronDown, ChevronUp } from "lucide-react"
import api from "@/lib/api"
import { useAuthStore } from "@/lib/store"
import { logout } from "@/lib/auth"
import { useRouter } from "next/navigation"
import type { Document, Collection } from "@/lib/types"

function statusDot(status: Document["processing_status"]) {
  return {
    pending: "bg-yellow-400",
    processing: "bg-blue-400 animate-pulse",
    ready: "bg-green-400",
    failed: "bg-red-400",
  }[status]
}

export function LibrarySidebar() {
  const { user, scope, setScope } = useAuthStore()
  const setUser = useAuthStore((s) => s.setUser)
  const router = useRouter()

  const [docs, setDocs] = useState<Document[]>([])
  const [collections, setCollections] = useState<Collection[]>([])
  const [uploading, setUploading] = useState(false)
  const [creatingCollection, setCreatingCollection] = useState(false)
  const [newCollectionName, setNewCollectionName] = useState("")
  const [docsExpanded, setDocsExpanded] = useState(true)
  const [collectionsExpanded, setCollectionsExpanded] = useState(true)
  const fileRef = useRef<HTMLInputElement>(null)

  function fetchDocs() {
    api.get<Document[]>("/documents").then(({ data }) => setDocs(data))
  }

  useEffect(() => {
    api.get<Document[]>("/documents").then(({ data }) => setDocs(data))
    api.get<Collection[]>("/collections").then(({ data }) => setCollections(data))
  }, [])

  useEffect(() => {
    const processing = docs.some(
      (d) => d.processing_status === "pending" || d.processing_status === "processing"
    )
    if (!processing) return
    const t = setTimeout(fetchDocs, 5000)
    return () => clearTimeout(t)
  }, [docs])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    const form = new FormData()
    form.append("file", file)
    try {
      const { data } = await api.post<Document>("/documents", form)
      setDocs((prev) => [data, ...prev])
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function handleDeleteDoc(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm("Delete this document? This cannot be undone.")) return
    await api.delete(`/documents/${id}`)
    setDocs((prev) => prev.filter((d) => d.id !== id))
    if (scope?.id === id) setScope(null)
  }

  async function handleCreateCollection() {
    const name = newCollectionName.trim()
    if (!name) return
    const { data } = await api.post<Collection>("/collections", { name })
    setCollections((prev) => [data, ...prev])
    setNewCollectionName("")
    setCreatingCollection(false)
  }

  async function handleDeleteCollection(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm("Delete this collection?")) return
    await api.delete(`/collections/${id}`)
    setCollections((prev) => prev.filter((c) => c.id !== id))
    if (scope?.id === id) setScope(null)
  }

  async function handleLogout() {
    await logout()
    setUser(null)
    router.replace("/login")
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-4 border-b border-gray-100 shrink-0">
        <span className="text-lg font-bold text-indigo-600">StudyBuddy</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Documents */}
        <div>
          <button
            onClick={() => setDocsExpanded((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-600"
          >
            <span className="flex items-center gap-2">
              <FileText className="h-3.5 w-3.5" />
              Documents
            </span>
            {docsExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>

          {docsExpanded && (
            <div>
              {docs.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => setScope({ type: "document", id: doc.id, name: doc.title })}
                  className={`group flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm transition-colors ${
                    scope?.id === doc.id
                      ? "bg-indigo-50 text-indigo-700"
                      : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(doc.processing_status)}`}
                  />
                  <span className="flex-1 truncate">{doc.title}</span>
                  <span
                    role="button"
                    onClick={(e) => handleDeleteDoc(doc.id, e)}
                    className="hidden shrink-0 rounded p-0.5 text-gray-300 hover:text-red-500 group-hover:block"
                  >
                    <Trash2 className="h-3 w-3" />
                  </span>
                </button>
              ))}
              {docs.length === 0 && (
                <p className="px-4 py-2 text-xs text-gray-400">No documents yet</p>
              )}
              <div className="px-4 py-2">
                <label
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-gray-300 px-3 py-1.5 text-xs text-gray-500 hover:border-indigo-400 hover:text-indigo-600 ${
                    uploading ? "pointer-events-none opacity-50" : ""
                  }`}
                >
                  {uploading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Upload className="h-3 w-3" />
                  )}
                  Upload document
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx"
                    className="hidden"
                    onChange={handleUpload}
                  />
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Collections */}
        <div className="mt-1">
          <button
            onClick={() => setCollectionsExpanded((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-600"
          >
            <span className="flex items-center gap-2">
              <FolderOpen className="h-3.5 w-3.5" />
              Collections
            </span>
            {collectionsExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>

          {collectionsExpanded && (
            <div>
              {collections.map((coll) => (
                <button
                  key={coll.id}
                  onClick={() => setScope({ type: "collection", id: coll.id, name: coll.name })}
                  className={`group flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm transition-colors ${
                    scope?.id === coll.id
                      ? "bg-indigo-50 text-indigo-700"
                      : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <FolderOpen className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                  <span className="flex-1 truncate">{coll.name}</span>
                  <span className="shrink-0 text-xs text-gray-400">{coll.document_count}</span>
                  <span
                    role="button"
                    onClick={(e) => handleDeleteCollection(coll.id, e)}
                    className="hidden shrink-0 rounded p-0.5 text-gray-300 hover:text-red-500 group-hover:block"
                  >
                    <Trash2 className="h-3 w-3" />
                  </span>
                </button>
              ))}

              {creatingCollection ? (
                <div className="flex gap-2 px-4 py-2">
                  <input
                    autoFocus
                    type="text"
                    value={newCollectionName}
                    onChange={(e) => setNewCollectionName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleCreateCollection()
                      if (e.key === "Escape") {
                        setCreatingCollection(false)
                        setNewCollectionName("")
                      }
                    }}
                    placeholder="Collection name…"
                    className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none"
                  />
                  <button
                    onClick={handleCreateCollection}
                    className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700"
                  >
                    OK
                  </button>
                </div>
              ) : (
                <div className="px-4 py-2">
                  <button
                    onClick={() => setCreatingCollection(true)}
                    className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-indigo-600"
                  >
                    <Plus className="h-3 w-3" />
                    New collection
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="shrink-0 border-t border-gray-200 p-4">
        <div className="flex items-center gap-2 mb-2">
          {user?.picture_url && (
            <Image
              src={user.picture_url}
              alt=""
              width={28}
              height={28}
              className="rounded-full"
              unoptimized
            />
          )}
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-gray-700">{user?.display_name}</p>
            <p className="truncate text-xs text-gray-400">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-700"
        >
          <LogOut className="h-3 w-3" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
