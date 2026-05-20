// Analytics types
export interface OverviewData {
  total_chats: number;
  active_now: number;
  escalation_rate: number;
  tickets_created: number;
  token_usage: number;
  ai_resolution_rate: number;
  period_days: number;
  close_reasons: Record<string, number>;
  semantic_cache: {
    embedding_cache_size: number;
    response_cache_size: number;
    total_entries: number;
    expired: number;
  };
}

export interface ActiveConnectionsData {
  active: number;
}

export interface TopicStat {
  _id: string;
  count: number;
  escalated: number;
  avg_messages: number;
}

export interface EscalationStat {
  _id: string;
  count: number;
}

export interface CostProvider {
  provider: string;
  total_tokens: number;
  session_count: number;
  estimated_cost: number;
}

export interface CostsData {
  providers: CostProvider[];
  period_days: number;
}

export interface SessionEvent {
  type: string;
  detail: string;
  ts: string;
}

export interface SessionSummary {
  id: string;
  chat_id?: string;
  customer_name: string;
  customer_email: string;
  topic_id: string;
  status: string;
  close_reason?: string;
  message_count: number;
  created_at: string;
  events?: SessionEvent[];
  topic_tags?: string[];
  order_number?: string;
  escalation_reason?: string;
}

export interface ConversationsResponse {
  total: number;
  sessions: SessionSummary[];
}

export interface ChatMessage {
  role: string;
  content: string;
  created_at: string;
}

export interface ConversationDetail {
  session: SessionSummary;
  messages: ChatMessage[];
}

export interface FeedbackData {
  up: number;
  down: number;
  total: number;
  satisfaction_rate: number;
  period_days: number;
}

export interface RatingsData {
  avg_rating: number;
  total: number;
  distribution: Record<string, number>;
  period_days: number;
}

export interface ProviderPerf {
  provider: string;
  avg_response_ms: number;
  avg_llm_ms: number;
  message_count: number;
}

export interface PerformanceData {
  avg_response_ms: number;
  avg_llm_ms: number;
  avg_chat_duration_s: number;
  by_provider: ProviderPerf[];
  period_days: number;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  module: string;
  traceback?: string;
}

export interface LogsResponse {
  total: number;
  logs: LogEntry[];
}

// Admin types
export interface LlmProviderConfig {
  api_key: string;
  default_model: string;
  enabled: boolean;
  base_url?: string;
}

export interface LlmConfig {
  [provider: string]: LlmProviderConfig;
}

export interface SubCard {
  id: string;
  title: string;
  description: string;
}

export interface TopicConfig {
  id: string;
  title: string;
  icon: string;
  description: string;
  visibility: string;
  llm_provider: string;
  sub_cards: SubCard[];
}

export interface KnowledgeSource {
  id: string;
  name: string;
  type: string;
  chunk_count: number;
  created_at: string;
}

export interface KnowledgeStatus {
  total_sources: number;
  total_vectors: number;
  qa_pairs: number;
  sources: KnowledgeSource[];
}

export interface QaPair {
  _id: string;
  question: string;
  answer: string;
}
