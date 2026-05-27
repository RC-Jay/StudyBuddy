"use client"

import { useState, useEffect } from "react"
import { Loader2, FileText, ChevronDown, ChevronRight } from "lucide-react"
import api from "@/lib/api"
import type { Summary } from "@/lib/types"

interface Props {
  scopeType: "document" | "collection"
  scopeId: string
  docType?: "book" | "research_paper"
  isSummarising?: boolean
}

// ─── Book layout helpers ───────────────────────────────────────────────────

interface TreeNode {
  title: string
  summary: Summary | null      // null for chapter headers that have sub-sections
  children: TreeNode[]
}

function buildTree(summaries: Summary[]): TreeNode[] {
  // All summaries with section_hint containing ">" are section-level.
  // Those without ">" are chapter-level.
  const chapterMap = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  for (const s of summaries) {
    if (!s.section_hint) continue
    if (s.section_hint.includes(" > ")) {
      const [chTitle, secTitle] = s.section_hint.split(" > ", 2)
      if (!chapterMap.has(chTitle)) {
        const node: TreeNode = { title: chTitle, summary: null, children: [] }
        chapterMap.set(chTitle, node)
        roots.push(node)
      }
      chapterMap.get(chTitle)!.children.push({
        title: secTitle,
        summary: s,
        children: [],
      })
    } else {
      // No ">": flat chapter node (leaf)
      if (!chapterMap.has(s.section_hint)) {
        const node: TreeNode = { title: s.section_hint, summary: s, children: [] }
        chapterMap.set(s.section_hint, node)
        roots.push(node)
      }
    }
  }
  return roots
}

function BookLayout({ summaries }: { summaries: Summary[] }) {
  const tree = buildTree(summaries)
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    // Expand all chapters by default
    const s = new Set<string>()
    tree.forEach((n) => s.add(n.title))
    return s
  })
  const [selected, setSelected] = useState<Summary | null>(() => {
    // Select first leaf by default
    for (const node of tree) {
      if (node.summary) return node.summary
      if (node.children.length > 0 && node.children[0].summary)
        return node.children[0].summary
    }
    return null
  })

  function toggle(title: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(title)) next.delete(title)
      else next.add(title)
      return next
    })
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Chapter tree */}
      <aside className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-gray-100 bg-gray-50 py-2">
        {tree.map((chapter) =>
          chapter.children.length > 0 ? (
            // Chapter with sub-sections
            <div key={chapter.title}>
              <button
                onClick={() => toggle(chapter.title)}
                className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-semibold text-gray-500 hover:text-gray-700"
              >
                {expanded.has(chapter.title) ? (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                )}
                <span className="truncate">{chapter.title}</span>
              </button>
              {expanded.has(chapter.title) &&
                chapter.children.map((sec) => (
                  <button
                    key={sec.title}
                    onClick={() => sec.summary && setSelected(sec.summary)}
                    className={`w-full py-1.5 pl-7 pr-3 text-left text-xs transition-colors hover:bg-white ${
                      selected?.id === sec.summary?.id
                        ? "bg-white font-medium text-indigo-700"
                        : "text-gray-600"
                    }`}
                  >
                    <span className="truncate block">{sec.title}</span>
                  </button>
                ))}
            </div>
          ) : (
            // Flat chapter (leaf)
            <button
              key={chapter.title}
              onClick={() => chapter.summary && setSelected(chapter.summary)}
              className={`flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs transition-colors hover:bg-white ${
                selected?.id === chapter.summary?.id
                  ? "bg-white font-medium text-indigo-700"
                  : "text-gray-600"
              }`}
            >
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-gray-300" />
              <span className="truncate">{chapter.title}</span>
            </button>
          )
        )}
      </aside>

      {/* Content panel */}
      <div className="flex-1 overflow-y-auto p-6">
        {selected ? (
          <div className="mx-auto max-w-2xl">
            <h2 className="mb-4 text-sm font-semibold text-gray-700">
              {selected.section_hint}
            </h2>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
              {selected.content}
            </p>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-gray-400">
            <p className="text-sm">Select a chapter to read its summary</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Research paper layout ─────────────────────────────────────────────────

function PaperLayout({ summaries }: { summaries: Summary[] }) {
  const fullSummary = summaries.find((s) => s.granularity === "full")
  const concepts = summaries.find((s) => s.granularity === "concepts")

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-2xl space-y-6">
        {fullSummary && (
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
            <div className="mb-3 flex items-center gap-2">
              <FileText className="h-4 w-4 text-indigo-500" />
              <span className="text-sm font-semibold text-gray-700">Summary</span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
              {fullSummary.content}
            </p>
          </div>
        )}
        {concepts && (
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
            <div className="mb-3 flex items-center gap-2">
              <FileText className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-semibold text-gray-700">Key Concepts</span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
              {concepts.content}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────

export function SummariseTab({ scopeType, scopeId, docType, isSummarising }: Props) {
  const [summaries, setSummaries] = useState<Summary[]>([])
  // loading starts true; component remounts on scope change (key={scope.id} in parent)
  const [loading, setLoading] = useState(true)

  function fetchSummaries(cancelled: { value: boolean }) {
    api.get<Summary[]>("/summaries").then(({ data }) => {
      if (cancelled.value) return
      const scoped = data.filter(
        (s) => s.scope_type === scopeType && s.scope_id === scopeId
      )
      setSummaries(scoped)
      setLoading(false)
    })
  }

  // Initial fetch on mount
  useEffect(() => {
    const cancelled = { value: false }
    fetchSummaries(cancelled)
    return () => { cancelled.value = true }
  // scopeId and scopeType are stable for the lifetime of this component instance
  // (parent uses key={scope.id} to remount on scope change)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Poll every 15s while summaries are still being generated
  useEffect(() => {
    if (!isSummarising) return
    const cancelled = { value: false }
    const interval = setInterval(() => fetchSummaries(cancelled), 15000)
    return () => {
      cancelled.value = true
      clearInterval(interval)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSummarising])

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
      </div>
    )
  }

  if (summaries.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-gray-400">
        <div className="text-center">
          <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-indigo-300" />
          <p className="text-sm font-medium text-gray-500">
            {isSummarising ? "Generating first summaries…" : "No summaries yet"}
          </p>
          <p className="mt-1 text-xs text-gray-400">
            {isSummarising
              ? "Sections will appear here as they are ready."
              : "Summaries are generated automatically when a document is processed."}
          </p>
        </div>
      </div>
    )
  }

  // Infer layout from doc_type prop or from granularity of existing summaries
  const effectiveDocType =
    docType ??
    (summaries.some((s) => s.granularity === "chapter") ? "book" : "research_paper")

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {effectiveDocType === "book" ? (
        <BookLayout summaries={summaries} />
      ) : (
        <PaperLayout summaries={summaries} />
      )}
    </div>
  )
}
