import { readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import type { AssessmentAnswers, DecisionKind } from "../lib/types";
import { actionClassFor } from "../lib/clinical/contract";
import {
  contentHash,
  loadSuite,
  type ManifestEntry,
  type Suite,
} from "./runner";

/**
 * Fail-closed release machinery. This module cannot authorize a release.
 * Missing metrics and unsigned clinical thresholds block promotion.
 * Expected labels are read from fixtures. They are not derived here.
 */

export const ACTION_DISTRIBUTION_KEYS = [
  "ANSWER",
  "ASK",
  "ABSTAIN",
  "ESCALATE",
] as const;

export type DistributionKey = (typeof ACTION_DISTRIBUTION_KEYS)[number];

export type GateStatus = "pass" | "fail" | "blocked";

export type GateRow = {
  id: string;
  status: GateStatus;
  reason: string;
};

export type PromotionDecision = {
  promotion: "blocked";
  release_authorization: "none";
  clinical_effectiveness: "not_established";
  rows: GateRow[];
  block_reasons: string[];
  distribution: Record<DistributionKey, number> | null;
};

export type GateFamily = {
  status?: "measured" | "not_measurable";
  value?: number;
  numerator?: number;
  denominator?: number;
  cases?: { language?: string; matched?: boolean }[];
};

export type AdversarialClass =
  | "look_alike"
  | "paraphrase_bypass"
  | "colloquial_misspelling_codeswitch"
  | "injection_inert";

export type AdversarialEntry = {
  id: string;
  class: AdversarialClass;
  language: "en" | "sw" | "und";
  lineage: "SYNTHETIC";
  execution: "inert_data_not_executed";
  training_set: false;
  input: Partial<AssessmentAnswers>;
  expected: DecisionKind | null;
  label_status: "engineering_assertion_unverified" | "withheld_not_a_clinical_label";
  note: string;
  provenance: ManifestEntry["provenance"];
  content_hash: string;
};

export type AdversarialCatalog = {
  purpose: "engineering_fixtures_only";
  training_set: false;
  label_limit: string;
  entries: AdversarialEntry[];
};

const BLANK: AssessmentAnswers = {
  who: null,
  presentation: "",
  photoAttached: false,
  awake: null,
  breathing: null,
  drinking: null,
  duration: null,
  mainProblem: null,
};

const REQUIRED_UNMEASURED = [
  "clinical_correctness",
  "calibration",
  "retrieval",
  "multilingual_generation",
  "medication_safety",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function hashWithoutContentHash(value: unknown): string {
  if (!isRecord(value)) return contentHash(value);
  const rest: Record<string, unknown> = {};
  for (const key of Object.keys(value)) {
    if (key === "content_hash") continue;
    rest[key] = value[key];
  }
  return contentHash(rest);
}

export function loadAdversarialSuite(evalsRoot: string): Suite {
  return loadSuite(evalsRoot, "adversarial/manifest.json");
}

export function loadAdversarialCatalog(evalsRoot: string): AdversarialCatalog {
  const path = resolve(evalsRoot, "adversarial/catalog.json");
  if (!path.startsWith(resolve(evalsRoot) + sep)) {
    throw new Error("Adversarial catalog outside evals");
  }
  const catalog = JSON.parse(readFileSync(path, "utf8")) as AdversarialCatalog;
  if (catalog.purpose !== "engineering_fixtures_only" || catalog.training_set !== false) {
    throw new Error("Adversarial catalog must stay an engineering fixture, not a training set");
  }
  if (!catalog.label_limit.includes("unverified")) {
    throw new Error("Adversarial catalog is missing the unverified-authorship limit");
  }
  const seen = new Set<string>();
  for (const entry of catalog.entries) {
    if (seen.has(entry.id)) throw new Error(`Duplicate adversarial id: ${entry.id}`);
    seen.add(entry.id);
    if (entry.lineage !== "SYNTHETIC" || entry.execution !== "inert_data_not_executed") {
      throw new Error(`Adversarial entry is not inert synthetic data: ${entry.id}`);
    }
    if (entry.training_set !== false) {
      throw new Error(`Adversarial entry must not be a training row: ${entry.id}`);
    }
    if (entry.provenance.label_derivation !== "explicit_assertion_not_runtime_output" ||
        entry.provenance.human_authorship !== "unverified" ||
        entry.provenance.clinical_review !== "not_reviewed") {
      throw new Error(`Adversarial provenance is not an unverified assertion: ${entry.id}`);
    }
    if (hashWithoutContentHash(entry) !== entry.content_hash) {
      throw new Error(`Adversarial hash mismatch: ${entry.id}`);
    }
    if (entry.class === "injection_inert" && !JSON.stringify(entry.input).includes("INERT_FIXTURE")) {
      throw new Error(`Injection fixture is missing its inert marker: ${entry.id}`);
    }
  }
  return catalog;
}

export type AdversarialObservation = {
  id: string;
  class: AdversarialClass;
  expected: DecisionKind | null;
  observed: DecisionKind;
  matched: boolean | null;
  executed: false;
};

export function observeAdversarial(
  entries: readonly AdversarialEntry[],
  decider: (answers: AssessmentAnswers) => { kind: DecisionKind },
): AdversarialObservation[] {
  return entries.map((entry) => {
    const observed = decider({ ...BLANK, ...entry.input }).kind;
    return {
      id: entry.id,
      class: entry.class,
      expected: entry.expected,
      observed,
      matched: entry.expected === null ? null : observed === entry.expected,
      executed: false,
    };
  });
}

export function distributionFromKinds(
  kinds: readonly DecisionKind[],
): Record<DistributionKey, number> {
  const counts: Record<DistributionKey, number> = {
    ANSWER: 0,
    ASK: 0,
    ABSTAIN: 0,
    ESCALATE: 0,
  };
  for (const kind of kinds) {
    counts[actionClassFor(kind)] += 1;
  }
  return counts;
}

function sliceRates(family: GateFamily | undefined): Record<string, { numerator: number; denominator: number }> {
  const slices: Record<string, { numerator: number; denominator: number }> = {};
  for (const item of family?.cases ?? []) {
    const key = item.language ?? "und";
    const slice = slices[key] ?? { numerator: 0, denominator: 0 };
    slice.denominator += 1;
    if (item.matched) slice.numerator += 1;
    slices[key] = slice;
  }
  return slices;
}

function measuredValue(family: GateFamily | undefined): number | null {
  if (!family || family.status !== "measured" || typeof family.value !== "number") return null;
  return family.value;
}

export function evaluateReleaseGate(input: {
  baseline: Record<string, GateFamily | undefined>;
  challenger: Record<string, GateFamily | undefined>;
  distribution: Partial<Record<DistributionKey, number>> | null;
  clinical_thresholds_signed: boolean;
}): PromotionDecision {
  const rows: GateRow[] = [];
  const blockReasons: string[] = [];

  const baselineRecall = measuredValue(input.baseline.red_flag_recall);
  const challengerRecall = measuredValue(input.challenger.red_flag_recall);
  if (baselineRecall === null || challengerRecall === null) {
    rows.push({
      id: "red_flag_recall_gte_baseline",
      status: "blocked",
      reason: "red-flag recall is missing or not measured",
    });
    blockReasons.push("missing_red_flag_recall");
  } else if (challengerRecall + 1e-12 < baselineRecall) {
    rows.push({
      id: "red_flag_recall_gte_baseline",
      status: "fail",
      reason: "challenger red-flag recall is below the frozen baseline",
    });
    blockReasons.push("red_flag_recall_regression");
  } else {
    rows.push({
      id: "red_flag_recall_gte_baseline",
      status: "pass",
      reason: "challenger red-flag recall is at least the frozen baseline",
    });
  }

  const baselineSlices = sliceRates(input.baseline.red_flag_recall);
  const challengerSlices = sliceRates(input.challenger.red_flag_recall);
  const sliceKeys = Object.keys(baselineSlices);
  let sliceFailed = false;
  if (sliceKeys.length === 0) {
    rows.push({
      id: "no_safety_critical_slice_regression",
      status: "blocked",
      reason: "baseline has no language slices to compare",
    });
    blockReasons.push("missing_slices");
  } else {
    for (const key of sliceKeys) {
      const before = baselineSlices[key];
      const after = challengerSlices[key];
      if (!after || after.denominator < before.denominator || after.numerator < before.numerator) {
        sliceFailed = true;
      }
    }
    rows.push({
      id: "no_safety_critical_slice_regression",
      status: sliceFailed ? "fail" : "pass",
      reason: sliceFailed
        ? "a safety-critical language slice regressed or disappeared"
        : "language slices did not regress against the frozen baseline",
    });
    if (sliceFailed) blockReasons.push("slice_regression");
  }

  const distribution = input.distribution;
  const distributionComplete = distribution !== null &&
    ACTION_DISTRIBUTION_KEYS.every((key) => typeof distribution[key] === "number");
  rows.push({
    id: "disposition_distribution_reported",
    status: distributionComplete ? "pass" : "blocked",
    reason: distributionComplete
      ? "ANSWER/ASK/ABSTAIN/ESCALATE counts are present, including zeros"
      : "disposition distribution is missing a required key",
  });
  if (!distributionComplete) blockReasons.push("missing_distribution");

  rows.push({
    id: "clinical_thresholds_signed",
    status: input.clinical_thresholds_signed ? "pass" : "blocked",
    reason: input.clinical_thresholds_signed
      ? "a signature flag was supplied; this module still cannot authorize release"
      : "clinical thresholds are unsigned",
  });
  if (!input.clinical_thresholds_signed) blockReasons.push("unsigned_clinical_threshold");

  const missingMetrics = REQUIRED_UNMEASURED.filter((family) => {
    const baseline = input.baseline[family];
    const challenger = input.challenger[family];
    return !baseline || baseline.status !== "measured" || !challenger || challenger.status !== "measured";
  });
  rows.push({
    id: "required_metrics_present",
    status: missingMetrics.length === 0 ? "pass" : "blocked",
    reason: missingMetrics.length === 0
      ? "required metric families are measured"
      : `missing or not_measurable: ${missingMetrics.join(", ")}`,
  });
  if (missingMetrics.length > 0) blockReasons.push("missing_metric");

  return {
    promotion: "blocked",
    release_authorization: "none",
    clinical_effectiveness: "not_established",
    rows,
    block_reasons: blockReasons.length > 0 ? blockReasons : ["release_not_authorized_by_this_module"],
    distribution: distributionComplete ? distribution as Record<DistributionKey, number> : null,
  };
}

export type ChampionComparison = {
  input_identity: "identical_frozen_inputs";
  input_count: number;
  agreement_count: number;
  disagreement_count: number;
  promotion: "blocked";
  release_authorization: "none";
};

export function compareChampionChallenger<T>(
  inputs: readonly T[],
  champion: (input: T) => string,
  challenger: (input: T) => string,
): ChampionComparison {
  let agreement = 0;
  for (const input of inputs) {
    if (champion(input) === challenger(input)) agreement += 1;
  }
  return {
    input_identity: "identical_frozen_inputs",
    input_count: inputs.length,
    agreement_count: agreement,
    disagreement_count: inputs.length - agreement,
    promotion: "blocked",
    release_authorization: "none",
  };
}

export function assertNoReleaseAuthorization(decision: PromotionDecision): void {
  if (decision.promotion !== "blocked" || decision.release_authorization !== "none") {
    throw new Error("release gate failed closed check");
  }
  if (decision.clinical_effectiveness !== "not_established") {
    throw new Error("clinical effectiveness must stay unestablished");
  }
}
