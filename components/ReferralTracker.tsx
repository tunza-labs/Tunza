/**
 * One household's referral, every stage in plain words, and the prompt that
 * closes the loop once the facility finishes the visit. Headline and status
 * come from describeReferral(), the single place referral state becomes words.
 */

import { ReferralStatus } from "@/components/ReferralStatus";
import { t, type Locale } from "@/lib/copy";
import {
  chpStepLabel,
  describeReferral,
  OUTCOME_CODES,
  outcomeLabel,
  REFERRAL_STAGES,
  type ReferralAction,
} from "@/lib/referral";
import type { DecisionKind, OutcomeCode, Referral, ReferralStage } from "@/lib/types";

type Props = {
  locale: Locale;
  referral: Referral;
  decisionKind: DecisionKind | null;
  onSend: () => void;
  onTheyLeft: () => void;
  onOutcome: (outcome: OutcomeCode) => void;
  onDemoAdvance?: () => void;
};

function stageTime(referral: Referral, stage: ReferralStage, locale: Locale): string | null {
  const entry = [...referral.history].reverse().find((item) => item.stage === stage);
  if (!entry) return null;
  return new Date(entry.at).toLocaleTimeString(locale === "sw" ? "sw-KE" : "en-KE", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ReferralTracker({
  locale,
  referral,
  decisionKind,
  onSend,
  onTheyLeft,
  onOutcome,
  onDemoAdvance,
}: Props) {
  const view = describeReferral("chp", referral, decisionKind, locale);
  const current = REFERRAL_STAGES.indexOf(referral.stage);
  const actionFor: Partial<Record<ReferralAction, () => void>> = {
    send: onSend,
    travel: onTheyLeft,
  };
  const onAction = view.action ? actionFor[view.action.id] : undefined;
  const action =
    view.action && onAction ? { label: view.action.label, onClick: onAction } : undefined;

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-line bg-raised px-4 py-4">
      <ReferralStatus
        locale={locale}
        role="chp"
        stage={referral.stage}
        stageLabel={view.stageLabel}
        headline={view.headline}
        status={view.status}
        arrivalMinutes={view.arrivalMinutes}
        action={action}
        headingLevel={2}
      />

      <ol className="flex flex-col gap-0" aria-label={t("referralEyebrow", locale)}>
        {REFERRAL_STAGES.map((stage, index) => {
          const state = index < current ? "done" : index === current ? "now" : "next";
          const time = state === "next" ? null : stageTime(referral, stage, locale);
          return (
            <li
              key={stage}
              data-stage={stage}
              data-state={state}
              aria-current={state === "now" ? "step" : undefined}
              className="flex min-h-10 items-start gap-3"
            >
              <span
                aria-hidden="true"
                className={`mt-1 size-4 shrink-0 rounded-full border-2 ${
                  state === "done"
                    ? "border-ink bg-ink"
                    : state === "now"
                      ? "border-action bg-action"
                      : "border-ink-soft bg-raised"
                }`}
              />
              <span className="flex flex-1 flex-col">
                <span
                  className={`text-label ${
                    state === "next" ? "text-ink-soft" : "font-semibold text-ink"
                  }`}
                >
                  {chpStepLabel(stage, locale)}
                  <span className="sr-only">
                    {" — "}
                    {state === "done"
                      ? t("chpStepDone", locale)
                      : state === "now"
                        ? t("chpStepNow", locale)
                        : t("chpStepNext", locale)}
                  </span>
                </span>
                {time ? (
                  <span className="text-caption text-ink-soft tabular-nums">{time}</span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ol>

      {referral.stage === "completed" ? (
        <section
          className="flex flex-col gap-2 rounded-2xl bg-today-soft px-4 py-3"
          aria-labelledby="chp-outcome-prompt"
        >
          <h3 id="chp-outcome-prompt" className="text-body font-semibold text-today">
            {t("chpOutcomePrompt", locale)}
          </h3>
          <p className="text-label text-today">{t("chpOutcomePromptDetail", locale)}</p>
          <div className="mt-1 flex flex-col gap-2">
            {OUTCOME_CODES.map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => onOutcome(code)}
                className="min-h-12 rounded-xl border border-line bg-raised px-3 text-left text-body font-medium text-ink"
              >
                {outcomeLabel(code, locale)}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {onDemoAdvance &&
      !referral.queued &&
      REFERRAL_STAGES.indexOf(referral.stage) < REFERRAL_STAGES.indexOf("completed") ? (
        <details className="rounded-xl border border-dashed border-line px-3 py-2">
          <summary className="min-h-10 cursor-pointer py-2 text-label font-medium text-ink-soft">
            {t("chpDemoControls", locale)}
          </summary>
          <button
            type="button"
            onClick={onDemoAdvance}
            className="mt-2 min-h-12 w-full rounded-xl border border-line px-3 text-left text-label font-medium text-ink"
          >
            {t("chpDemoAdvance", locale)}
          </button>
        </details>
      ) : null}
    </section>
  );
}
