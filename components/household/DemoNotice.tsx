"use client";

import { useCallback, useId, useState } from "react";
import { Icon } from "@/components/Icon";
import { t, type Locale } from "@/lib/copy";

const SEEN_KEY = "tunza.v2.noticeSeen";

function readSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

/** Whether this phone has already seen the honest-limits notice. */
export function useNoticeSeen(): { seen: boolean; markSeen: () => void } {
  const [seen, setSeen] = useState(readSeen);
  const markSeen = useCallback(() => {
    setSeen(true);
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {
      // Storage can be blocked; the notice simply shows again next time.
    }
  }, []);
  return { seen, markSeen };
}

/** The honest limits: a demonstration, not a diagnosis. */
export function DemoNotice({ locale, onDismiss }: { locale: Locale; onDismiss: () => void }) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={titleId}
      className="flex flex-col gap-3 rounded-2xl border border-line bg-raised px-4 py-4"
      data-demo-notice
    >
      <div className="flex items-center gap-2 text-ink">
        <Icon name="info" className="size-6 text-ink-soft" />
        <h2 id={titleId} className="text-heading font-semibold">
          {t("noticeTitle", locale)}
        </h2>
      </div>
      <p className="text-body text-ink">{t("noticeBody", locale)}</p>
      <button
        type="button"
        onClick={onDismiss}
        className="min-h-12 self-start rounded-2xl border border-line px-4 text-body font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        {t("noticeDismiss", locale)}
      </button>
    </section>
  );
}
