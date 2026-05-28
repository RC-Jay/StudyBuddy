"use client"

import { useAuthStore } from "@/lib/store"
import { LibrarySidebar } from "@/components/workspace/LibrarySidebar"
import { ChatTab } from "@/components/workspace/ChatTab"
import { SummariseTab } from "@/components/workspace/SummariseTab"
import { QuizTab } from "@/components/workspace/QuizTab"
import { CollectionDocsTab } from "@/components/workspace/CollectionDocsTab"
import { MessageSquare, FileText, ClipboardList, BookOpen, Loader2, AlertCircle, Library, Upload, Video, Sparkles, Brain } from "lucide-react"
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
        <div className="flex flex-1 flex-col overflow-y-auto bg-gray-50">
          <div className="mx-auto w-full max-w-3xl px-8 py-16">

            {/* Hero */}
            <div className="mb-12 text-center">
              <div className="mb-4 inline-flex items-center justify-center rounded-2xl bg-indigo-600 p-4 shadow-lg">
                <BookOpen className="h-10 w-10 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Welcome to StudyBuddy
              </h1>
              <p className="mt-3 text-base text-gray-500">
                Your AI-powered study companion for academic documents and educational videos.
                <br />
                Upload something from the sidebar to get started.
              </p>
            </div>

            {/* Feature cards */}
            <div className="mb-10 grid grid-cols-3 gap-4">
              <div className="rounded-xl border border-indigo-100 bg-white p-5 shadow-sm">
                <div className="mb-3 inline-flex rounded-lg bg-indigo-50 p-2.5">
                  <MessageSquare className="h-5 w-5 text-indigo-600" />
                </div>
                <h3 className="mb-1 text-sm font-semibold text-gray-800">Chat</h3>
                <p className="text-xs leading-relaxed text-gray-500">
                  Ask questions about any document or video and get cited answers grounded in the source material.
                </p>
              </div>

              <div className="rounded-xl border border-violet-100 bg-white p-5 shadow-sm">
                <div className="mb-3 inline-flex rounded-lg bg-violet-50 p-2.5">
                  <Sparkles className="h-5 w-5 text-violet-600" />
                </div>
                <h3 className="mb-1 text-sm font-semibold text-gray-800">Summaries</h3>
                <p className="text-xs leading-relaxed text-gray-500">
                  Get chapter-by-chapter summaries and key concepts extracted automatically from books, papers, and videos.
                </p>
              </div>

              <div className="rounded-xl border border-emerald-100 bg-white p-5 shadow-sm">
                <div className="mb-3 inline-flex rounded-lg bg-emerald-50 p-2.5">
                  <Brain className="h-5 w-5 text-emerald-600" />
                </div>
                <h3 className="mb-1 text-sm font-semibold text-gray-800">Quiz</h3>
                <p className="text-xs leading-relaxed text-gray-500">
                  Test your understanding with AI-generated multiple choice, short answer, and true/false questions.
                </p>
              </div>
            </div>

            {/* What you can add */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-sm font-semibold text-gray-700">What you can add</h2>
              <div className="grid grid-cols-3 gap-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex-shrink-0 rounded-md bg-gray-50 p-2">
                    <FileText className="h-4 w-4 text-gray-500" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-700">PDF &amp; DOCX</p>
                    <p className="mt-0.5 text-xs text-gray-400">Books, research papers, lecture notes — up to 50 MB</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex-shrink-0 rounded-md bg-red-50 p-2">
                    <Video className="h-4 w-4 text-red-500" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-700">YouTube</p>
                    <p className="mt-0.5 text-xs text-gray-400">Academic and educational videos with transcripts</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex-shrink-0 rounded-md bg-rose-50 p-2">
                    <Upload className="h-4 w-4 text-rose-500" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-700">TED Talks</p>
                    <p className="mt-0.5 text-xs text-gray-400">Paste any ted.com/talks URL to ingest the transcript</p>
                  </div>
                </div>
              </div>
            </div>

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
                  toc={scope.toc}
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
