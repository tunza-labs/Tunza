import { describe, expect, it } from "vitest";
import type { DecisionKind } from "../lib/types";
import {
  CONTRACT_VERSION,
  DISPOSITION_TABLE,
  DISPOSITIONS,
  RESOLUTION_STATUS_UNRESOLVED,
  SECTION_KEYS,
  TRUST_TIER_NONE,
  ContractValidationError,
  actionClassFor,
  appendClinicalEvent,
  assessmentIssues,
  createContradiction,
  demoProvenance,
  dispositionFromDecisionKind,
  emptyRetrievedEvidence,
  eventsOfType,
  headlineKeyFor,
  minimalAssessment,
  validateClinicalAssessment,
  validateContradiction,
  type ClinicalAssessment,
  type ClinicalEvent,
  type Disposition,
} from "../lib/clinical/contract";

const GENERATED_AT = "2026-10-07T12:00:00Z";

const DECISION_KINDS: DecisionKind[] = [
  "go_now",
  "get_care_today",
  "monitor_at_home",
  "need_one_more_answer",
];

const EXISTING_HEADLINES = [
  "goNow",
  "getCareToday",
  "monitorAtHome",
  "needOneMore",
] as const;

function syntheticEvent(overrides: Partial<ClinicalEvent> = {}): ClinicalEvent {
  return {
    event_id: "evt-1",
    encounter_id: "enc-1",
    type: "temperature",
    value: 37.4,
    unit: "C",
    timestamp: "2026-10-07T08:00:00Z",
    source: "fixture",
    confidence: 1,
    provenance: "synthetic-fixture",
    ...overrides,
  };
}

function filledAssessment(): ClinicalAssessment {
  const base = minimalAssessment({
    rulesVersion: "demo-assessment/unvalidated",
    generatedAt: GENERATED_AT,
    disposition: "need_one_more_answer",
  });
  return validateClinicalAssessment({
    ...base,
    observed_facts: [
      {
        fact_id: "fact-1",
        value: "awake unknown",
        source: "fixture",
        timestamp: GENERATED_AT,
        confidence: 1,
        provenance: "synthetic-fixture",
      },
    ],
    derived_features: [
      {
        feature_id: "feat-1",
        name: "reading_count",
        value: 2,
        unit: null,
        inputs: ["evt-1", "evt-2"],
      },
    ],
    hypotheses: [
      {
        hypothesis_id: "hyp-1",
        statement: "candidate only",
        supporting_ids: ["fact-1"],
        contradicting_ids: [],
      },
    ],
    uncertainties: [
      { uncertainty_id: "unc-1", statement: "duration unknown" },
    ],
    contradictions: [
      createContradiction({
        claim_a: "temperature 37.4 C",
        claim_b: "temperature 39.2 C",
        sources: ["evt-1", "evt-2"],
        clinical_importance: "high",
      }),
    ],
    required_information: [
      { question_id: "duration", statement: "how long" },
    ],
    red_flags: [{ flag_id: "flag-1", code: "demo_floor", source: "fixture" }],
    next_action: {
      disposition: "need_one_more_answer",
      action: "ASK",
      ideal_action: null,
      locally_executable_action: null,
      resource_gap: null,
    },
  });
}

describe("clinical contract sections", () => {
  it("names exactly ten sections", () => {
    expect(SECTION_KEYS).toEqual([
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
    ]);
    expect(new Set(SECTION_KEYS).size).toBe(10);
  });

  it("accepts a fixture that keeps every section", () => {
    const assessment = filledAssessment();
    expect(assessment.retrieved_evidence).toEqual({
      retrieval_status: "not_run",
      trust_tier: TRUST_TIER_NONE,
      items: [],
    });
    expect(assessment.provenance.model_id).toBeNull();
    expect(assessment.provenance.knowledge_version).toBeNull();
    expect(assessment.provenance.last_sync).toBeNull();
    expect(CONTRACT_VERSION).toBe("clinical-contract/v1");
  });

  it("fails when any section is missing", () => {
    const fixture = filledAssessment();
    for (const section of SECTION_KEYS) {
      const broken: Record<string, unknown> = { ...fixture };
      delete broken[section];
      expect(assessmentIssues(broken).some((issue) => issue.path === section)).toBe(
        true,
      );
      expect(() => validateClinicalAssessment(broken)).toThrow(
        ContractValidationError,
      );
    }
  });

  it("fails when a section is present but null", () => {
    const fixture = filledAssessment() as unknown as Record<string, unknown>;
    fixture.provenance = null;
    const issues = assessmentIssues(fixture);
    expect(issues.some((issue) => issue.path === "provenance")).toBe(true);
  });
});

describe("retrieved evidence", () => {
  it("requires an explicit status and trust_tier none on an empty bundle", () => {
    const evidence = emptyRetrievedEvidence("empty");
    expect(evidence.trust_tier).toBe("none");
    expect(evidence.items).toEqual([]);
    const fixture = filledAssessment() as unknown as Record<string, unknown>;
    fixture.retrieved_evidence = { trust_tier: "none", items: [] };
    expect(
      assessmentIssues(fixture).some(
        (issue) => issue.path === "retrieved_evidence.retrieval_status",
      ),
    ).toBe(true);
  });

  it("rejects a non-none trust tier and any admitted item", () => {
    const fixture = filledAssessment() as unknown as Record<string, unknown>;
    fixture.retrieved_evidence = {
      retrieval_status: "not_run",
      trust_tier: "A",
      items: [],
    };
    expect(
      assessmentIssues(fixture).some(
        (issue) => issue.path === "retrieved_evidence.trust_tier",
      ),
    ).toBe(true);

    fixture.retrieved_evidence = {
      retrieval_status: "not_run",
      trust_tier: "none",
      items: [{ source_id: "unverified" }],
    };
    expect(
      assessmentIssues(fixture).some(
        (issue) => issue.path === "retrieved_evidence.items",
      ),
    ).toBe(true);
  });
});

describe("provenance", () => {
  it("records null model, knowledge, and sync on the demo path", () => {
    const provenance = demoProvenance("demo-assessment/unvalidated", GENERATED_AT);
    expect(provenance).toEqual({
      rules_version: "demo-assessment/unvalidated",
      model_id: null,
      knowledge_version: null,
      last_sync: null,
      generated_at: GENERATED_AT,
    });
  });

  it("rejects an omitted null and a knowledge version without last_sync", () => {
    const fixture = filledAssessment() as unknown as {
      provenance: Record<string, unknown>;
    };
    delete fixture.provenance.model_id;
    expect(
      assessmentIssues(fixture).some((issue) => issue.path === "provenance.model_id"),
    ).toBe(true);

    fixture.provenance.model_id = null;
    fixture.provenance.knowledge_version = "unset-corpus";
    fixture.provenance.last_sync = null;
    expect(
      assessmentIssues(fixture).some((issue) => issue.path === "provenance.last_sync"),
    ).toBe(true);
  });
});

describe("disposition table", () => {
  it("maps the four existing kinds plus escalate and abstain", () => {
    expect(Object.keys(DISPOSITION_TABLE).sort()).toEqual([...DISPOSITIONS].sort());
    for (const kind of DECISION_KINDS) {
      expect(dispositionFromDecisionKind(kind)).toBe(kind);
      expect(DISPOSITION_TABLE[kind]).toBeDefined();
    }
    expect(actionClassFor("need_one_more_answer")).toBe("ASK");
    expect(headlineKeyFor("need_one_more_answer")).toBe("needOneMore");
    expect(actionClassFor("abstain")).toBe("ABSTAIN");
    expect(headlineKeyFor("abstain")).toBeNull();
    expect(headlineKeyFor("escalate")).toBe("goNow");
    expect(actionClassFor("go_now")).toBe("ESCALATE");
  });

  it("does not introduce a headline outside the existing four", () => {
    const headlines = Object.values(DISPOSITION_TABLE).map((row) => row.headlineKey);
    for (const headline of headlines) {
      expect(headline === null || EXISTING_HEADLINES.includes(headline)).toBe(true);
    }
    expect(new Set(headlines.filter((key) => key !== null)).size).toBe(4);
  });

  it("rejects an action class that drifts from the table", () => {
    const fixture = filledAssessment();
    fixture.next_action = {
      ...fixture.next_action,
      disposition: "go_now",
      action: "ANSWER",
    };
    expect(
      assessmentIssues(fixture).some((issue) => issue.path === "next_action.action"),
    ).toBe(true);
  });

  it("requires an explicit gap when ideal and local actions differ", () => {
    const fixture = filledAssessment();
    fixture.next_action = {
      disposition: "go_now",
      action: "ESCALATE",
      ideal_action: "urgent facility",
      locally_executable_action: "demo facility list",
      resource_gap: null,
    };
    expect(
      assessmentIssues(fixture).some(
        (issue) => issue.path === "next_action.resource_gap",
      ),
    ).toBe(true);
    fixture.next_action.resource_gap = "capability data is demo only";
    expect(validateClinicalAssessment(fixture).next_action.disposition).toBe(
      "go_now" satisfies Disposition,
    );
  });
});

describe("contradictions", () => {
  it("stays unresolved and rejects any other resolution status", () => {
    const created = createContradiction({
      claim_a: "37.4 C",
      claim_b: "39.2 C",
      sources: ["evt-1", "evt-2"],
      clinical_importance: "high",
    });
    expect(created.resolution_status).toBe(RESOLUTION_STATUS_UNRESOLVED);
    expect(validateContradiction(created).resolution_status).toBe("unresolved");

    expect(() =>
      validateContradiction({ ...created, resolution_status: "resolved" }),
    ).toThrow(/unresolved/);
  });
});

describe("append-only events", () => {
  it("keeps both temperature readings and does not mutate the prior log", () => {
    const first = syntheticEvent({
      event_id: "evt-1",
      value: 37.4,
      timestamp: "2026-10-07T08:00:00Z",
    });
    const second = syntheticEvent({
      event_id: "evt-2",
      value: 39.2,
      timestamp: "2026-10-07T10:00:00Z",
    });
    const afterFirst = appendClinicalEvent([], first);
    const afterSecond = appendClinicalEvent(afterFirst, second);

    expect(afterFirst).toHaveLength(1);
    expect(afterSecond.map((event) => event.value)).toEqual([37.4, 39.2]);
    expect(eventsOfType(afterSecond, "temperature").map((event) => event.value)).toEqual([
      37.4,
      39.2,
    ]);
    expect(() => {
      (afterSecond as ClinicalEvent[]).push(syntheticEvent({ event_id: "evt-3" }));
    }).toThrow(TypeError);
    expect(() => {
      (afterSecond[0] as ClinicalEvent).value = 40;
    }).toThrow(TypeError);
  });

  it("rejects a repeated event id instead of overwriting", () => {
    const first = syntheticEvent({ event_id: "evt-1", value: 37.4 });
    const replacement = syntheticEvent({ event_id: "evt-1", value: 39.2 });
    const log = appendClinicalEvent([], first);
    expect(() => appendClinicalEvent(log, replacement)).toThrow(/append-only/);
    expect(log[0]?.value).toBe(37.4);
  });
});
