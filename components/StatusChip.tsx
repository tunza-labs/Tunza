/** CHP work-list chip. Words carry the meaning; color only reinforces it. */

import { t, type Locale } from "@/lib/copy";
import { STATUS_LABEL_KEY, type HouseholdStatus } from "@/lib/chp";

/** Token pairs (text, fill). tests/contrast.test.ts checks each one. */
export const CHIP_TOKENS: Record<HouseholdStatus, [string, string]> = {
  attention: ["urgent", "urgent-soft"],
  referral: ["watch", "watch-soft"],
  followup: ["today", "today-soft"],
  stable: ["ink-soft", "paper"],
};

const CHIP_CLASS: Record<HouseholdStatus, string> = {
  attention: "text-urgent bg-urgent-soft",
  referral: "text-watch bg-watch-soft",
  followup: "text-today bg-today-soft",
  stable: "text-ink-soft bg-paper",
};

export function StatusChip({
  status,
  locale,
}: {
  status: HouseholdStatus;
  locale: Locale;
}) {
  return (
    <span
      data-status={status}
      className={`inline-flex min-h-7 items-center rounded-xl px-2.5 text-label font-semibold ${CHIP_CLASS[status]}`}
    >
      {t(STATUS_LABEL_KEY[status], locale)}
    </span>
  );
}

export { CHIP_CLASS };
