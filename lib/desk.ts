import { decide, decisionHeadline, EMPTY_ANSWERS } from "./assessment";
import { runClinicalPipeline, type RenderedAssessment } from "./clinical/pipeline";
import type { DisagreementRecord } from "./clinical/reconcile";
import { fill, t, type CopyKey, type Locale } from "./copy";
import {
  capacityOf,
  facilityById,
  redirectTarget,
  type CapacityMap,
} from "./facilities";
import { canPerform, outcomeLabel, stageLabel } from "./referral";
import type {
  AssessmentAnswers,
  CareState,
  DecisionKind,
  DemoReferralCase,
  Encounter,
  FacilityCapacity,
  PatientSex,
  Referral,
  ReferralHistoryEntry,
  ReferralStage,
  Role,
  ShadowCandidate,
} from "./types";

/**
 * The facility desk: the professional inbox and case view.
 *
 * Every case here is demo data. Synthetic cases are built from fixed answers
 * and labelled "Synthetic demo"; the session case is the one referral this
 * demo session created. The answer shown is always decide() on the answers.
 * A shadow model candidate is read from the reconcile disagreement record
 * for the engineering panel only and never changes a displayed answer.
 */

export const DESK_DEFAULT_FACILITY_ID = "north-demo";

export const CAPACITY_OPTIONS: FacilityCapacity[] = ["accepting", "busy", "closed"];

const CAPACITY_KEY: Record<FacilityCapacity, CopyKey> = {
  accepting: "capacityAccepting",
  busy: "capacityBusy",
  closed: "capacityClosed",
};

export function capacityLabel(capacity: FacilityCapacity, locale: Locale): string {
  return t(CAPACITY_KEY[capacity], locale);
}

/**
 * Inbox display order for sorting rows only. It is not a clinical severity
 * score and feeds no decision. An unfinished assessment sits above
 * monitor-at-home because someone still has to look at it.
 */
export const INBOX_ORDER: Record<DecisionKind, number> = {
  go_now: 0,
  get_care_today: 1,
  need_one_more_answer: 2,
  monitor_at_home: 3,
};

export type DeskCase = {
  id: string;
  source: "session" | "synthetic";
  encounter: Encounter;
  referral: Referral;
  ageMonths: number | null;
  sex: PatientSex | null;
  shadowCandidate: ShadowCandidate | null;
};

type Seed = {
  key: string;
  ageMonths: number | null;
  sex: PatientSex | null;
  answers: Partial<AssessmentAnswers>;
  /** [stage, minutes before the anchor, who recorded it] */
  history: [ReferralStage, number, Role][];
  shadowCandidate: ShadowCandidate | null;
};

const SHADOW_MODEL_ID = "shadow-demo (synthetic)";

/** Synthetic referrals. Invented for the demo; no real person. */
const SEEDS: Seed[] = [
  {
    key: "a",
    ageMonths: 36,
    sex: "female",
    answers: {
      who: "child",
      presentation: "Fever and breathing very hard since morning",
      awake: "sleepy",
      breathing: "severe",
      drinking: "little",
      duration: "today",
    },
    history: [
      ["created", 14, "chp"],
      ["sent", 12, "chp"],
    ],
    shadowCandidate: { disposition: "get_care_today", model_id: SHADOW_MODEL_ID },
  },
  {
    key: "b",
    ageMonths: 34 * 12,
    sex: "male",
    answers: {
      who: "household_adult",
      presentation: "Deep cut on the leg from a panga, bleeding has slowed",
      awake: "alert",
      breathing: "fine",
      drinking: "yes",
      duration: "today",
      mainProblem: "injury",
    },
    history: [
      ["created", 42, "chp"],
      ["sent", 40, "chp"],
      ["received", 30, "facility"],
    ],
    shadowCandidate: { disposition: "go_now", model_id: SHADOW_MODEL_ID },
  },
  {
    key: "c",
    ageMonths: 9,
    sex: "male",
    answers: {
      who: "child",
      presentation: "Convulsion this morning, now feeding poorly",
      awake: "sleepy",
      breathing: "fine",
      drinking: "little",
      duration: "today",
    },
    history: [
      ["created", 92, "household"],
      ["sent", 90, "household"],
      ["received", 88, "facility"],
      ["accepted", 86, "facility"],
      ["patient_moving", 80, "household"],
    ],
    shadowCandidate: null,
  },
  {
    key: "d",
    ageMonths: 61 * 12,
    sex: "female",
    answers: {
      who: "household_adult",
      presentation: "Cough and fever for two weeks",
      awake: "alert",
      breathing: "fine",
      drinking: "yes",
      duration: "longer",
    },
    history: [
      ["created", 202, "chp"],
      ["sent", 200, "chp"],
      ["received", 198, "facility"],
      ["accepted", 196, "facility"],
      ["patient_moving", 190, "chp"],
      ["arrived", 150, "chp"],
      ["seen", 140, "facility"],
      ["completed", 60, "facility"],
    ],
    shadowCandidate: { disposition: "self-care", model_id: SHADOW_MODEL_ID },
  },
  {
    key: "e",
    ageMonths: null,
    sex: null,
    answers: {
      who: "household_adult",
      presentation: "Vomiting since yesterday, drinking only a little",
      awake: "alert",
      breathing: "fine",
      drinking: "little",
      duration: "two_days",
    },
    history: [
      ["created", 57, "chp"],
      ["sent", 55, "chp"],
    ],
    shadowCandidate: null,
  },
];

function minutesBefore(anchorMs: number, minutes: number): string {
  return new Date(anchorMs - minutes * 60_000).toISOString();
}

/** Build the synthetic inbox relative to an anchor time. */
export function seedDemoCases(anchorIso: string): DemoReferralCase[] {
  const anchor = new Date(anchorIso).getTime();
  return SEEDS.map((seed) => {
    const history: ReferralHistoryEntry[] = seed.history.map(([stage, ago, by]) => ({
      stage,
      at: minutesBefore(anchor, ago),
      by,
    }));
    const first = history[0].at;
    const last = history[history.length - 1];
    const encounter: Encounter = {
      id: `demo-enc-${seed.key}`,
      answers: { ...EMPTY_ANSWERS, ...seed.answers },
      asked: [],
      currentQuestion: null,
      decision: null,
      startedBy: history[0].by,
      createdAt: first,
      updatedAt: first,
    };
    encounter.decision = decide(encounter.answers);
    const referral: Referral = {
      id: `demo-ref-${seed.key}`,
      encounterId: encounter.id,
      stage: last.stage,
      facilityId: DESK_DEFAULT_FACILITY_ID,
      expectedArrivalMinutes: facilityById(DESK_DEFAULT_FACILITY_ID).travelMinutes,
      queued: false,
      failure: null,
      askMore: null,
      outcome: null,
      history,
      createdAt: first,
      updatedAt: last.at,
    };
    return {
      encounter,
      referral,
      ageMonths: seed.ageMonths,
      sex: seed.sex,
      shadowCandidate: seed.shadowCandidate,
    };
  });
}

/** The session referral reaches the desk only once it has been sent. */
function sessionCase(state: CareState): DeskCase | null {
  const { referral, encounter } = state;
  if (!referral || !encounter) return null;
  if (referral.queued || referral.stage === "created") return null;
  return {
    id: referral.id,
    source: "session",
    encounter,
    referral,
    ageMonths: null,
    sex: null,
    shadowCandidate: null,
  };
}

export function deskCases(state: CareState): DeskCase[] {
  const live = sessionCase(state);
  const demo: DeskCase[] = state.demoCases.map((item) => ({
    id: item.referral.id,
    source: "synthetic",
    encounter: item.encounter,
    referral: item.referral,
    ageMonths: item.ageMonths,
    sex: item.sex,
    shadowCandidate: item.shadowCandidate,
  }));
  return live ? [live, ...demo] : demo;
}

/** When the referral reached a facility: its first "sent" entry. */
export function arrivedAt(referral: Referral): string {
  return referral.history.find((entry) => entry.stage === "sent")?.at ?? referral.createdAt;
}

export function isClosed(referral: Referral): boolean {
  return referral.stage === "outcome_returned";
}

/**
 * Open cases at this desk first, then cases now at another facility, then
 * closed ones. Within each group: urgency, then longest waiting first.
 */
export function sortDeskCases(cases: DeskCase[], deskFacilityId: string): DeskCase[] {
  const group = (item: DeskCase) =>
    isClosed(item.referral) ? 2 : item.referral.facilityId === deskFacilityId ? 0 : 1;
  return [...cases].sort((a, b) => {
    const byGroup = group(a) - group(b);
    if (byGroup !== 0) return byGroup;
    const byUrgency =
      INBOX_ORDER[decide(a.encounter.answers).kind] -
      INBOX_ORDER[decide(b.encounter.answers).kind];
    if (byUrgency !== 0) return byUrgency;
    return Date.parse(arrivedAt(a.referral)) - Date.parse(arrivedAt(b.referral));
  });
}

export function formatAge(ageMonths: number | null, locale: Locale): string | null {
  if (ageMonths === null || ageMonths < 0) return null;
  if (ageMonths < 24) return fill(t("ageMonthsTpl", locale), { n: ageMonths });
  return fill(t("ageYearsTpl", locale), { n: Math.floor(ageMonths / 12) });
}

export function formatSex(sex: PatientSex | null, locale: Locale): string | null {
  if (sex === "female") return t("sexFemale", locale);
  if (sex === "male") return t("sexMale", locale);
  return null;
}

export function formatWaited(sinceIso: string, nowMs: number, locale: Locale): string {
  const minutes = Math.max(0, Math.round((nowMs - Date.parse(sinceIso)) / 60_000));
  if (minutes < 60) return fill(t("deskWaitedMinTpl", locale), { m: minutes });
  return fill(t("deskWaitedHourTpl", locale), {
    h: Math.floor(minutes / 60),
    m: minutes % 60,
  });
}

function whoLabel(answers: AssessmentAnswers, locale: Locale): string {
  if (answers.who === "child") return t("deskWhoChild", locale);
  if (answers.who === "self" || answers.who === "household_adult") {
    return t("deskWhoAdult", locale);
  }
  return t("deskWhoUnknown", locale);
}

export type DeskRow = {
  id: string;
  source: DeskCase["source"];
  sourceLabel: string;
  patientLabel: string;
  kind: DecisionKind;
  answerLabel: string;
  topDanger: string | null;
  stage: ReferralStage;
  stageLabel: string;
  waitedLabel: string;
  atDesk: boolean;
  facilityName: string;
  closed: boolean;
  canAccept: boolean;
  /** Redirect and cannot take are both offered; both use the redirect logic. */
  canRedirect: boolean;
  /** Redirect would be allowed, but no other facility is open. */
  redirectBlocked: boolean;
  redirectTo: string | null;
};

export function deskRow(
  item: DeskCase,
  deskFacilityId: string,
  capacity: CapacityMap,
  locale: Locale,
  nowMs: number,
): DeskRow {
  const decision = decide(item.encounter.answers);
  const referral = item.referral;
  const atDesk = referral.facilityId === deskFacilityId;
  const target = redirectTarget(referral.facilityId, capacity);
  const redirectAllowed = atDesk && canPerform(referral, "redirect");
  const patientLabel = [
    whoLabel(item.encounter.answers, locale),
    formatAge(item.ageMonths, locale),
    formatSex(item.sex, locale),
  ]
    .filter((part): part is string => Boolean(part))
    .join(" · ");
  const dangerKey = decision.dangerSignKeys[0];
  return {
    id: item.id,
    source: item.source,
    sourceLabel:
      item.source === "synthetic"
        ? t("deskSourceSynthetic", locale)
        : t("deskSourceSession", locale),
    patientLabel,
    kind: decision.kind,
    answerLabel: decisionHeadline(decision.kind, locale),
    topDanger: dangerKey ? t(dangerKey, locale) : null,
    stage: referral.stage,
    stageLabel: stageLabel(referral.stage, locale),
    waitedLabel: formatWaited(arrivedAt(referral), nowMs, locale),
    atDesk,
    facilityName: facilityById(referral.facilityId).name,
    closed: isClosed(referral),
    canAccept: atDesk && canPerform(referral, "accept"),
    canRedirect: redirectAllowed && target !== null,
    redirectBlocked: redirectAllowed && target === null,
    redirectTo: target?.name ?? null,
  };
}

/** One line a clinician can read before deciding to open the case. */
export function caseSummary(row: DeskRow, locale: Locale): string {
  return [
    row.patientLabel,
    row.answerLabel,
    row.topDanger ?? t("deskNoDangerFlagged", locale),
    row.stageLabel,
  ].join(" · ");
}

const ASKED_KEY: Record<DecisionKind, CopyKey> = {
  go_now: "askedGoNow",
  get_care_today: "askedToday",
  need_one_more_answer: "askedOneMore",
  monitor_at_home: "askedMonitor",
};

/** What the sender asked of the facility, from the rules answer. */
export function askedOfFacility(kind: DecisionKind, locale: Locale): string {
  return t(ASKED_KEY[kind], locale);
}

const ROLE_KEY: Record<Role, CopyKey> = {
  household: "roleHousehold",
  chp: "roleChp",
  facility: "roleFacility",
};

export type TimelineEntry = {
  key: string;
  at: string;
  stageLabel: string;
  byLabel: string;
  note: string | null;
};

export function timeline(referral: Referral, locale: Locale): TimelineEntry[] {
  return referral.history.map((entry, index) => {
    let note: string | null = null;
    if (entry.reason === "cannot_take" && entry.note) {
      note = fill(t("deskTimelineCannotTakeTpl", locale), { f: entry.note });
    } else if (entry.note) {
      note = fill(t("deskTimelineRedirectedTpl", locale), { f: entry.note });
    } else if (entry.stage === "outcome_returned" && referral.outcome) {
      note = outcomeLabel(referral.outcome, locale);
    }
    return {
      key: `${index}-${entry.stage}`,
      at: entry.at,
      stageLabel: stageLabel(entry.stage, locale),
      byLabel: t(ROLE_KEY[entry.by], locale),
      note,
    };
  });
}

export type ShadowReview = {
  /** decide() on the answers. This is the only answer ever displayed. */
  rulesKind: DecisionKind;
  candidatePresent: boolean;
  /** The reconcile disagreement record, if the candidate disagreed. */
  record: DisagreementRecord | null;
  rendered: RenderedAssessment | null;
};

/**
 * Run the existing pipeline for one case. The candidate goes in only so the
 * reconciler can write its disagreement record; the displayed answer stays
 * decide(). If the pipeline refuses the input, the assessment is absent
 * rather than guessed.
 */
export function reviewCase(item: DeskCase, locale: Locale): ShadowReview {
  const rulesKind = decide(item.encounter.answers).kind;
  try {
    const result = runClinicalPipeline({
      encounter: item.encounter,
      generatedAt: item.referral.createdAt,
      locale,
      candidate: item.shadowCandidate,
    });
    return {
      rulesKind,
      candidatePresent: item.shadowCandidate !== null,
      record: result.disagreement,
      rendered: result.rendered,
    };
  } catch {
    return {
      rulesKind,
      candidatePresent: item.shadowCandidate !== null,
      record: null,
      rendered: null,
    };
  }
}

const REASON_KEY: Record<DisagreementRecord["reason"], CopyKey> = {
  candidate_below_floor: "engReasonBelowFloor",
  candidate_not_approved: "engReasonNotApproved",
  candidate_unrecognized: "engReasonUnrecognized",
};

export function disagreementReasonLabel(
  reason: DisagreementRecord["reason"],
  locale: Locale,
): string {
  return t(REASON_KEY[reason], locale);
}

export function deskCapacity(state: CareState, facilityId: string): FacilityCapacity {
  return capacityOf(state.facilityCapacity, facilityId);
}
