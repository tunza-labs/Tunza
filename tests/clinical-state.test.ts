import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { EMPTY_ANSWERS } from "../lib/assessment";
import {
  appendObservation,
  normalizeUnit,
  projectAnswers,
  structuralTrend,
  toCelsius,
  type EncounterState,
} from "../lib/clinical/state";
import type { ClinicalEvent } from "../lib/clinical/contract";
import type { AssessmentAnswers } from "../lib/types";

const AT = "2026-10-07T08:00:00Z";

function answers(partial: Partial<AssessmentAnswers> = {}): AssessmentAnswers {
  return { ...EMPTY_ANSWERS, ...partial };
}

function temp(
  id: string,
  value: number,
  timestamp: string,
  unit = "C",
): ClinicalEvent {
  return {
    event_id: id,
    encounter_id: "enc-1",
    type: "temperature",
    value,
    unit,
    timestamp,
    source: "fixture",
    confidence: 1,
    provenance: "synthetic-fixture",
  };
}

function withTemps(state: EncounterState, events: ClinicalEvent[]): EncounterState {
  return events.reduce((current, event) => appendObservation(current, event), state);
}

describe("append-only encounter state", () => {
  it("keeps both temperatures and has no authoritative temperature field", () => {
    const state = withTemps(
      projectAnswers({
        encounterId: "enc-1",
        answers: answers({ who: "child", presentation: "hot body" }),
        timestamp: AT,
      }),
      [
        temp("temp-1", 37.4, "2026-10-07T08:00:00Z"),
        temp("temp-2", 39.2, "2026-10-07T11:00:00Z"),
      ],
    );
    expect(Object.hasOwn(state, "temperature")).toBe(false);
    const readings = state.events.filter((event) => event.type === "temperature");
    expect(readings.map((event) => event.value)).toEqual([37.4, 39.2]);
    expect(readings.map((event) => event.timestamp)).toEqual([
      "2026-10-07T08:00:00Z",
      "2026-10-07T11:00:00Z",
    ]);
  });

  it("records explicit unknown separately from not recorded", () => {
    const state = projectAnswers({
      encounterId: "enc-1",
      answers: answers({ awake: "unknown", breathing: null, presentation: "   " }),
      timestamp: AT,
    });
    expect(state.presence.find((item) => item.field === "awake")).toEqual({
      field: "awake",
      presence: "explicit_unknown",
    });
    expect(state.presence.find((item) => item.field === "breathing")).toEqual({
      field: "breathing",
      presence: "not_recorded",
    });
    expect(state.presence.find((item) => item.field === "presentation")).toEqual({
      field: "presentation",
      presence: "not_recorded",
    });
    expect(state.events.some((event) => event.type === "breathing")).toBe(false);
    expect(state.events.find((event) => event.type === "awake")?.value).toBe("unknown");
  });

  it("normalizes unit labels without replacing the stored number", () => {
    expect(normalizeUnit("celsius")).toBe("C");
    expect(normalizeUnit("°F")).toBe("F");
    expect(toCelsius(98.6, "F")).toBe(37);
    const state = appendObservation(
      projectAnswers({ encounterId: "enc-1", answers: answers(), timestamp: AT }),
      temp("temp-f", 98.6, AT, "fahrenheit"),
    );
    const reading = state.events.find((event) => event.event_id === "temp-f");
    expect(reading?.value).toBe(98.6);
    expect(reading?.unit).toBe("F");
  });

  it("keeps same-type categorical conflicts unresolved and does not pick one", () => {
    const base = projectAnswers({
      encounterId: "enc-1",
      answers: answers({ drinking: "yes" }),
      timestamp: AT,
    });
    const next = appendObservation(base, {
      event_id: "drink-2",
      encounter_id: "enc-1",
      type: "drinking",
      value: "no",
      unit: null,
      timestamp: "2026-10-07T09:00:00Z",
      source: "fixture",
      confidence: 1,
      provenance: "synthetic-fixture",
    });
    expect(next.events.filter((event) => event.type === "drinking")).toHaveLength(2);
    expect(next.contradictions).toHaveLength(1);
    expect(next.contradictions[0].resolution_status).toBe("unresolved");
    expect(next.contradictions[0].claim_a).not.toBe(next.contradictions[0].claim_b);
  });

  it("does not treat a later temperature as a contradiction or a cutoff", () => {
    const state = withTemps(
      projectAnswers({ encounterId: "enc-1", answers: answers(), timestamp: AT }),
      [
        temp("temp-1", 37.4, "2026-10-07T08:00:00Z"),
        temp("temp-2", 39.2, "2026-10-07T11:00:00Z"),
      ],
    );
    expect(state.contradictions).toHaveLength(0);
    expect(structuralTrend(state.events, "temperature")).toMatchObject({
      value: "increased over 3 hours",
      unit: null,
    });
  });

  it("describes three declining readings without an LLM or a disposition", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "../lib/clinical/state.ts"),
      "utf8",
    );
    expect(source).not.toMatch(/decide\(/);
    expect(source).not.toMatch(/anthropic|openai|fetch\(/i);
    const state = withTemps(
      projectAnswers({ encounterId: "enc-1", answers: answers(), timestamp: AT }),
      [
        temp("temp-1", 39.2, "2026-10-07T08:00:00Z"),
        temp("temp-2", 38.4, "2026-10-07T09:00:00Z"),
        temp("temp-3", 37.6, "2026-10-07T10:00:00Z"),
      ],
    );
    const feature = structuralTrend(state.events, "temperature");
    expect(feature?.value).toBe("three declining readings");
    expect(feature && "disposition" in feature).toBe(false);
  });

  it("refuses an event from another encounter", () => {
    const state = projectAnswers({
      encounterId: "enc-1",
      answers: answers(),
      timestamp: AT,
    });
    const foreign = { ...temp("temp-x", 37, AT), encounter_id: "enc-2" };
    expect(() => appendObservation(state, foreign)).toThrow(/another encounter/);
  });
});
