"use client"

import { useState, useEffect } from "react"
import { Loader2, FileText } from "lucide-react"
import api from "@/lib/api"
import type { Document, Collection, Summary } from "@/lib/types"

export default function SummariesPage() {
  const [docs, setDocs] = useState<Document[]>([])
  const [collections, setCollections] = useState<Collection[]>([])
  const [summaries, setSummaries] = useState<Summary[]>([])
  const [generating, setGenerating] = useState(false)
  const [config, setConfig] = useState({ scopeType: "document", scopeId: "", granularity: "full", sectionHint: "" })
  const [activeSummary, setActiveSummary] = useState<Summary | null>(null)

  useEffect(() => {
    api.get<Document[]>("/documents").then(({ data }) => setDocs(data.filter((d) => d.processing_status === "ready")))
    api.get<Collection[]>("/collections").then(({ data }) => setCollections(data))
    api.get<Summary[]>("/summaries").then(({ data }) => setSummaries(data))
  }, [])

  async function generate() {
    if (!config.scopeId) return
    setGenerating(true)
    try {
      const { data } = await api.post<Summary>("/summaries", {
        scope_type: config.scopeType,
        scope_id: config.scopeId,
        granularity: config.granularity,
        section_hint: config.granularity === "section" ? config.sectionHint : null,
      })
      setSummaries((prev) => [data, ...prev])
      setActiveSummary(data)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex h-full">
      {/* Saved summaries */}
      <aside className="flex w-56 flex-col border-r border-gray-200 bg-white">
        <div className="px-4 py-3 border-b border-gray-100">
          <span className="text-sm font-medium text-gray-700">Saved</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {summaries.map((s) => (
            <button key={s.id} onClick={() => setActiveSummary(s)} className={`w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 ${activeSummary?.id === s.id ? "bg-indigo-50 text-indigo-700" : "text-gray-700"}`}>
              <p className="capitalize font-medium">{s.granularity}</p>
              <p className="text-xs text-gray-400 truncate">{s.scope_type} · {new Date(s.created_at).toLocaleDateString()}</p>
            </button>
          ))}
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-auto">
        {/* Generate form */}
        <div className="border-b border-gray-200 bg-white p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600">Scope</label>
              <select value={config.scopeType} onChange={(e) => setConfig((c) => ({ ...c, scopeType: e.target.value, scopeId: "" }))} className="mt-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none">
                <option value="document">Document</option>
                <option value="collection">Collection</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600">{config.scopeType === "document" ? "Document" : "Collection"}</label>
              <select value={config.scopeId} onChange={(e) => setConfig((c) => ({ ...c, scopeId: e.target.value }))} className="mt-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none">
                <option value="">Select…</option>
                {(config.scopeType === "document" ? docs : collections).map((item) => (
                  <option key={item.id} value={item.id}>{(item as Document).title || (item as Collection).name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600">Type</label>
              <select value={config.granularity} onChange={(e) => setConfig((c) => ({ ...c, granularity: e.target.value }))} className="mt-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none">
                <option value="full">Full Summary</option>
                <option value="tldr">TLDR</option>
                <option value="concepts">Key Concepts</option>
                <option value="section">Section</option>
              </select>
            </div>
            {config.granularity === "section" && (
              <div>
                <label className="block text-xs font-medium text-gray-600">Section</label>
                <input type="text" placeholder="e.g. Chapter 3, Methodology" value={config.sectionHint} onChange={(e) => setConfig((c) => ({ ...c, sectionHint: e.target.value }))} className="mt-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none" />
              </div>
            )}
            <button onClick={generate} disabled={!config.scopeId || generating} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {generating ? <><Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" />Generating…</> : "Generate"}
            </button>
          </div>
        </div>

        {/* Summary content */}
        <div className="flex-1 overflow-auto p-6">
          {activeSummary ? (
            <div className="mx-auto max-w-2xl rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <div className="mb-4 flex items-center gap-2">
                <FileText className="h-4 w-4 text-indigo-500" />
                <span className="text-sm font-medium capitalize text-gray-700">{activeSummary.granularity} Summary</span>
                {activeSummary.section_hint && <span className="text-sm text-gray-400">· {activeSummary.section_hint}</span>}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">{activeSummary.content}</p>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-gray-400">
              <p className="text-sm">Select a saved summary or generate a new one</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
