export type PortCode = 'LAX' | 'SHA' | 'RTM';
export type Action = 'release' | 'slow' | 'inspect' | 'reroute';
export type Scenario = { port: PortCode; lanes_open: number; customs_online: boolean; power_zone_b: boolean };
export type Container = {
  container_id: string; carrier_code: string; cargo_type: string; consignee_type: string;
  zone: string; arrived_at: string; free_days_left: number; port: PortCode; currency: string;
  priority: number; urgency: number; conflict_score: number; action: Action; reason: string;
  demurrage_per_day: number; demurrage_usd_per_day: number; port_demurrage_per_day: number; carrier_demurrage_per_day: number;
  sources: {
    carrier: { declared_status: string; declared_weight_kg: number; history_mismatches_last10: number };
    scale: { weight_kg: number }; customs: { hold: boolean; hold_type: string; est_days_to_clear: number };
    reefer: { temp_c: number; setpoint_c: number; last_ping_min: number } | null;
  };
  decision_trace?: { rule_fired: string; mode: string; trust_at_decision: Record<string, number | null>; weights: Record<string, number> };
};
export type Stats = Record<Action, number> & { baseline_demurrage_usd_per_day: number; optimized_demurrage_usd_per_day: number; savings_usd_per_day: number };
export type ModelStatus = { configured: boolean; model: string | null; key_expires_at?: string | null; server_available: boolean; source: 'none' | 'session' | 'render_environment' };
export type Snapshot = { revision: number; scenario: Scenario; queue: Container[]; stats: Stats; model: ModelStatus; expires_at: string; data_kind: string };
export type Port = { code: PortCode; name: string; currency: string; symbol: string; language: string; customs_agency: string };
export type PlanAction = {
  container_id: string; cargo_type: string; consignee_type: string; blocker: string; fix: string; who: string;
  currency: string; language: string; unlocks_per_day: number; demurrage_per_day: number; why: string;
  before: { action: Action; rank: number; priority: number; out_today: boolean };
  after: { action: Action; rank: number; priority: number; out_today: boolean };
  draft: { to: string; subject: string; body: string; source: string; language: string; fallback_reason?: string };
  approval: { status: string; note?: string; at?: string; dispatch?: string };
};
export type Plan = {
  port: PortCode; port_name: string; currency: string; summary: string; actions: PlanAction[];
  gate_capacity_today: number; total_unlocked_per_day: number; agent_mode: string;
  generated_at: string; trace: { step: number; kind: string; text: string; ms: number; t_ms: number; detail?: unknown }[];
};
export type Job = { id: string; status: string; input_revision: number; stale: boolean; result: Plan | null; error: string | null; created_at: string; use_model?: boolean };
