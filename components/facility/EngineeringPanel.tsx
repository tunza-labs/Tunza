import { decisionHeadline } from "@/lib/assessment";
import { t, type Locale } from "@/lib/copy";
import { disagreementReasonLabel, type ShadowReview } from "@/lib/desk";
import { isEngineerView } from "@/lib/engineer";
import type { Role } from "@/lib/types";

type Props = {
  locale: Locale;
  role: Role;
  review: ShadowReview;
};

/**
 * Engineering view of the reconcile disagreement record. Engineers only
 * (build flag), facility role, collapsed by default. It reads the record; it never feeds the displayed
 * answer, which is always decide() on the case answers.
 */
export function EngineeringPanel({ locale, role, review }: Props) {
  if (role !== "facility" || !isEngineerView()) {
    return null;
  }
  const record = review.record;

  return (
    <details
      className="rounded-2xl border border-line bg-raised px-4 py-3"
      data-engineering-panel
    >
      <summary className="cursor-pointer text-label font-medium text-ink">
        {t("engPanelSummary", locale)}
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        <p className="rounded-xl bg-warn-soft px-3 py-2 text-label font-semibold text-warn">
          {t("engPanelLabel", locale)}
        </p>
        <p className="text-label text-ink-soft">{t("engPanelNote", locale)}</p>
        {record ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-label">
            <dt className="font-medium text-ink-soft">{t("engPanelRulesAnswer", locale)}</dt>
            <dd className="font-semibold text-ink">
              {decisionHeadline(review.rulesKind, locale)}
            </dd>
            <dt className="font-medium text-ink-soft">{t("engPanelCandidate", locale)}</dt>
            <dd className="text-ink">
              <code className="font-mono">{record.candidate}</code>
              <span className="block text-caption font-semibold text-warn">
                {t("engPanelLabel", locale)}
              </span>
            </dd>
            <dt className="font-medium text-ink-soft">{t("engPanelModel", locale)}</dt>
            <dd className="text-ink">
              <code className="font-mono">
                {record.model_id ?? t("unknownValue", locale)}
              </code>
            </dd>
            <dt className="font-medium text-ink-soft">{t("engPanelReason", locale)}</dt>
            <dd className="text-ink">{disagreementReasonLabel(record.reason, locale)}</dd>
          </dl>
        ) : (
          <p className="text-label font-medium text-ink">
            {review.candidatePresent
              ? t("engPanelAgreed", locale)
              : t("engPanelNoCandidate", locale)}
          </p>
        )}
      </div>
    </details>
  );
}
