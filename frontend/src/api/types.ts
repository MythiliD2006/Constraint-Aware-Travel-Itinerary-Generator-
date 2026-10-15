// Shapes returned by the FastAPI backend (see backend/app/routes.py).

export type Interest = 'history' | 'culture' | 'art' | 'spiritual' | 'nature' | 'shopping'
export type Pace = 'relaxed' | 'moderate' | 'packed'
export type Tier = 'budget' | 'standard' | 'comfort'

export interface DestinationSummary {
  id: string
  name: string
  region: string
  summary: string
  base: string
  attraction_count: number
}

export interface AttractionInfo {
  id: string
  name: string
  category: string
  lineage: string[]
  description: string
  hours: string[]
  closed_on: string[]
  entry_fee: number
  duration: number
  interests: { interest: Interest; source: string }[]
  properties: Record<string, { value: unknown; source: string }>
}

export interface DestinationDetail {
  id: string
  name: string
  region: string
  summary: string
  base: string
  attractions: AttractionInfo[]
  interests: Interest[]
  disclaimer: string
}

export interface PlanRequest {
  destination_id: string
  start_date: string
  days: number
  travelers: number
  budget: number
  accommodation: Tier
  pace: Pace
  interests: Interest[]
  must_visit: string[]
  exclude: string[]
  seed: number
}

export interface ScheduleItem {
  day: number
  kind: 'travel' | 'visit' | 'lunch'
  start: number
  end: number
  start_time: string
  end_time: string
  attraction_id: string | null
  label: string
  mode: 'walk' | 'cab' | null
  distance_km: number
  cost: number
  origin: string | null
  target: string | null
  waited: number
  category?: string
  hours?: string[]
  visitor_notes?: { text: string; inherited_from: string }[]
}

export interface DayPlan {
  day: number
  date: string
  weekday: string
  items: ScheduleItem[]
  visit_count: number
  activity_cost: number
}

export interface BudgetSummary {
  currency: string
  limit: number
  accommodation: number
  food: number
  entry_fees: number
  local_transport: number
  total: number
  remaining: number
  within_budget: boolean
  nights: number
  rooms: number
  tier: Tier
  notes: string[]
}

export interface Check {
  name: string
  passed: boolean
  details: string[]
}

export interface Issue {
  code: string
  attraction_id: string | null
  message: string
}

export interface TreeNode {
  task: string
  method: string | null
  primitive: boolean
  children: TreeNode[]
}

export interface SearchStats {
  nodes_expanded: number
  backtracks: number
  primitive_failures: number
  elapsed_ms: number
  daily_limit?: number
  candidates?: number
}

interface PlanBase {
  destination: { id: string; name: string; base: string }
  request: PlanRequest
  pace: { day_start: string; day_end: string; lunch_minutes: number }
  disclaimer: string
  budget: BudgetSummary
  stats: SearchStats | null
}

export interface FeasiblePlan extends PlanBase {
  status: 'ok'
  days: DayPlan[]
  checks: Check[]
  selected: { attraction_id: string; name: string; day: number; reasons: string[] }[]
  rejected: { attraction_id: string; name: string; code: string; reason: string }[]
  warnings: string[]
  decomposition: TreeNode
}

export interface InfeasiblePlan extends PlanBase {
  status: 'infeasible'
  issues: Issue[]
  suggestions: string[]
}

export type PlanResult = FeasiblePlan | InfeasiblePlan

export interface SavedSummary {
  id: number
  title: string
  destination_id: string
  destination_name: string
  created_at: string
  days: number
  total_cost: number
  budget: number
}

export interface SavedDetail extends SavedSummary {
  request: PlanRequest
  result: FeasiblePlan
}

export interface KnowledgeOverview {
  classes: {
    name: string
    parent: string | null
    properties: Record<string, unknown>
    interests: string[]
    instances: string[]
  }[]
  rules: string[]
  fact_counts: Record<string, number>
  sample_facts: string[]
  example_queries: string[]
}

export interface QueryResult {
  query: string[]
  proved: boolean
  has_variables: boolean
  inferences: number
  answers: { bindings: Record<string, string>; proof: { depth: number; goal: string; clause: string }[] }[]
}
