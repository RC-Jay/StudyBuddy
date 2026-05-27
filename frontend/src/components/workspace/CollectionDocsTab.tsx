"use client"

import { useState, useEffect } from "react"
import { Loader2, FolderOpen, Plus, X } from "lucide-react"
import api from "@/lib/api"
import type { Document, Collection } from "@/lib/types"

interface Props {
  collectionId: string
}

export function CollectionDocsTab({ collectionId }: Props) {
  const [allDocs, setAllDocs] = useState<Document[]>([])
  const [collection, setCollection] = useState<Collection | null>(null)
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<Document[]>("/documents"),
      api.get<Collection[]>("/collections"),
    ]).then(([docsRes, collRes]) => {
      setAllDocs(docsRes.data.filter((d) => d.processing_status === "ready" || d.processing_status === "summarising"))
      setCollection(collRes.data.find((c) => c.id === collectionId) ?? null)
      setLoading(false)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleAdd(docId: string) {
    setToggling(docId)
    try {
      await api.post(`/collections/${collectionId}/documents/${docId}`)
      setCollection((prev) =>
        prev
          ? { ...prev, document_ids: [...prev.document_ids, docId], document_count: prev.document_count + 1 }
          : prev
      )
    } finally {
      setToggling(null)
    }
  }

  async function handleRemove(docId: string) {
    setToggling(docId)
    try {
      await api.delete(`/collections/${collectionId}/documents/${docId}`)
      setCollection((prev) =>
        prev
          ? {
              ...prev,
              document_ids: prev.document_ids.filter((id) => id !== docId),
              document_count: prev.document_count - 1,
            }
          : prev
      )
    } finally {
      setToggling(null)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
      </div>
    )
  }

  const memberIds = new Set(collection?.document_ids ?? [])
  const members = allDocs.filter((d) => memberIds.has(d.id))
  const nonMembers = allDocs.filter((d) => !memberIds.has(d.id))

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-xl space-y-6">
        {/* Current members */}
        <div>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
            In this collection ({members.length})
          </h2>
          {members.length === 0 ? (
            <p className="text-sm text-gray-400">No documents added yet.</p>
          ) : (
            <ul className="space-y-1">
              {members.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center gap-3 rounded-lg border border-gray-100 bg-white px-4 py-3"
                >
                  <FolderOpen className="h-4 w-4 shrink-0 text-indigo-400" />
                  <span className="flex-1 truncate text-sm text-gray-800">{doc.title}</span>
                  <button
                    onClick={() => handleRemove(doc.id)}
                    disabled={toggling === doc.id}
                    title="Remove from collection"
                    className="shrink-0 rounded p-1 text-gray-300 hover:text-red-500 disabled:opacity-40"
                  >
                    {toggling === doc.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <X className="h-3.5 w-3.5" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Available to add */}
        {nonMembers.length > 0 && (
          <div>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Add documents
            </h2>
            <ul className="space-y-1">
              {nonMembers.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center gap-3 rounded-lg border border-gray-100 bg-white px-4 py-3 opacity-70 hover:opacity-100 transition-opacity"
                >
                  <FolderOpen className="h-4 w-4 shrink-0 text-gray-300" />
                  <span className="flex-1 truncate text-sm text-gray-600">{doc.title}</span>
                  <button
                    onClick={() => handleAdd(doc.id)}
                    disabled={toggling === doc.id}
                    title="Add to collection"
                    className="shrink-0 rounded p-1 text-gray-300 hover:text-indigo-500 disabled:opacity-40"
                  >
                    {toggling === doc.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Plus className="h-3.5 w-3.5" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
