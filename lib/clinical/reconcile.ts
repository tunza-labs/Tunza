import type { Decision } from "../types";
import { isDisposition, type Disposition } from "./contract";

/**
 * Demo-floor reconciler. The only approved path in this wave is decide().
 * A lower candidate is rewritten up to that floor. An unapproved higher
 * candidate is not applied. This rank is an engineering order so a
 * candidate cannot downgrade the floor. It is not a clinical severity score.
 */

export const RECONCILE_MODULE = "clinical-reconcile/v1";
export const UNAPPROVED_CLINICAL_RULES = "disabled" as const;

const RANK: Record<string, number> = {
  go_now: 40,
  escalate: 40,
  urgent: 40,
  get_care_today: 30,
  "see-clinic": 30,
  see_clinic: 30,
  need_one_more_answer: 20,
  abstain: 20,
  monitor_at_home: 10,
  "self-care": 10,
  self_care: 10,
};

export class ReconcileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReconcileError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export type CandidateInput = {
  disposition: string;
  model_id: string | null;
};

export type DisagreementReason =
  | "candidate_below_floor"
  | "candidate_not_approved"
  | "candidate_unrecognized";

export type DisagreementRecord = {
  floor: Disposition;
  candidate: string;
  candidate_rank: number | null;
  reconciled: Disposition;
  rewritten_to_floor: true;
  reason: DisagreementReason;
  model_id: string | null;
};

export type ReconcileResult = {
  disposition: Disposition;
  disagreement: DisagreementRecord | null;
  fail_open: false;
};

function floorDisposition(floor: Decision | Disposition): Disposition {
  const kind = typeof floor === "string" ? floor : floor?.kind;
  if (!isDisposition(kind)) {
    throw new ReconcileError(
      "floor is not an approved disposition; refusing to invent a lower one",
    );
  }
  return kind;
}

function disagreement(
  floor: Disposition,
  candidate: CandidateInput,
  reason: DisagreementReason,
  candidateRank: number | null,
): DisagreementRecord {
  return {
    floor,
    candidate: candidate.disposition,
    candidate_rank: candidateRank,
    reconciled: floor,
    rewritten_to_floor: true,
    reason,
    model_id: candidate.model_id,
  };
}

export function reconcile(input: {
  floor: Decision | Disposition;
  candidate?: CandidateInput | null;
}): ReconcileResult {
  const floor = floorDisposition(input.floor);
  if (!input.candidate) {
    return { disposition: floor, disagreement: null, fail_open: false };
  }
  const candidate = input.candidate.disposition.trim();
  const normalized: CandidateInput = {
    disposition: candidate,
    model_id: input.candidate.model_id,
  };
  if (candidate === floor) {
    return { disposition: floor, disagreement: null, fail_open: false };
  }
  const rank = RANK[candidate] ?? null;
  if (rank === null) {
    return {
      disposition: floor,
      disagreement: disagreement(floor, normalized, "candidate_unrecognized", null),
      fail_open: false,
    };
  }
  const floorRank = RANK[floor];
  if (rank < floorRank) {
    return {
      disposition: floor,
      disagreement: disagreement(floor, normalized, "candidate_below_floor", rank),
      fail_open: false,
    };
  }
  return {
    disposition: floor,
    disagreement: disagreement(floor, normalized, "candidate_not_approved", rank),
    fail_open: false,
  };
}

/**
 * Telemetry or persistence failure must not replace the safer answer.
 * The returned disposition is computed before the sink runs.
 */
export function reconcileWithTelemetry(
  input: { floor: Decision | Disposition; candidate?: CandidateInput | null },
  sink?: (record: DisagreementRecord) => void,
): ReconcileResult {
  const result = reconcile(input);
  if (result.disagreement && sink) {
    try {
      sink(result.disagreement);
    } catch {
      return result;
    }
  }
  return result;
}
