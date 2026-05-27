"use client"

import { useState, useEffect } from "react"
import { Loader2, Flag, Clock, ClipboardList } from "lucide-react"
import api from "@/lib/api"
import type { QuizSession, Question } from "@/lib/types"

interface Props {
  scopeType: "document" | "collection"
  scopeId: string
}

type Phase = "setup" | "active" | "debrief"

interface AnswerResult {
  question_id: string
  user_answer: string
  correct_answer: string
  is_correct: boolean
  score: number
  feedback: string | null
  explanation: string
}

export function QuizTab({ scopeType, scopeId }: Props) {
  const [phase, setPhase] = useState<Phase>("setup")
  const [config, setConfig] = useState({
    format: "mcq",
    difficulty: "intermediate",
    questionCount: 10,
    mode: "practice",
    topicFocus: "",
    timeLimit: "",
  })
  const [session, setSession] = useState<QuizSession | null>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [results, setResults] = useState<AnswerResult[]>([])
  const [score, setScore] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [timeLeft, setTimeLeft] = useState<number | null>(null)

  useEffect(() => {
    if (timeLeft === null || timeLeft <= 0 || phase !== "active") return
    const t = setTimeout(() => {
      if (timeLeft === 1) submitAnswers()
      else setTimeLeft((v) => (v ?? 1) - 1)
    }, 1000)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeft, phase])

  async function startQuiz() {
    setLoading(true)
    try {
      const { data } = await api.post("/quiz/sessions", {
        mode: config.mode,
        scope_type: scopeType,
        scope_id: scopeId,
        format: config.format,
        difficulty: config.difficulty,
        question_count: config.questionCount,
        topic_focus: config.topicFocus || null,
        time_limit_seconds:
          config.mode === "exam" && config.timeLimit
            ? parseInt(config.timeLimit) * 60
            : null,
      })
      setSession(data.session)
      setQuestions(data.questions)
      setAnswers({})
      if (data.session.time_limit_seconds) setTimeLeft(data.session.time_limit_seconds)
      setPhase("active")
    } finally {
      setLoading(false)
    }
  }

  async function submitAnswers() {
    if (!session) return
    setSubmitting(true)
    try {
      const answerList = questions.map((q) => ({
        question_id: q.id,
        answer: answers[q.id] ?? "",
      }))
      const { data } = await api.post(`/quiz/sessions/${session.id}/submit`, {
        answers: answerList,
      })
      setResults(data.results)
      setScore(data.overall_score)
      setPhase("debrief")
    } finally {
      setSubmitting(false)
    }
  }

  async function flagQuestion(qid: string) {
    await api.post(`/quiz/questions/${qid}/flag`)
  }

  if (phase === "setup") {
    return (
      <div className="flex flex-1 items-start justify-center overflow-auto p-6">
        <div className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-indigo-500" />
            <h2 className="text-base font-semibold text-gray-900">Configure Quiz</h2>
          </div>

          {[
            {
              label: "Format",
              key: "format",
              options: [
                { v: "mcq", l: "Multiple Choice" },
                { v: "short_answer", l: "Short Answer" },
                { v: "true_false", l: "True / False" },
              ],
            },
            {
              label: "Difficulty",
              key: "difficulty",
              options: [
                { v: "introductory", l: "Introductory" },
                { v: "intermediate", l: "Intermediate" },
                { v: "advanced", l: "Advanced" },
              ],
            },
            {
              label: "Mode",
              key: "mode",
              options: [
                { v: "practice", l: "Practice" },
                { v: "exam", l: "Exam (timed, closed-book)" },
              ],
            },
          ].map(({ label, key, options }) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700">{label}</label>
              <select
                value={String((config as unknown as Record<string, unknown>)[key])}
                onChange={(e) => setConfig((c) => ({ ...c, [key]: e.target.value }))}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              >
                {options.map(({ v, l }) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          ))}

          <div>
            <label className="block text-sm font-medium text-gray-700">Questions</label>
            <input
              type="number"
              min={1}
              max={30}
              value={config.questionCount}
              onChange={(e) =>
                setConfig((c) => ({ ...c, questionCount: parseInt(e.target.value) || 10 }))
              }
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Topic focus (optional)
            </label>
            <input
              type="text"
              placeholder="e.g. Chapter 3, methodology"
              value={config.topicFocus}
              onChange={(e) => setConfig((c) => ({ ...c, topicFocus: e.target.value }))}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          {config.mode === "exam" && (
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Time limit (minutes)
              </label>
              <input
                type="number"
                min={1}
                placeholder="e.g. 30"
                value={config.timeLimit}
                onChange={(e) => setConfig((c) => ({ ...c, timeLimit: e.target.value }))}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          )}

          <button
            onClick={startQuiz}
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
                Generating…
              </>
            ) : (
              "Start Quiz"
            )}
          </button>
        </div>
      </div>
    )
  }

  if (phase === "active") {
    return (
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
          <span className="text-sm text-gray-600">
            {questions.length} questions · {config.difficulty} · {config.format.replace("_", " ")}
          </span>
          <div className="flex items-center gap-4">
            {timeLeft !== null && (
              <span
                className={`flex items-center gap-1.5 text-sm font-medium ${
                  timeLeft < 60 ? "text-red-600" : "text-gray-700"
                }`}
              >
                <Clock className="h-4 w-4" />
                {Math.floor(timeLeft / 60)}:{String(timeLeft % 60).padStart(2, "0")}
              </span>
            )}
            <button
              onClick={submitAnswers}
              disabled={submitting}
              className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {submitting ? "Submitting…" : "Submit"}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6 space-y-4">
          {questions.map((q, idx) => (
            <div key={q.id} className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-gray-200">
              <div className="flex items-start justify-between gap-4">
                <p className="text-sm font-medium text-gray-900">
                  <span className="mr-2 text-gray-400">{idx + 1}.</span>
                  {q.stem}
                </p>
                <button
                  onClick={() => flagQuestion(q.id)}
                  title="Flag as bad quality"
                  className="shrink-0 rounded p-1 text-gray-300 hover:text-red-500"
                >
                  <Flag className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {q.format === "mcq" &&
                  q.options?.map((opt, i) => (
                    <label
                      key={i}
                      className="flex cursor-pointer items-center gap-3 rounded-lg border border-gray-200 px-3 py-2 hover:bg-indigo-50 has-[:checked]:border-indigo-400 has-[:checked]:bg-indigo-50"
                    >
                      <input
                        type="radio"
                        name={q.id}
                        value={opt}
                        checked={answers[q.id] === opt}
                        onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                        className="accent-indigo-600"
                      />
                      <span className="text-sm text-gray-700">{opt}</span>
                    </label>
                  ))}
                {q.format === "true_false" &&
                  ["True", "False"].map((opt) => (
                    <label
                      key={opt}
                      className="flex cursor-pointer items-center gap-3 rounded-lg border border-gray-200 px-3 py-2 hover:bg-indigo-50 has-[:checked]:border-indigo-400 has-[:checked]:bg-indigo-50"
                    >
                      <input
                        type="radio"
                        name={q.id}
                        value={opt}
                        checked={answers[q.id] === opt}
                        onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                        className="accent-indigo-600"
                      />
                      <span className="text-sm text-gray-700">{opt}</span>
                    </label>
                  ))}
                {q.format === "short_answer" && (
                  <textarea
                    rows={3}
                    placeholder="Your answer…"
                    value={answers[q.id] ?? ""}
                    onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                    className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <h2 className="font-semibold text-gray-900">Results</h2>
        <div className="flex items-center gap-4">
          <span className="text-2xl font-bold text-indigo-600">{score}%</span>
          <button
            onClick={() => setPhase("setup")}
            className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            New Quiz
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-6 space-y-4">
        {results.map((r, idx) => {
          const q = questions.find((q) => q.id === r.question_id)
          return (
            <div
              key={r.question_id}
              className={`rounded-xl p-5 ring-1 ${
                r.is_correct ? "bg-green-50 ring-green-200" : "bg-red-50 ring-red-200"
              }`}
            >
              <p className="text-sm font-medium text-gray-900">
                <span className="mr-2 text-gray-400">{idx + 1}.</span>
                {q?.stem}
              </p>
              <div className="mt-2 space-y-1 text-sm">
                <p>
                  <span className="font-medium text-gray-600">Your answer:</span>{" "}
                  {r.user_answer || <em className="text-gray-400">no answer</em>}
                </p>
                {!r.is_correct && (
                  <p>
                    <span className="font-medium text-green-700">Correct:</span>{" "}
                    {r.correct_answer}
                  </p>
                )}
                {r.feedback && <p className="text-gray-600">{r.feedback}</p>}
                <p className="text-xs text-gray-500">{r.explanation}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
