import type { Facility, FacilityCapacity } from "./types";

/** Clearly fake demo facilities — not real sites. */
export const DEMO_FACILITIES: Facility[] = [
  {
    id: "north-demo",
    name: "North Demo Health Centre",
    travelMinutes: 42,
    canHandleUrgent: true,
    services: ["Urgent care", "Under-5", "Observation"],
  },
  {
    id: "west-demo",
    name: "West Demo Sub-County Hospital",
    travelMinutes: 70,
    canHandleUrgent: true,
    services: ["Emergency", "Theatre", "Maternity"],
  },
];

export function facilityById(id: string): Facility {
  const found = DEMO_FACILITIES.find((item) => item.id === id);
  if (!found) {
    return DEMO_FACILITIES[0];
  }
  return found;
}

export function pickFacility(urgent: boolean): Facility {
  if (urgent) {
    return DEMO_FACILITIES.find((item) => item.canHandleUrgent) ?? DEMO_FACILITIES[0];
  }
  return DEMO_FACILITIES[0];
}

export function redirectFacility(currentId: string): Facility {
  return DEMO_FACILITIES.find((item) => item.id !== currentId) ?? DEMO_FACILITIES[1];
}

/** Capacity per facility id. A facility with no entry is accepting. */
export type CapacityMap = Partial<Record<string, FacilityCapacity>>;

export function capacityOf(capacity: CapacityMap, id: string): FacilityCapacity {
  return capacity[id] ?? "accepting";
}

/**
 * Capacity-aware redirect target. Skips closed facilities and prefers one
 * accepting now over one that is busy. Returns null when no other facility
 * is open, so the caller keeps the referral instead of sending it to a
 * closed door. With no capacity reported this matches redirectFacility().
 */
export function redirectTarget(
  currentId: string,
  capacity: CapacityMap = {},
): Facility | null {
  const others = DEMO_FACILITIES.filter((item) => item.id !== currentId);
  return (
    others.find((item) => capacityOf(capacity, item.id) === "accepting") ??
    others.find((item) => capacityOf(capacity, item.id) === "busy") ??
    null
  );
}
