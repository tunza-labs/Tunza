"use client";

/**
 * The CHP's intake: all six structured fields on one screen, because a
 * trained CHP answers faster than a caregiver walked through one question at
 * a time. Every field has "I don't know". The note feeds decide() and the
 * handoff; it is never logged or sent anywhere else.
 */

import { useState } from "react";
import {
  answeredCount,
  INTAKE_FIELDS,
  intakeValue,
  setIntakeValue,
  type IntakeField,
} from "@/lib/chp";
import { fill, t, type Locale } from "@/lib/copy";
import { questionContent } from "@/lib/questions";
import type { AssessmentAnswers } from "@/lib/types";

type Props = {
  locale: Locale;
  householdLabel: string;
  initial: AssessmentAnswers;
  onSubmit: (answers: AssessmentAnswers) => void;
  onCancel: () => void;
};

function fieldContent(
  field: IntakeField,
  answers: AssessmentAnswers,
  locale: Locale,
): { question: string; choices: { id: string; label: string }[] } {
  if (field === "who") {
    return {
      question: t("chpWhoQuestion", locale),
      choices: [
        { id: "child", label: t("whoChild", locale) },
        { id: "household_adult", label: t("chpMemberAdult", locale) },
      ],
    };
  }
  const content = questionContent(field, answers.who, locale);
  return { question: content.question, choices: content.choices };
}

export function ChpIntake({ locale, householdLabel, initial, onSubmit, onCancel }: Props) {
  const [answers, setAnswers] = useState<AssessmentAnswers>(initial);
  const answered = answeredCount(answers);

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(answers);
      }}
    >
      <header className="flex flex-col gap-1">
        <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-soft">
          {householdLabel}
        </p>
        <h1 className="text-decision font-bold tracking-tight text-ink">
          {t("chpIntakeTitle", locale)}
        </h1>
        <p className="text-label font-medium text-ink-soft tabular-nums" aria-live="polite">
          {fill(t("chpIntakeAnsweredTpl", locale), {
            n: answered,
            total: INTAKE_FIELDS.length,
          })}
        </p>
      </header>

      {INTAKE_FIELDS.map((field) => {
        const content = fieldContent(field, answers, locale);
        const current = intakeValue(answers, field);
        const options = [
          ...content.choices,
          { id: "unknown", label: t("dontKnow", locale) },
        ];
        return (
          <fieldset key={field} data-field={field} className="flex flex-col gap-2">
            <legend className="mb-2 text-body font-semibold text-ink">
              {content.question}
            </legend>
            <div className="grid grid-cols-2 gap-2">
              {options.map((option) => {
                const checked = current === option.id;
                return (
                  <label
                    key={option.id}
                    className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-label font-medium text-ink ${
                      checked ? "border-action bg-raised" : "border-line bg-raised"
                    } has-focus-visible:outline-2 has-focus-visible:outline-action`}
                  >
                    <input
                      type="radio"
                      name={field}
                      value={option.id}
                      checked={checked}
                      onChange={() =>
                        setAnswers((prev) => setIntakeValue(prev, field, option.id))
                      }
                      className="size-5 shrink-0 accent-action"
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        );
      })}

      <div className="flex flex-col gap-2">
        <label htmlFor="chp-note" className="text-body font-semibold text-ink">
          {t("chpNoteLabel", locale)}
        </label>
        <textarea
          id="chp-note"
          aria-describedby="chp-note-hint"
          value={answers.presentation}
          onChange={(event) => {
            const text = event.target.value;
            setAnswers((prev) => ({ ...prev, presentation: text }));
          }}
          rows={3}
          placeholder={t("whatPlaceholder", locale)}
          autoComplete="off"
          className="min-h-24 rounded-2xl border border-line bg-raised px-4 py-3 text-body text-ink outline-none focus:border-action"
        />
        <p id="chp-note-hint" className="text-caption text-ink-soft">
          {t("chpNoteHint", locale)}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <button
          type="submit"
          className="min-h-14 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink"
        >
          {t("chpSeeResult", locale)}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="min-h-12 rounded-2xl border border-line px-4 text-body font-medium text-ink"
        >
          {t("chpCancel", locale)}
        </button>
      </div>
    </form>
  );
}
