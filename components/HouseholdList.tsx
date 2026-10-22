/** The CHP work list: most urgent household first, one reason per row. */

import { StatusChip } from "@/components/StatusChip";
import { fill, t, type Locale } from "@/lib/copy";
import type { HouseholdStatus } from "@/lib/chp";

export type HouseholdRow = {
  id: string;
  label: string;
  member: string;
  status: HouseholdStatus;
  reason: string;
};

type Props = {
  locale: Locale;
  rows: HouseholdRow[];
  attentionCount: number;
  onOpen: (id: string) => void;
};

const EDGE: Record<HouseholdStatus, string> = {
  attention: "border-l-urgent",
  referral: "border-l-watch",
  followup: "border-l-today",
  stable: "border-l-line",
};

export function HouseholdList({ locale, rows, attentionCount, onOpen }: Props) {
  return (
    <section className="flex flex-col gap-3" aria-labelledby="chp-list-title">
      <header className="flex flex-col gap-1">
        <h1
          id="chp-list-title"
          className="text-decision font-bold tracking-tight text-ink"
        >
          {t("chpTitle", locale)}
        </h1>
        <p className="text-body font-semibold text-ink">
          <span className="tabular-nums">
            {fill(t("chpCountTpl", locale), { n: rows.length })}
          </span>
          {attentionCount > 0 ? (
            <>
              {" · "}
              <span className="tabular-nums text-urgent">
                {fill(t("chpAttentionCountTpl", locale), { n: attentionCount })}
              </span>
            </>
          ) : null}
        </p>
        <p className="text-caption text-ink-soft">{t("chpDemoNotice", locale)}</p>
      </header>

      <ul className="flex flex-col gap-2">
        {rows.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              onClick={() => onOpen(row.id)}
              data-household={row.id}
              className={`flex min-h-16 w-full flex-col gap-1.5 rounded-2xl border border-line border-l-4 bg-raised px-4 py-3 text-left ${EDGE[row.status]}`}
            >
              <span className="flex w-full flex-wrap items-center justify-between gap-2">
                <span className="text-body font-semibold text-ink">{row.label}</span>
                <StatusChip status={row.status} locale={locale} />
              </span>
              <span className="text-label font-medium text-ink">{row.reason}</span>
              <span className="text-label text-ink-soft">{row.member}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
