import { describe, expect, it } from "vitest";
import { decide } from "../lib/assessment";
import { SECTION_KEYS, headlineKeyFor } from "../lib/clinical/contract";
import { t, type Locale } from "../lib/copy";
import {
  arrivedAt,
  askedOfFacility,
  caseSummary,
  deskCases,
  deskRow,
  formatAge,
  formatSex,
  formatWaited,
  INBOX_ORDER,
  reviewCase,
  seedDemoCases,
  sortDeskCases,
  timeline,
  type DeskCase,
} from "../lib/desk";
import { applyReferralAction, createReferral } from "../lib/referral";
import { careReducer, initialCareState } from "../lib/store";
import type { CareState, DecisionKind } from "../lib/types";

const ANCHOR = "2026-10-22T12:00:00.000Z";
const NOW = Date.parse(ANCHOR);
const LOCALES: Locale[] = ["en", "sw"];

function demoState(overrides: Partial<CareState> = {}): CareState {
  return {
    ...initialCareState,
    role: "facility",
    grants: { chp: false, facility: true },
    demoCases: seedDemoCases(ANCHOR),
    ...overrides,
  };
}

function caseById(state: CareState, id: string): DeskCase {
  const found = deskCases(state).find((item) => item.id === id);
  if (!found) throw new Error(`no case ${id}`);
  return found;
}

describe("synthetic demo referrals", () => {
  it("are labelled synthetic, use demo ids, and land at the demo desk", () => {
    const cases = deskCases(demoState());
    expect(cases).toHaveLength(5);
    for (const item of cases) {
      expect(item.source).toBe("synthetic");
      expect(item.id).toMatch(/^demo-ref-/);
      expect(item.referral.facilityId).toBe("north-demo");
    }
  });

  it("get their answer from decide(), never a stored field", () => {
    const kinds = Object.fromEntries(
      deskCases(demoState()).map((item) => [item.id, decide(item.encounter.answers).kind]),
    );
    expect(kinds).toEqual({
      "demo-ref-a": "go_now",
      "demo-ref-b": "get_care_today",
      "demo-ref-c": "go_now",
      "demo-ref-d": "get_care_today",
      "demo-ref-e": "get_care_today",
    });
  });

  it("only shows the session referral once it has been sent", () => {
    const created = createReferral({ encounterId: "enc-live", urgent: true, by: "chp" });
    const state = demoState({
      encounter: { ...initialCareState.encounter!, id: "enc-live" },
      referral: created,
    });
    expect(deskCases(state).some((item) => item.source === "session")).toBe(false);
    const sent = applyReferralAction(created, "send", "chp", {
      offline: false,
      noFacilityResponse: false,
      weakConnection: false,
    });
    const withSent = deskCases({ ...state, referral: sent });
    expect(withSent[0].source).toBe("session");
    expect(withSent[0].ageMonths).toBeNull();
  });
});

describe("inbox order", () => {
  it("sorts by urgency, then longest waiting, open cases at this desk first", () => {
    const state = demoState();
    const order = sortDeskCases(deskCases(state), "north-demo").map((item) => item.id);
    expect(order).toEqual([
      "demo-ref-c", // go_now, sent 90 min ago
      "demo-ref-a", // go_now, sent 12 min ago
      "demo-ref-d", // get_care_today, sent 200 min ago
      "demo-ref-e", // get_care_today, sent 55 min ago
      "demo-ref-b", // get_care_today, sent 40 min ago
    ]);
  });

  it("drops closed cases and cases now at another facility below open ones", () => {
    let state = demoState();
    state = careReducer(state, { type: "deskAction", referralId: "demo-ref-c", action: "arrive" });
    state = careReducer(state, { type: "deskAction", referralId: "demo-ref-a", action: "redirect" });
    state = careReducer(state, {
      type: "deskAction",
      referralId: "demo-ref-d",
      action: "return_outcome",
      outcome: "treated",
    });
    const order = sortDeskCases(deskCases(state), "north-demo").map((item) => item.id);
    expect(order).toEqual(["demo-ref-c", "demo-ref-e", "demo-ref-b", "demo-ref-a", "demo-ref-d"]);
  });

  it("keeps the display order an ordering only, covering every decision kind", () => {
    const kinds: DecisionKind[] = [
      "go_now",
      "get_care_today",
      "need_one_more_answer",
      "monitor_at_home",
    ];
    expect(kinds.map((kind) => INBOX_ORDER[kind])).toEqual([0, 1, 2, 3]);
  });

  it("reads arrival from the first send", () => {
    const item = caseById(demoState(), "demo-ref-b");
    expect(arrivedAt(item.referral)).toBe(new Date(NOW - 40 * 60_000).toISOString());
  });
});

describe("inbox rows", () => {
  it.each(LOCALES)("show age, sex, answer, top danger sign and stage (%s)", (locale) => {
    const state = demoState();
    const row = deskRow(caseById(state, "demo-ref-a"), "north-demo", {}, locale, NOW);
    expect(row.patientLabel).toBe(
      [t("deskWhoChild", locale), formatAge(36, locale), t("sexFemale", locale)].join(" · "),
    );
    expect(row.answerLabel).toBe(t("goNow", locale));
    expect(row.topDanger).toBe(t("dangerStrugglingBreathe", locale));
    expect(row.stageLabel).toBe(t("stageSent", locale));
    expect(row.sourceLabel).toBe(t("deskSourceSynthetic", locale));
    expect(row.canAccept).toBe(true);
    expect(row.canRedirect).toBe(true);
    expect(row.redirectTo).toBe("West Demo Sub-County Hospital");
  });

  it("leaves age and sex out when they were not recorded", () => {
    const row = deskRow(caseById(demoState(), "demo-ref-e"), "north-demo", {}, "en", NOW);
    expect(row.patientLabel).toBe("Adult");
    expect(row.topDanger).toBeNull();
  });

  it("blocks redirect and cannot take when no other facility is open", () => {
    const row = deskRow(
      caseById(demoState(), "demo-ref-a"),
      "north-demo",
      { "west-demo": "closed" },
      "en",
      NOW,
    );
    expect(row.canRedirect).toBe(false);
    expect(row.redirectBlocked).toBe(true);
    expect(row.canAccept).toBe(true);
  });

  it("offers no actions on a case that is now at another facility", () => {
    const row = deskRow(caseById(demoState(), "demo-ref-a"), "west-demo", {}, "en", NOW);
    expect(row.atDesk).toBe(false);
    expect(row.canAccept).toBe(false);
    expect(row.canRedirect).toBe(false);
    expect(row.redirectBlocked).toBe(false);
  });

  it.each(LOCALES)("summarise in one line without the free-text story (%s)", (locale) => {
    for (const item of deskCases(demoState())) {
      const row = deskRow(item, "north-demo", {}, locale, NOW);
      const summary = caseSummary(row, locale);
      expect(summary).toContain(row.answerLabel);
      expect(summary).toContain(row.stageLabel);
      expect(summary).not.toContain("\n");
      const story = item.encounter.answers.presentation;
      expect(summary).not.toContain(story);
    }
  });
});

describe("formatting", () => {
  it.each(LOCALES)("formats age, sex and waiting time (%s)", (locale) => {
    expect(formatAge(9, locale)).toContain("9");
    expect(formatAge(36, locale)).toContain("3");
    expect(formatAge(null, locale)).toBeNull();
    expect(formatSex("male", locale)).toBe(t("sexMale", locale));
    expect(formatSex(null, locale)).toBeNull();
    const since = new Date(NOW - 75 * 60_000).toISOString();
    expect(formatWaited(since, NOW, locale)).toContain("15");
    expect(formatWaited(new Date(NOW - 5 * 60_000).toISOString(), NOW, locale)).toContain("5");
  });

  it.each(LOCALES)("states what was asked of the facility for every answer (%s)", (locale) => {
    const lines = (
      ["go_now", "get_care_today", "need_one_more_answer", "monitor_at_home"] as DecisionKind[]
    ).map((kind) => askedOfFacility(kind, locale));
    expect(new Set(lines).size).toBe(4);
    for (const line of lines) expect(line.trim()).not.toBe("");
  });
});

describe("timeline", () => {
  it.each(LOCALES)("names every stage in words and marks cannot take (%s)", (locale) => {
    const state = careReducer(demoState(), {
      type: "deskAction",
      referralId: "demo-ref-b",
      action: "decline",
    });
    const entries = timeline(caseById(state, "demo-ref-b").referral, locale);
    expect(entries.map((entry) => entry.stageLabel)).toEqual([
      t("stageCreated", locale),
      t("stageSent", locale),
      t("stageReceived", locale),
      t("stageSent", locale),
    ]);
    expect(entries.every((entry) => !entry.stageLabel.includes("_"))).toBe(true);
    expect(entries[3].note).toContain("West Demo Sub-County Hospital");
    expect(entries[3].note).toContain(t("deskTimelineCannotTakeTpl", locale).split("{f}")[0]);
  });
});

describe("shadow candidate review", () => {
  it("never changes the displayed answer", () => {
    for (const item of deskCases(demoState())) {
      const review = reviewCase(item, "en");
      const floor = decide(item.encounter.answers).kind;
      expect(review.rulesKind).toBe(floor);
      expect(review.rendered?.headlineKey).toBe(headlineKeyFor(floor));
      const nextAction = review.rendered?.sections.find((s) => s.key === "next_action");
      expect((nextAction?.body as { disposition: string }).disposition).toBe(floor);
      if (review.record) {
        expect(review.record.reconciled).toBe(floor);
        expect(review.record.rewritten_to_floor).toBe(true);
      }
    }
  });

  it("reads the candidate from the reconcile disagreement record", () => {
    const state = demoState();
    const lower = reviewCase(caseById(state, "demo-ref-a"), "en");
    expect(lower.record?.candidate).toBe("get_care_today");
    expect(lower.record?.reason).toBe("candidate_below_floor");

    const higher = reviewCase(caseById(state, "demo-ref-b"), "en");
    expect(higher.record?.candidate).toBe("go_now");
    expect(higher.record?.reason).toBe("candidate_not_approved");
    expect(higher.rulesKind).toBe("get_care_today");

    const none = reviewCase(caseById(state, "demo-ref-c"), "en");
    expect(none.candidatePresent).toBe(false);
    expect(none.record).toBeNull();
  });

  it("renders all ten contract sections in both languages", () => {
    const item = caseById(demoState(), "demo-ref-a");
    for (const locale of LOCALES) {
      const review = reviewCase(item, locale);
      expect(review.rendered?.sections.map((section) => section.key)).toEqual([...SECTION_KEYS]);
    }
  });
});

describe("desk reducer actions", () => {
  it("moves a synthetic case and leaves the session referral alone", () => {
    const state = careReducer(demoState(), {
      type: "deskAction",
      referralId: "demo-ref-a",
      action: "accept",
    });
    expect(caseById(state, "demo-ref-a").referral.stage).toBe("accepted");
    expect(state.referral).toBeNull();
  });

  it("routes the session referral through the same action path", () => {
    const created = createReferral({ encounterId: "enc-live", urgent: true, by: "chp" });
    const sent = applyReferralAction(created, "send", "chp", {
      offline: false,
      noFacilityResponse: false,
      weakConnection: false,
    });
    const state = careReducer(demoState({ referral: sent }), {
      type: "deskAction",
      referralId: sent.id,
      action: "accept",
    });
    expect(state.referral?.stage).toBe("accepted");
    expect(caseById(state, "demo-ref-a").referral.stage).toBe("sent");
  });

  it("cannot take uses the redirect logic and records the reason", () => {
    const state = careReducer(demoState(), {
      type: "deskAction",
      referralId: "demo-ref-a",
      action: "decline",
    });
    const referral = caseById(state, "demo-ref-a").referral;
    expect(referral.facilityId).toBe("west-demo");
    expect(referral.failure).toBe("redirected");
    expect(referral.history.at(-1)?.reason).toBe("cannot_take");
  });

  it("the redirect reads capacity and keeps the referral when nothing is open", () => {
    const closed = careReducer(demoState(), {
      type: "setCapacity",
      facilityId: "west-demo",
      capacity: "closed",
    });
    expect(closed.facilityCapacity["west-demo"]).toBe("closed");
    const after = careReducer(closed, {
      type: "deskAction",
      referralId: "demo-ref-a",
      action: "redirect",
    });
    expect(after).toBe(closed);
  });

  it("returns an outcome code on a completed case", () => {
    const state = careReducer(demoState(), {
      type: "deskAction",
      referralId: "demo-ref-d",
      action: "return_outcome",
      outcome: "referred_onward",
    });
    const referral = caseById(state, "demo-ref-d").referral;
    expect(referral.stage).toBe("outcome_returned");
    expect(referral.outcome).toBe("referred_onward");
  });

  it("switches the desk facility and reseeds demo cases on start over", () => {
    let state = careReducer(demoState(), { type: "setDeskFacility", facilityId: "west-demo" });
    expect(state.deskFacilityId).toBe("west-demo");
    state = careReducer(state, { type: "deskAction", referralId: "demo-ref-a", action: "accept" });
    state = careReducer(state, { type: "reset" });
    expect(state.demoCases).toHaveLength(5);
    expect(caseById(state, "demo-ref-a").referral.stage).toBe("sent");
    expect(state.deskFacilityId).toBe("north-demo");
    expect(state.facilityCapacity).toEqual({});
  });
});
