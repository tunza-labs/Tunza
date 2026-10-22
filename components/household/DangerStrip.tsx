/**
 * The always-on danger strip for the household surface, built from the
 * Warning state. Calm: the signs that mean "go now", in the watch tone. Alert:
 * the signs that are present, in the emergency tone, announced assertively.
 * It never decides anything itself — the alert state is driven only by the
 * decide() output the caller passes in.
 */

import { Warning } from "@/components/Warning";
import { t, type CopyKey, type Locale } from "@/lib/copy";
import { warningCopy } from "@/lib/failures";

/** Mirrors the watch signs decide() returns; a test keeps the two in step. */
export const HOUSEHOLD_WATCH_KEYS: CopyKey[] = [
  "watchNotWaking",
  "watchBreathingHard",
  "watchCannotDrink",
  "watchSeizureBleeding",
];

type Props = {
  locale: Locale;
  /** Signs present now. null means calm (no danger sign present). */
  danger: CopyKey[] | null;
  /** Watch signs to show when calm; defaults to the household list. */
  watchKeys?: CopyKey[];
};

export function DangerStrip({ locale, danger, watchKeys = HOUSEHOLD_WATCH_KEYS }: Props) {
  if (danger) {
    const copy = warningCopy("danger_sign", locale);
    return (
      <section aria-label={t("dangerStripLabel", locale)} data-danger-strip="alert">
        <Warning
          named="danger_sign"
          eyebrow={copy.eyebrow}
          title={copy.title}
          body={danger.length > 0 ? danger.map((key) => t(key, locale)).join(" · ") : copy.body}
          assertive
        />
      </section>
    );
  }
  const copy = warningCopy("watch_sign", locale);
  return (
    <section aria-label={t("dangerStripLabel", locale)} data-danger-strip="calm">
      <Warning
        named="watch_sign"
        eyebrow={t("dangerStripLabel", locale)}
        title={copy.title}
        body={watchKeys.map((key) => t(key, locale)).join(" · ")}
      />
    </section>
  );
}
