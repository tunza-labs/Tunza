import { describe, expect, it } from "vitest";
import type { Decision } from "../lib/types";
import { isDisposition } from "../lib/clinical/contract";
import {
  UNAPPROVED_CLINICAL_RULES,
  ReconcileError,
  reconcile,
  reconcileWithTelemetry,
} from "../lib/clinical/reconcile";

const FLOOR: Decision = {
  kind: "go_now",
  reasonKeys: ["dangerNotWaking"],
  dangerSignKeys: ["dangerNotWaking"],
  watchSignKeys: [],
};

describe("safety-floor reconciler", () => {
  it("rewrites self-care against go_now and records the disagreement", () => {
    const result = reconcile({
      floor: FLOOR,
      candidate: { disposition: "self-care", model_id: "claude-sonnet-4-5" },
    });
    expect(result.disposition).toBe("go_now");
    expect(result.fail_open).toBe(false);
    expect(result.disagreement).toMatchObject({
      floor: "go_now",
      candidate: "self-care",
      reconciled: "go_now",
      rewritten_to_floor: true,
      reason: "candidate_below_floor",
      model_id: "claude-sonnet-4-5",
    });
    expect(isDisposition("self-care")).toBe(false);
  });

  it("rewrites monitor_at_home against go_now instead of merging silently", () => {
    const result = reconcile({
      floor: "go_now",
      candidate: { disposition: "monitor_at_home", model_id: null },
    });
    expect(result.disposition).toBe("go_now");
    expect(result.disagreement?.reason).toBe("candidate_below_floor");
  });

  it("does not apply an unapproved higher candidate", () => {
    expect(UNAPPROVED_CLINICAL_RULES).toBe("disabled");
    const result = reconcile({
      floor: "monitor_at_home",
      candidate: { disposition: "go_now", model_id: "candidate-model" },
    });
    expect(result.disposition).toBe("monitor_at_home");
    expect(result.disagreement?.reason).toBe("candidate_not_approved");
  });

  it("keeps the floor when the candidate is unrecognized", () => {
    const result = reconcile({
      floor: FLOOR,
      candidate: { disposition: "send-home", model_id: null },
    });
    expect(result.disposition).toBe("go_now");
    expect(result.disagreement?.reason).toBe("candidate_unrecognized");
  });

  it("does not fail open when telemetry throws", () => {
    const result = reconcileWithTelemetry(
      {
        floor: FLOOR,
        candidate: { disposition: "self-care", model_id: null },
      },
      () => {
        throw new Error("telemetry store unavailable");
      },
    );
    expect(result.disposition).toBe("go_now");
    expect(result.disagreement?.reconciled).toBe("go_now");
  });

  it("refuses an invalid floor instead of inventing monitor_at_home", () => {
    expect(() =>
      reconcile({
        floor: { ...FLOOR, kind: "self-care" as Decision["kind"] },
      }),
    ).toThrow(ReconcileError);
  });
});
