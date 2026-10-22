"use client";

import { Icon } from "@/components/Icon";
import { t, type Locale } from "@/lib/copy";
import { smsHref } from "@/lib/householdShare";

/**
 * One tap to send the handoff to a community health promoter. Uses the
 * phone's share sheet when it has one, otherwise an SMS link. Nothing is sent
 * by Tunza itself and nothing is logged.
 */
export function ShareHandoff({ locale, text }: { locale: Locale; text: string }) {
  return (
    <a
      href={smsHref(text)}
      onClick={(event) => {
        const nav = navigator as Navigator & {
          share?: (data: { text: string }) => Promise<void>;
        };
        if (typeof nav.share === "function") {
          event.preventDefault();
          nav.share({ text }).catch(() => {
            // Cancelled or unsupported: the person can tap again.
          });
        }
      }}
      className="flex min-h-14 items-center justify-center gap-2 rounded-2xl border border-line bg-raised px-4 text-center text-body font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
    >
      <Icon name="share" className="size-5 text-ink-soft" />
      {t("shareChp", locale)}
    </a>
  );
}
