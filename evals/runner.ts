import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import type { AssessmentAnswers, DecisionKind } from "../lib/types";

// Engineering observations only. No clinical contract, model, network, clock,
// clinical thresholds, or dependency on decide() for expected labels.
export const MEASURABLE_FAMILIES = [
  "red_flag_recall", "abstention", "non_downgrade",
] as const;
export type Family = (typeof MEASURABLE_FAMILIES)[number];
export type EvalCase = {
  id: string;
  family: Family;
  language: "en" | "sw" | "und";
  lineage: "SYNTHETIC";
  input: Partial<AssessmentAnswers>;
  expected: DecisionKind;
  follow_up?: { input: Partial<AssessmentAnswers>; expected: DecisionKind };
};
export type ManifestEntry = {
  id: string;
  path: string;
  content_hash: string;
  lineage: "SYNTHETIC";
  provenance: {
    input_origin: string;
    label_source: string;
    label_derivation: "explicit_assertion_not_runtime_output";
    human_authorship: "unverified";
    clinical_review: "not_reviewed";
  };
};
export const LABEL_AUTHORSHIP_CHOICE =
  "Accept the test-sourced labels for engineering-only regression with human authorship explicitly unverified.";

export type LabelAuthorshipDecision = {
  choice: typeof LABEL_AUTHORSHIP_CHOICE;
  human_authorship: "unverified";
  clinical_review: "not_reviewed";
  use: "engineering_regression_ruler_only";
  not_a_clinical_label_set: true;
};

export type Manifest = {
  schema_version: 1;
  suite_id: string;
  purpose: "engineering_fixtures_only";
  hash_encoding: "sha256_sorted_keys_compact_json_utf8";
  label_authorship_decision: LabelAuthorshipDecision;
  cases: ManifestEntry[];
};

// Host amendment: the authorship decision is required governance metadata.
// It is excluded from the frozen measurement hash so the baseline identity
// does not move when the caveat is recorded.
export function measurementManifest(
  manifest: Manifest,
): Omit<Manifest, "label_authorship_decision"> {
  const copy: Manifest = { ...manifest, cases: manifest.cases };
  delete (copy as Partial<Manifest>).label_authorship_decision;
  return copy;
}
export type Suite = { manifest: Manifest; cases: EvalCase[] };
export type Decider = (answers: AssessmentAnswers) => { kind: DecisionKind };

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map(
      (key) => `${JSON.stringify(key)}:${canonical(object[key])}`,
    ).join(",")}}`;
  }
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error("Not a JSON value");
  return encoded;
}
export function contentHash(value: unknown): string {
  return createHash("sha256").update(canonical(value)).digest("hex");
}
export function fileHash(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const DEFAULT_INPUT: AssessmentAnswers = {
  who: null, presentation: "", photoAttached: false, awake: null,
  breathing: null, drinking: null, duration: null, mainProblem: null,
};
const INPUT_ENUMS = {
  who: [null, "self", "household_adult", "child", "unknown"],
  awake: [null, "alert", "sleepy", "not_waking", "unknown"],
  breathing: [null, "fine", "difficult", "severe", "unknown"],
  drinking: [null, "yes", "little", "no", "unknown"],
  duration: [null, "today", "two_days", "longer", "unknown"],
  mainProblem: [null, "breathing", "fever", "injury", "stomach", "other", "unknown"],
};
const KINDS: DecisionKind[] = [
  "go_now", "get_care_today", "monitor_at_home", "need_one_more_answer",
];
function requireInput(value: Partial<AssessmentAnswers>): void {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid fixture input");
  }
  for (const [key, item] of Object.entries(value)) {
    if (key === "presentation" && typeof item === "string") continue;
    if (key === "photoAttached" && typeof item === "boolean") continue;
    if (Object.hasOwn(INPUT_ENUMS, key) &&
        (INPUT_ENUMS[key as keyof typeof INPUT_ENUMS] as unknown[]).includes(item)) continue;
    throw new Error(`Invalid fixture input field: ${key}`);
  }
}
export function validateCase(item: EvalCase): void {
  if (!item || typeof item.id !== "string" || !/^[a-z0-9-]+$/.test(item.id) ||
      !MEASURABLE_FAMILIES.includes(item.family) ||
      !["en", "sw", "und"].includes(item.language) ||
      item.lineage !== "SYNTHETIC" || !KINDS.includes(item.expected)) {
    throw new Error("Invalid engineering case metadata");
  }
  requireInput(item.input);
  const expected = item.family === "abstention" ? "need_one_more_answer" : "go_now";
  if (item.expected !== expected) throw new Error("Label is outside this family's v0 scope");
  if (item.family === "non_downgrade") {
    if (!item.follow_up || item.follow_up.expected !== "go_now") {
      throw new Error("Non-downgrade requires an independently labeled urgent pair");
    }
    requireInput(item.follow_up.input);
  } else if (item.follow_up) {
    throw new Error("Unexpected follow-up outside non-downgrade family");
  }
}

// A manifest chooses explicit cases, including future files in adversarial/.
// Unlisted objects in a file do not enter the frozen baseline suite.
export function loadSuite(evalsRoot: string, manifestName = "manifest.json"): Suite {
  const manifest: Manifest = JSON.parse(readFileSync(resolve(evalsRoot, manifestName), "utf8"));
  if (manifest.schema_version !== 1 || !manifest.suite_id ||
      manifest.purpose !== "engineering_fixtures_only" ||
      manifest.hash_encoding !== "sha256_sorted_keys_compact_json_utf8" ||
      !Array.isArray(manifest.cases) || manifest.cases.length === 0) {
    throw new Error("Invalid or empty eval manifest");
  }
  const decision = manifest.label_authorship_decision;
  if (!decision || decision.choice !== LABEL_AUTHORSHIP_CHOICE ||
      decision.human_authorship !== "unverified" ||
      decision.clinical_review !== "not_reviewed" ||
      decision.use !== "engineering_regression_ruler_only" ||
      decision.not_a_clinical_label_set !== true) {
    throw new Error("Missing unverified-authorship decision");
  }
  const seen = new Set<string>();
  const cases = manifest.cases.map((entry) => {
    if (seen.has(entry.id)) throw new Error(`Duplicate manifest id: ${entry.id}`);
    seen.add(entry.id);
    if (entry.lineage !== "SYNTHETIC" || !entry.provenance?.input_origin ||
        !entry.provenance.label_source ||
        entry.provenance.label_derivation !== "explicit_assertion_not_runtime_output" ||
        entry.provenance.human_authorship !== "unverified" ||
        entry.provenance.clinical_review !== "not_reviewed") {
      throw new Error(`Missing or unsupported provenance: ${entry.id}`);
    }
    const path = resolve(evalsRoot, entry.path);
    if (!path.startsWith(resolve(evalsRoot) + sep)) throw new Error("Fixture path outside evals");
    const data: EvalCase[] = JSON.parse(readFileSync(path, "utf8"));
    if (!Array.isArray(data)) throw new Error("Case file must be an array");
    const matches = data.filter((item) => item.id === entry.id);
    if (matches.length !== 1) throw new Error(`Missing or duplicate case: ${entry.id}`);
    const item = matches[0];
    validateCase(item);
    if (contentHash(item) !== entry.content_hash) throw new Error(`Hash mismatch: ${entry.id}`);
    return item;
  });
  return { manifest, cases };
}

export type CaseResult = {
  id: string;
  content_hash: string;
  language: EvalCase["language"];
  expected: DecisionKind;
  observed: DecisionKind;
  follow_up?: { expected: DecisionKind; observed: DecisionKind };
  matched: boolean;
};
export type MeasuredFamily = {
  status: "measured";
  scope: string;
  metric: string;
  numerator: number;
  denominator: number;
  value: number;
  cases: CaseResult[];
};
export type UnmeasurableFamily = { status: "not_measurable"; reason: string };
export type FamilyResult = MeasuredFamily | UnmeasurableFamily;
const DEFINITIONS: Record<Family, { scope: string; metric: string }> = {
  red_flag_recall: {
    scope: "Recall on fixed synthetic keyword-positive cases only. Not clinical sensitivity or specificity.",
    metric: "keyword_positive_recall",
  },
  abstention: {
    scope: "Incomplete-story ASK behavior only. decide() has no separate ABSTAIN disposition.",
    metric: "incomplete_story_ask_rate",
  },
  non_downgrade: {
    scope: "Paired decide() calls retaining the urgent finding while adding other answers. Not model reconciliation.",
    metric: "urgent_pair_preservation_rate",
  },
};
const UNMEASURABLE = {
  clinical_correctness: "No independently adjudicated clinical cases or approved clinical reference labels.",
  calibration: "decide() emits no calibrated probabilities and no clinical outcome labels are available.",
  retrieval: "No retrieval implementation or approved evidence corpus.",
  multilingual_generation: "Keyword cases include English and Kiswahili, but no multilingual generation is evaluated.",
  medication_safety: "No medication recommendation or interaction checker is evaluated.",
};

export function evaluateSuite(suite: Suite, decider: Decider) {
  const families: Record<string, FamilyResult> = {};
  for (const family of MEASURABLE_FAMILIES) {
    const cases = suite.cases.filter((item) => item.family === family).map((item): CaseResult => {
      validateCase(item);
      const observed = decider({ ...DEFAULT_INPUT, ...item.input }).kind;
      if (!KINDS.includes(observed)) throw new Error(`Invalid decision for ${item.id}`);
      const followUp = item.follow_up
        ? { expected: item.follow_up.expected,
          observed: decider({ ...DEFAULT_INPUT, ...item.follow_up.input }).kind }
        : undefined;
      if (followUp && !KINDS.includes(followUp.observed)) throw new Error(`Invalid follow-up for ${item.id}`);
      return {
        id: item.id, content_hash: contentHash(item), language: item.language,
        expected: item.expected, observed,
        ...(followUp ? { follow_up: followUp } : {}),
        matched: observed === item.expected && (!followUp || followUp.observed === followUp.expected),
      };
    });
    if (cases.length === 0) {
      families[family] = { status: "not_measurable", reason: "No cases in this family. Never treated as a pass." };
      continue;
    }
    const numerator = cases.filter((item) => item.matched).length;
    families[family] = {
      status: "measured", ...DEFINITIONS[family], numerator,
      denominator: cases.length, value: numerator / cases.length, cases,
    };
  }
  for (const [family, reason] of Object.entries(UNMEASURABLE)) {
    families[family] = { status: "not_measurable", reason };
  }
  return {
    schema_version: 1,
    suite_id: suite.manifest.suite_id,
    manifest_hash: contentHash(measurementManifest(suite.manifest)),
    purpose: "engineering_regression_observation_only",
    release_authorization: "none",
    label_limit: "Explicit existing assertions and task invariants, not runtime-derived labels. Human authorship unverified, no clinical review.",
    families,
  };
}
