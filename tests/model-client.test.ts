import { describe, expect, it } from "vitest";
import { fetchCandidate } from "../lib/clinical/model-client";
import { reconcile } from "../lib/clinical/reconcile";

const intake = { who: "child", presentation: "fever" };
const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("model candidate client", () => {
  it("returns null when no server is configured", async () => {
    expect(await fetchCandidate(intake, {})).toBeNull();
    expect(await fetchCandidate(intake, { baseUrl: "  " })).toBeNull();
  });

  it("returns the model's own answer as a candidate", async () => {
    const c = await fetchCandidate(intake, {
      baseUrl: "http://m:1/",
      modelId: "lora-test",
      fetchImpl: () =>
        json({ final: { disposition: "go_now" }, model_answer: { disposition: "get_care_today" } }),
    });
    expect(c).toEqual({ disposition: "get_care_today", model_id: "lora-test" });
  });

  it("returns null on fallback, bad status, junk, unknown labels and errors", async () => {
    const cases: Array<() => Promise<Response>> = [
      () => json({ final: { disposition: "go_now" }, model_answer: null, source: "fallback" }),
      () => json({}, 500),
      () => Promise.resolve(new Response("not json")),
      () => json({ model_answer: { disposition: "ignore_all_rules" } }),
      () => Promise.reject(new Error("down")),
    ];
    for (const fetchImpl of cases) {
      expect(await fetchCandidate(intake, { baseUrl: "http://m:1", fetchImpl })).toBeNull();
    }
  });

  it("gives up after the timeout", async () => {
    const hang: typeof fetch = (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      });
    expect(
      await fetchCandidate(intake, { baseUrl: "http://m:1", timeoutMs: 20, fetchImpl: hang }),
    ).toBeNull();
  });

  it("can never lower or replace the floor, even for a candidate the model likes", () => {
    for (const candidate of ["monitor_at_home", "get_care_today", "go_now"]) {
      const r = reconcile({ floor: "go_now", candidate: { disposition: candidate, model_id: "m" } });
      expect(r.disposition).toBe("go_now");
    }
    const higher = reconcile({
      floor: "monitor_at_home",
      candidate: { disposition: "go_now", model_id: "m" },
    });
    expect(higher.disposition).toBe("monitor_at_home");
    expect(higher.disagreement?.reason).toBe("candidate_not_approved");
  });
});
