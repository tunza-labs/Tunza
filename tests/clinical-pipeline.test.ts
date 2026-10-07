import { describe, expect, it } from "vitest";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { decide, EMPTY_ANSWERS } from "../lib/assessment";
import { t } from "../lib/copy";
import { SECTION_KEYS } from "../lib/clinical/contract";
import {
  pipelineDecider,
  renderAssessment,
  runClinicalPipeline,
} from "../lib/clinical/pipeline";
import { evaluateSuite, loadSuite } from "../evals/runner";
import type { ClinicalEvent } from "../lib/clinical/contract";
import type { AssessmentAnswers, Encounter } from "../lib/types";

const ROOT = resolve(import.meta.dirname, "..");
const GENERATED_AT = "2026-10-07T12:00:00Z";

function encounter(partial: Partial<AssessmentAnswers>, id = "enc-1"): Encounter {
  return {
    id,
    answers: { ...EMPTY_ANSWERS, ...partial },
    asked: [],
    currentQuestion: null,
    decision: null,
    startedBy: "household",
    createdAt: "2026-10-07T08:00:00Z",
    updatedAt: "2026-10-07T08:00:00Z",
  };
}

function temp(id: string, value: number, timestamp: string): ClinicalEvent {
  return {
    event_id: id,
    encounter_id: "enc-1",
    type: "temperature",
    value,
    unit: "C",
    timestamp,
    source: "fixture",
    confidence: 1,
    provenance: "synthetic-fixture",
  };
}

describe("clinical pipeline", () => {
  it("keeps the demo floor when a candidate says self-care", () => {
    const result = runClinicalPipeline({
      encounter: encounter({
        who: "child",
        presentation: "He is unconscious and not waking",
      }),
      generatedAt: GENERATED_AT,
      candidate: { disposition: "self-care", model_id: "claude-sonnet-4-5" },
    });
    expect(decide(encounter({
      who: "child",
      presentation: "He is unconscious and not waking",
    }).answers).kind).toBe("go_now");
    expect(result.assessment.next_action.disposition).toBe("go_now");
    expect(result.assessment.next_action.action).toBe("ESCALATE");
    expect(result.disagreement).toMatchObject({
      candidate: "self-care",
      reconciled: "go_now",
      reason: "candidate_below_floor",
    });
    expect(result.assessment.provenance.model_id).toBeNull();
    expect(result.assessment.provenance.knowledge_version).toBeNull();
    expect(result.assessment.provenance.last_sync).toBeNull();
    expect(result.assessment.retrieved_evidence).toEqual({
      retrieval_status: "not_run",
      trust_tier: "none",
      items: [],
    });
  });

  it("does not answer monitor_at_home when critical answers are missing", () => {
    const answers = encounter({
      awake: "unknown",
      breathing: "unknown",
      presentation: "",
    }).answers;
    expect(decide(answers).kind).not.toBe("monitor_at_home");
    const result = runClinicalPipeline({
      encounter: encounter({
        awake: "unknown",
        breathing: "unknown",
        presentation: "",
      }),
      generatedAt: GENERATED_AT,
    });
    expect(result.assessment.next_action.disposition).toBe(decide(answers).kind);
    expect(result.assessment.next_action.disposition).toBe("need_one_more_answer");
  });

  it("renders ten structured sections through existing copy keys in both languages", () => {
    const result = runClinicalPipeline({
      encounter: encounter({ who: "child", drinking: "no", presentation: "fever" }),
      generatedAt: GENERATED_AT,
    });
    for (const locale of ["en", "sw"] as const) {
      const rendered = renderAssessment(result.assessment, locale);
      expect(rendered.collapsed).toBe(false);
      expect(rendered.sections.map((section) => section.key)).toEqual([...SECTION_KEYS]);
      expect(rendered.headlineKey).toBe("goNow");
      expect(rendered.headline).toBe(t("goNow", locale));
      expect(rendered.sections.every((section) => section.label === t(section.labelKey, locale))).toBe(true);
      expect(rendered.sections.some((section) => section.body === rendered.headline)).toBe(false);
    }
  });

  it("carries a structural temperature trend without calling a model", () => {
    const result = runClinicalPipeline({
      encounter: encounter({ who: "child", presentation: "hot body" }),
      generatedAt: GENERATED_AT,
      extraEvents: [
        temp("temp-1", 37.4, "2026-10-07T08:00:00Z"),
        temp("temp-2", 39.2, "2026-10-07T11:00:00Z"),
      ],
    });
    expect(result.assessment.provenance.model_id).toBeNull();
    expect(result.state.events.filter((event) => event.type === "temperature")).toHaveLength(2);
    expect(result.assessment.derived_features.map((feature) => feature.value)).toContain(
      "increased over 3 hours",
    );
    expect(Object.hasOwn(result.assessment, "temperature")).toBe(false);
  });

  it("matches the frozen decide baseline without replacing it", () => {
    const suite = loadSuite(resolve(ROOT, "evals"));
    const baseline = JSON.parse(
      readFileSync(resolve(ROOT, "evals/reports/baseline-decide.json"), "utf8"),
    );
    const observation = evaluateSuite(suite, pipelineDecider);
    expect(observation.families).toEqual(baseline.families);
    expect(observation.release_authorization).toBe("none");
    const reportPath = resolve(ROOT, "evals/reports/wave1-pipeline.json");
    if (process.env.TUNZA_CAPTURE_PIPELINE === "1") {
      mkdirSync(resolve(ROOT, "evals/reports"), { recursive: true });
      const reportBody = {
        schema_version: 1,
        frozen_baseline: "evals/reports/baseline-decide.json",
        frozen_baseline_replaced: false,
        decider: "lib/clinical/pipeline.ts#pipelineDecider",
        ship_gate: "none",
        label_limit: "Engineering regression only. Human authorship unverified. Not a clinical label set.",
        comparison: {
          families_equal: true,
          diffs: [],
        },
        observation,
      };
      writeFileSync(reportPath, JSON.stringify(reportBody, null, 2) + "\n", { flag: "wx" });
    }
    const report = JSON.parse(readFileSync(reportPath, "utf8"));
    expect(report.frozen_baseline_replaced).toBe(false);
    expect(report.ship_gate).toBe("none");
    expect(report.observation.families).toEqual(baseline.families);
    expect(report.comparison.families_equal).toBe(true);
  });
});
