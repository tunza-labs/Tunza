"use client";

import { useEffect, useId, useRef } from "react";
import { PatientHandoff } from "@/components/PatientHandoff";
import { AssessmentSections } from "@/components/facility/AssessmentSections";
import { EngineeringPanel } from "@/components/facility/EngineeringPanel";
import { OutcomeForm } from "@/components/facility/OutcomeForm";
import { fill, t, type Locale } from "@/lib/copy";
import type { DeskRow, ShadowReview, TimelineEntry } from "@/lib/desk";
import type { HandoffFact } from "@/lib/handoff";
import type { OutcomeCode, Role } from "@/lib/types";

type Props = {
  locale: Locale;
  role: Role;
  row: DeskRow;
  summary: string;
  asked: string;
  handoff: { why: string; known: HandoffFact[]; missing: string[] };
  review: ShadowReview;
  timeline: TimelineEntry[];
  /** The next lifecycle step for this facility, from describeReferral(). */
  stageAction?: { label: string; onClick: () => void };
  /** Ask the sender one missing fact before deciding. */
  askMore?: () => void;
  outcomeDue: boolean;
  outcomeText: string | null;
  onBack: () => void;
  onAccept: () => void;
  onRedirect: () => void;
  onDecline: () => void;
  onOutcome: (outcome: OutcomeCode) => void;
};

/**
 * One referral, in the order a busy clinician reads it: the one-line
 * summary, what was asked of this facility, the decision buttons, then the
 * handoff facts, the structured assessment, and the timeline.
 */
export function CaseView({
  locale,
  role,
  row,
  summary,
  asked,
  handoff,
  review,
  timeline,
  stageAction,
  askMore,
  outcomeDue,
  outcomeText,
  onBack,
  onAccept,
  onRedirect,
  onDecline,
  onOutcome,
}: Props) {
  const timelineId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Opening a case moves keyboard focus to its summary line.
  useEffect(() => {
    headingRef.current?.focus();
  }, [row.id]);

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={onBack}
        className="min-h-10 self-start text-label font-medium text-ink-soft underline"
      >
        {t("deskBackToInbox", locale)}
      </button>

      <header className="flex flex-col gap-2" aria-live="polite">
        <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-soft">
          {row.sourceLabel} · {t("referralEyebrow", locale)} · {row.stageLabel}
        </p>
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-heading font-bold tracking-tight text-ink outline-none"
        >
          {summary}
        </h1>
        <p className="text-body text-ink">
          <span className="font-semibold">{t("deskAskedLabel", locale)}: </span>
          {asked}
        </p>
        <p className="text-label text-ink-soft tabular-nums">{row.waitedLabel}</p>
        {!row.atDesk ? (
          <p className="text-label font-medium text-ink-soft">
            {fill(t("deskAtOtherTpl", locale), { f: row.facilityName })}
          </p>
        ) : null}
        {outcomeText ? (
          <p className="text-body font-semibold text-ink">
            {fill(t("outcomeReturnedTpl", locale), { o: outcomeText })}
          </p>
        ) : null}
      </header>

      {row.canAccept || row.canRedirect || stageAction || row.redirectBlocked || askMore ? (
        <div className="flex flex-col gap-2">
          {row.canAccept ? (
            <button
              type="button"
              onClick={onAccept}
              className="min-h-12 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink"
            >
              {t("actionAccept", locale)}
            </button>
          ) : stageAction ? (
            <button
              type="button"
              onClick={stageAction.onClick}
              className="min-h-12 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink"
            >
              {stageAction.label}
            </button>
          ) : null}
          {row.canRedirect ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={onRedirect}
                  className="min-h-12 rounded-xl border border-line bg-raised px-3 text-body font-medium text-ink"
                >
                  {t("deskActionRedirect", locale)}
                </button>
                <button
                  type="button"
                  onClick={onDecline}
                  className="min-h-12 rounded-xl border border-line bg-raised px-3 text-body font-medium text-ink"
                >
                  {t("deskActionDecline", locale)}
                </button>
              </div>
              {row.redirectTo ? (
                <p className="text-label text-ink-soft">
                  {fill(t("deskRedirectToTpl", locale), { f: row.redirectTo })}
                </p>
              ) : null}
            </>
          ) : null}
          {row.redirectBlocked ? (
            <p className="text-label font-medium text-today">
              {t("deskNoOpenFacility", locale)}
            </p>
          ) : null}
          {askMore ? (
            <button
              type="button"
              onClick={askMore}
              className="min-h-12 rounded-xl border border-line bg-raised px-3 text-left text-body font-medium text-ink"
            >
              {t("askMore", locale)}
            </button>
          ) : null}
        </div>
      ) : null}

      {outcomeDue ? <OutcomeForm locale={locale} onSubmit={onOutcome} /> : null}

      <PatientHandoff
        locale={locale}
        why={handoff.why}
        known={handoff.known}
        missing={handoff.missing}
      />

      <AssessmentSections locale={locale} rendered={review.rendered} />

      <section
        aria-labelledby={timelineId}
        className="rounded-2xl border border-line bg-raised px-4 py-4"
      >
        <h2 id={timelineId} className="text-heading font-semibold text-ink">
          {t("deskTimelineHeading", locale)}
        </h2>
        <ol className="mt-2 flex flex-col gap-2">
          {timeline.map((entry) => (
            <li key={entry.key} className="grid grid-cols-[4.5rem_1fr] gap-2 text-label">
              <time dateTime={entry.at} className="text-ink-soft tabular-nums">
                {clock(entry.at)}
              </time>
              <span className="text-ink">
                <span className="font-semibold">{entry.stageLabel}</span>
                {" · "}
                {entry.byLabel}
                {entry.note ? (
                  <span className="block text-ink-soft">{entry.note}</span>
                ) : null}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <EngineeringPanel locale={locale} role={role} review={review} />
    </div>
  );
}

/** 24-hour clock time; the full timestamp stays on the <time> element. */
function clock(iso: string): string {
  const date = new Date(iso);
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
