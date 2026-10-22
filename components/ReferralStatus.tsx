/** V1 care-path component. Reused across household, CHP, and facility. */

import { t, type Locale } from "@/lib/copy";
import type { ReferralStage, Role } from "@/lib/types";
import type { ReactNode } from "react";

type Props = {
  locale: Locale;
  role: Role;
  stage: ReferralStage;
  stageLabel: string;
  headline: string;
  status: string;
  arrivalMinutes: number | null;
  action?: { label: string; onClick: () => void };
  /** 1 when the status is the page; 2 when it sits under a page heading. */
  headingLevel?: 1 | 2;
  children?: ReactNode;
};

/** Render a "{m}" copy template with the number in tabular figures. */
function TemplateNumber({
  template,
  value,
}: {
  template: string;
  value: number;
}) {
  const [before, after] = template.split("{m}");
  return (
    <>
      {before}
      <span className="tabular-nums">{value}</span>
      {after}
    </>
  );
}

export function ReferralStatus({
  locale,
  role,
  stage,
  stageLabel,
  headline,
  status,
  arrivalMinutes,
  action,
  headingLevel = 1,
  children,
}: Props) {
  const showArrivalInHeadline =
    role === "facility" && stage === "accepted" && arrivalMinutes !== null;
  const Heading = headingLevel === 2 ? "h2" : "h1";

  return (
    <section className="flex flex-col gap-5" aria-live="polite">
      <header className="flex flex-col gap-3">
        <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-soft">
          {t("referralEyebrow", locale)} · {stageLabel}
        </p>
        <Heading
          className={`${headingLevel === 2 ? "text-heading" : "text-decision"} font-bold tracking-tight text-ink`}
        >
          {headline}
          {showArrivalInHeadline ? (
            <>
              {" — "}
              <TemplateNumber
                template={t("expectedArrivalTpl", locale)}
                value={arrivalMinutes}
              />
            </>
          ) : null}
        </Heading>
        <p className="text-body font-semibold text-ink">{status}</p>
        {arrivalMinutes !== null && !showArrivalInHeadline ? (
          <p className="text-body font-semibold text-ink-soft">
            <TemplateNumber template={t("travelTpl", locale)} value={arrivalMinutes} />
          </p>
        ) : null}
      </header>

      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="min-h-14 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink"
        >
          {action.label}
        </button>
      ) : null}

      {children}
    </section>
  );
}
