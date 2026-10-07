import type { CopyKey } from "../copy";
import type { DecisionKind } from "../types";

/**
 * Internal clinical contract. Runtime shape check only.
 * Not a clinical protocol, not a diagnosis, and not a training record.
 *
 * The ten sections stay separate. Nothing in this module collapses them
 * into one paragraph or admits retrieved authority (no approved sources).
 */

export const CONTRACT_VERSION = "clinical-contract/v1";

export const SECTION_KEYS = [
  "observed_facts",
  "retrieved_evidence",
  "derived_features",
  "hypotheses",
  "uncertainties",
  "contradictions",
  "required_information",
  "red_flags",
  "next_action",
  "provenance",
] as const;

export type AssessmentSection = (typeof SECTION_KEYS)[number];

const OBJECT_SECTIONS = new Set<AssessmentSection>([
  "retrieved_evidence",
  "next_action",
  "provenance",
]);

export const RETRIEVAL_STATUSES = [
  "not_run",
  "empty",
  "failed",
  "unavailable",
] as const;

export type RetrievalStatus = (typeof RETRIEVAL_STATUSES)[number];

/** Reserved for a later wave. Not admitted by the validator. */
export const RESERVED_TRUST_TIERS = ["A", "B", "C", "D", "E"] as const;

export type ReservedTrustTier = (typeof RESERVED_TRUST_TIERS)[number];

export const TRUST_TIER_NONE = "none" as const;

export type TrustTier = typeof TRUST_TIER_NONE | ReservedTrustTier;

/**
 * Shape a future approved artifact would need. This wave rejects every item.
 * Unverified text must not become clinical authority by being present.
 */
export type ReservedEvidenceItem = {
  source_id: string;
  publisher: string;
  jurisdiction: string;
  document_version: string;
  publication_date: string;
  effective_date: string;
  review_date: string;
  section: string;
  retrieval_score: number | null;
  reranking_score: number | null;
  trust_tier: ReservedTrustTier;
  content_hash: string;
};

export type RetrievedEvidence = {
  retrieval_status: RetrievalStatus;
  trust_tier: typeof TRUST_TIER_NONE;
  items: [];
};

export const ACTION_CLASSES = ["ANSWER", "ASK", "ABSTAIN", "ESCALATE"] as const;

export type ActionClass = (typeof ACTION_CLASSES)[number];

/** Headlines that already exist. This module adds none. */
export type ExistingHeadlineKey =
  | "goNow"
  | "getCareToday"
  | "monitorAtHome"
  | "needOneMore";

type _HeadlineIsCopyKey = ExistingHeadlineKey extends CopyKey ? true : never;
const _headlineIsCopyKey: _HeadlineIsCopyKey = true;
void _headlineIsCopyKey;

export const DISPOSITIONS = [
  "go_now",
  "get_care_today",
  "monitor_at_home",
  "need_one_more_answer",
  "escalate",
  "abstain",
] as const;

export type Disposition = (typeof DISPOSITIONS)[number];

type _CoversDecisionKind = DecisionKind extends Disposition ? true : never;
const _coversDecisionKind: _CoversDecisionKind = true;
void _coversDecisionKind;

export type DispositionRow = {
  action: ActionClass;
  /** Null means there is no user-visible headline. Do not invent one. */
  headlineKey: ExistingHeadlineKey | null;
};

/**
 * One table. `need_one_more_answer` is the only missing-info ASK state.
 * `escalate` reuses the existing urgent headline. `abstain` has none.
 */
export const DISPOSITION_TABLE: Record<Disposition, DispositionRow> = {
  go_now: { action: "ESCALATE", headlineKey: "goNow" },
  get_care_today: { action: "ANSWER", headlineKey: "getCareToday" },
  monitor_at_home: { action: "ANSWER", headlineKey: "monitorAtHome" },
  need_one_more_answer: { action: "ASK", headlineKey: "needOneMore" },
  escalate: { action: "ESCALATE", headlineKey: "goNow" },
  abstain: { action: "ABSTAIN", headlineKey: null },
};

export function actionClassFor(disposition: Disposition): ActionClass {
  return DISPOSITION_TABLE[disposition].action;
}

export function headlineKeyFor(
  disposition: Disposition,
): ExistingHeadlineKey | null {
  return DISPOSITION_TABLE[disposition].headlineKey;
}

export function isDisposition(value: unknown): value is Disposition {
  return (
    typeof value === "string" &&
    (DISPOSITIONS as readonly string[]).includes(value)
  );
}

/** DecisionKind is a subset. Adding a kind in types.ts fails this file's check. */
export function dispositionFromDecisionKind(kind: DecisionKind): Disposition {
  return kind;
}

export const RESOLUTION_STATUS_UNRESOLVED = "unresolved" as const;

export type ResolutionStatus = typeof RESOLUTION_STATUS_UNRESOLVED;

export const CLINICAL_IMPORTANCE = ["low", "moderate", "high"] as const;

export type ClinicalImportance = (typeof CLINICAL_IMPORTANCE)[number];

export type Contradiction = {
  claim_a: string;
  claim_b: string;
  sources: string[];
  clinical_importance: ClinicalImportance;
  resolution_status: ResolutionStatus;
};

export type ClinicalEvent = {
  event_id: string;
  encounter_id: string;
  type: string;
  value: string | number | boolean | null;
  unit: string | null;
  timestamp: string;
  source: string;
  confidence: number;
  provenance: string;
};

export type ObservedFact = {
  fact_id: string;
  value: string;
  source: string;
  timestamp: string;
  confidence: number;
  provenance: string;
};

export type DerivedFeature = {
  feature_id: string;
  name: string;
  value: string | number | boolean;
  unit: string | null;
  inputs: string[];
};

export type Hypothesis = {
  hypothesis_id: string;
  statement: string;
  supporting_ids: string[];
  contradicting_ids: string[];
};

export type Uncertainty = {
  uncertainty_id: string;
  statement: string;
};

export type RequiredInformation = {
  question_id: string;
  statement: string;
};

export type RedFlag = {
  flag_id: string;
  code: string;
  source: string;
};

export type NextAction = {
  disposition: Disposition;
  action: ActionClass;
  ideal_action: string | null;
  locally_executable_action: string | null;
  resource_gap: string | null;
};

export type Provenance = {
  rules_version: string;
  model_id: string | null;
  knowledge_version: string | null;
  last_sync: string | null;
  generated_at: string;
};

export type ClinicalAssessment = {
  observed_facts: ObservedFact[];
  retrieved_evidence: RetrievedEvidence;
  derived_features: DerivedFeature[];
  hypotheses: Hypothesis[];
  uncertainties: Uncertainty[];
  contradictions: Contradiction[];
  required_information: RequiredInformation[];
  red_flags: RedFlag[];
  next_action: NextAction;
  provenance: Provenance;
};

export type ContractIssue = {
  path: string;
  message: string;
};

export class ContractValidationError extends Error {
  readonly issues: readonly ContractIssue[];

  constructor(issues: readonly ContractIssue[]) {
    super(
      issues.map((issue) => `${issue.path}: ${issue.message}`).join("; ") ||
        "contract validation failed",
    );
    this.name = "ContractValidationError";
    this.issues = issues;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

const ISO_TIMESTAMP =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isIsoTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    ISO_TIMESTAMP.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isConfidence(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isNonEmptyString(value);
}

function push(issues: ContractIssue[], path: string, message: string): void {
  issues.push({ path, message });
}

export function emptyRetrievedEvidence(
  retrievalStatus: RetrievalStatus = "not_run",
): RetrievedEvidence {
  return {
    retrieval_status: retrievalStatus,
    trust_tier: TRUST_TIER_NONE,
    items: [],
  };
}

export function demoProvenance(
  rulesVersion: string,
  generatedAt: string,
): Provenance {
  return {
    rules_version: rulesVersion,
    model_id: null,
    knowledge_version: null,
    last_sync: null,
    generated_at: generatedAt,
  };
}

/** Always unresolved. This module has no resolver. */
export function createContradiction(input: {
  claim_a: string;
  claim_b: string;
  sources: string[];
  clinical_importance: ClinicalImportance;
}): Contradiction {
  return {
    claim_a: input.claim_a,
    claim_b: input.claim_b,
    sources: [...input.sources],
    clinical_importance: input.clinical_importance,
    resolution_status: RESOLUTION_STATUS_UNRESOLVED,
  };
}

export function minimalAssessment(input: {
  rulesVersion: string;
  generatedAt: string;
  disposition: Disposition;
}): ClinicalAssessment {
  const action = actionClassFor(input.disposition);
  const assessment: ClinicalAssessment = {
    observed_facts: [],
    retrieved_evidence: emptyRetrievedEvidence("not_run"),
    derived_features: [],
    hypotheses: [],
    uncertainties: [],
    contradictions: [],
    required_information: [],
    red_flags: [],
    next_action: {
      disposition: input.disposition,
      action,
      ideal_action: null,
      locally_executable_action: null,
      resource_gap: null,
    },
    provenance: demoProvenance(input.rulesVersion, input.generatedAt),
  };
  return validateClinicalAssessment(assessment);
}

export function validateClinicalAssessment(input: unknown): ClinicalAssessment {
  const issues = assessmentIssues(input);
  if (issues.length > 0) {
    throw new ContractValidationError(issues);
  }
  return input as ClinicalAssessment;
}

export function assessmentIssues(input: unknown): ContractIssue[] {
  const issues: ContractIssue[] = [];
  if (!isRecord(input)) {
    push(issues, "root", "expected an object with ten sections");
    return issues;
  }

  for (const section of SECTION_KEYS) {
    if (!(section in input) || input[section] === undefined) {
      push(issues, section, "missing section");
      continue;
    }
    const value = input[section];
    if (OBJECT_SECTIONS.has(section)) {
      if (!isRecord(value)) {
        push(issues, section, "expected an object");
      }
    } else if (!Array.isArray(value)) {
      push(issues, section, "expected an array");
    }
  }

  if (issues.length > 0) {
    return issues;
  }

  const record = input;
  validateObservedFacts(record.observed_facts, issues);
  validateRetrievedEvidence(record.retrieved_evidence, issues);
  validateDerivedFeatures(record.derived_features, issues);
  validateHypotheses(record.hypotheses, issues);
  validateUncertainties(record.uncertainties, issues);
  validateContradictions(record.contradictions, issues);
  validateRequiredInformation(record.required_information, issues);
  validateRedFlags(record.red_flags, issues);
  validateNextAction(record.next_action, issues);
  validateProvenance(record.provenance, issues);
  return issues;
}

function validateObservedFacts(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `observed_facts[${index}]`;
    if (!isRecord(item)) {
      push(issues, path, "expected an object");
      return;
    }
    requireId(item, "fact_id", path, issues);
    requireString(item, "value", path, issues);
    requireString(item, "source", path, issues);
    requireTimestamp(item, "timestamp", path, issues);
    requireConfidence(item, path, issues);
    requireString(item, "provenance", path, issues);
  });
}

function validateRetrievedEvidence(value: unknown, issues: ContractIssue[]): void {
  if (!isRecord(value)) return;
  if (!("retrieval_status" in value)) {
    push(issues, "retrieved_evidence.retrieval_status", "missing retrieval_status");
  } else if (
    typeof value.retrieval_status !== "string" ||
    !(RETRIEVAL_STATUSES as readonly string[]).includes(value.retrieval_status)
  ) {
    push(
      issues,
      "retrieved_evidence.retrieval_status",
      `expected one of ${RETRIEVAL_STATUSES.join(", ")}`,
    );
  }
  if (!("trust_tier" in value)) {
    push(issues, "retrieved_evidence.trust_tier", "missing trust_tier");
  } else if (value.trust_tier !== TRUST_TIER_NONE) {
    push(
      issues,
      "retrieved_evidence.trust_tier",
      "trust_tier must be none until an approved source is named",
    );
  }
  if (!("items" in value)) {
    push(issues, "retrieved_evidence.items", "missing items");
  } else if (!Array.isArray(value.items) || value.items.length > 0) {
    push(
      issues,
      "retrieved_evidence.items",
      "evidence items are not admitted; bundle must be empty",
    );
  }
}

function validateDerivedFeatures(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `derived_features[${index}]`;
    if (!isRecord(item)) {
      push(issues, path, "expected an object");
      return;
    }
    requireId(item, "feature_id", path, issues);
    requireString(item, "name", path, issues);
    if (
      typeof item.value !== "string" &&
      typeof item.value !== "number" &&
      typeof item.value !== "boolean"
    ) {
      push(issues, `${path}.value`, "expected string, number, or boolean");
    } else if (typeof item.value === "number" && !Number.isFinite(item.value)) {
      push(issues, `${path}.value`, "expected a finite number");
    } else if (typeof item.value === "string" && item.value.trim().length === 0) {
      push(issues, `${path}.value`, "expected a non-empty string");
    }
    if (item.unit !== null && !isNonEmptyString(item.unit)) {
      push(issues, `${path}.unit`, "expected a non-empty string or null");
    }
    requireStringArray(item, "inputs", path, issues);
  });
}

function validateHypotheses(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `hypotheses[${index}]`;
    if (!isRecord(item)) {
      push(issues, path, "expected an object");
      return;
    }
    requireId(item, "hypothesis_id", path, issues);
    requireString(item, "statement", path, issues);
    requireStringArray(item, "supporting_ids", path, issues);
    requireStringArray(item, "contradicting_ids", path, issues);
  });
}

function validateUncertainties(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `uncertainties[${index}]`;
    if (!isRecord(item)) {
      push(issues, path, "expected an object");
      return;
    }
    requireId(item, "uncertainty_id", path, issues);
    requireString(item, "statement", path, issues);
  });
}

function validateRequiredInformation(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `required_information[${index}]`;
    if (!isRecord(item)) {
      push(issues, path, "expected an object");
      return;
    }
    requireId(item, "question_id", path, issues);
    requireString(item, "statement", path, issues);
  });
}

function validateRedFlags(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `red_flags[${index}]`;
    if (!isRecord(item)) {
      push(issues, path, "expected an object");
      return;
    }
    requireId(item, "flag_id", path, issues);
    requireString(item, "code", path, issues);
    requireString(item, "source", path, issues);
  });
}

function validateContradictions(value: unknown, issues: ContractIssue[]): void {
  if (!Array.isArray(value)) return;
  value.forEach((item, index) => {
    const path = `contradictions[${index}]`;
    issues.push(...contradictionIssues(item, path));
  });
}

export function contradictionIssues(
  input: unknown,
  path = "contradiction",
): ContractIssue[] {
  const issues: ContractIssue[] = [];
  if (!isRecord(input)) {
    push(issues, path, "expected an object");
    return issues;
  }
  requireString(input, "claim_a", path, issues);
  requireString(input, "claim_b", path, issues);
  if (
    isNonEmptyString(input.claim_a) &&
    isNonEmptyString(input.claim_b) &&
    input.claim_a.trim() === input.claim_b.trim()
  ) {
    push(issues, `${path}.claim_b`, "claims must differ");
  }
  if (!Array.isArray(input.sources) || input.sources.length === 0) {
    push(issues, `${path}.sources`, "expected a non-empty array of sources");
  } else if (!input.sources.every((source) => isNonEmptyString(source))) {
    push(issues, `${path}.sources`, "each source must be a non-empty string");
  }
  if (
    typeof input.clinical_importance !== "string" ||
    !(CLINICAL_IMPORTANCE as readonly string[]).includes(input.clinical_importance)
  ) {
    push(
      issues,
      `${path}.clinical_importance`,
      `expected one of ${CLINICAL_IMPORTANCE.join(", ")}`,
    );
  }
  if (!("resolution_status" in input)) {
    push(issues, `${path}.resolution_status`, "missing resolution_status");
  } else if (input.resolution_status !== RESOLUTION_STATUS_UNRESOLVED) {
    push(
      issues,
      `${path}.resolution_status`,
      "contradictions are not resolved here; resolution_status must be unresolved",
    );
  }
  return issues;
}

export function validateContradiction(input: unknown): Contradiction {
  const issues = contradictionIssues(input);
  if (issues.length > 0) {
    throw new ContractValidationError(issues);
  }
  return input as Contradiction;
}

function validateNextAction(value: unknown, issues: ContractIssue[]): void {
  if (!isRecord(value)) return;
  if (!isDisposition(value.disposition)) {
    push(
      issues,
      "next_action.disposition",
      `expected one of ${DISPOSITIONS.join(", ")}`,
    );
  }
  if (
    typeof value.action !== "string" ||
    !(ACTION_CLASSES as readonly string[]).includes(value.action)
  ) {
    push(
      issues,
      "next_action.action",
      `expected one of ${ACTION_CLASSES.join(", ")}`,
    );
  } else if (
    isDisposition(value.disposition) &&
    value.action !== actionClassFor(value.disposition)
  ) {
    push(
      issues,
      "next_action.action",
      `must match disposition table (${actionClassFor(value.disposition)})`,
    );
  }
  requireNullableString(value, "ideal_action", "next_action", issues);
  requireNullableString(value, "locally_executable_action", "next_action", issues);
  requireNullableString(value, "resource_gap", "next_action", issues);
  if (
    isNonEmptyString(value.ideal_action) &&
    isNonEmptyString(value.locally_executable_action) &&
    value.ideal_action !== value.locally_executable_action &&
    value.resource_gap === null
  ) {
    push(
      issues,
      "next_action.resource_gap",
      "gap must be explicit when ideal and local actions differ",
    );
  }
}

function validateProvenance(value: unknown, issues: ContractIssue[]): void {
  if (!isRecord(value)) return;
  const path = "provenance";
  requireString(value, "rules_version", path, issues);
  requireExplicitNullable(value, "model_id", path, issues, false);
  requireExplicitNullable(value, "knowledge_version", path, issues, false);
  requireExplicitNullable(value, "last_sync", path, issues, true);
  requireTimestamp(value, "generated_at", path, issues);
  if (isNonEmptyString(value.knowledge_version) && value.last_sync === null) {
    push(
      issues,
      "provenance.last_sync",
      "knowledge_version requires last_sync; do not claim a version without a sync time",
    );
  }
}

function requireExplicitNullable(
  record: Record<string, unknown>,
  key: string,
  path: string,
  issues: ContractIssue[],
  timestamp: boolean,
): void {
  if (!(key in record)) {
    push(issues, `${path}.${key}`, "missing field; null must be explicit");
    return;
  }
  const value = record[key];
  if (value === null) return;
  if (timestamp) {
    if (!isIsoTimestamp(value)) {
      push(issues, `${path}.${key}`, "expected an ISO timestamp or null");
    }
    return;
  }
  if (!isNonEmptyString(value)) {
    push(issues, `${path}.${key}`, "expected a non-empty string or null");
  }
}

export function clinicalEventIssues(
  input: unknown,
  path = "event",
): ContractIssue[] {
  const issues: ContractIssue[] = [];
  if (!isRecord(input)) {
    push(issues, path, "expected an object");
    return issues;
  }
  requireId(input, "event_id", path, issues);
  requireId(input, "encounter_id", path, issues);
  requireString(input, "type", path, issues);
  if (
    input.value !== null &&
    typeof input.value !== "string" &&
    typeof input.value !== "number" &&
    typeof input.value !== "boolean"
  ) {
    push(issues, `${path}.value`, "expected string, number, boolean, or null");
  } else if (typeof input.value === "number" && !Number.isFinite(input.value)) {
    push(issues, `${path}.value`, "expected a finite number");
  } else if (typeof input.value === "string" && input.value.trim().length === 0) {
    push(issues, `${path}.value`, "expected a non-empty string or null");
  }
  if (input.unit !== null && !isNonEmptyString(input.unit)) {
    push(issues, `${path}.unit`, "expected a non-empty string or null");
  }
  requireTimestamp(input, "timestamp", path, issues);
  requireString(input, "source", path, issues);
  requireConfidence(input, path, issues);
  requireString(input, "provenance", path, issues);
  return issues;
}

export function validateClinicalEvent(input: unknown): ClinicalEvent {
  const issues = clinicalEventIssues(input);
  if (issues.length > 0) {
    throw new ContractValidationError(issues);
  }
  return input as ClinicalEvent;
}

/**
 * Copy-and-append. Rejects a repeated event_id. Does not replace, collapse,
 * or pick a current value.
 */
export function appendClinicalEvent(
  log: readonly ClinicalEvent[],
  event: ClinicalEvent,
): readonly ClinicalEvent[] {
  if (!Array.isArray(log)) {
    throw new ContractValidationError([
      { path: "log", message: "expected an array of events" },
    ]);
  }
  const issues: ContractIssue[] = [];
  log.forEach((existing, index) => {
    issues.push(...clinicalEventIssues(existing, `log[${index}]`));
  });
  issues.push(...clinicalEventIssues(event, "event"));
  if (issues.length > 0) {
    throw new ContractValidationError(issues);
  }
  if (log.some((existing) => existing.event_id === event.event_id)) {
    throw new ContractValidationError([
      {
        path: "event.event_id",
        message: "append-only: event_id already recorded",
      },
    ]);
  }
  const next = [
    ...log.map((existing) => Object.freeze({ ...existing })),
    Object.freeze({ ...event }),
  ];
  return Object.freeze(next);
}

/** Every matching event, oldest first. Never reduced to one reading. */
export function eventsOfType(
  log: readonly ClinicalEvent[],
  type: string,
): readonly ClinicalEvent[] {
  return [...log]
    .filter((event) => event.type === type)
    .sort(
      (a, b) =>
        a.timestamp.localeCompare(b.timestamp) ||
        a.event_id.localeCompare(b.event_id),
    );
}

function requireId(
  record: Record<string, unknown>,
  key: string,
  path: string,
  issues: ContractIssue[],
): void {
  requireString(record, key, path, issues);
}

function requireString(
  record: Record<string, unknown>,
  key: string,
  path: string,
  issues: ContractIssue[],
): void {
  if (!isNonEmptyString(record[key])) {
    push(issues, `${path}.${key}`, "expected a non-empty string");
  }
}

function requireTimestamp(
  record: Record<string, unknown>,
  key: string,
  path: string,
  issues: ContractIssue[],
): void {
  if (!isIsoTimestamp(record[key])) {
    push(issues, `${path}.${key}`, "expected an ISO timestamp");
  }
}

function requireConfidence(
  record: Record<string, unknown>,
  path: string,
  issues: ContractIssue[],
): void {
  if (!isConfidence(record.confidence)) {
    push(issues, `${path}.confidence`, "expected a number from 0 to 1");
  }
}

function requireStringArray(
  record: Record<string, unknown>,
  key: string,
  path: string,
  issues: ContractIssue[],
): void {
  const value = record[key];
  if (!Array.isArray(value) || !value.every((item) => isNonEmptyString(item))) {
    push(issues, `${path}.${key}`, "expected an array of non-empty strings");
  }
}

function requireNullableString(
  record: Record<string, unknown>,
  key: string,
  path: string,
  issues: ContractIssue[],
): void {
  if (!(key in record)) {
    push(issues, `${path}.${key}`, "missing field; null must be explicit");
    return;
  }
  if (!isNullableString(record[key])) {
    push(issues, `${path}.${key}`, "expected a non-empty string or null");
  }
}
