"use client"

import { useState, useEffect, useRef } from "react"
import { Upload, Trash2, FileText, Loader2, RefreshCw } from "lucide-react"
import api from "@/lib/api"
import type { Document } from "@/lib/types"

function statusColor(status: Document["processing_status"]) {
  return { pending: "text-yellow-600 bg-yellow-50", processing: "text-blue-600 bg-blue-50", ready: "text-green-600 bg-green-50", failed: "text-red-600 bg-red-50" }[status]
}

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function LibraryPage() {
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchDocs()
  }, [])

  // Poll processing documents every 5s
  useEffect(() => {
    const processing = docs.some((d) => d.processing_status === "pending" || d.processing_status === "processing")
    if (!processing) return
    const t = setTimeout(fetchDocs, 5000)
    return () => clearTimeout(t)
  }, [docs])

  async function fetchDocs() {
    try {
      const { data } = await api.get<Document[]>("/documents")
      setDocs(data)
    } catch {
      setError("Failed to load documents")
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    const form = new FormData()
    form.append("file", file)
    try {
      const { data } = await api.post<Document>("/documents", form)
      setDocs((prev) => [data, ...prev])
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(msg || "Upload failed")
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this document? This cannot be undone.")) return
    await api.delete(`/documents/${id}`)
    setDocs((prev) => prev.filter((d) => d.id !== id))
  }

  return (
    <div className="flex flex-1 flex-col overflow-auto">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-lg font-semibold text-gray-900">Library</h1>
        <div className="flex items-center gap-2">
          <button onClick={fetchDocs} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100">
            <RefreshCw className="h-4 w-4" />
          </button>
          <label className={`flex cursor-pointer items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 ${uploading ? "opacity-50 pointer-events-none" : ""}`}>
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Upload
            <input ref={fileRef} type="file" accept=".pdf,.docx" className="hidden" onChange={handleUpload} />
          </label>
        </div>
      </header>

      <div className="flex-1 p-6">
        {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
          </div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <FileText className="mb-3 h-12 w-12" />
            <p className="text-sm">No documents yet. Upload a PDF or DOCX to get started.</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {docs.map((doc) => (
              <div key={doc.id} className="flex flex-col rounded-xl bg-white p-4 shadow-sm ring-1 ring-gray-200">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 shrink-0 text-indigo-500" />
                    <span className="truncate text-sm font-medium text-gray-900">{doc.title}</span>
                  </div>
                  <button onClick={() => handleDelete(doc.id)} className="shrink-0 rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${statusColor(doc.processing_status)}`}>
                    {doc.processing_status}
                  </span>
                  <span className="text-xs text-gray-400">
                    {doc.page_count ? `${doc.page_count}p · ` : ""}{fileSize(doc.file_size_bytes)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
