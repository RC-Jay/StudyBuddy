export interface User {
  id: string
  phone: string
  email: string | null
  display_name: string
}

export interface AuthState {
  user: User | null
  accessToken: string | null
}

export interface Document {
  id: string
  title: string
  file_type: string
  page_count: number | null
  file_size_bytes: number
  processing_status: "pending" | "processing" | "ready" | "failed"
  created_at: string
}

export interface Collection {
  id: string
  name: string
  created_at: string
  document_count: number
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  citations: { document: string; page: number | null }[] | null
  created_at: string
}

export interface ChatSession {
  id: string
  scope_type: "document" | "collection"
  scope_id: string
  title: string | null
  created_at: string
  message_count: number
  messages?: ChatMessage[]
}

export interface Question {
  id: string
  format: "mcq" | "short_answer" | "true_false"
  difficulty: string
  stem: string
  options: string[] | null
  correct_answer?: string
  explanation?: string
}

export interface QuizSession {
  id: string
  mode: "practice" | "exam"
  scope_type: string
  scope_id: string
  config: {
    format: string
    difficulty: string
    question_count: number
    topic_focus: string | null
  }
  question_ids: string[]
  score: number | null
  started_at: string
  completed_at: string | null
  time_limit_seconds: number | null
}

export interface Summary {
  id: string
  scope_type: string
  scope_id: string
  granularity: "full" | "section" | "concepts" | "tldr"
  section_hint: string | null
  content: string
  created_at: string
}
