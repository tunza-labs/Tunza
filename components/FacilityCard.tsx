/** V1 care-path component. Reused across household, CHP, and facility. */

import { t, type Locale } from "@/lib/copy";

type Props = {
  locale: Locale;
  name: string;
  travelMinutes?: number | null;
  distanceKm?: number | null;
  canHandle: boolean;
  services?: string[];
  address?: string;
  statusLabel: string;
  /** Overrides the default "Facility" eyebrow (household: "Nearest facility"). */
  eyebrow?: string;
};

function TemplateNumber({
  template,
  token,
  value,
}: {
  template: string;
  token: string;
  value: string;
}) {
  const [before, after] = template.split(token);
  return (
    <>
      {before}
      <span className="tabular-nums font-semibold text-ink">{value}</span>
      {after}
    </>
  );
}

export function FacilityCard({
  locale,
  name,
  travelMinutes = null,
  distanceKm = null,
  canHandle,
  services,
  address,
  statusLabel,
  eyebrow,
}: Props) {
  return (
    <article className="rounded-2xl border border-line bg-raised px-4 py-4">
      <p className="text-caption font-medium uppercase tracking-[0.12em] text-ink-soft">
        {eyebrow ?? t("facilityEyebrow", locale)}
      </p>
      <h2 className="mt-1 text-heading font-semibold text-ink">{name}</h2>
      {travelMinutes !== null ? (
        <p className="mt-2 text-body font-medium text-ink-soft">
          <TemplateNumber
            template={t("facilityTravelTpl", locale)}
            token="{m}"
            value={String(travelMinutes)}
          />
        </p>
      ) : distanceKm !== null ? (
        <p className="mt-2 text-body font-medium text-ink-soft">
          <TemplateNumber
            template={t("facilityDistanceTpl", locale)}
            token="{km}"
            value={distanceKm.toFixed(1)}
          />
        </p>
      ) : null}
      <p
        className={`mt-2 text-body font-semibold ${canHandle ? "text-ink" : "text-urgent"}`}
      >
        {statusLabel}
      </p>
      {services && services.length > 0 ? (
        <p className="mt-2 text-label text-ink-soft">{services.join(" · ")}</p>
      ) : address ? (
        <p className="mt-2 text-label text-ink-soft">{address}</p>
      ) : null}
    </article>
  );
}
