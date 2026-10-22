/**
 * The CHP's day in three numbers. It takes counts, not households, so no
 * household label or patient detail can reach this view or anything that
 * copies it.
 */

import { t, type Locale } from "@/lib/copy";
import type { DailySummaryCounts } from "@/lib/chp";

export function DailySummary({
  locale,
  counts,
}: {
  locale: Locale;
  counts: DailySummaryCounts;
}) {
  const items = [
    { id: "seen", label: t("chpSummarySeen", locale), value: counts.seen },
    { id: "referred", label: t("chpSummaryReferred", locale), value: counts.referred },
    { id: "followups", label: t("chpSummaryFollowUps", locale), value: counts.followUps },
  ];
  return (
    <section
      className="rounded-2xl border border-line bg-raised px-4 py-3"
      aria-labelledby="chp-summary-title"
    >
      <h2
        id="chp-summary-title"
        className="text-caption font-medium uppercase tracking-[0.12em] text-ink-soft"
      >
        {t("chpSummaryTitle", locale)}
      </h2>
      <dl className="mt-2 grid grid-cols-3 gap-2">
        {items.map((item) => (
          <div key={item.id} data-summary={item.id} className="flex flex-col-reverse">
            <dt className="text-label font-medium text-ink-soft">{item.label}</dt>
            <dd className="text-decision font-bold tabular-nums text-ink">{item.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-caption text-ink-soft">{t("chpSummaryPrivacy", locale)}</p>
    </section>
  );
}
