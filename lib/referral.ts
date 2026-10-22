import { fill, t, type CopyKey, type Locale } from "./copy";
import {
  facilityById,
  pickFacility,
  redirectTarget,
  type CapacityMap,
} from "./facilities";
import { createId, nowIso } from "./ids";
import type {
  DecisionKind,
  OutcomeCode,
  Referral,
  ReferralStage,
  Role,
} from "./types";

export const REFERRAL_STAGES: ReferralStage[] = [
  "created",
  "sent",
  "received",
  "accepted",
  "patient_moving",
  "arrived",
  "seen",
  "completed",
  "outcome_returned",
];

export type ReferralAction =
  | "send"
  | "receive"
  | "accept"
  | "travel"
  | "arrive"
  | "start_care"
  | "complete"
  | "return_outcome"
  | "redirect"
  | "decline"
  | "ask_more";

const STAGE_AFTER: Record<ReferralAction, ReferralStage | null> = {
  send: "sent",
  receive: "received",
  accept: "accepted",
  travel: "patient_moving",
  arrive: "arrived",
  start_care: "seen",
  complete: "completed",
  return_outcome: "outcome_returned",
  redirect: "sent",
  decline: "sent",
  ask_more: "received",
};

export type ReferralView = {
  stageLabel: string;
  headline: string;
  status: string;
  action: { id: ReferralAction; label: string } | null;
  arrivalMinutes: number | null;
};

export function createReferral(input: {
  encounterId: string;
  urgent: boolean;
  by: Role;
}): Referral {
  const facility = pickFacility(input.urgent);
  const at = nowIso();
  return {
    id: createId("ref"),
    encounterId: input.encounterId,
    stage: "created",
    facilityId: facility.id,
    expectedArrivalMinutes: facility.travelMinutes,
    queued: false,
    failure: null,
    askMore: null,
    outcome: null,
    history: [{ stage: "created", at, by: input.by }],
    createdAt: at,
    updatedAt: at,
  };
}

export function canPerform(
  referral: Referral,
  action: ReferralAction,
): boolean {
  const { stage } = referral;

  switch (action) {
    case "send":
      return stage === "created";
    case "receive":
      return stage === "sent";
    case "accept":
      return stage === "sent" || stage === "received";
    case "travel":
      return stage === "accepted";
    case "arrive":
      return stage === "patient_moving";
    case "start_care":
      return stage === "arrived";
    case "complete":
      return stage === "seen";
    case "return_outcome":
      return stage === "completed";
    case "redirect":
    case "decline":
      return stage === "sent" || stage === "received" || stage === "accepted";
    case "ask_more":
      return stage === "sent" || stage === "received";
    default:
      return false;
  }
}

export function applyReferralAction(
  referral: Referral,
  action: ReferralAction,
  by: Role,
  options: {
    offline: boolean;
    noFacilityResponse: boolean;
    weakConnection: boolean;
    outcome?: OutcomeCode;
    /** Reported facility capacity; the redirect skips closed facilities. */
    capacity?: CapacityMap;
  },
): Referral {
  const at = nowIso();

  if (action === "send" && options.offline) {
    return {
      ...referral,
      queued: true,
      failure: "offline",
      updatedAt: at,
    };
  }

  if (action === "send" && options.noFacilityResponse) {
    return {
      ...referral,
      stage: "sent",
      queued: false,
      failure: "no_facility_response",
      history: [...referral.history, { stage: "sent", at, by }],
      updatedAt: at,
    };
  }

  if (action === "send") {
    const failure = options.weakConnection ? "weak_connection" : null;
    return {
      ...referral,
      stage: "sent",
      queued: false,
      failure,
      history: [...referral.history, { stage: "sent", at, by }],
      updatedAt: at,
    };
  }

  if (action === "redirect" || action === "decline") {
    // "Cannot take" goes through the same redirect so the referral is never
    // left without a destination. With no open facility it stays put.
    const nextFacility = redirectTarget(referral.facilityId, options.capacity);
    if (!nextFacility) {
      return referral;
    }
    const entry =
      action === "decline"
        ? { stage: "sent" as const, at, by, note: nextFacility.name, reason: "cannot_take" as const }
        : { stage: "sent" as const, at, by, note: nextFacility.name };
    return {
      ...referral,
      stage: "sent",
      facilityId: nextFacility.id,
      expectedArrivalMinutes: nextFacility.travelMinutes,
      failure: "redirected",
      askMore: null,
      history: [...referral.history, entry],
      updatedAt: at,
    };
  }

  if (action === "ask_more") {
    return {
      ...referral,
      stage: "received",
      askMore: "can_walk",
      history: [...referral.history, { stage: "received", at, by }],
      updatedAt: at,
    };
  }

  if (action === "accept") {
    const receivedHistory =
      referral.stage === "sent"
        ? [...referral.history, { stage: "received" as const, at, by }]
        : referral.history;
    return {
      ...referral,
      stage: "accepted",
      failure: referral.failure === "no_facility_response" ? null : referral.failure,
      queued: false,
      history: [...receivedHistory, { stage: "accepted", at, by }],
      updatedAt: at,
    };
  }

  if (action === "return_outcome") {
    return {
      ...referral,
      stage: "outcome_returned",
      outcome: options.outcome ?? "treated",
      history: [...referral.history, { stage: "outcome_returned", at, by }],
      updatedAt: at,
    };
  }

  const stage = STAGE_AFTER[action];
  if (!stage) {
    return referral;
  }

  return {
    ...referral,
    stage,
    history: [...referral.history, { stage, at, by }],
    updatedAt: at,
  };
}

const STAGE_LABEL_KEY: Record<ReferralStage, CopyKey> = {
  created: "stageCreated",
  sent: "stageSent",
  received: "stageReceived",
  accepted: "stageAccepted",
  patient_moving: "stagePatientMoving",
  arrived: "stageArrived",
  seen: "stageSeen",
  completed: "stageCompleted",
  outcome_returned: "stageOutcomeReturned",
};

export function stageLabel(stage: ReferralStage, locale: Locale): string {
  return t(STAGE_LABEL_KEY[stage], locale);
}

export function outcomeLabel(outcome: OutcomeCode, locale: Locale): string {
  switch (outcome) {
    case "treated":
      return t("outcomeTreated", locale);
    case "referred_onward":
      return t("outcomeHigher", locale);
    case "did_not_arrive":
      return t("outcomeNoShow", locale);
    case "unknown":
      return t("outcomeUnknown", locale);
  }
}

/**
 * The one place where referral state becomes words. Every surface renders the
 * same event through this translation: (stage x role x language) -> what this
 * person needs to know, and the one thing they can do about it.
 */
export function describeReferral(
  role: Role,
  referral: Referral,
  decisionKind: DecisionKind | null,
  locale: Locale,
): ReferralView {
  const facility = facilityById(referral.facilityId);
  const urgent = decisionKind === "go_now";
  const minutes = referral.expectedArrivalMinutes;
  const label = stageLabel(referral.stage, locale);
  const f = facility.name;

  const view = (
    headlineKey: CopyKey,
    statusKey: CopyKey,
    action: { id: ReferralAction; label: CopyKey } | null,
    arrivalMinutes: number | null,
  ): ReferralView => ({
    stageLabel: label,
    headline: fill(t(headlineKey, locale), { f }),
    status: fill(t(statusKey, locale), { f }),
    action: action ? { id: action.id, label: t(action.label, locale) } : null,
    arrivalMinutes,
  });

  if (referral.queued || referral.failure === "offline") {
    if (role === "household") {
      return view(
        "refQueuedHouseholdHeadline",
        "refQueuedHouseholdStatus",
        { id: "send", label: "actionSendFacility" },
        null,
      );
    }
    if (role === "chp") {
      return view(
        "refQueuedChpHeadline",
        "refQueuedChpStatus",
        { id: "send", label: "actionSendReferral" },
        null,
      );
    }
  }

  if (referral.failure === "no_facility_response" && referral.stage === "sent") {
    if (role === "facility") {
      return view(
        "refSentFacilityHeadline",
        "refNoResponseFacilityStatus",
        { id: "accept", label: "actionAccept" },
        null,
      );
    }
    if (role === "household") {
      return view("refNoResponseHeadline", "refNoResponseHouseholdStatus", null, null);
    }
    return view("refNoResponseHeadline", "refNoResponseOtherStatus", null, null);
  }

  switch (referral.stage) {
    case "created":
      if (role === "household") {
        return view(
          "refCreatedHouseholdHeadline",
          "refCreatedHouseholdStatus",
          { id: "send", label: urgent ? "actionSendNow" : "actionSendFacility" },
          null,
        );
      }
      if (role === "chp") {
        return view(
          "refCreatedChpHeadline",
          "refCreatedChpStatus",
          { id: "send", label: "actionSendReferral" },
          null,
        );
      }
      return view("refCreatedFacilityHeadline", "refCreatedFacilityStatus", null, null);
    case "sent":
      if (role === "household") {
        return view("refSentHouseholdHeadline", "refSentHouseholdStatus", null, null);
      }
      if (role === "chp") {
        return view("refSentChpHeadline", "refSentChpStatus", null, null);
      }
      return view(
        "refSentFacilityHeadline",
        "refSentFacilityStatus",
        { id: "accept", label: "actionAccept" },
        null,
      );
    case "received":
      if (role === "household") {
        return view(
          "refReceivedHouseholdHeadline",
          "refReceivedHouseholdStatus",
          null,
          null,
        );
      }
      if (role === "chp") {
        return view("refReceivedChpHeadline", "refReceivedChpStatus", null, null);
      }
      return view(
        "refReceivedFacilityHeadline",
        "refReceivedFacilityStatus",
        { id: "accept", label: "actionAccept" },
        null,
      );
    case "accepted":
      if (role === "household") {
        return view(
          "refAcceptedHouseholdHeadline",
          "refAcceptedHouseholdStatus",
          { id: "travel", label: "actionWeveLeft" },
          minutes,
        );
      }
      if (role === "chp") {
        return view(
          "refAcceptedChpHeadline",
          "refAcceptedChpStatus",
          { id: "travel", label: "actionTheyLeft" },
          minutes,
        );
      }
      return view(
        urgent ? "refAcceptedFacilityUrgentHeadline" : "refAcceptedFacilityHeadline",
        "refAcceptedFacilityStatus",
        null,
        minutes,
      );
    case "patient_moving":
      if (role === "household") {
        return view(
          "refMovingHouseholdHeadline",
          "refMovingHouseholdStatus",
          { id: "arrive", label: "actionWeveArrived" },
          minutes,
        );
      }
      if (role === "chp") {
        return view("refMovingChpHeadline", "refMovingChpStatus", null, minutes);
      }
      return view(
        "refMovingFacilityHeadline",
        "refMovingFacilityStatus",
        { id: "arrive", label: "actionTheyreHere" },
        minutes,
      );
    case "arrived":
      if (role === "household") {
        return view(
          "refArrivedHouseholdHeadline",
          "refArrivedHouseholdStatus",
          null,
          null,
        );
      }
      if (role === "chp") {
        return view("refArrivedChpHeadline", "refArrivedChpStatus", null, null);
      }
      return view(
        "refArrivedFacilityHeadline",
        "refArrivedFacilityStatus",
        { id: "start_care", label: "actionStartCare" },
        null,
      );
    case "seen":
      if (role === "household") {
        return view("refSeenHouseholdHeadline", "refSeenHouseholdStatus", null, null);
      }
      if (role === "chp") {
        return view("refSeenChpHeadline", "refSeenChpStatus", null, null);
      }
      return view(
        "refSeenFacilityHeadline",
        "refSeenFacilityStatus",
        { id: "complete", label: "actionCompleteVisit" },
        null,
      );
    case "completed":
      if (role === "household") {
        return view(
          "refCompletedHouseholdHeadline",
          "refCompletedHouseholdStatus",
          null,
          null,
        );
      }
      if (role === "chp") {
        return view("refCompletedChpHeadline", "refCompletedChpStatus", null, null);
      }
      return view(
        "refCompletedFacilityHeadline",
        "refCompletedFacilityStatus",
        { id: "return_outcome", label: "actionReturnOutcome" },
        null,
      );
    case "outcome_returned": {
      const outcomeText = referral.outcome
        ? outcomeLabel(referral.outcome, locale)
        : null;
      if (role === "household") {
        const base = view(
          "refOutcomeHouseholdHeadline",
          "refOutcomeHouseholdStatus",
          null,
          null,
        );
        return { ...base, status: outcomeText ?? base.status };
      }
      if (role === "chp") {
        const base = view("refOutcomeChpHeadline", "refOutcomeChpStatus", null, null);
        return { ...base, status: outcomeText ?? base.status };
      }
      const base = view(
        "refOutcomeFacilityHeadline",
        "refOutcomeFacilityStatus",
        null,
        null,
      );
      return { ...base, status: outcomeText ?? base.status };
    }
  }
}

export function followUpItems(
  role: Role,
  referral: Referral | null,
  decisionKind: DecisionKind | null,
  locale: Locale,
): { id: string; label: string; detail?: string }[] {
  if (role !== "chp") {
    return [];
  }
  if (decisionKind === "monitor_at_home" && !referral) {
    return [
      {
        id: "watch-home",
        label: t("fuWatchHome", locale),
        detail: t("fuWatchHomeDetail", locale),
      },
    ];
  }
  if (referral?.stage === "accepted") {
    return [
      {
        id: "confirm-travel",
        label: t("fuConfirmTravel", locale),
        detail: t("fuConfirmTravelDetail", locale),
      },
    ];
  }
  if (referral?.stage === "outcome_returned") {
    return [
      {
        id: "post-outcome",
        label: t("fuPostOutcome", locale),
        detail: referral.outcome
          ? outcomeLabel(referral.outcome, locale)
          : t("fuPostOutcomeDetail", locale),
      },
    ];
  }
  return [];
}
