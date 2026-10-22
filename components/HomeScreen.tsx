/**
 * The household landing — the one full-brand surface in the product, carried
 * over from the earlier Tunza app's home screen. The shell paints the whole
 * screen red on this view (chrome and footer included); this component is the
 * content. Everything after this screen wears paper.
 */

import { Icon } from "@/components/Icon";
import { t, type Locale } from "@/lib/copy";

type Props = {
  locale: Locale;
  continueDetail: string | null;
  onStart: () => void;
  onNearby: () => void;
  onContinue: () => void;
  onHealthWorker: () => void;
};

export function HomeScreen({
  locale,
  continueDetail,
  onStart,
  onNearby,
  onContinue,
  onHealthWorker,
}: Props) {
  const card =
    "rounded-2xl border border-white/15 bg-white/10 p-4 text-left text-white transition hover:bg-white/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white";
  return (
    <section className="flex min-h-full grow flex-col text-white">
      <div className="mt-10">
        <h1 className="text-[3rem] font-bold leading-none tracking-tight">Tunza</h1>
        <p className="mt-3 text-heading font-normal text-white/85">
          {t("homeTagline", locale)}
        </p>
      </div>

      <button
        type="button"
        onClick={onStart}
        className="mt-8 min-h-14 rounded-2xl bg-raised px-4 text-body font-semibold text-action focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        {t("homeGetStarted", locale)}
      </button>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <button type="button" onClick={onStart} className={card}>
          <Icon name="thermometer" className="mb-2 size-6 text-white/85" />
          <p className="text-label font-semibold">{t("homeCardAssessTitle", locale)}</p>
          <p className="mt-1 text-caption text-white/70">
            {t("homeCardAssessDesc", locale)}
          </p>
        </button>
        <button type="button" onClick={onNearby} className={card}>
          <Icon name="pin" className="mb-2 size-6 text-white/85" />
          <p className="text-label font-semibold">{t("homeCardNearbyTitle", locale)}</p>
          <p className="mt-1 text-caption text-white/70">
            {t("homeCardNearbyDesc", locale)}
          </p>
        </button>
        {continueDetail ? (
          <button type="button" onClick={onContinue} className={`${card} col-span-2`}>
            <Icon name="arrow" className="mb-2 size-6 text-white/85" />
            <p className="text-label font-semibold">
              {t("homeCardContinueTitle", locale)}
            </p>
            <p className="mt-1 text-caption text-white/70">{continueDetail}</p>
          </button>
        ) : null}
      </div>

      <p className="mt-auto pt-10 text-label text-white/70">
        {t("homeMission", locale)}
      </p>
      <button
        type="button"
        onClick={onHealthWorker}
        className="mt-3 min-h-12 self-start text-label font-medium text-white underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        {t("homeHealthWorker", locale)}
      </button>
    </section>
  );
}
