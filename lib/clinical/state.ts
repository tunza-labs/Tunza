import type { AssessmentAnswers, Encounter } from "../types";
import {
  appendClinicalEvent,
  createContradiction,
  eventsOfType,
  validateClinicalEvent,
  type ClinicalEvent,
  type Contradiction,
  type DerivedFeature,
} from "./contract";

/**
 * Encounter-scoped projection. Not a patient registry and not a clinical
 * protocol. Observations are append-only. This module does not choose a
 * disposition and does not apply clinical cutoffs.
 */

export const STATE_MODULE = "clinical-state/v1";

export type Presence = "recorded" | "explicit_unknown" | "not_recorded";

export type FieldPresence = {
  field: string;
  presence: Presence;
};

export type EncounterState = {
  encounter_id: string;
  events: readonly ClinicalEvent[];
  contradictions: readonly Contradiction[];
  presence: readonly FieldPresence[];
};

const ANSWER_FIELDS = [
  "who",
  "presentation",
  "photoAttached",
  "awake",
  "breathing",
  "drinking",
  "duration",
  "mainProblem",
] as const;

type AnswerField = (typeof ANSWER_FIELDS)[number];

const UNIT_ALIASES: Record<string, string> = {
  c: "C",
  celsius: "C",
  "°c": "C",
  degc: "C",
  f: "F",
  fahrenheit: "F",
  "°f": "F",
  degf: "F",
};

export class StateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StateError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Unit-label normalization only. Not a clinical threshold. */
export function normalizeUnit(unit: string | null): string | null {
  if (unit === null) return null;
  const key = unit.trim().toLowerCase().replace(/\s+/g, "");
  if (!key) return null;
  return UNIT_ALIASES[key] ?? unit.trim();
}

/**
 * Measurement conversion for comparison. Not a fever cutoff and not a
 * disposition input.
 */
export function toCelsius(value: number, unit: string | null): number | null {
  const normalized = normalizeUnit(unit);
  if (normalized === "C") return value;
  if (normalized === "F") return ((value - 32) * 5) / 9;
  return null;
}

function presenceOf(field: AnswerField, value: AssessmentAnswers[AnswerField]): Presence {
  if (field === "presentation") {
    return typeof value === "string" && value.trim().length > 0
      ? "recorded"
      : "not_recorded";
  }
  if (value === null) return "not_recorded";
  if (value === "unknown") return "explicit_unknown";
  return "recorded";
}

function claimText(event: ClinicalEvent): string {
  const unit = event.unit ? ` ${event.unit}` : "";
  return `${event.type}=${String(event.value)}${unit} @${event.timestamp}#${event.event_id}`;
}

function withNormalizedUnit(event: ClinicalEvent): ClinicalEvent {
  const unit = normalizeUnit(event.unit);
  if (unit === event.unit) return event;
  const note = event.unit ? `; unit_normalized_from=${event.unit}` : "";
  return {
    ...event,
    unit,
    provenance: `${event.provenance}${note}`,
  };
}

function isNumericSeries(prior: ClinicalEvent, next: ClinicalEvent): boolean {
  return (
    typeof prior.value === "number" &&
    typeof next.value === "number" &&
    prior.timestamp !== next.timestamp
  );
}

function conflictsFor(
  existing: readonly ClinicalEvent[],
  next: ClinicalEvent,
): Contradiction[] {
  const conflicts: Contradiction[] = [];
  for (const prior of existing) {
    if (prior.type !== next.type) continue;
    if (prior.value === next.value && prior.unit === next.unit) continue;
    if (isNumericSeries(prior, next)) continue;
    conflicts.push(
      createContradiction({
        claim_a: claimText(prior),
        claim_b: claimText(next),
        sources: [prior.source, next.source],
        clinical_importance: "low",
      }),
    );
  }
  return conflicts;
}

export function projectAnswers(input: {
  encounterId: string;
  answers: AssessmentAnswers;
  timestamp: string;
  source?: string;
}): EncounterState {
  if (!input.encounterId.trim()) {
    throw new StateError("encounter_id is required; state is encounter-scoped");
  }
  const source = input.source ?? "encounter_answers";
  const presence: FieldPresence[] = [];
  let events: readonly ClinicalEvent[] = [];
  for (const field of ANSWER_FIELDS) {
    const value = input.answers[field];
    const presenceKind = presenceOf(field, value);
    presence.push({ field, presence: presenceKind });
    if (presenceKind === "not_recorded") continue;
    const event = validateClinicalEvent({
      event_id: `${input.encounterId}:${field}:${input.timestamp}`,
      encounter_id: input.encounterId,
      type: field,
      value,
      unit: null,
      timestamp: input.timestamp,
      source,
      confidence: 1,
      provenance: "assessment_answers",
    });
    events = appendClinicalEvent(events, event);
  }
  return {
    encounter_id: input.encounterId,
    events,
    contradictions: [],
    presence,
  };
}

export function projectEncounter(encounter: Encounter): EncounterState {
  return projectAnswers({
    encounterId: encounter.id,
    answers: encounter.answers,
    timestamp: encounter.updatedAt,
    source: `encounter:${encounter.startedBy}`,
  });
}

export function appendObservation(
  state: EncounterState,
  event: ClinicalEvent,
): EncounterState {
  const normalized = withNormalizedUnit(validateClinicalEvent(event));
  if (normalized.encounter_id !== state.encounter_id) {
    throw new StateError(
      "encounter-scoped: refusing to append an event from another encounter",
    );
  }
  const events = appendClinicalEvent(state.events, normalized);
  const contradictions = Object.freeze([
    ...state.contradictions,
    ...conflictsFor(state.events, normalized),
  ]);
  return {
    encounter_id: state.encounter_id,
    events,
    contradictions,
    presence: state.presence,
  };
}

function elapsedHours(start: string, end: string): number | null {
  const from = Date.parse(start);
  const to = Date.parse(end);
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return null;
  return (to - from) / 3_600_000;
}

function formatHours(hours: number): string {
  if (Math.abs(hours - Math.round(hours)) < 1e-9) return String(Math.round(hours));
  return hours.toFixed(1);
}

function comparable(event: ClinicalEvent): number | null {
  if (typeof event.value !== "number") return null;
  if (event.type === "temperature") return toCelsius(event.value, event.unit);
  return event.value;
}

/**
 * Structural delta only. Phrases describe change across readings. They do
 * not assign a clinical meaning and they do not affect disposition.
 */
export function structuralTrend(
  events: readonly ClinicalEvent[],
  type: string,
): DerivedFeature | null {
  const series = eventsOfType(events, type).filter(
    (event) => typeof event.value === "number",
  );
  if (series.length < 2) return null;
  if (type === "temperature") {
    if (series.some((event) => toCelsius(event.value as number, event.unit) === null)) {
      return null;
    }
  } else if (new Set(series.map((event) => normalizeUnit(event.unit))).size !== 1) {
    return null;
  }
  const values = series.map((event) => comparable(event));
  if (values.some((value) => value === null)) return null;
  const numbers = values as number[];
  const strictlyDecreasing = numbers.every(
    (value, index) => index === 0 || value < numbers[index - 1],
  );
  const first = numbers[0];
  const last = numbers[numbers.length - 1];
  const hours = elapsedHours(
    series[0].timestamp,
    series[series.length - 1].timestamp,
  );
  let text: string;
  if (strictlyDecreasing && numbers.length >= 3) {
    text =
      numbers.length === 3
        ? "three declining readings"
        : `${numbers.length} declining readings`;
  } else if (last > first) {
    text =
      hours === null || hours === 0
        ? "increased"
        : `increased over ${formatHours(hours)} hours`;
  } else if (last < first) {
    text =
      hours === null || hours === 0
        ? "decreased"
        : `decreased over ${formatHours(hours)} hours`;
  } else {
    text = "unchanged across readings";
  }
  return {
    feature_id: `trend:${type}:${series.map((event) => event.event_id).join("+")}`,
    name: `${type}_structural_delta`,
    value: text,
    unit: null,
    inputs: series.map((event) => event.event_id),
  };
}
