"use client";

import { useId, useState } from "react";
import { t, type Locale } from "@/lib/copy";
import { outcomeLabel } from "@/lib/referral";
import type { OutcomeCode } from "@/lib/types";

export const OUTCOME_CODES: OutcomeCode[] = [
  "treated",
  "referred_onward",
  "did_not_arrive",
  "unknown",
];

type Props = {
  locale: Locale;
  onSubmit: (outcome: OutcomeCode) => void;
};

/**
 * Closes the loop to the CHP. Codes only: there is no free-text field, so
 * nothing the clinician types can leave this screen.
 */
export function OutcomeForm({ locale, onSubmit }: Props) {
  const name = useId();
  const [chosen, setChosen] = useState<OutcomeCode | null>(null);

  return (
    <form
      className="rounded-2xl border border-line bg-raised px-4 py-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen) onSubmit(chosen);
      }}
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="text-heading font-semibold text-ink">
          {t("outcomeFormHeading", locale)}
        </legend>
        <p className="text-label text-ink-soft">{t("outcomeFormHint", locale)}</p>
        {OUTCOME_CODES.map((code) => (
          <label
            key={code}
            className={`flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border px-3 text-body font-medium text-ink ${
              chosen === code ? "border-action" : "border-line"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={code}
              checked={chosen === code}
              onChange={() => setChosen(code)}
              className="size-4 accent-action"
            />
            {outcomeLabel(code, locale)}
          </label>
        ))}
      </fieldset>
      <button
        type="submit"
        disabled={!chosen}
        className="mt-4 min-h-12 w-full rounded-2xl bg-action px-4 text-body font-semibold text-action-ink disabled:cursor-not-allowed disabled:opacity-40"
      >
        {t("outcomeFormSubmit", locale)}
      </button>
    </form>
  );
}
