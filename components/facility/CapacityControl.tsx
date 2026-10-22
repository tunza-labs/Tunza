"use client";

import { useId } from "react";
import { t, type Locale } from "@/lib/copy";
import { CAPACITY_OPTIONS, capacityLabel } from "@/lib/desk";
import type { FacilityCapacity } from "@/lib/types";

type Props = {
  locale: Locale;
  facilities: { id: string; name: string }[];
  deskFacilityId: string;
  capacity: FacilityCapacity;
  onDeskFacility: (facilityId: string) => void;
  onCapacity: (capacity: FacilityCapacity) => void;
};

/**
 * Which demo facility this desk acts as, and whether it can take referrals
 * now. The redirect logic reads the capacity set here.
 */
export function CapacityControl({
  locale,
  facilities,
  deskFacilityId,
  capacity,
  onDeskFacility,
  onCapacity,
}: Props) {
  const name = useId();
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-line bg-raised px-4 py-3">
      <label className="flex flex-col gap-1">
        <span className="text-caption font-medium uppercase tracking-[0.12em] text-ink-soft">
          {t("deskActingAs", locale)}
        </span>
        <select
          value={deskFacilityId}
          onChange={(event) => onDeskFacility(event.target.value)}
          className="min-h-10 rounded-xl border border-line bg-raised px-2 text-label font-medium text-ink"
        >
          {facilities.map((facility) => (
            <option key={facility.id} value={facility.id}>
              {facility.name}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-label font-medium text-ink">
          {t("deskCapacityLegend", locale)}
        </legend>
        <div className="flex flex-wrap gap-2">
          {CAPACITY_OPTIONS.map((option) => (
            <label
              key={option}
              className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-xl border px-3 text-label font-medium text-ink ${
                capacity === option ? "border-action" : "border-line"
              }`}
            >
              <input
                type="radio"
                name={name}
                value={option}
                checked={capacity === option}
                onChange={() => onCapacity(option)}
                className="size-4 accent-action"
              />
              {capacityLabel(option, locale)}
            </label>
          ))}
        </div>
      </fieldset>
      <p className="text-caption text-ink-soft">{t("deskCapacityHint", locale)}</p>
    </section>
  );
}
