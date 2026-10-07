import { describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { decide } from "../lib/assessment";
import {
  assertNoReleaseAuthorization,
  compareChampionChallenger,
  distributionFromKinds,
  evaluateReleaseGate,
  loadAdversarialCatalog,
  loadAdversarialSuite,
  observeAdversarial,
} from "../evals/gates";
import { LABEL_AUTHORSHIP_CHOICE, loadSuite } from "../evals/runner";

const ROOT = resolve(import.meta.dirname, "..");
const EVALS = resolve(ROOT, "evals");

describe("adversarial fixtures and release gates", () => {
  it("loads the adversarial suite with the same manifest contract", () => {
    const suite = loadAdversarialSuite(EVALS);
    expect(suite.manifest.purpose).toBe("engineering_fixtures_only");
    expect(suite.manifest.label_authorship_decision.choice).toBe(LABEL_AUTHORSHIP_CHOICE);
    expect(suite.cases.length).toBeGreaterThan(0);
    expect(suite.cases.every((item) => item.lineage === "SYNTHETIC")).toBe(true);
    expect(suite.cases.every((item) => item.expected === "go_now")).toBe(true);
  });

  it("keeps injection strings inert and does not derive labels from decide()", () => {
    const catalog = loadAdversarialCatalog(EVALS);
    const gatesSource = readFileSync(resolve(EVALS, "gates.ts"), "utf8");
    expect(gatesSource).not.toMatch(/\beval\s*\(/);
    expect(gatesSource).not.toMatch(/new Function/);
    expect(catalog.training_set).toBe(false);
    expect(catalog.entries.some((entry) => entry.class === "injection_inert")).toBe(true);
    expect(catalog.entries.every((entry) => entry.execution === "inert_data_not_executed")).toBe(true);
    const observations = observeAdversarial(catalog.entries, decide);
    const injection = observations.find((item) => item.id === "injection-inert-unconscious");
    expect(injection?.executed).toBe(false);
    expect(injection?.observed).toBe("go_now");
    expect(observations.filter((item) => item.expected === null).every((item) => item.matched === null)).toBe(true);
  });

  it("records paraphrase and misspelling observations without treating them as a ship gate", () => {
    const catalog = loadAdversarialCatalog(EVALS);
    const observations = observeAdversarial(catalog.entries, decide);
    const paraphrase = observations.find((item) => item.id === "paraphrase-passed-out-en");
    const misspelling = observations.find((item) => item.id === "sw-misspelling-degedege");
    expect(paraphrase?.expected).toBe("go_now");
    expect(misspelling?.expected).toBe("go_now");
    expect(paraphrase?.matched).toBe(false);
    expect(misspelling?.matched).toBe(false);
  });

  it("blocks promotion when the clinical threshold is unsigned or a metric is missing", () => {
    const baseline = JSON.parse(
      readFileSync(resolve(EVALS, "reports/baseline-decide.json"), "utf8"),
    );
    const distribution = distributionFromKinds(
      loadSuite(EVALS).cases.map((item) => item.expected),
    );
    expect(distribution).toEqual({
      ANSWER: 0,
      ASK: 3,
      ABSTAIN: 0,
      ESCALATE: 6,
    });
    const unsigned = evaluateReleaseGate({
      baseline: baseline.families,
      challenger: baseline.families,
      distribution,
      clinical_thresholds_signed: false,
    });
    assertNoReleaseAuthorization(unsigned);
    expect(unsigned.block_reasons).toContain("unsigned_clinical_threshold");
    expect(unsigned.block_reasons).toContain("missing_metric");
    expect(unsigned.rows.find((row) => row.id === "red_flag_recall_gte_baseline")?.status).toBe("pass");

    const signedStillBlocked = evaluateReleaseGate({
      baseline: baseline.families,
      challenger: baseline.families,
      distribution,
      clinical_thresholds_signed: true,
    });
    expect(signedStillBlocked.promotion).toBe("blocked");
    expect(signedStillBlocked.release_authorization).toBe("none");
    expect(signedStillBlocked.block_reasons).toContain("missing_metric");
  });

  it("fails closed on recall regression and missing distribution", () => {
    const baseline = JSON.parse(
      readFileSync(resolve(EVALS, "reports/baseline-decide.json"), "utf8"),
    );
    const regressed = structuredClone(baseline.families);
    regressed.red_flag_recall.value = 0;
    regressed.red_flag_recall.numerator = 0;
    regressed.red_flag_recall.cases = regressed.red_flag_recall.cases.map(
      (item: { matched: boolean }) => ({ ...item, matched: false }),
    );
    const decision = evaluateReleaseGate({
      baseline: baseline.families,
      challenger: regressed,
      distribution: { ANSWER: 0, ASK: 0, ESCALATE: 1 },
      clinical_thresholds_signed: false,
    });
    expect(decision.promotion).toBe("blocked");
    expect(decision.rows.find((row) => row.id === "red_flag_recall_gte_baseline")?.status).toBe("fail");
    expect(decision.rows.find((row) => row.id === "disposition_distribution_reported")?.status).toBe("blocked");
  });

  it("compares champion and challenger on identical inputs and still blocks promotion", () => {
    const inputs = loadSuite(EVALS).cases;
    const comparison = compareChampionChallenger(
      inputs,
      (item) => item.expected,
      (item) => decide({ ...{
        who: null, presentation: "", photoAttached: false, awake: null,
        breathing: null, drinking: null, duration: null, mainProblem: null,
      }, ...item.input }).kind,
    );
    expect(comparison.input_identity).toBe("identical_frozen_inputs");
    expect(comparison.input_count).toBe(inputs.length);
    expect(comparison.promotion).toBe("blocked");
    expect(comparison.release_authorization).toBe("none");
    expect(comparison.agreement_count).toBe(inputs.length);
  });

  it("rejects a manifest that drops the unverified-authorship decision", () => {
    const suite = loadSuite(EVALS);
    const root = mkdtempSync(resolve(tmpdir(), "tunza-authorship-"));
    try {
      mkdirSync(resolve(root, "cases"));
      const manifest = structuredClone(suite.manifest);
      delete (manifest as { label_authorship_decision?: unknown }).label_authorship_decision;
      writeFileSync(resolve(root, "manifest.json"), JSON.stringify(manifest));
      writeFileSync(
        resolve(root, "cases/engineering.json"),
        readFileSync(resolve(EVALS, "cases/engineering.json")),
      );
      expect(() => loadSuite(root)).toThrow(/unverified-authorship/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
