"use client";

import { useEffect, useState } from "react";
import { FacilityCard } from "@/components/FacilityCard";
import { t, type Locale } from "@/lib/copy";
import { DEMO_FACILITIES } from "@/lib/facilities";
import { decodeGeohashCenter, encodeGeohash } from "@/lib/geohash";
import { categoryLabel, fetchNearbyPlaces, rankPlaces, type RankedPlace } from "@/lib/places";

type Status = "locating" | "ready" | "fallback";

/**
 * Real nearby facilities, ported from the earlier Tunza app. The device's
 * precise position stays in this component (for accurate distances); the
 * server only ever sees the coarse precision-5 geohash cell center. Every
 * failure — no geolocation, permission denied, offline, lookup unconfigured,
 * nothing found — falls back to the demo list with an honest note. Offline,
 * it skips the lookup entirely, and while locating it already shows the demo
 * list, so there is always something to act on without waiting.
 */
export function NearbyFacilities({
  locale,
  offline = false,
}: {
  locale: Locale;
  offline?: boolean;
}) {
  const [status, setStatus] = useState<Status>(() =>
    !offline && typeof navigator !== "undefined" && "geolocation" in navigator
      ? "locating"
      : "fallback",
  );
  const [places, setPlaces] = useState<RankedPlace[]>([]);

  useEffect(() => {
    let active = true;

    if (offline || typeof navigator === "undefined" || !("geolocation" in navigator)) {
      return;
    }

    // Geolocation's own timeout does not run while a permission prompt sits
    // unanswered — never leave someone on "locating" forever.
    const watchdog = window.setTimeout(() => {
      if (active) setStatus((s) => (s === "locating" ? "fallback" : s));
    }, 12_000);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (!active) return;
        const { latitude, longitude } = pos.coords;
        // Coarsen to the precision-5 cell center; only this leaves the device.
        const center = decodeGeohashCenter(encodeGeohash(latitude, longitude, 5));
        fetchNearbyPlaces(center.lat, center.lng, locale)
          .then((rows) => {
            if (!active) return;
            const ranked = rankPlaces(rows, latitude, longitude);
            if (ranked.length === 0) {
              setStatus("fallback");
              return;
            }
            setPlaces(ranked);
            setStatus("ready");
          })
          .catch(() => {
            if (active) setStatus("fallback");
          });
      },
      () => {
        if (active) setStatus("fallback");
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 600_000 },
    );

    return () => {
      active = false;
      window.clearTimeout(watchdog);
    };
  }, [locale, offline]);

  if (status === "locating" || status === "fallback") {
    return (
      <>
        <p className="text-label text-ink-soft" role="status">
          {status === "locating"
            ? t("nearbyLocating", locale)
            : t("nearbyDemoFallback", locale)}
        </p>
        {DEMO_FACILITIES.map((facility) => (
          <FacilityCard
            key={facility.id}
            locale={locale}
            name={facility.name}
            travelMinutes={facility.travelMinutes}
            canHandle
            services={facility.services}
            statusLabel={
              facility.canHandleUrgent
                ? t("facilityUrgentCapable", locale)
                : t("facilityGeneralCare", locale)
            }
          />
        ))}
      </>
    );
  }

  return (
    <>
      {places.map((place, index) => (
        <FacilityCard
          key={`${place.name}-${index}`}
          locale={locale}
          name={place.name}
          distanceKm={place.km}
          canHandle
          address={place.address}
          statusLabel={categoryLabel(place.category, locale)}
        />
      ))}
    </>
  );
}
