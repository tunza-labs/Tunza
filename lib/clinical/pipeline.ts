import { EMPTY_ANSWERS } from "../assessment";
import { t, type CopyKey, type Locale } from "../copy";
import type { AssessmentAnswers, DecisionKind, Encounter } from "../types";
import {
  SECTION_KEYS,
  actionClassFor,
  demoProvenance,
  emptyRetrievedEvidence,
  headlineKeyFor,
  validateClinicalAssessment,
  type AssessmentSection,
  type ClinicalAssessment,
  type ClinicalEvent,
  type DerivedFeature,
  type ExistingHeadlineKey,
} from "./contract";
import {
  reconcileWithTelemetry,
  type CandidateInput,
  type DisagreementRecord,
} from "./reconcile";
import {
  appendObservation,
  projectEncounter,
  structuralTrend,
  type EncounterState,
} from "./state";
import { decide } from "../assessment";

/**
 * Demo-path wiring: decide() → reconciler → ten-section contract.
 * No model call. model_id and knowledge_version stay null.
 * Internal sections stay structured. This is not a prose generator.
 */

export const PIPELINE_RULES_VERSION = "demo-floor/unvalidated";

const SECTION_LABELS: Record<AssessmentSection, CopyKey> = {
  observed_facts: "contractObservedFacts",
  retrieved_evidence: "contractRetrievedEvidence",
  derived_features: "contractDerivedFeatures",
  hypotheses: "contractHypotheses",
  uncertainties: "contractUncertainties",
  contradictions: "contractContradictions",
  required_information: "contractRequiredInformation",
  red_flags: "contractRedFlags",
  next_action: "contractNextAction",
  provenance: "contractProvenance",
};

export type RenderedSection = {
  key: AssessmentSection;
  labelKey: CopyKey;
  label: string;
  body: unknown;
};

export type RenderedAssessment = {
  locale: Locale;
  headlineKey: ExistingHeadlineKey | null;
  headline: string | null;
  sections: RenderedSection[];
  collapsed: false;
};

export type PipelineResult = {
  state: EncounterState;
  assessment: ClinicalAssessment;
  disagreement: DisagreementRecord | null;
  rendered: RenderedAssessment;
};

function requireTimestamp(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new Error("generatedAt must be an explicit ISO timestamp");
  }
  return value;
}

function trends(events: readonly ClinicalEvent[]): DerivedFeature[] {
  const types = [...new Set(events.map((event) => event.type))];
  const features: DerivedFeature[] = [];
  for (const type of types) {
    const feature = structuralTrend(events, type);
    if (feature) features.push(feature);
  }
  return features;
}

export function renderAssessment(
  assessment: ClinicalAssessment,
  locale: Locale,
): RenderedAssessment {
  const headlineKey = headlineKeyFor(assessment.next_action.disposition);
  return {
    locale,
    headlineKey,
    headline: headlineKey ? t(headlineKey, locale) : null,
    collapsed: false,
    sections: SECTION_KEYS.map((key) => ({
      key,
      labelKey: SECTION_LABELS[key],
      label: t(SECTION_LABELS[key], locale),
      body: assessment[key],
    })),
  };
}

export function runClinicalPipeline(input: {
  encounter: Encounter;
  generatedAt: string;
  locale?: Locale;
  candidate?: CandidateInput | null;
  extraEvents?: readonly ClinicalEvent[];
}): PipelineResult {
  const generatedAt = requireTimestamp(input.generatedAt);
  let state = projectEncounter(input.encounter);
  for (const event of input.extraEvents ?? []) {
    state = appendObservation(state, event);
  }
  const floor = decide(input.encounter.answers);
  const reconciled = reconcileWithTelemetry({
    floor,
    candidate: input.candidate ?? null,
  });
  const applied = reconciled.disposition;
  const observedFacts = state.events.map((event) => ({
    fact_id: event.event_id,
    value: `${event.type}=${String(event.value)}${event.unit ? ` ${event.unit}` : ""}`,
    source: event.source,
    timestamp: event.timestamp,
    confidence: event.confidence,
    provenance: event.provenance,
  }));
  const uncertainties = state.presence
    .filter((item) => item.presence !== "recorded")
    .map((item) => ({
      uncertainty_id: `presence:${item.field}`,
      statement: `${item.field}:${item.presence}`,
    }));
  const required = state.presence
    .filter((item) => item.presence !== "recorded")
    .map((item) => ({
      question_id: item.field,
      statement: `${item.field}:${item.presence}`,
    }));
  const redFlags = floor.dangerSignKeys.map((code, index) => ({
    flag_id: `floor:${index}:${code}`,
    code,
    source: "decide",
  }));
  const assessment = validateClinicalAssessment({
    observed_facts: observedFacts,
    retrieved_evidence: emptyRetrievedEvidence("not_run"),
    derived_features: trends(state.events),
    hypotheses: [],
    uncertainties,
    contradictions: state.contradictions,
    required_information: required,
    red_flags: redFlags,
    next_action: {
      disposition: applied,
      action: actionClassFor(applied),
      ideal_action: applied,
      locally_executable_action: applied,
      resource_gap: null,
    },
    provenance: demoProvenance(PIPELINE_RULES_VERSION, generatedAt),
  });
  return {
    state,
    assessment,
    disagreement: reconciled.disagreement,
    rendered: renderAssessment(assessment, input.locale ?? "en"),
  };
}

/** Eval adapter. Demo path only: no candidate, so the floor is decide(). */
export function pipelineDecider(
  answers: AssessmentAnswers,
): { kind: DecisionKind } {
  const encounter: Encounter = {
    id: "eval-encounter",
    answers: { ...EMPTY_ANSWERS, ...answers },
    asked: [],
    currentQuestion: null,
    decision: null,
    startedBy: "household",
    createdAt: "2026-10-07T00:00:00Z",
    updatedAt: "2026-10-07T00:00:00Z",
  };
  const result = runClinicalPipeline({
    encounter,
    generatedAt: "2026-10-07T00:00:00Z",
  });
  const kind = result.assessment.next_action.disposition;
  if (kind === "escalate" || kind === "abstain") {
    throw new Error("demo path must stay on the existing decision kinds");
  }
  return { kind };
}
