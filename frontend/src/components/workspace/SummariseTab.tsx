"use client"

import { useState, useEffect } from "react"
import { Loader2, FileText, ChevronDown, ChevronRight, BookOpen } from "lucide-react"
import api from "@/lib/api"
import type { Summary, TocItem } from "@/lib/types"

interface Props {
  scopeType: "document" | "collection"
  scopeId: string
  docType?: "book" | "research_paper"
  isSummarising?: boolean
  expectedTotal?: number
  toc?: TocItem[] | null
}

// ─── Progress bar ──────────────────────────────────────────────────────────

function GeneratingBar({ done, total }: { done: number; total?: number }) {
  const pct = total ? Math.min(100, Math.round((done / total) * 100)) : null

  return (
    <div className="shrink-0 border-b border-indigo-100 bg-indigo-50 px-4 py-2.5">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-indigo-600">
          <Loader2 className="h-3 w-3 animate-spin" />
          Generating summaries…
        </span>
        <span className="text-xs text-indigo-500">
          {total ? `${done} / ${total} done` : `${done} ready`}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-indigo-100">
        {pct !== null ? (
          <div
            className="h-full rounded-full bg-indigo-500 transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        ) : (
          <div className="h-full w-2/5 rounded-full bg-indigo-400 [animation:slide-x_1.6s_ease-in-out_infinite]" />
        )}
      </div>
    </div>
  )
}

// ─── Tree building ─────────────────────────────────────────────────────────

interface TreeNode {
  /** Display label */
  title: string
  /** Full section_hint — used as the expand/select key */
  hint: string
  summary: Summary | null
  children: TreeNode[]
}

/**
 * Build the outline tree from the stored TOC (preferred) or fall back to
 * reconstructing it from the flat summaries list.
 *
 * TOC item shapes (from backend):
 *   type="part"    → { title, chapters: [{ title, sections: string[] }] }
 *   type="chapter" → { title, sections: string[] }
 *
 * section_hint formats produced by the backend:
 *   "Part I. Data Structures"                        → Part node (depth 0)
 *   "Part I. Data Structures > 1. Chapter"           → Chapter node (depth 1)
 *   "Escaping monolithic hell > 1.1 The slow march"  → Section node (depth 1)
 */
function buildTreeFromToc(toc: TocItem[], summaryMap: Map<string, Summary>): TreeNode[] {
  const roots: TreeNode[] = []

  for (const item of toc) {
    if (item.type === "part") {
      // Depth-0: Part node (summary keyed by part title alone)
      const partHint = item.title
      const partNode: TreeNode = {
        title: item.title,
        hint: partHint,
        summary: summaryMap.get(partHint) ?? null,
        children: [],
      }
      roots.push(partNode)

      for (const ch of item.chapters ?? []) {
        const chHint = `${partHint} > ${ch.title}`
        const chNode: TreeNode = {
          title: ch.title,
          hint: chHint,
          summary: summaryMap.get(chHint) ?? null,
          children: [],
        }
        partNode.children.push(chNode)

        for (const sec of ch.sections ?? []) {
          const secHint = `${chHint} > ${sec}`
          chNode.children.push({
            title: sec,
            hint: secHint,
            summary: summaryMap.get(secHint) ?? null,
            children: [],
          })
        }
      }
    } else {
      // type="chapter" — depth-0 standalone chapter
      const chHint = item.title
      const chNode: TreeNode = {
        title: item.title,
        hint: chHint,
        summary: summaryMap.get(chHint) ?? null,
        children: [],
      }
      roots.push(chNode)

      for (const sec of item.sections ?? []) {
        const secHint = `${chHint} > ${sec}`
        chNode.children.push({
          title: sec,
          hint: secHint,
          summary: summaryMap.get(secHint) ?? null,
          children: [],
        })
      }
    }
  }

  return roots
}

/**
 * Fallback: reconstruct tree from flat summaries when no TOC is stored.
 */
function buildTreeFromSummaries(summaries: Summary[]): TreeNode[] {
  const byHint = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  function getOrCreate(hint: string, title: string, parentHint: string | null): TreeNode {
    if (byHint.has(hint)) return byHint.get(hint)!
    const node: TreeNode = { title, hint, summary: null, children: [] }
    byHint.set(hint, node)
    if (parentHint === null) roots.push(node)
    else byHint.get(parentHint)!.children.push(node)
    return node
  }

  for (const s of summaries) {
    if (!s.section_hint) continue
    const parts = s.section_hint.split(" > ")
    if (parts.length === 1) {
      getOrCreate(parts[0], parts[0], null).summary = s
    } else if (parts.length === 2) {
      getOrCreate(parts[0], parts[0], null)
      getOrCreate(s.section_hint, parts[1], parts[0]).summary = s
    } else if (parts.length === 3) {
      const p01 = `${parts[0]} > ${parts[1]}`
      getOrCreate(parts[0], parts[0], null)
      getOrCreate(p01, parts[1], parts[0])
      getOrCreate(s.section_hint, parts[2], p01).summary = s
    }
  }
  return roots
}

function firstSelectableSummary(nodes: TreeNode[]): Summary | null {
  for (const n of nodes) {
    if (n.summary) return n.summary
    const found = firstSelectableSummary(n.children)
    if (found) return found
  }
  return null
}

// ─── Recursive tree item ───────────────────────────────────────────────────

function TreeItem({
  node,
  depth,
  expanded,
  onToggle,
  selected,
  onSelect,
}: {
  node: TreeNode
  depth: number
  expanded: Set<string>
  onToggle: (hint: string) => void
  selected: Summary | null
  onSelect: (s: Summary) => void
}) {
  const hasChildren = node.children.length > 0
  const isExpanded = expanded.has(node.hint)
  const isSelected = node.summary !== null && selected?.id === node.summary.id
  const hasSummary = node.summary !== null
  const paddingLeft = 12 + depth * 16

  // Style by depth: depth-0 = part/standalone (bolder), deeper = lighter
  const baseTextCls =
    depth === 0
      ? "text-xs font-semibold py-2"
      : "text-xs py-1.5"

  const colorCls = hasSummary
    ? depth === 0
      ? "text-gray-600 hover:text-gray-800"
      : "text-gray-600 hover:text-gray-800"
    : "text-gray-400"

  return (
    <div>
      <button
        style={{ paddingLeft, paddingRight: 12 }}
        onClick={() => {
          if (hasChildren) onToggle(node.hint)
          if (hasSummary) onSelect(node.summary!)
        }}
        disabled={!hasChildren && !hasSummary}
        className={`flex w-full items-center gap-1.5 text-left transition-colors ${baseTextCls} ${colorCls} ${
          isSelected ? "bg-white !text-indigo-700 font-medium" : "hover:bg-white"
        } disabled:cursor-default disabled:hover:bg-transparent`}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )
        ) : (
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${hasSummary ? "bg-indigo-400" : "bg-gray-200"}`} />
        )}
        <span className="truncate">{node.title}</span>
        {!hasSummary && !hasChildren && (
          <Loader2 className="ml-auto h-2.5 w-2.5 shrink-0 animate-spin text-gray-300" />
        )}
      </button>

      {hasChildren && isExpanded &&
        node.children.map((child) => (
          <TreeItem
            key={child.hint}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
            selected={selected}
            onSelect={onSelect}
          />
        ))}
    </div>
  )
}

// ─── Book layout ───────────────────────────────────────────────────────────

function BookLayout({
  summaries,
  toc,
  isSummarising,
  expectedTotal,
}: {
  summaries: Summary[]
  toc?: TocItem[] | null
  isSummarising?: boolean
  expectedTotal?: number
}) {
  // Build a hint→summary map for O(1) lookup when overlaying summaries onto TOC nodes
  const summaryMap = new Map(
    summaries.filter((s) => s.section_hint).map((s) => [s.section_hint!, s])
  )

  const tree = toc && toc.length > 0
    ? buildTreeFromToc(toc, summaryMap)
    : buildTreeFromSummaries(summaries)

  const [expanded, setExpanded] = useState<Set<string>>(() => {
    // Expand all depth-0 nodes initially
    const s = new Set<string>()
    tree.forEach((n) => s.add(n.hint))
    return s
  })

  const [selected, setSelected] = useState<Summary | null>(() =>
    firstSelectableSummary(tree)
  )

  function toggle(hint: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(hint)) next.delete(hint)
      else next.add(hint)
      return next
    })
  }

  const totalNodes = toc
    ? toc.reduce((acc, item) => {
        if (item.type === "part") {
          return acc + 1 + (item.chapters?.reduce((a, ch) => a + 1 + (ch.sections?.length ?? 0), 0) ?? 0)
        }
        return acc + 1 + (item.sections?.length ?? 0)
      }, 0)
    : undefined

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {isSummarising && <GeneratingBar done={summaries.length} total={expectedTotal ?? totalNodes} />}
      <div className="flex flex-1 overflow-hidden">
        {/* Tree sidebar */}
        <aside className="flex w-64 shrink-0 flex-col overflow-y-auto border-r border-gray-100 bg-gray-50 py-2">
          {/* Outline header */}
          <div className="flex items-center gap-1.5 px-3 pb-2 pt-1">
            <BookOpen className="h-3 w-3 text-gray-400" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              Book Outline
            </span>
          </div>

          {tree.map((node) => (
            <TreeItem
              key={node.hint}
              node={node}
              depth={0}
              expanded={expanded}
              onToggle={toggle}
              selected={selected}
              onSelect={setSelected}
            />
          ))}
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
              <div className="text-center">
                <BookOpen className="mx-auto mb-3 h-8 w-8 opacity-30" />
                <p className="text-sm">Select a section to read its summary</p>
                {isSummarising && (
                  <p className="mt-1 text-xs text-indigo-400">Summaries are being generated…</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Research paper layout ─────────────────────────────────────────────────

function PaperLayout({
  summaries,
  isSummarising,
  expectedTotal,
}: {
  summaries: Summary[]
  isSummarising?: boolean
  expectedTotal?: number
}) {
  const fullSummary = summaries.find((s) => s.granularity === "full")
  const concepts = summaries.find((s) => s.granularity === "concepts")

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {isSummarising && <GeneratingBar done={summaries.length} total={expectedTotal} />}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-2xl space-y-6">
          {fullSummary ? (
            <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <div className="mb-3 flex items-center gap-2">
                <FileText className="h-4 w-4 text-indigo-500" />
                <span className="text-sm font-semibold text-gray-700">Summary</span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
                {fullSummary.content}
              </p>
            </div>
          ) : isSummarising ? (
            <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-indigo-100">
              <div className="mb-3 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
                <span className="text-sm font-semibold text-gray-400">Summary generating…</span>
              </div>
              <div className="space-y-2">
                <div className="h-3 w-full animate-pulse rounded bg-gray-100" />
                <div className="h-3 w-5/6 animate-pulse rounded bg-gray-100" />
                <div className="h-3 w-4/6 animate-pulse rounded bg-gray-100" />
              </div>
            </div>
          ) : null}

          {concepts ? (
            <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <div className="mb-3 flex items-center gap-2">
                <FileText className="h-4 w-4 text-purple-500" />
                <span className="text-sm font-semibold text-gray-700">Key Concepts</span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
                {concepts.content}
              </p>
            </div>
          ) : isSummarising ? (
            <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-indigo-100">
              <div className="mb-3 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-purple-400" />
                <span className="text-sm font-semibold text-gray-400">Key Concepts generating…</span>
              </div>
              <div className="space-y-2">
                <div className="h-3 w-full animate-pulse rounded bg-gray-100" />
                <div className="h-3 w-3/4 animate-pulse rounded bg-gray-100" />
                <div className="h-3 w-5/6 animate-pulse rounded bg-gray-100" />
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────

export function SummariseTab({ scopeType, scopeId, docType, isSummarising, expectedTotal, toc }: Props) {
  const [summaries, setSummaries] = useState<Summary[]>([])
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

  useEffect(() => {
    const cancelled = { value: false }
    fetchSummaries(cancelled)
    return () => { cancelled.value = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
      <div className="flex flex-1 flex-col overflow-hidden">
        {isSummarising && <GeneratingBar done={0} total={expectedTotal} />}
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
      </div>
    )
  }

  const effectiveDocType =
    docType ??
    (summaries.some((s) => s.granularity === "chapter") ? "book" : "research_paper")

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {effectiveDocType === "book" ? (
        <BookLayout summaries={summaries} toc={toc} isSummarising={isSummarising} expectedTotal={expectedTotal} />
      ) : (
        <PaperLayout summaries={summaries} isSummarising={isSummarising} expectedTotal={expectedTotal} />
      )}
    </div>
  )
}
