"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { fill, t, type Locale } from "@/lib/copy";
import type { DeskRow } from "@/lib/desk";
import type { DecisionKind } from "@/lib/types";

const ANSWER_TONE: Record<DecisionKind, string> = {
  go_now: "text-urgent",
  get_care_today: "text-today",
  need_one_more_answer: "text-ink",
  monitor_at_home: "text-watch",
};

type Props = {
  locale: Locale;
  rows: DeskRow[];
  onOpen: (id: string) => void;
  onAccept: (id: string) => void;
  onRedirect: (id: string) => void;
  onDecline: (id: string) => void;
  /** Return keyboard focus to this row's open button (after "Back"). */
  focusRowId?: string | null;
  children?: ReactNode;
};

const SMALL_BUTTON =
  "min-h-9 w-full rounded-lg border px-2 text-left text-caption font-semibold";

/** The professional inbox: one row per referral, urgent first. */
export function DeskInbox({
  locale,
  rows,
  onOpen,
  onAccept,
  onRedirect,
  onDecline,
  focusRowId,
  children,
}: Props) {
  const titleId = useId();
  const tableRef = useRef<HTMLTableElement>(null);
  const [initialFocusRowId] = useState(focusRowId);

  // Returning from a case view puts focus back on the row that was opened.
  useEffect(() => {
    if (!initialFocusRowId) return;
    const buttons = tableRef.current?.querySelectorAll<HTMLButtonElement>(
      "button[data-open-row]",
    );
    buttons?.forEach((button) => {
      if (button.dataset.openRow === initialFocusRowId) button.focus();
    });
  }, [initialFocusRowId]);
  const waiting = rows.filter((row) => row.atDesk && !row.closed).length;

  return (
    <section className="flex flex-col gap-4" aria-labelledby={titleId}>
      <header className="flex flex-col gap-1">
        <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-soft">
          {t("demoLabel", locale)}
        </p>
        <h1 id={titleId} className="text-decision font-bold tracking-tight text-ink">
          {t("deskTitle", locale)}
        </h1>
        <p className="text-body font-semibold text-ink tabular-nums">
          {fill(t("deskWaitingCountTpl", locale), { n: waiting })}
        </p>
        <p className="text-label text-ink-soft">{t("deskDemoNotice", locale)}</p>
      </header>

      {children}

      <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
        <table ref={tableRef} className="w-full border-collapse text-left text-label text-ink">
          <caption className="px-3 pt-3 text-left text-caption text-ink-soft">
            {t("deskTableCaption", locale)}
          </caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="px-3 py-2 text-caption font-medium text-ink-soft">
                {t("deskColPatient", locale)}
              </th>
              <th scope="col" className="px-2 py-2 text-caption font-medium text-ink-soft">
                {t("deskColAnswer", locale)}
              </th>
              <th scope="col" className="px-2 py-2 text-caption font-medium text-ink-soft">
                {t("deskColStage", locale)}
              </th>
              <th scope="col" className="px-2 py-2 text-caption font-medium text-ink-soft">
                {t("deskColActions", locale)}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const inactive = row.closed || !row.atDesk;
              return (
                <tr
                  key={row.id}
                  data-row-id={row.id}
                  className="border-b border-line align-top last:border-b-0"
                >
                  <th scope="row" className="px-3 py-2 font-normal">
                    <button
                      type="button"
                      data-open-row={row.id}
                      onClick={() => onOpen(row.id)}
                      className="text-left font-semibold text-ink underline decoration-line underline-offset-2"
                    >
                      {row.patientLabel}
                    </button>
                    <span className="block text-caption text-ink-soft tabular-nums">
                      {row.waitedLabel}
                    </span>
                    <span className="block text-caption text-ink-soft">{row.sourceLabel}</span>
                  </th>
                  <td className="px-2 py-2">
                    <span className={`block font-semibold ${ANSWER_TONE[row.kind]}`}>
                      {row.answerLabel}
                    </span>
                    <span className="block text-caption text-ink-soft">
                      {row.topDanger ?? t("deskNoDangerFlagged", locale)}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <span className={inactive ? "text-ink-soft" : "font-medium"}>
                      {row.stageLabel}
                    </span>
                    {!row.atDesk ? (
                      <span className="block text-caption text-ink-soft">
                        {fill(t("deskAtOtherTpl", locale), { f: row.facilityName })}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex min-w-24 flex-col gap-1">
                      {row.canAccept ? (
                        <button
                          type="button"
                          onClick={() => onAccept(row.id)}
                          aria-label={`${t("actionAccept", locale)}: ${row.patientLabel}`}
                          className={`${SMALL_BUTTON} border-action bg-action text-action-ink`}
                        >
                          {t("actionAccept", locale)}
                        </button>
                      ) : null}
                      {row.canRedirect ? (
                        <>
                          <button
                            type="button"
                            onClick={() => onRedirect(row.id)}
                            aria-label={`${t("deskActionRedirect", locale)}: ${row.patientLabel}`}
                            className={`${SMALL_BUTTON} border-line text-ink`}
                          >
                            {t("deskActionRedirect", locale)}
                          </button>
                          <button
                            type="button"
                            onClick={() => onDecline(row.id)}
                            aria-label={`${t("deskActionDecline", locale)}: ${row.patientLabel}`}
                            className={`${SMALL_BUTTON} border-line text-ink`}
                          >
                            {t("deskActionDecline", locale)}
                          </button>
                        </>
                      ) : null}
                      {row.redirectBlocked ? (
                        <span className="text-caption font-medium text-today">
                          {t("deskNoOpenFacility", locale)}
                        </span>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
