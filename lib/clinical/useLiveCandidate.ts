"use client";

import { useEffect, useState } from "react";
import { isEngineerView } from "@/lib/engineer";
import type { AssessmentAnswers } from "@/lib/types";
import type { CandidateInput } from "./reconcile";

const KEYS = ["who", "awake", "breathing", "drinking", "duration", "mainProblem", "presentation"] as const;

/**
 * Engineer view only. Asks /api/candidate for a shadow answer on the open
 * case. Off unless the engineer flag is set and an id is given. Any failure
 * leaves it null; it never changes the displayed answer.
 */
export function useLiveCandidate(
  id: string | null,
  answers: AssessmentAnswers | null,
): CandidateInput | null {
  const [live, setLive] = useState<{ id: string; candidate: CandidateInput } | null>(null);
  const enabled = isEngineerView() && id !== null && answers !== null;

  useEffect(() => {
    if (!enabled || id === null || answers === null) return;
    let cancelled = false;
    const intake: Record<string, unknown> = {};
    for (const key of KEYS) {
      const value = (answers as Record<string, unknown>)[key];
      if (value !== undefined && value !== null && value !== "") intake[key] = value;
    }
    fetch("/api/candidate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(intake),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { candidate?: CandidateInput | null } | null) => {
        if (!cancelled && body?.candidate) setLive({ id, candidate: body.candidate });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [enabled, id, answers]);

  return enabled && live && live.id === id ? live.candidate : null;
}
