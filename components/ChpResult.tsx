/**
 * The CHP result: the decide() answer, the danger signs it found, and the
 * structured handoff, one tap to send. Only the deterministic decision is
 * shown here; the shadow model answer is for professionals and never reaches
 * this screen.
 */

import { DecisionResult } from "@/components/DecisionResult";
import { PatientHandoff } from "@/components/PatientHandoff";
import { decisionHeadline, decisionStatus } from "@/lib/assessment";
import { fill, t, type Locale } from "@/lib/copy";
import type { HandoffFact } from "@/lib/handoff";
import type { Decision } from "@/lib/types";

export type HandoffState =
  | { kind: "none" }
  | { kind: "queued" }
  | { kind: "sent"; facility: string };

type Props = {
  locale: Locale;
  householdLabel: string;
  decision: Decision;
  why: string;
  facts: HandoffFact[];
  missing: string[];
  handoff: HandoffState;
  canSend: boolean;
  onSend: () => void;
  onTrack: () => void;
  onFinishAnswers: () => void;
  onBack: () => void;
};

export function ChpResult({
  locale,
  householdLabel,
  decision,
  why,
  facts,
  missing,
  handoff,
  canSend,
  onSend,
  onTrack,
  onFinishAnswers,
  onBack,
}: Props) {
  const kind = decision.kind;
  const danger = decision.dangerSignKeys.map((key) => t(key, locale));

  const action = canSend
    ? { label: t("chpSendHandoff", locale), onClick: onSend }
    : handoff.kind === "sent"
      ? { label: t("chpTrackReferral", locale), onClick: onTrack }
      : kind === "need_one_more_answer"
        ? { label: t("chpFinishAnswers", locale), onClick: onFinishAnswers }
        : undefined;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-soft">
        {householdLabel}
      </p>
      <DecisionResult
        locale={locale}
        kind={kind}
        headline={decisionHeadline(kind, locale)}
        status={decisionStatus(kind, locale)}
        action={action}
        why={decision.reasonKeys.map((key) => t(key, locale))}
      >
        {danger.length > 0 ? (
          <aside
            className="rounded-2xl bg-urgent-soft px-4 py-3 text-urgent"
            data-named-state="danger_sign"
          >
            <p className="text-caption font-medium uppercase tracking-[0.12em]">
              {t("chpDangerFound", locale)}
            </p>
            <ul className="mt-1 flex flex-col gap-1 text-body font-semibold">
              {danger.map((sign) => (
                <li key={sign}>{sign}</li>
              ))}
            </ul>
          </aside>
        ) : kind !== "go_now" ? (
          <p className="text-label font-medium text-ink-soft">
            {t("chpNoDangerFound", locale)}
          </p>
        ) : null}

        {handoff.kind === "queued" ? (
          <aside
            className="rounded-2xl bg-warn-soft px-4 py-3 text-warn"
            role="status"
            data-named-state="offline"
          >
            <p className="text-body font-semibold">{t("chpQueuedNotice", locale)}</p>
            <p className="mt-1 text-label">{t("chpQueuedDetail", locale)}</p>
          </aside>
        ) : null}

        {handoff.kind === "sent" ? (
          <p className="text-body font-semibold text-ink" role="status">
            {fill(t("chpSentTpl", locale), { f: handoff.facility })}
          </p>
        ) : null}

        {kind === "monitor_at_home" ? (
          <p className="text-body font-semibold text-ink">
            {t("chpFollowUpTomorrow", locale)}
          </p>
        ) : null}
      </DecisionResult>

      <PatientHandoff locale={locale} why={why} known={facts} missing={missing} />

      <button
        type="button"
        onClick={onBack}
        className="min-h-12 rounded-2xl border border-line px-4 text-body font-medium text-ink"
      >
        {t("chpBackToList", locale)}
      </button>
    </div>
  );
}
