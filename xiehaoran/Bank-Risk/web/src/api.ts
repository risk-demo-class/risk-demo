// 后端 API 封装 (同源: FastAPI 同时托管页面与 /api)
const BASE = "/api";

// ============================================================
// 类型定义 (严格对齐后端 schemas.py)
// ============================================================
export interface RiskCheckRequest {
  event_type: string;
  source_id: string;
  user_id: string;
  order_id?: string;
  receive_id?: string;
  event_data?: Record<string, any>;
}

export interface RuleHitInfo {
  rule_id: string;
  rule_name: string;
  rule_category: string;
  risk_level: string;
  risk_score: number;
  action: string;
  description: string | null;
}

export interface RiskCheckResponse {
  assessment_id: string;
  event_id: string;
  user_id: string;
  final_score: number;
  risk_level: string;
  decision: string;
  rule_count: number;
  triggered_rules: RuleHitInfo[];
  features: Record<string, number>;
  create_time: string;
  ml_score: number | null;
  ml_decision: string | null;
  blocked_by: string | null;
  message: string | null;
}

export interface RuleMeta {
  rule_id: string;
  rule_name: string;
  rule_category: string;
  event_type: string;
  risk_level: string;
  risk_score: number;
  action: string;
  priority: number;
  is_enabled: boolean;
  description: string | null;
  rule_condition: any;
}

export interface FeatureMeta {
  key: string;
  name: string;
  family: string;
  desc: string;
  range: string;
}

export interface ModelEval {
  rows: any[];
  base: { train_auc: number; val_auc: number; val_f1: number; n_runs: number } | null;
  hard: { train_auc: number; val_auc: number; val_f1: number; n_runs: number } | null;
  feature_importance: { feature: string; gain: number }[];
}

export interface AssessmentItem {
  assessment_id: string;
  event_id: string;
  user_id: string;
  event_type: string;
  final_score: number;
  risk_level: string;
  decision: string;
  rule_count: number;
  ml_score: number | null;
  ml_decision: string | null;
  create_time: string;
}

export interface BlacklistItem {
  blacklist_id: number;
  blacklist_type: string;
  blacklist_value: string;
  reason: string | null;
  expire_time: string | null;
  create_time: string | null;
}

export interface CaseItem {
  case_id: string;
  assessment_id: string;
  user_id: string;
  case_status: string;
  case_category: string | null;
  final_score: number | null;
  risk_level: string | null;
  create_time: string | null;
  source_id: string | null;
  event_type: string | null;
}

export interface CaseDetail extends CaseItem {
  case_status: string;
  risk_detail: any;
  reviewer: string | null;
  review_comment: string | null;
  review_time: string | null;
  triggered_rules: RuleHitInfo[];
  user_profile: Record<string, any> | null;
  ml_score: number | null;
  ml_decision: string | null;
  decision: string | null;
}

export interface CaseStatistics {
  total: number;
  pending: number;
  reviewing: number;
  approved: number;
  rejected: number;
  closed: number;
  by_category: Record<string, number>;
}

export interface DashboardOverview {
  today_assessments: number;
  today_high_risk: number;
  pass_rate: number;
  pending_cases: number;
  trend_7d: { date: string; count: number; high_risk_count: number }[];
  top_rules: { rule_id: string; rule_name: string; hit_count: number }[];
  risk_level_distribution: { level: string; count: number }[];
  decision_distribution: { decision: string; count: number }[];
}

export interface AgentChatResponse {
  reply: string;
  session_id: string;
  thinking?: string;
}

// ============================================================
// 请求封装
// ============================================================
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`请求失败 ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败 ${res.status}`);
  }
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败 ${res.status}`);
  }
  return res.json();
}

async function del<T = any>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败 ${res.status}`);
  }
  return res.json();
}

// ============================================================
// API 集合
// ============================================================
export const api = {
  // 仪表盘
  dashboardOverview: () => get<DashboardOverview>("/dashboard/overview"),

  // 风险检查 (核心决策)
  riskCheck: (payload: RiskCheckRequest) => post<RiskCheckResponse>("/risk/check", payload),

  // 规则
  rules: (
    category?: string,
    page = 1,
    page_size = 50,
    sort_by?: "rule_id" | "risk_score" | "priority" | "risk_level",
    order?: "asc" | "desc",
  ) =>
    get<{ items: RuleMeta[]; total: number; page: number; page_size: number }>(
      `/rules?page=${page}&page_size=${page_size}` +
      `${category ? `&category=${category}` : ""}` +
      `${sort_by ? `&sort_by=${sort_by}` : ""}` +
      `${order ? `&order=${order}` : ""}`
    ),
  createRule: (rule: any) => post<RuleMeta>("/rules", rule),
  updateRule: (ruleId: string, rule: any) => put<RuleMeta>(`/rules/${ruleId}`, rule),
  toggleRule: (ruleId: string) => put<RuleMeta>(`/rules/${ruleId}/toggle`, {}),
  deleteRule: (ruleId: string) => del(`/rules/${ruleId}`),

  // 案件
  cases: (params: { status?: string; active_only?: boolean; page?: number; page_size?: number } = {}) =>
    get<{ items: CaseItem[]; total: number; page: number; page_size: number }>(
      `/cases?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` +
      `${params.status ? `&status=${params.status}` : ""}` +
      `${params.active_only ? `&active_only=true` : ""}`
    ),
  caseStatistics: () => get<CaseStatistics>("/cases/statistics"),
  caseDetail: (caseId: string) => get<CaseDetail>(`/cases/${caseId}`),
  reviewCase: (caseId: string, data: any) => post<CaseDetail>(`/cases/${caseId}/review`, data),

  // 评估历史
  assessments: (params: { page?: number; page_size?: number; decision?: string; risk_level?: string; event_type?: string; user_id?: string } = {}) =>
    get<{ items: AssessmentItem[]; total: number; page: number; page_size: number }>(
      `/assessments?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` +
      `${params.decision ? `&decision=${params.decision}` : ""}` +
      `${params.risk_level ? `&risk_level=${params.risk_level}` : ""}` +
      `${params.event_type ? `&event_type=${params.event_type}` : ""}` +
      `${params.user_id ? `&user_id=${params.user_id}` : ""}`
    ),
  assessmentDetail: (id: string) => get<any>(`/assessments/${id}`),

  // 黑名单
  blacklist: (params: { page?: number; page_size?: number; blacklist_type?: string } = {}) =>
    get<{ items: BlacklistItem[]; total: number; page: number; page_size: number }>(
      `/blacklist?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` +
      `${params.blacklist_type ? `&blacklist_type=${params.blacklist_type}` : ""}`
    ),
  blacklistStatistics: () =>
    get<{ total: number; account: number; ip: number; phone: number; by_type: Record<string, number> }>("/blacklist/statistics"),
  addBlacklist: (item: any) => post<BlacklistItem>("/blacklist", item),
  deleteBlacklist: (id: number) => del(`/blacklist/${id}`),

  // 模型评估 + 特征
  modelEval: () => get<ModelEval>("/model-eval"),
  features: () =>
    get<{
      feature_order: string[];
      count: number;
      features: FeatureMeta[];
      families: Record<string, { name: string; features: FeatureMeta[] }>;
    }>("/features"),

  // AI Agent
  agentChat: (message: string, session_id?: string) =>
    post<AgentChatResponse>("/agent/chat", { message, session_id }),
};

// ============================================================
// 语义映射 (对齐后端枚举)
// ============================================================
export const DECISION_META: Record<string, { label: string; color: string; bg: string }> = {
  pass: { label: "通过", color: "#52C41A", bg: "#F6FFED" },
  review: { label: "复核", color: "#1677FF", bg: "#E6F4FF" },
  reject: { label: "拒绝", color: "#FF4D4F", bg: "#FFF1F0" },
  freeze: { label: "冻结", color: "#722ED1", bg: "#F9F0FF" },
  report: { label: "报送", color: "#FA8C16", bg: "#FFF7E6" },
};

export const EVENT_OPTIONS = [
  { value: "transfer", label: "转账交易" },
  { value: "loan_apply", label: "贷款申请" },
  { value: "card_txn", label: "卡片交易" },
  { value: "repay", label: "还款" },
  { value: "login", label: "登录" },
];

export const RULE_CATEGORY_OPTIONS = [
  { value: "账户风险", label: "账户风险" },
  { value: "交易风险", label: "交易风险" },
  { value: "信贷风险", label: "信贷风险" },
  { value: "反洗钱", label: "反洗钱" },
  { value: "设备风险", label: "设备风险" },
  { value: "登录风险", label: "登录风险" },
];

export const RISK_LEVEL_OPTIONS = [
  { value: "低", label: "低" },
  { value: "中", label: "中" },
  { value: "高", label: "高" },
  { value: "极高", label: "极高" },
];

export const BLACKLIST_TYPE_OPTIONS = [
  { value: "account", label: "账户" },
  { value: "device", label: "设备" },
  { value: "ip", label: "IP" },
  { value: "phone", label: "手机号" },
  { value: "id_card", label: "证件号" },
  { value: "merchant", label: "商户" },
  { value: "beneficiary", label: "受益人" },
];
