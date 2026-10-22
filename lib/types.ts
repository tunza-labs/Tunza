import type { CopyKey } from "./copy";

export type Role = "household" | "chp" | "facility";

/**
 * The canonical referral lifecycle from the README. Internal names never
 * appear on screen; the copy layer translates them per role and language.
 */
export type ReferralStage =
  | "created"
  | "sent"
  | "received"
  | "accepted"
  | "patient_moving"
  | "arrived"
  | "seen"
  | "completed"
  | "outcome_returned";

export type NamedFailure =
  | "offline"
  | "no_facility_response"
  | "redirected"
  | "stale_information"
  | "incomplete_assessment"
  | "weak_connection";

export type DecisionKind =
  | "go_now"
  | "get_care_today"
  | "monitor_at_home"
  | "need_one_more_answer";

export type OutcomeCode =
  | "treated"
  | "referred_onward"
  | "did_not_arrive"
  | "unknown";

export type AskMoreCode = "can_walk";

export type PersonKind = "self" | "household_adult" | "child" | "unknown";

export type QuestionId =
  | "who"
  | "what"
  | "awake"
  | "breathing"
  | "drinking"
  | "duration"
  | "main_problem";

export type AwakeAnswer = "alert" | "sleepy" | "not_waking" | "unknown";
export type BreathingAnswer = "fine" | "difficult" | "severe" | "unknown";
export type DrinkingAnswer = "yes" | "little" | "no" | "unknown";
export type DurationAnswer = "today" | "two_days" | "longer" | "unknown";
export type MainProblemAnswer =
  | "breathing"
  | "fever"
  | "injury"
  | "stomach"
  | "other"
  | "unknown";

export type AssessmentAnswers = {
  who: PersonKind | null;
  presentation: string;
  photoAttached: boolean;
  awake: AwakeAnswer | null;
  breathing: BreathingAnswer | null;
  drinking: DrinkingAnswer | null;
  duration: DurationAnswer | null;
  mainProblem: MainProblemAnswer | null;
};

/** Decisions carry copy keys, not sentences — language is applied at render. */
export type Decision = {
  kind: DecisionKind;
  reasonKeys: CopyKey[];
  dangerSignKeys: CopyKey[];
  watchSignKeys: CopyKey[];
};

export type ReferralHistoryEntry = {
  stage: ReferralStage;
  at: string;
  by: Role;
  note?: string;
  /** Set when a facility said it cannot take the patient. */
  reason?: "cannot_take";
};

export type Referral = {
  id: string;
  encounterId: string;
  stage: ReferralStage;
  facilityId: string;
  expectedArrivalMinutes: number;
  queued: boolean;
  failure: NamedFailure | null;
  askMore: AskMoreCode | null;
  outcome: OutcomeCode | null;
  history: ReferralHistoryEntry[];
  createdAt: string;
  updatedAt: string;
};

export type Facility = {
  id: string;
  name: string;
  travelMinutes: number;
  canHandleUrgent: boolean;
  services: string[];
};

export type Encounter = {
  id: string;
  answers: AssessmentAnswers;
  asked: QuestionId[];
  currentQuestion: QuestionId | null;
  decision: Decision | null;
  startedBy: Role;
  createdAt: string;
  updatedAt: string;
};

/** A facility's self-reported capacity. The redirect logic reads it. */
export type FacilityCapacity = "accepting" | "busy" | "closed";

export type PatientSex = "female" | "male";

/** A model's proposed disposition, kept for engineering review only. */
export type ShadowCandidate = { disposition: string; model_id: string | null };

/**
 * A synthetic referral for the facility desk demo. Never a real patient.
 * The answer shown is always decide() on these answers; the shadow
 * candidate is never applied.
 */
export type DemoReferralCase = {
  encounter: Encounter;
  referral: Referral;
  ageMonths: number | null;
  sex: PatientSex | null;
  shadowCandidate: ShadowCandidate | null;
};

/** The household surface's top-level view; other roles ignore it. */
export type HouseholdView = "home" | "path" | "nearby" | "gate";

/** Roles behind the health-worker gate. */
export type GatedRole = "chp" | "facility";

export type CareState = {
  role: Role;
  locale: "en" | "sw";
  view: HouseholdView;
  /** Device-level access grants for the gated surfaces (placeholder for real
   *  worker identity; codes are checked server-side in /api/access). */
  grants: Record<GatedRole, boolean>;
  gateRole: GatedRole | null;
  injectedFailures: NamedFailure[];
  encounter: Encounter | null;
  referral: Referral | null;
  online: boolean;
  /** Capacity per demo facility id; missing means accepting. */
  facilityCapacity: Record<string, FacilityCapacity>;
  /** The demo facility the facility desk is acting as. */
  deskFacilityId: string;
  /** Synthetic referrals shown in the facility inbox, clearly labelled demo. */
  demoCases: DemoReferralCase[];
};
