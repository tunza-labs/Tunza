import { decide, decisionHeadline, EMPTY_ANSWERS } from "./assessment";
import { fill, t, type CopyKey, type Locale } from "./copy";
import {
  applyReferralAction,
  canPerform,
  createReferral,
  describeReferral,
  type ReferralAction,
} from "./referral";
import type {
  AssessmentAnswers,
  Decision,
  Encounter,
  OutcomeCode,
  PersonKind,
  Referral,
} from "./types";

/**
 * The CHP work list. Pure functions over a synthetic, clearly labelled demo
 * roster: no real households, no names, nothing sent anywhere. The clinical
 * answer always comes from decide() in lib/assessment.ts; this module only
 * orders, labels, and moves the referral through the shared lifecycle.
 */

export type Household = {
  id: string;
  /** Display number only: households are "Demo household 3", never a name. */
  number: number;
  member: PersonKind;
  answers: AssessmentAnswers | null;
  decision: Decision | null;
  assessedAt: string | null;
  referral: Referral | null;
  followUpDueAt: string | null;
  demo: true;
};

export type HouseholdStatus = "attention" | "referral" | "followup" | "stable";

export const STATUS_ORDER: HouseholdStatus[] = [
  "attention",
  "referral",
  "followup",
  "stable",
];

export const STATUS_LABEL_KEY: Record<HouseholdStatus, CopyKey> = {
  attention: "chpStatusAttention",
  referral: "chpStatusReferral",
  followup: "chpStatusFollowUp",
  stable: "chpStatusStable",
};

/** Conditions that change how a send behaves, read from the shared store. */
export type SendConditions = {
  offline: boolean;
  noFacilityResponse: boolean;
  weakConnection: boolean;
};

const HOUR = 60 * 60 * 1000;
export const FOLLOW_UP_AFTER_MS = 24 * HOUR;

/** The six structured intake fields, in the order the CHP sees them. */
export const INTAKE_FIELDS = [
  "who",
  "awake",
  "breathing",
  "drinking",
  "duration",
  "main_problem",
] as const;

export type IntakeField = (typeof INTAKE_FIELDS)[number];

const ANSWER_KEY: Record<IntakeField, keyof AssessmentAnswers> = {
  who: "who",
  awake: "awake",
  breathing: "breathing",
  drinking: "drinking",
  duration: "duration",
  main_problem: "mainProblem",
};

export function intakeValue(
  answers: AssessmentAnswers,
  field: IntakeField,
): string | null {
  return answers[ANSWER_KEY[field]] as string | null;
}

export function setIntakeValue(
  answers: AssessmentAnswers,
  field: IntakeField,
  value: string,
): AssessmentAnswers {
  return { ...answers, [ANSWER_KEY[field]]: value };
}

export function answeredCount(answers: AssessmentAnswers): number {
  return INTAKE_FIELDS.filter((field) => intakeValue(answers, field) !== null)
    .length;
}

export function intakeStart(household: Household): AssessmentAnswers {
  return {
    ...EMPTY_ANSWERS,
    who: household.member === "unknown" ? null : household.member,
  };
}

function isActive(referral: Referral | null): referral is Referral {
  return !!referral && referral.stage !== "outcome_returned";
}

/** A decision the CHP has not acted on yet: assessed after the last referral. */
function decisionPending(household: Household): boolean {
  if (!household.decision || !household.assessedAt) {
    return false;
  }
  const referral = household.referral;
  if (!referral) {
    return true;
  }
  return Date.parse(household.assessedAt) > Date.parse(referral.createdAt);
}

export function householdStatus(
  household: Household,
  now: number,
): HouseholdStatus {
  const referral = household.referral;
  if (isActive(referral)) {
    if (
      referral.queued ||
      referral.failure === "offline" ||
      referral.failure === "no_facility_response" ||
      referral.stage === "created"
    ) {
      return "attention";
    }
    if (referral.stage === "completed") {
      return "followup";
    }
    return "referral";
  }
  const kind = household.decision?.kind;
  if (
    decisionPending(household) &&
    (kind === "go_now" || kind === "get_care_today" || kind === "need_one_more_answer")
  ) {
    return "attention";
  }
  if (!household.decision) {
    return "followup";
  }
  if (household.followUpDueAt && Date.parse(household.followUpDueAt) <= now) {
    return "followup";
  }
  return "stable";
}

/** Lower is more urgent: Go now before Get care today before anything else. */
function urgencyRank(household: Household): number {
  switch (household.decision?.kind) {
    case "go_now":
      return 0;
    case "get_care_today":
      return 1;
    case "need_one_more_answer":
      return 2;
    default:
      return 3;
  }
}

function lastTouched(household: Household): number {
  const times = [household.assessedAt, household.referral?.updatedAt]
    .filter((value): value is string => !!value)
    .map((value) => Date.parse(value));
  return times.length > 0 ? Math.max(...times) : 0;
}

/** Most urgent first; inside a status, the one waiting longest comes first. */
export function sortHouseholds(list: Household[], now: number): Household[] {
  return [...list].sort((a, b) => {
    const status =
      STATUS_ORDER.indexOf(householdStatus(a, now)) -
      STATUS_ORDER.indexOf(householdStatus(b, now));
    if (status !== 0) return status;
    const urgency = urgencyRank(a) - urgencyRank(b);
    if (urgency !== 0) return urgency;
    const waited = lastTouched(a) - lastTouched(b);
    if (waited !== 0) return waited;
    return a.number - b.number;
  });
}

export function statusCounts(
  list: Household[],
  now: number,
): Record<HouseholdStatus, number> {
  const counts: Record<HouseholdStatus, number> = {
    attention: 0,
    referral: 0,
    followup: 0,
    stable: 0,
  };
  for (const household of list) {
    counts[householdStatus(household, now)] += 1;
  }
  return counts;
}

/** One line: why this household is where it is in the list. */
export function householdReason(
  household: Household,
  now: number,
  locale: Locale,
): string {
  const referral = household.referral;
  if (isActive(referral)) {
    if (referral.queued || referral.failure === "offline") {
      return t("chpQueuedNotice", locale);
    }
    if (referral.stage === "completed") {
      return t("chpReasonRecordOutcome", locale);
    }
    return describeReferral(
      "chp",
      referral,
      household.decision?.kind ?? null,
      locale,
    ).headline;
  }
  const kind = household.decision?.kind;
  if (decisionPending(household)) {
    if (kind === "need_one_more_answer") {
      return t("chpReasonNeedsAnswers", locale);
    }
    if (kind === "go_now" || kind === "get_care_today") {
      return fill(t("chpReasonHandoffTpl", locale), {
        d: decisionHeadline(kind, locale),
      });
    }
  }
  if (!household.decision) {
    return t("chpReasonNotVisited", locale);
  }
  if (householdStatus(household, now) === "followup") {
    return t("chpReasonFollowUp", locale);
  }
  return t("chpReasonStable", locale);
}

export function householdLabel(household: Household, locale: Locale): string {
  if (household.id === SHARED_CASE_ID) {
    return t("chpSharedCase", locale);
  }
  return fill(t("chpHouseholdTpl", locale), { n: household.number });
}

export function memberLabel(member: PersonKind, locale: Locale): string {
  switch (member) {
    case "child":
      return t("whoChild", locale);
    case "household_adult":
    case "self":
      return t("chpMemberAdult", locale);
    default:
      return t("whoValueUnknown", locale);
  }
}

/** Can the CHP send a handoff for this household right now? */
export function canSendHandoff(household: Household): boolean {
  const kind = household.decision?.kind;
  if (kind !== "go_now" && kind !== "get_care_today") {
    return false;
  }
  return !isActive(household.referral) && decisionPending(household);
}

/** Where the handoff for the latest decision stands. */
export function handoffFor(household: Household): "none" | "queued" | "sent" {
  if (!household.referral || decisionPending(household)) {
    return "none";
  }
  return household.referral.queued ? "queued" : "sent";
}

export const SHARED_CASE_ID = "shared-care-path";

/**
 * The live demo case from the shared store (started on the household
 * surface, answered by the facility) shown as one more row, so all three
 * surfaces still look at the same referral.
 */
export function fromCarePath(
  encounter: Encounter | null,
  referral: Referral | null,
): Household | null {
  if (!encounter || !referral) {
    return null;
  }
  return {
    id: SHARED_CASE_ID,
    number: 0,
    member: encounter.answers.who ?? "unknown",
    answers: encounter.answers,
    decision: encounter.decision,
    assessedAt: referral.createdAt,
    referral,
    followUpDueAt: null,
    demo: true,
  };
}

function sameLocalDay(iso: string | null | undefined, now: number): boolean {
  if (!iso) return false;
  const a = new Date(iso);
  const b = new Date(now);
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Counts only. Takes households, returns numbers: no label can leak out. */
export type DailySummaryCounts = {
  seen: number;
  referred: number;
  followUps: number;
};

export function dailySummary(list: Household[], now: number): DailySummaryCounts {
  return {
    seen: list.filter((household) => sameLocalDay(household.assessedAt, now)).length,
    referred: list.filter((household) =>
      sameLocalDay(household.referral?.createdAt, now),
    ).length,
    followUps: list.filter(
      (household) => householdStatus(household, now) === "followup",
    ).length,
  };
}

// ---------------------------------------------------------------------------
// Transitions

export function assessHousehold(
  household: Household,
  answers: AssessmentAnswers,
  now: number,
): Household {
  const decision = decide(answers);
  return {
    ...household,
    member: answers.who ?? household.member,
    answers,
    decision,
    assessedAt: new Date(now).toISOString(),
    followUpDueAt:
      decision.kind === "monitor_at_home"
        ? new Date(now + FOLLOW_UP_AFTER_MS).toISOString()
        : null,
  };
}

/**
 * One tap: build the referral and send it. Offline, the shared referral
 * logic queues it on the phone instead (queued: true) until flushQueued runs.
 */
export function sendHandoff(
  household: Household,
  conditions: SendConditions,
): Household {
  if (!canSendHandoff(household) || !household.decision || !household.assessedAt) {
    return household;
  }
  const created = createReferral({
    encounterId: `${household.id}@${household.assessedAt}`,
    urgent: household.decision.kind === "go_now",
    by: "chp",
  });
  return {
    ...household,
    referral: applyReferralAction(created, "send", "chp", conditions),
  };
}

export function flushQueued(
  list: Household[],
  conditions: SendConditions,
): Household[] {
  if (conditions.offline) {
    return list;
  }
  let changed = false;
  const next = list.map((household) => {
    if (!household.referral?.queued) {
      return household;
    }
    changed = true;
    return {
      ...household,
      referral: applyReferralAction(household.referral, "send", "chp", conditions),
    };
  });
  return changed ? next : list;
}

export function hasQueued(list: Household[]): boolean {
  return list.some((household) => household.referral?.queued);
}

/** The CHP closes the loop once the facility has finished the visit. */
export function recordOutcome(
  household: Household,
  outcome: OutcomeCode,
  now: number,
): Household {
  if (!household.referral || !canPerform(household.referral, "return_outcome")) {
    return household;
  }
  return {
    ...household,
    referral: applyReferralAction(household.referral, "return_outcome", "chp", {
      offline: false,
      noFacilityResponse: false,
      weakConnection: false,
      outcome,
    }),
    // After care comes a home visit to confirm they are improving.
    followUpDueAt: new Date(now).toISOString(),
  };
}

export function clearFollowUp(household: Household): Household {
  return { ...household, followUpDueAt: null };
}

/** The CHP's own step: confirm the family has left (accepted -> moving). */
export function confirmTravel(household: Household): Household {
  if (!household.referral || !canPerform(household.referral, "travel")) {
    return household;
  }
  return {
    ...household,
    referral: applyReferralAction(household.referral, "travel", "chp", {
      offline: false,
      noFacilityResponse: false,
      weakConnection: false,
    }),
  };
}

const DEMO_FACILITY_STEPS: ReferralAction[] = [
  "receive",
  "accept",
  "travel",
  "arrive",
  "start_care",
  "complete",
];

/**
 * Demo only: stand in for the facility so the loop can be walked end to end
 * on one phone. Never runs on its own; a labelled demo button calls it.
 */
export function demoAdvance(household: Household): Household {
  const referral = household.referral;
  if (!referral || referral.queued) {
    return household;
  }
  const action = DEMO_FACILITY_STEPS.find((step) => canPerform(referral, step));
  if (!action) {
    return household;
  }
  return {
    ...household,
    referral: applyReferralAction(referral, action, "facility", {
      offline: false,
      noFacilityResponse: false,
      weakConnection: false,
    }),
  };
}

// ---------------------------------------------------------------------------
// Roster state

export type RosterAction =
  | { type: "assess"; id: string; answers: AssessmentAnswers; now: number }
  | { type: "sendHandoff"; id: string; conditions: SendConditions }
  | { type: "flushQueued"; conditions: SendConditions }
  | { type: "recordOutcome"; id: string; outcome: OutcomeCode; now: number }
  | { type: "confirmTravel"; id: string }
  | { type: "clearFollowUp"; id: string }
  | { type: "demoAdvance"; id: string }
  | { type: "reset"; households: Household[] };

function updateOne(
  list: Household[],
  id: string,
  change: (household: Household) => Household,
): Household[] {
  return list.map((household) => (household.id === id ? change(household) : household));
}

export function rosterReducer(list: Household[], action: RosterAction): Household[] {
  switch (action.type) {
    case "assess":
      return updateOne(list, action.id, (h) => assessHousehold(h, action.answers, action.now));
    case "sendHandoff":
      return updateOne(list, action.id, (h) => sendHandoff(h, action.conditions));
    case "flushQueued":
      return flushQueued(list, action.conditions);
    case "recordOutcome":
      return updateOne(list, action.id, (h) => recordOutcome(h, action.outcome, action.now));
    case "confirmTravel":
      return updateOne(list, action.id, confirmTravel);
    case "clearFollowUp":
      return updateOne(list, action.id, clearFollowUp);
    case "demoAdvance":
      return updateOne(list, action.id, demoAdvance);
    case "reset":
      return action.households;
    default:
      return list;
  }
}

// ---------------------------------------------------------------------------
// Synthetic demo roster

const CALM: SendConditions = {
  offline: false,
  noFacilityResponse: false,
  weakConnection: false,
};

function blank(number: number, member: PersonKind): Household {
  return {
    id: `demo-hh-${number}`,
    number,
    member,
    answers: null,
    decision: null,
    assessedAt: null,
    referral: null,
    followUpDueAt: null,
    demo: true,
  };
}

function seedAnswers(partial: Partial<AssessmentAnswers>): AssessmentAnswers {
  return { ...EMPTY_ANSWERS, ...partial };
}

function walk(household: Household, steps: ReferralAction[]): Household {
  let referral = household.referral;
  for (const step of steps) {
    if (referral && canPerform(referral, step)) {
      referral = applyReferralAction(referral, step, step === "travel" ? "chp" : "facility", CALM);
    }
  }
  return { ...household, referral };
}

/**
 * Seven synthetic households, one per state the CHP needs to recognise.
 * Decisions come from decide() on synthetic answers, never hand-written.
 */
export function seedHouseholds(now: number): Household[] {
  const at = (hoursAgo: number) => now - hoursAgo * HOUR;

  const urgent = assessHousehold(
    blank(1, "child"),
    seedAnswers({ who: "child", awake: "not_waking", presentation: "Hot body, very sleepy" }),
    at(0.25),
  );

  const sent = sendHandoff(
    assessHousehold(
      blank(2, "household_adult"),
      seedAnswers({
        who: "household_adult",
        awake: "alert",
        breathing: "difficult",
        drinking: "yes",
        duration: "two_days",
        mainProblem: "breathing",
      }),
      at(2),
    ),
    CALM,
  );

  const accepted = walk(
    sendHandoff(
      assessHousehold(
        blank(3, "child"),
        seedAnswers({
          who: "child",
          awake: "alert",
          breathing: "fine",
          drinking: "little",
          duration: "two_days",
          mainProblem: "fever",
        }),
        at(3),
      ),
      CALM,
    ),
    ["accept"],
  );

  const completed = walk(
    sendHandoff(
      assessHousehold(
        blank(4, "household_adult"),
        seedAnswers({
          who: "household_adult",
          awake: "alert",
          breathing: "fine",
          drinking: "yes",
          duration: "today",
          mainProblem: "injury",
          presentation: "Deep cut on the leg",
        }),
        at(5),
      ),
      CALM,
    ),
    ["accept", "travel", "arrive", "start_care", "complete"],
  );

  const followUpDue = assessHousehold(
    blank(5, "child"),
    seedAnswers({
      who: "child",
      awake: "alert",
      breathing: "fine",
      drinking: "yes",
      duration: "today",
      mainProblem: "stomach",
    }),
    at(30),
  );

  const stable = assessHousehold(
    blank(6, "household_adult"),
    seedAnswers({
      who: "household_adult",
      awake: "alert",
      breathing: "fine",
      drinking: "yes",
      duration: "today",
      mainProblem: "other",
    }),
    at(1),
  );

  const closed = clearFollowUp(
    recordOutcome(
      walk(
        sendHandoff(
          assessHousehold(
            blank(7, "child"),
            seedAnswers({
              who: "child",
              awake: "sleepy",
              breathing: "fine",
              drinking: "yes",
              duration: "two_days",
              mainProblem: "fever",
            }),
            at(48),
          ),
          CALM,
        ),
        ["accept", "travel", "arrive", "start_care", "complete"],
      ),
      "treated",
      now,
    ),
  );

  return [urgent, sent, accepted, completed, followUpDue, stable, closed];
}

/** Read a stored roster; anything malformed falls back to fresh demo seeds. */
export function parseRoster(raw: string | null, now: number): Household[] {
  if (!raw) return seedHouseholds(now);
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (
      Array.isArray(parsed) &&
      parsed.length > 0 &&
      parsed.every(
        (item) =>
          item &&
          typeof item === "object" &&
          (item as Household).demo === true &&
          typeof (item as Household).id === "string" &&
          typeof (item as Household).number === "number",
      )
    ) {
      return parsed as Household[];
    }
  } catch {
    // Demo persistence must never break the work list.
  }
  return seedHouseholds(now);
}
