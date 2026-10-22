import { describe, expect, it } from "vitest";
import { decide, EMPTY_ANSWERS } from "../lib/assessment";
import {
  answeredCount,
  assessHousehold,
  canSendHandoff,
  dailySummary,
  demoAdvance,
  flushQueued,
  FOLLOW_UP_AFTER_MS,
  fromCarePath,
  handoffFor,
  householdLabel,
  householdReason,
  householdStatus,
  INTAKE_FIELDS,
  intakeStart,
  intakeValue,
  memberLabel,
  parseRoster,
  recordOutcome,
  rosterReducer,
  seedHouseholds,
  sendHandoff,
  setIntakeValue,
  SHARED_CASE_ID,
  sortHouseholds,
  STATUS_ORDER,
  statusCounts,
  type Household,
} from "../lib/chp";
import { t, type Locale } from "../lib/copy";
import { answerFacts, chpHandoffFacts, handoffFacts } from "../lib/handoff";
import { createReferral } from "../lib/referral";

const LOCALES: Locale[] = ["en", "sw"];
const calm = { offline: false, noFacilityResponse: false, weakConnection: false };
const offline = { ...calm, offline: true };

function byNumber(list: Household[], n: number): Household {
  const found = list.find((household) => household.number === n);
  if (!found) throw new Error(`no household ${n}`);
  return found;
}

function blank(number = 9): Household {
  return {
    id: `demo-hh-${number}`,
    number,
    member: "child",
    answers: null,
    decision: null,
    assessedAt: null,
    referral: null,
    followUpDueAt: null,
    demo: true,
  };
}

describe("demo roster", () => {
  const now = Date.now();
  const roster = seedHouseholds(now);

  it("is synthetic, numbered, and clearly demo", () => {
    expect(roster).toHaveLength(7);
    for (const household of roster) {
      expect(household.demo).toBe(true);
      expect(householdLabel(household, "en")).toMatch(/^Demo household \d+$/);
      expect(householdLabel(household, "sw")).toMatch(/^Kaya ya majaribio \d+$/);
    }
  });

  it("takes every decision from decide(), never a hand-written one", () => {
    for (const household of roster) {
      expect(household.answers).not.toBeNull();
      expect(household.decision).toEqual(decide(household.answers!));
    }
  });

  it("covers each status the CHP must recognise", () => {
    expect(householdStatus(byNumber(roster, 1), now)).toBe("attention");
    expect(householdStatus(byNumber(roster, 2), now)).toBe("referral");
    expect(householdStatus(byNumber(roster, 3), now)).toBe("referral");
    expect(householdStatus(byNumber(roster, 4), now)).toBe("followup");
    expect(householdStatus(byNumber(roster, 5), now)).toBe("followup");
    expect(householdStatus(byNumber(roster, 6), now)).toBe("stable");
    expect(householdStatus(byNumber(roster, 7), now)).toBe("stable");
  });

  it("counts statuses", () => {
    expect(statusCounts(roster, now)).toEqual({
      attention: 1,
      referral: 2,
      followup: 2,
      stable: 2,
    });
  });
});

describe("sortHouseholds", () => {
  it("puts the most urgent first and never lets a calmer status jump ahead", () => {
    const now = Date.now();
    const sorted = sortHouseholds(seedHouseholds(now), now);
    expect(sorted[0].number).toBe(1);
    const ranks = sorted.map((household) =>
      STATUS_ORDER.indexOf(householdStatus(household, now)),
    );
    expect(ranks).toEqual([...ranks].sort((a, b) => a - b));
  });

  it("orders Go now ahead of Get care today inside the same status", () => {
    const now = Date.now();
    const today = assessHousehold(
      blank(1),
      { ...EMPTY_ANSWERS, who: "child", awake: "alert", breathing: "difficult", drinking: "yes", mainProblem: "breathing" },
      now - 60_000,
    );
    const goNow = assessHousehold(
      blank(2),
      { ...EMPTY_ANSWERS, who: "child", awake: "not_waking" },
      now,
    );
    expect(today.decision?.kind).toBe("get_care_today");
    expect(goNow.decision?.kind).toBe("go_now");
    const sorted = sortHouseholds([today, goNow], now);
    expect(sorted.map((household) => household.number)).toEqual([2, 1]);
  });
});

describe("assessment and handoff", () => {
  it("monitor at home sets a follow-up 24 hours out, then becomes due", () => {
    const now = Date.now();
    const assessed = assessHousehold(
      blank(),
      {
        ...EMPTY_ANSWERS,
        who: "child",
        awake: "alert",
        breathing: "fine",
        drinking: "yes",
        duration: "today",
        mainProblem: "stomach",
      },
      now,
    );
    expect(assessed.decision?.kind).toBe("monitor_at_home");
    expect(Date.parse(assessed.followUpDueAt!)).toBe(now + FOLLOW_UP_AFTER_MS);
    expect(householdStatus(assessed, now)).toBe("stable");
    expect(householdStatus(assessed, now + FOLLOW_UP_AFTER_MS)).toBe("followup");
  });

  it("an unvisited household is due a visit; an incomplete one needs attention", () => {
    const now = Date.now();
    expect(householdStatus(blank(), now)).toBe("followup");
    expect(householdReason(blank(), now, "en")).toBe(t("chpReasonNotVisited", "en"));
    const incomplete = assessHousehold(
      blank(),
      { ...EMPTY_ANSWERS, who: "child", awake: "unknown", breathing: "unknown", drinking: "unknown", mainProblem: "other" },
      now,
    );
    expect(incomplete.decision?.kind).toBe("need_one_more_answer");
    expect(householdStatus(incomplete, now)).toBe("attention");
    expect(canSendHandoff(incomplete)).toBe(false);
  });

  it("queues the handoff offline and says so", () => {
    const now = Date.now() - 1000;
    const urgent = byNumber(seedHouseholds(now), 1);
    expect(canSendHandoff(urgent)).toBe(true);
    const queued = sendHandoff(urgent, offline);
    expect(queued.referral?.queued).toBe(true);
    expect(queued.referral?.stage).toBe("created");
    expect(handoffFor(queued)).toBe("queued");
    expect(householdStatus(queued, now)).toBe("attention");
    for (const locale of LOCALES) {
      expect(householdReason(queued, now, locale)).toBe(t("chpQueuedNotice", locale));
    }
    expect(t("chpQueuedNotice", "en")).toBe("Queued, will send when online");
  });

  it("sends everything queued once back online, and nothing while offline", () => {
    const now = Date.now() - 1000;
    const roster = seedHouseholds(now);
    const queued = roster.map((household) =>
      household.number === 1 ? sendHandoff(household, offline) : household,
    );
    expect(flushQueued(queued, offline)).toBe(queued);
    const sent = flushQueued(queued, calm);
    const one = byNumber(sent, 1);
    expect(one.referral?.queued).toBe(false);
    expect(one.referral?.stage).toBe("sent");
    expect(handoffFor(one)).toBe("sent");
    expect(householdStatus(one, now)).toBe("referral");
    expect(canSendHandoff(one)).toBe(false);
  });

  it("does not send a handoff for monitor at home", () => {
    const now = Date.now();
    expect(canSendHandoff(byNumber(seedHouseholds(now), 6))).toBe(false);
    const six = byNumber(seedHouseholds(now), 6);
    expect(sendHandoff(six, calm)).toBe(six);
  });
});

describe("closing the loop", () => {
  it("asks for the outcome only once the visit is finished", () => {
    const now = Date.now();
    const roster = seedHouseholds(now);
    const accepted = byNumber(roster, 3);
    expect(recordOutcome(accepted, "treated", now)).toBe(accepted);

    const completed = byNumber(roster, 4);
    expect(completed.referral?.stage).toBe("completed");
    expect(householdReason(completed, now, "en")).toBe(t("chpReasonRecordOutcome", "en"));
    const closed = recordOutcome(completed, "referred_onward", now);
    expect(closed.referral?.stage).toBe("outcome_returned");
    expect(closed.referral?.outcome).toBe("referred_onward");
    expect(closed.referral?.history.at(-1)?.by).toBe("chp");
    expect(householdStatus(closed, now)).toBe("followup");

    const well = rosterReducer([closed], { type: "clearFollowUp", id: closed.id })[0];
    expect(householdStatus(well, now)).toBe("stable");
  });

  it("demo advance stands in for the facility one step at a time", () => {
    const now = Date.now();
    let household = byNumber(seedHouseholds(now), 2);
    const seen: string[] = [household.referral!.stage];
    for (let i = 0; i < 10; i += 1) {
      household = demoAdvance(household);
      seen.push(household.referral!.stage);
    }
    expect(seen.slice(0, 7)).toEqual([
      "sent",
      "received",
      "accepted",
      "patient_moving",
      "arrived",
      "seen",
      "completed",
    ]);
    expect(seen.at(-1)).toBe("completed");
  });

  it("the CHP can confirm the family has left", () => {
    const now = Date.now();
    const roster = seedHouseholds(now);
    const next = rosterReducer(roster, { type: "confirmTravel", id: "demo-hh-3" });
    expect(byNumber(next, 3).referral?.stage).toBe("patient_moving");
  });
});

describe("daily summary", () => {
  it("counts today's work and returns numbers only", () => {
    const now = Date.now();
    const roster = seedHouseholds(now);
    const summary = dailySummary(roster, now);
    expect(Object.keys(summary).sort()).toEqual(["followUps", "referred", "seen"]);
    for (const value of Object.values(summary)) {
      expect(typeof value).toBe("number");
    }
    expect(summary.followUps).toBe(statusCounts(roster, now).followup);
    const text = JSON.stringify(summary);
    for (const household of roster) {
      expect(text).not.toContain(householdLabel(household, "en"));
      expect(text).not.toContain(household.id);
    }
  });

  it("counts nothing for another day", () => {
    const now = Date.now();
    const roster = seedHouseholds(now);
    const later = now + 5 * 24 * 60 * 60 * 1000;
    const summary = dailySummary(roster, later);
    expect(summary.seen).toBe(0);
    expect(summary.referred).toBe(0);
  });
});

describe("intake helpers", () => {
  it("has the six structured fields", () => {
    expect([...INTAKE_FIELDS]).toEqual([
      "who",
      "awake",
      "breathing",
      "drinking",
      "duration",
      "main_problem",
    ]);
  });

  it("reads and writes each field and counts answers", () => {
    let answers = intakeStart(blank());
    expect(intakeValue(answers, "who")).toBe("child");
    expect(answeredCount(answers)).toBe(1);
    answers = setIntakeValue(answers, "main_problem", "fever");
    expect(answers.mainProblem).toBe("fever");
    answers = setIntakeValue(answers, "breathing", "unknown");
    expect(answeredCount(answers)).toBe(3);
  });

  it("labels members without names", () => {
    for (const locale of LOCALES) {
      expect(memberLabel("child", locale)).toBe(t("whoChild", locale));
      expect(memberLabel("household_adult", locale)).toBe(t("chpMemberAdult", locale));
    }
  });
});

describe("parseRoster", () => {
  it("falls back to fresh demo seeds on missing or malformed storage", () => {
    const now = Date.now();
    expect(parseRoster(null, now)).toHaveLength(7);
    expect(parseRoster("{not json", now)).toHaveLength(7);
    expect(parseRoster(JSON.stringify([{ id: "x", name: "real" }]), now)).toHaveLength(7);
  });

  it("keeps a stored demo roster", () => {
    const now = Date.now();
    const stored = seedHouseholds(now).slice(0, 2);
    expect(parseRoster(JSON.stringify(stored), now)).toEqual(stored);
  });
});

describe("shared care path row", () => {
  it("maps the live demo case and stays out when there is no referral", () => {
    expect(fromCarePath(null, null)).toBeNull();
    const answers = { ...EMPTY_ANSWERS, who: "child" as const, awake: "not_waking" as const };
    const encounter = {
      id: "enc",
      answers,
      asked: [],
      currentQuestion: null,
      decision: decide(answers),
      startedBy: "household" as const,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    expect(fromCarePath(encounter, null)).toBeNull();
    const referral = createReferral({ encounterId: "enc", urgent: true, by: "household" });
    const row = fromCarePath(encounter, referral)!;
    expect(row.id).toBe(SHARED_CASE_ID);
    expect(householdLabel(row, "en")).toBe(t("chpSharedCase", "en"));
    expect(householdStatus(row, Date.now())).toBe("attention");
  });
});

describe("CHP handoff facts", () => {
  it.each(LOCALES)("carries main problem and danger signs, and no demo temperature (%s)", (locale) => {
    const answers = { ...EMPTY_ANSWERS, who: "child" as const, awake: "not_waking" as const, mainProblem: "fever" as const };
    const facts = chpHandoffFacts(answers, decide(answers), locale);
    const labels = facts.map((fact) => fact.label);
    expect(labels).not.toContain(t("handoffTemp", locale));
    expect(labels).toContain(t("handoffMainProblem", locale));
    const danger = facts.find((fact) => fact.label === t("handoffDangerSigns", locale));
    expect(danger?.value).toBe(t("dangerNotWaking", locale));
    expect(facts.find((fact) => fact.label === t("handoffMainProblem", locale))?.value).toBe(
      t("mainFever", locale),
    );
  });

  it("says none found when decide() found no danger sign", () => {
    const answers = { ...EMPTY_ANSWERS, who: "household_adult" as const, awake: "alert" as const, breathing: "fine" as const, drinking: "yes" as const, mainProblem: "other" as const };
    const facts = chpHandoffFacts(answers, decide(answers), "en");
    expect(facts.at(-1)?.value).toBe(t("handoffNoDangerSigns", "en"));
  });

  it("leaves the existing handoff unchanged: answer facts plus the demo temperature", () => {
    const answers = { ...EMPTY_ANSWERS, who: "child" as const };
    const full = handoffFacts(answers, false, new Date().toISOString(), "en");
    expect(full.slice(0, -1)).toEqual(answerFacts(answers, "en"));
    expect(full.at(-1)?.label).toBe(t("handoffTemp", "en"));
  });
});
