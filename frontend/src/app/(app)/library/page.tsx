"use client"

import { useAuthStore } from "@/lib/store"
import { LibrarySidebar } from "@/components/workspace/LibrarySidebar"
import { ChatTab } from "@/components/workspace/ChatTab"
import { SummariseTab } from "@/components/workspace/SummariseTab"
import { QuizTab } from "@/components/workspace/QuizTab"
import { CollectionDocsTab } from "@/components/workspace/CollectionDocsTab"
import { MessageSquare, FileText, ClipboardList, BookOpen, Loader2, AlertCircle, Library } from "lucide-react"
import type { WorkspaceScope } from "@/lib/store"

const documentTabs = [
  { id: "chat" as const, label: "Chat", icon: MessageSquare },
  { id: "summarise" as const, label: "Summaries", icon: FileText },
  { id: "quiz" as const, label: "Quiz", icon: ClipboardList },
]

const collectionTabs = [
  { id: "chat" as const, label: "Chat", icon: MessageSquare },
  { id: "documents" as const, label: "Documents", icon: Library },
  { id: "quiz" as const, label: "Quiz", icon: ClipboardList },
]

function getTabsForScope(scope: WorkspaceScope) {
  return scope.type === "collection" ? collectionTabs : documentTabs
}

export default function LibraryPage() {
  const { scope, activeTab, setActiveTab } = useAuthStore()

  // If the active tab isn't available for the current scope, fall back to chat
  const visibleTabs = scope ? getTabsForScope(scope).map((t) => t.id) : []
  const effectiveTab =
    scope && visibleTabs.includes(activeTab) ? activeTab : "chat"

  const isSummarising = scope?.status === "summarising"
  const tabsVisible =
    !scope?.status || scope.status === "ready" || scope.status === "summarising"

  return (
    <div className="flex h-full overflow-hidden">
      <LibrarySidebar />

      {/* Workspace */}
      {!scope ? (
        <div className="flex flex-1 items-center justify-center bg-gray-50">
          <div className="text-center text-gray-400">
            <BookOpen className="mx-auto mb-4 h-14 w-14 opacity-20" />
            <p className="text-base font-medium text-gray-500">Select a document or collection</p>
            <p className="mt-1 text-sm">Then chat, summarise, or quiz yourself on it</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-hidden bg-gray-50">
          {/* Workspace header */}
          <div className="border-b border-gray-200 bg-white px-6 pt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400 capitalize">
              {scope.type}
            </p>
            <h1 className="mt-0.5 truncate text-base font-semibold text-gray-900">
              {scope.name}
            </h1>
            {tabsVisible && (
              <div className="mt-3 flex gap-1">
                {getTabsForScope(scope).map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setActiveTab(id)}
                    className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                      effectiveTab === id
                        ? "border-indigo-600 text-indigo-700"
                        : "border-transparent text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Processing / failed state */}
          {scope.status === "processing" || scope.status === "pending" ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center text-gray-500">
                <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-indigo-400" />
                <p className="text-sm font-medium">Processing document…</p>
                <p className="mt-1 text-xs text-gray-400">
                  Extracting and embedding content. This usually takes a few minutes.
                </p>
              </div>
            </div>
          ) : scope.status === "failed" ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center text-gray-500">
                <AlertCircle className="mx-auto mb-3 h-8 w-8 text-red-400" />
                <p className="text-sm font-medium text-red-600">Processing failed</p>
                <p className="mt-1 text-xs text-gray-400">
                  The document could not be processed. Delete it and try uploading again.
                </p>
              </div>
            </div>
          ) : (
            /* Tab content */
            <div className="flex flex-1 flex-col overflow-hidden">
              {effectiveTab === "chat" && (
                <ChatTab key={scope.id} scopeType={scope.type} scopeId={scope.id} />
              )}
              {effectiveTab === "summarise" && (
                <SummariseTab
                  key={scope.id}
                  scopeType={scope.type}
                  scopeId={scope.id}
                  docType={scope.doc_type}
                  isSummarising={isSummarising}
                  expectedTotal={scope.expected_summary_count}
                />
              )}
              {effectiveTab === "quiz" && (
                <QuizTab key={scope.id} scopeType={scope.type} scopeId={scope.id} />
              )}
              {effectiveTab === "documents" && scope.type === "collection" && (
                <CollectionDocsTab key={scope.id} collectionId={scope.id} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
