// Mirrors backend/app/models.py

export type Severity = "HIGH" | "MEDIUM" | "LOW";

export type FailureCategory =
  | "FUNCTIONAL_ERROR"
  | "EDGE_CASE_FAILURE"
  | "REQUIREMENT_MISSED"
  | "SECURITY_ISSUE"
  | "ROBUSTNESS_FAILURE"
  | "TEST_FAILURE"
  | "ENVIRONMENT_FAILURE"
  | "PERFORMANCE_FAILURE"
  | "POSSIBLE_TEST_GAMING";

export type CaseCategory = "normal" | "edge" | "robustness" | "performance";
export type CaseOutcome = "passed" | "failed" | "error" | "skipped" | "not_run";
export type RequirementStatus = "met" | "partial" | "not_met" | "not_evaluated";
export type GamingRisk = "none" | "low" | "medium" | "high";

export interface Finding {
  severity: Severity;
  rule: string;
  message: string;
  file: string;
  line: number | null;
  recommendation: string | null;
}

export interface CaseResult {
  test_id: string;
  file: string;
  category: CaseCategory;
  description: string;
  outcome: CaseOutcome;
  requirements: string[];
  error_type: string | null;
  error_message: string | null;
}

export interface OwnTestSummary {
  ran: boolean;
  found: boolean;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  failing_tests: string[];
}

export interface RequirementResult {
  id: string;
  description: string;
  status: RequirementStatus;
  passed: number;
  total: number;
  failing_tests: string[];
}

export interface GamingSignal {
  rule: string;
  message: string;
  confidence: Severity;
  file: string | null;
  line: number | null;
}

export interface Failure {
  category: FailureCategory;
  severity: Severity;
  message: string;
  test_id: string | null;
  file: string | null;
  line: number | null;
  heuristic: boolean;
}

export interface ScoreComponent {
  key: string;
  label: string;
  weight: number;
  ratio: number;
  points: number;
  explanation: string;
}

export interface ExecutionRecord {
  name: string;
  command: string;
  exit_code: number | null;
  duration_seconds: number;
  timed_out: boolean;
  stdout: string;
  stderr: string;
  output_truncated: boolean;
  mode: string;
}

export interface EvaluationResult {
  evaluation_id: string;
  created_at: string;
  task_id: string;
  task_title: string;
  task_description: string;
  repository_name: string;
  overall_score: number;
  raw_score: number;
  score_cap_applied: boolean;
  functional_score: number;
  edge_case_score: number;
  requirement_score: number;
  security_score: number;
  quality_score: number;
  score_breakdown: ScoreComponent[];
  tests_passed: number;
  tests_failed: number;
  own_tests: OwnTestSummary;
  failures: Failure[];
  cases: CaseResult[];
  requirements: RequirementResult[];
  security_findings: Finding[];
  quality_findings: Finding[];
  gaming_signals: GamingSignal[];
  gaming_risk: GamingRisk;
  dependencies: string[];
  recommendations: string[];
  executions: ExecutionRecord[];
  execution_mode: string;
  bandit_used: boolean;
  duration_seconds: number;
}

export interface ExampleInfo {
  name: string;
  description: string;
}

export interface TaskInfo {
  task_id: string;
  title: string;
  default_description: string;
  requirements: string[];
}

export interface HealthInfo {
  status: string;
  execution_mode: string;
  bandit_available: boolean;
  docker_available: boolean;
}
