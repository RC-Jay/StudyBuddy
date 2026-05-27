"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Image from "next/image"
import { Upload, Trash2, FileText, Loader2, Plus, FolderOpen, LogOut, ChevronDown, ChevronUp, AlertCircle, FolderPlus, Check } from "lucide-react"
import api from "@/lib/api"
import { useAuthStore } from "@/lib/store"
import { logout } from "@/lib/auth"
import { useRouter } from "next/navigation"
import type { Document, Collection } from "@/lib/types"

function DocStatusIndicator({ status }: { status: Document["processing_status"] }) {
  if (status === "processing" || status === "pending") {
    return <Loader2 className="h-3 w-3 shrink-0 animate-spin text-blue-400" />
  }
  if (status === "summarising") {
    return <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400 animate-pulse" />
  }
  if (status === "failed") {
    return <AlertCircle className="h-3 w-3 shrink-0 text-red-400" />
  }
  return <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-green-400" />
}

interface CollectionPickerProps {
  doc: Document
  collections: Collection[]
  onToggle: (collId: string, inCollection: boolean) => Promise<void>
  onClose: () => void
  anchorRect: DOMRect
}

function CollectionPicker({ doc, collections, onToggle, onClose, anchorRect }: CollectionPickerProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener("mousedown", handleMouseDown)
    return () => document.removeEventListener("mousedown", handleMouseDown)
  }, [onClose])

  // Position: right of the sidebar, aligned with the anchor button
  const top = Math.min(anchorRect.top, window.innerHeight - 200)
  const left = anchorRect.right + 4

  return (
    <div
      ref={ref}
      style={{ position: "fixed", top, left, zIndex: 50 }}
      className="w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
    >
      <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Add to collection
      </p>
      {collections.length === 0 && (
        <p className="px-3 py-2 text-xs text-gray-400">No collections yet</p>
      )}
      {collections.map((coll) => {
        const isMember = coll.document_ids.includes(doc.id)
        return (
          <button
            key={coll.id}
            onClick={() => onToggle(coll.id, isMember)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-gray-700 hover:bg-gray-50"
          >
            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-gray-400" />
            <span className="flex-1 truncate">{coll.name}</span>
            {isMember && <Check className="h-3 w-3 shrink-0 text-indigo-500" />}
          </button>
        )
      })}
    </div>
  )
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
  const [pickerDocId, setPickerDocId] = useState<string | null>(null)
  const [pickerAnchorRect, setPickerAnchorRect] = useState<DOMRect | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const fetchDocs = useCallback(() => {
    api.get<Document[]>("/documents").then(({ data }) => {
      setDocs(data)
      const currentScope = useAuthStore.getState().scope
      if (currentScope?.type === "document") {
        const updated = data.find((d) => d.id === currentScope.id)
        if (updated && (updated.processing_status !== currentScope.status || updated.expected_summary_count !== currentScope.expected_summary_count)) {
          setScope({ ...currentScope, status: updated.processing_status, expected_summary_count: updated.expected_summary_count ?? undefined })
        }
      }
    })
  }, [setScope])

  useEffect(() => {
    api.get<Document[]>("/documents").then(({ data }) => setDocs(data))
    api.get<Collection[]>("/collections").then(({ data }) => setCollections(data))
  }, [])

  useEffect(() => {
    const inFlight = docs.some(
      (d) =>
        d.processing_status === "pending" ||
        d.processing_status === "processing" ||
        d.processing_status === "summarising"
    )
    if (!inFlight) return
    const t = setTimeout(fetchDocs, 60000)
    return () => clearTimeout(t)
  }, [docs, fetchDocs])

  function selectDoc(doc: Document) {
    if (doc.processing_status !== "ready" && doc.processing_status !== "summarising") return
    setScope({
      type: "document",
      id: doc.id,
      name: doc.title,
      status: doc.processing_status,
      doc_type: doc.doc_type ?? undefined,
      expected_summary_count: doc.expected_summary_count ?? undefined,
    })
  }

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

  function openPicker(doc: Document, e: React.MouseEvent) {
    e.stopPropagation()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setPickerDocId(doc.id)
    setPickerAnchorRect(rect)
  }

  async function handleToggleCollection(collId: string, isMember: boolean) {
    if (!pickerDocId) return
    if (isMember) {
      await api.delete(`/collections/${collId}/documents/${pickerDocId}`)
      setCollections((prev) =>
        prev.map((c) =>
          c.id === collId
            ? { ...c, document_ids: c.document_ids.filter((id) => id !== pickerDocId), document_count: c.document_count - 1 }
            : c
        )
      )
    } else {
      await api.post(`/collections/${collId}/documents/${pickerDocId}`)
      setCollections((prev) =>
        prev.map((c) =>
          c.id === collId
            ? { ...c, document_ids: [...c.document_ids, pickerDocId], document_count: c.document_count + 1 }
            : c
        )
      )
    }
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

  const pickerDoc = pickerDocId ? docs.find((d) => d.id === pickerDocId) ?? null : null

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
              {docs.map((doc) => {
                const isReady = doc.processing_status === "ready" || doc.processing_status === "summarising"
                const isSelected = scope?.id === doc.id
                return (
                  <div
                    key={doc.id}
                    onClick={() => selectDoc(doc)}
                    className={`group flex w-full items-center gap-2.5 px-4 py-2 text-sm transition-colors ${
                      isReady ? "cursor-pointer" : "cursor-default"
                    } ${
                      isSelected
                        ? "bg-indigo-50 text-indigo-700"
                        : isReady
                        ? "text-gray-700 hover:bg-gray-50"
                        : "text-gray-400"
                    }`}
                  >
                    <DocStatusIndicator status={doc.processing_status} />
                    <span className="flex-1 truncate">{doc.title}</span>
                    {doc.processing_status === "failed" && (
                      <span
                        title={doc.processing_error ?? undefined}
                        className="shrink-0 cursor-help rounded bg-red-50 px-1 py-0.5 text-xs text-red-500"
                      >
                        failed
                      </span>
                    )}
                    {/* Action buttons — visible on row hover */}
                    {isReady && (
                      <span
                        role="button"
                        onClick={(e) => openPicker(doc, e)}
                        title="Add to collection"
                        className="hidden shrink-0 rounded p-0.5 text-gray-300 hover:text-indigo-500 group-hover:block"
                      >
                        <FolderPlus className="h-3 w-3" />
                      </span>
                    )}
                    <span
                      role="button"
                      onClick={(e) => handleDeleteDoc(doc.id, e)}
                      className="hidden shrink-0 rounded p-0.5 text-gray-300 hover:text-red-500 group-hover:block"
                    >
                      <Trash2 className="h-3 w-3" />
                    </span>
                  </div>
                )
              })}
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

      {/* Collection picker popover */}
      {pickerDoc && pickerAnchorRect && (
        <CollectionPicker
          doc={pickerDoc}
          collections={collections}
          onToggle={handleToggleCollection}
          onClose={() => setPickerDocId(null)}
          anchorRect={pickerAnchorRect}
        />
      )}
    </aside>
  )
}
