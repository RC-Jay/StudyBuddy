"use client"

import { useState, useEffect } from "react"
import { Loader2, FileText } from "lucide-react"
import api from "@/lib/api"
import type { Summary } from "@/lib/types"

interface Props {
  scopeType: "document" | "collection"
  scopeId: string
}

export function SummariseTab({ scopeType, scopeId }: Props) {
  const [summaries, setSummaries] = useState<Summary[]>([])
  const [generating, setGenerating] = useState(false)
  const [granularity, setGranularity] = useState("full")
  const [sectionHint, setSectionHint] = useState("")
  const [activeSummary, setActiveSummary] = useState<Summary | null>(null)

  useEffect(() => {
    let cancelled = false

    api.get<Summary[]>("/summaries").then(({ data }) => {
      if (cancelled) return
      const scoped = data.filter(
        (s) => s.scope_type === scopeType && s.scope_id === scopeId
      )
      setSummaries(scoped)
      if (scoped.length > 0) setActiveSummary(scoped[0])
    })

    return () => {
      cancelled = true
    }
  }, [scopeId, scopeType])

  async function generate() {
    setGenerating(true)
    try {
      const { data } = await api.post<Summary>("/summaries", {
        scope_type: scopeType,
        scope_id: scopeId,
        granularity,
        section_hint: granularity === "section" ? sectionHint : null,
      })
      setSummaries((prev) => [data, ...prev])
      setActiveSummary(data)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600">Type</label>
            <select
              value={granularity}
              onChange={(e) => setGranularity(e.target.value)}
              className="mt-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            >
              <option value="full">Full Summary</option>
              <option value="tldr">TLDR</option>
              <option value="concepts">Key Concepts</option>
              <option value="section">Section</option>
            </select>
          </div>

          {granularity === "section" && (
            <div>
              <label className="block text-xs font-medium text-gray-600">Section</label>
              <input
                type="text"
                placeholder="e.g. Chapter 3, Methodology"
                value={sectionHint}
                onChange={(e) => setSectionHint(e.target.value)}
                className="mt-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          )}

          <button
            onClick={generate}
            disabled={generating || (granularity === "section" && !sectionHint.trim())}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {generating ? (
              <>
                <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" />
                Generating…
              </>
            ) : (
              "Generate"
            )}
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {summaries.length > 0 && (
          <aside className="flex w-44 shrink-0 flex-col overflow-y-auto border-r border-gray-100 bg-gray-50">
            <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Saved
            </div>
            {summaries.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveSummary(s)}
                className={`w-full px-3 py-2 text-left text-xs transition-colors hover:bg-white ${
                  activeSummary?.id === s.id
                    ? "bg-white font-medium text-indigo-700"
                    : "text-gray-600"
                }`}
              >
                <p className="capitalize">{s.granularity}</p>
                <p className="text-gray-400">{new Date(s.created_at).toLocaleDateString()}</p>
              </button>
            ))}
          </aside>
        )}

        <div className="flex-1 overflow-y-auto p-6">
          {activeSummary ? (
            <div className="mx-auto max-w-2xl rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <div className="mb-4 flex items-center gap-2">
                <FileText className="h-4 w-4 text-indigo-500" />
                <span className="text-sm font-medium capitalize text-gray-700">
                  {activeSummary.granularity} Summary
                </span>
                {activeSummary.section_hint && (
                  <span className="text-sm text-gray-400">· {activeSummary.section_hint}</span>
                )}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
                {activeSummary.content}
              </p>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-gray-400">
              <div className="text-center">
                <FileText className="mx-auto mb-3 h-10 w-10 opacity-20" />
                <p className="text-sm">Generate a summary of this document</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
