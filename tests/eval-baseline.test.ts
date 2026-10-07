import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { decide } from "../lib/assessment";
import {
  contentHash, evaluateSuite, fileHash, loadSuite, MEASURABLE_FAMILIES,
  type EvalCase, type Manifest, type MeasuredFamily, validateCase,
} from "../evals/runner";

const ROOT = resolve(import.meta.dirname, "..");
const EVALS = resolve(ROOT, "evals");
const BASELINE = resolve(EVALS, "reports/baseline-decide.json");
const suite = loadSuite(EVALS);
const tempPaths: string[] = [];

function measured(report: ReturnType<typeof evaluateSuite>, family: string): MeasuredFamily {
  const result = report.families[family];
  if (result.status !== "measured") throw new Error(`Missing measurable family ${family}`);
  return result;
}
function temporarySuite(change: (manifest: Manifest, cases: EvalCase[]) => void): string {
  const root = mkdtempSync(resolve(tmpdir(), "tunza-eval-"));
  tempPaths.push(root);
  const manifest = structuredClone(suite.manifest);
  const cases: EvalCase[] = JSON.parse(readFileSync(resolve(EVALS, "cases/engineering.json"), "utf8"));
  change(manifest, cases);
  mkdirSync(resolve(root, "cases"));
  writeFileSync(resolve(root, "manifest.json"), JSON.stringify(manifest));
  writeFileSync(resolve(root, "cases/engineering.json"), JSON.stringify(cases));
  return root;
}
afterEach(() => {
  for (const path of tempPaths.splice(0)) rmSync(path, { recursive: true, force: true });
});

describe("frozen decide engineering baseline", () => {
  it("matches the independently specified labels and frozen per-family observations", () => {
    const observation = evaluateSuite(suite, decide);
    // Explicit, one-time capture only. Normal npm test is read-only for reports.
    // wx refuses replacement even if capture is accidentally requested again.
    if (process.env.TUNZA_CAPTURE_BASELINE === "1") {
      mkdirSync(resolve(EVALS, "reports"), { recursive: true });
      writeFileSync(BASELINE, JSON.stringify({
        source: {
          git_commit: "2a1812d450c092d5e6c0e63f8c3dd8b28c1bf869",
          decider: "lib/assessment.ts#decide",
          decider_sha256: fileHash(resolve(ROOT, "lib/assessment.ts")),
          labels_source: "tests/assessment.test.ts plus explicit task invariants",
          existing_test_sha256: fileHash(resolve(ROOT, "tests/assessment.test.ts")),
          capture: "vitest one-time exclusive creation, before any decide behavior changes",
        },
        ...observation,
      }, null, 2) + "\n", { flag: "wx" });
    }
    const { source, ...baseline } = JSON.parse(readFileSync(BASELINE, "utf8"));
    expect(source.decider_sha256).toBe(fileHash(resolve(ROOT, "lib/assessment.ts")));
    expect(source.existing_test_sha256).toBe(fileHash(resolve(ROOT, "tests/assessment.test.ts")));
    expect(observation).toEqual(baseline);
    for (const family of MEASURABLE_FAMILIES) {
      const result = measured(observation, family);
      expect(result.denominator).toBe(3);
      expect(result.numerator).toBe(3);
    }
  });

  it("is deterministic and does not mutate fixtures", () => {
    const before = JSON.stringify(suite);
    expect(evaluateSuite(suite, decide)).toEqual(evaluateSuite(suite, decide));
    expect(JSON.stringify(suite)).toBe(before);
  });

  it("reports unavailable families explicitly without a numeric substitute", () => {
    const report = evaluateSuite(suite, decide);
    for (const family of ["clinical_correctness", "calibration", "retrieval", "multilingual_generation", "medication_safety"]) {
      expect(report.families[family]).toEqual({
        status: "not_measurable", reason: expect.any(String),
      });
    }
    expect(report.release_authorization).toBe("none");
    const inspect = (value: unknown) => {
      if (value && typeof value === "object") {
        for (const [key, child] of Object.entries(value)) {
          expect(key).not.toMatch(/^(score|accuracy|aggregate_score|aggregate_accuracy|overall)$/);
          inspect(child);
        }
      }
    };
    inspect(report);
  });

  it("detects an always-home decider rather than grading its own generated labels", () => {
    const report = evaluateSuite(suite, () => ({ kind: "monitor_at_home" }));
    for (const family of MEASURABLE_FAMILIES) {
      expect(measured(report, family).numerator).toBe(0);
    }
  });

  it("does not reward an always-urgent decider for incomplete-story ASK behavior", () => {
    const report = evaluateSuite(suite, () => ({ kind: "go_now" }));
    expect(measured(report, "abstention").numerator).toBe(0);
  });

  it("detects a downgrade in the second member even when the initial urgent result matches", () => {
    const pairs = { ...suite, cases: suite.cases.filter((item) => item.family === "non_downgrade") };
    const report = evaluateSuite(pairs, (answers) => ({
      kind: answers.mainProblem === "other" ? "monitor_at_home" : "go_now",
    }));
    const result = measured(report, "non_downgrade");
    expect(result.numerator).toBe(0);
    expect(result.cases.every((item) => item.observed === "go_now")).toBe(true);
  });

  it("marks absent case families not measurable instead of reporting a vacuous pass", () => {
    const report = evaluateSuite({ ...suite, cases: [] }, decide);
    for (const family of MEASURABLE_FAMILIES) {
      expect(report.families[family].status).toBe("not_measurable");
    }
  });

  it("hashes semantic JSON content independently of object-key ordering", () => {
    expect(contentHash({ b: 2, a: { y: 4, x: 3 } })).toBe(contentHash({ a: { x: 3, y: 4 }, b: 2 }));
    expect(contentHash({ a: 1 })).not.toBe(contentHash({ a: 2 }));
  });

  it("rejects altered content before running decide", () => {
    const root = temporarySuite((_manifest, cases) => { cases[0].input.presentation = "changed"; });
    expect(() => loadSuite(root)).toThrow("Hash mismatch");
  });

  it("rejects duplicate manifest entries", () => {
    const root = temporarySuite((manifest) => { manifest.cases.push(manifest.cases[0]); });
    expect(() => loadSuite(root)).toThrow("Duplicate manifest id");
  });

  it("rejects an empty manifest", () => {
    const root = temporarySuite((manifest) => { manifest.cases = []; });
    expect(() => loadSuite(root)).toThrow("Invalid or empty eval manifest");
  });

  it("rejects duplicate case bodies instead of choosing one arbitrarily", () => {
    const root = temporarySuite((_manifest, cases) => { cases.push(cases[0]); });
    expect(() => loadSuite(root)).toThrow("Missing or duplicate case");
  });

  it("rejects missing label provenance", () => {
    const root = temporarySuite((manifest) => { manifest.cases[0].provenance.label_source = ""; });
    expect(() => loadSuite(root)).toThrow("provenance");
  });

  it("rejects non-synthetic lineage", () => {
    const root = temporarySuite((manifest) => {
      Object.assign(manifest.cases[0], { lineage: "REAL_DEIDENTIFIED" });
    });
    expect(() => loadSuite(root)).toThrow("provenance");
  });

  it("rejects malformed or missing paired labels", () => {
    const item = structuredClone(suite.cases.find((entry) => entry.family === "non_downgrade")!);
    delete item.follow_up;
    expect(() => validateCase(item)).toThrow("independently labeled urgent pair");
    Object.assign(item.input, { breathing: "invented" });
    expect(() => validateCase(item)).toThrow("Invalid fixture input field");
  });
});
