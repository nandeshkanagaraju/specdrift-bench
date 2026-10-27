/** Mirrors specdrift/api/models.py. Keep the two in step. */

export type VerdictValue = "COMPLIANT" | "DRIFT" | "UNCERTAIN";

export interface CategoryCount {
  category: string;
  name: string;
  n: number;
  escapes: number;
  escapes_rate: number;
  is_drift: boolean;
}

export interface DetectorInfo {
  name: string;
  model: string;
  llm_calls: number;
  cache_hits: number;
  scored: boolean;
  precision: number;
  recall: number;
  f1: number;
  false_alarm_rate: number;
  uncertain_rate: number;
}

export interface Summary {
  generated: string;
  projects: string[];
  total_cases: number;
  valid_cases: number;
  invalid_cases: number;
  drift_cases: number;
  negative_cases: number;
  escapes_tests: number;
  escapes_rate: number;
  categories: CategoryCount[];
  detectors: DetectorInfo[];
}

export interface CategoryMetric {
  category: string;
  name: string;
  n: number;
  metric: string;
  value: number;
  uncertain: number;
  is_drift: boolean;
}

export interface DetectorMetrics {
  detector: string;
  model: string;
  cases_scored: number;
  counts: Record<string, number>;
  overall: Record<string, number>;
  per_category: CategoryMetric[];
  attribution: Record<string, number>;
}

export interface RetrievalReport {
  embedder: string;
  n_rule_queries: number;
  overall: Record<string, number>;
  per_category: Record<string, Record<string, number>>;
  misses: { case_id: string; rule_id: string; gold_symbol: string }[];
}

export interface MetricsResponse {
  detectors: DetectorMetrics[];
  retrieval: RetrievalReport | null;
}

export interface CaseRow {
  id: string;
  project: string;
  category: string;
  category_name: string;
  label: string;
  target_rules: string[];
  gold_symbol: string;
  file: string;
  note: string;
  status: string;
  escapes_tests: boolean | null;
  verdicts: Record<string, VerdictValue>;
}

export interface CaseList {
  total: number;
  page: number;
  page_size: number;
  items: CaseRow[];
}

export interface Rule {
  id: string;
  text: string;
  section: string;
}

export interface Verdict {
  case_id: string;
  rule_id: string;
  detector: string;
  verdict: VerdictValue;
  confidence: number;
  violated_clause: string;
  evidence: { file: string; start_line: number; end_line: number };
  counterexample: { input: string; expected: string; actual: string };
  retrieved_chunks: string[];
  run: number;
  latency_ms: number;
  cache_hit: boolean;
  parse_error: boolean;
  downgraded: boolean;
}

export interface RetrievedChunk {
  chunk_id: string;
  qualname: string;
  file: string;
  start_line: number;
  end_line: number;
  score: number;
  is_gold: boolean;
}

export interface CaseOutcome {
  case_id: string;
  category: string;
  label: string;
  outcome: "TP" | "FN" | "FP" | "TN";
  flagged_rules: string[];
  spurious_rules: string[];
  attribution: string;
  uncertain: number;
  confidence: number;
}

export interface CaseDetail {
  case: CaseRow;
  rules: Rule[];
  before_source: string;
  after_source: string;
  changed_lines: number[];
  verdicts: Record<string, Verdict[]>;
  retrieved: Record<string, RetrievedChunk[]>;
  outcomes: Record<string, CaseOutcome>;
}

export interface Project {
  name: string;
  rule_count: number;
  case_count: number;
  spec: string;
  rules: Rule[];
}

export interface SourceFile {
  path: string;
  lines: number;
  source: string;
}

/** A project the user pasted or uploaded, saved as a workspace the checker can read. */
export interface UploadRecord {
  id: string;
  name: string;
  rules: Rule[];
  files: SourceFile[];
  warnings: string[];
  spec_path: string;
}

/** Emitted by POST /api/check while the run is in flight. */
export type StageId = "setup" | "spec" | "chunk" | "rank" | "verify" | "gate";

export interface StageEvent {
  stage: StageId;
  state: "running" | "done";
  detail?: string;
  total?: number;
}

/** What Stage 1 actually handed the model for one rule. */
export interface RuleDetail {
  rule_id: string;
  retrieved: number;
  constant_context: number;
}

export interface CheckSummary {
  status: "PASS" | "DRIFT" | "NEEDS_HUMAN";
  counts: Record<VerdictValue, number>;
  rules: number;
  chunks: number;
  model: string;
  scope_note: string;
}

/** One category's planted change, announced before it is checked. */
export interface SweepCase {
  case_id: string;
  category: string;
  category_name: string;
  project: string;
  note: string;
  file: string;
  target_rules: string[];
  escapes_tests: boolean | null;
  before: string;
  after: string;
  line: number;
}

/** What the detector made of it. */
export interface SweepResult {
  case_id: string;
  category: string;
  project: string;
  caught: boolean;
  flagged_rules: string[];
  target_rules: string[];
  rules_checked: number;
  escapes_tests: boolean | null;
}

/** A mean with its bootstrap 95% interval. */
export interface Stat {
  mean: number;
  ci95: [number, number];
}

export interface TrainedArm {
  name: string;
  label: string;
  runs: number;
  recall: Stat;
  precision: Stat;
  strict_precision: Stat;
  false_alarm_rate: Stat;
  uncertain_rate: Stat;
}

export interface PairedDifference {
  difference: number;
  ci95: [number, number];
}

export interface GateRun {
  run: number;
  false_alarms: number;
  clean: number;
  caught: number;
  drift: number;
  gate: string;
  note: string;
}

/** docs/trained-model-results.json: the curated result of the fine-tuned-verifier evaluation. */
export interface TrainedModelResults {
  title: string;
  generated: string;
  verdict: { headline: string; text: string };
  benchmark_arms: TrainedArm[];
  paired_tuned_minus_baseline: Record<string, { false_alarm_rate: PairedDifference; recall: PairedDifference }>;
  per_category: Array<Record<string, string | number>>;
  unseen_projects: Record<string, { recall: Stat; false_alarm_rate: Stat; rules: number; drift_rules: number }>;
  gate_runs: GateRun[];
  untuned_gate: { false_alarms: number; clean: number; caught: number; drift: number };
  ranking_auc: Array<{ set: string; untuned: number; tuned: number; tuned_ci95: [number, number] }>;
  training: { base: string; method: string; examples: number; validation: number; libraries: number; steps: number };
  caveats: string[];
}
