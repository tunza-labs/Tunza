/** V1 care-path component. Reused across household, CHP, and facility. */

"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { t, type Locale } from "@/lib/copy";
import type { DecisionKind } from "@/lib/types";

type Props = {
  locale: Locale;
  kind: DecisionKind;
  headline: string;
  status: string;
  action?: { label: string; onClick: () => void };
  why?: string[];
  /** Support shown between the verdict and the action (household: why, what to do, where). */
  lead?: ReactNode;
  /** Move focus to the verdict when it appears, so it is announced first. */
  autoFocus?: boolean;
  children?: ReactNode;
};

const HEADLINE_COLOR: Record<DecisionKind, string> = {
  go_now: "text-urgent",
  get_care_today: "text-today",
  monitor_at_home: "text-watch",
  need_one_more_answer: "text-ink",
};

export function DecisionResult({
  locale,
  kind,
  headline,
  status,
  action,
  why,
  lead,
  autoFocus = false,
  children,
}: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (autoFocus) {
      headingRef.current?.focus();
    }
  }, [autoFocus, kind]);

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-soft">
          {t("nextAction", locale)}
        </p>
        <h1
          ref={headingRef}
          tabIndex={-1}
          className={`text-decision font-bold tracking-tight outline-none ${HEADLINE_COLOR[kind]}`}
        >
          {headline}
        </h1>
        <p className="text-body font-semibold text-ink">{status}</p>
      </header>

      {lead}

      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="min-h-14 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
        >
          {action.label}
        </button>
      ) : null}

      {children}

      {why && why.length > 0 ? (
        <details className="rounded-2xl border border-line bg-raised px-4 py-3">
          <summary className="cursor-pointer text-label font-medium text-ink">
            {t("whyThis", locale)}
          </summary>
          <ul className="mt-3 flex flex-col gap-2 text-label text-ink-soft">
            {why.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
