import { describe, expect, it } from "vitest";
import { redirectTarget } from "../lib/facilities";
import {
  applyReferralAction,
  chpStepLabel,
  canPerform,
  createReferral,
  describeReferral,
  OUTCOME_CODES,
  outcomeLabel,
  REFERRAL_STAGES,
} from "../lib/referral";
import type { Referral } from "../lib/types";

const calm = {
  offline: false,
  noFacilityResponse: false,
  weakConnection: false,
};

function acceptedUrgent(): Referral {
  const created = createReferral({
    encounterId: "enc-demo",
    urgent: true,
    by: "household",
  });
  const sent = applyReferralAction(created, "send", "household", calm);
  return applyReferralAction(sent, "accept", "facility", calm);
}

describe("referral object", () => {
  it("uses the canonical lifecycle from the README", () => {
    expect(REFERRAL_STAGES).toEqual([
      "created",
      "sent",
      "received",
      "accepted",
      "patient_moving",
      "arrived",
      "seen",
      "completed",
      "outcome_returned",
    ]);
  });

  it("moves through the whole care path, including seen", () => {
    const created = createReferral({
      encounterId: "enc-demo",
      urgent: true,
      by: "household",
    });
    expect(created.stage).toBe("created");
    expect(created.expectedArrivalMinutes).toBe(42);

    const sent = applyReferralAction(created, "send", "household", calm);
    expect(sent.stage).toBe("sent");

    const accepted = applyReferralAction(sent, "accept", "facility", calm);
    expect(accepted.stage).toBe("accepted");
    expect(accepted.history.map((entry) => entry.stage)).toEqual([
      "created",
      "sent",
      "received",
      "accepted",
    ]);

    const moving = applyReferralAction(accepted, "travel", "household", calm);
    expect(moving.stage).toBe("patient_moving");
    const arrived = applyReferralAction(moving, "arrive", "household", calm);
    expect(arrived.stage).toBe("arrived");
    const seen = applyReferralAction(arrived, "start_care", "facility", calm);
    expect(seen.stage).toBe("seen");
    const completed = applyReferralAction(seen, "complete", "facility", calm);
    expect(completed.stage).toBe("completed");
    const returned = applyReferralAction(completed, "return_outcome", "facility", {
      ...calm,
      outcome: "treated",
    });
    expect(returned.stage).toBe("outcome_returned");
    expect(returned.outcome).toBe("treated");
  });

  it("queues send when offline instead of dropping the path", () => {
    const created = createReferral({
      encounterId: "enc-demo",
      urgent: true,
      by: "household",
    });
    const queued = applyReferralAction(created, "send", "household", {
      ...calm,
      offline: true,
    });
    expect(queued.stage).toBe("created");
    expect(queued.queued).toBe(true);
    expect(queued.failure).toBe("offline");
  });

  it("names no facility response on send", () => {
    const created = createReferral({
      encounterId: "enc-demo",
      urgent: true,
      by: "household",
    });
    const sent = applyReferralAction(created, "send", "household", {
      ...calm,
      noFacilityResponse: true,
    });
    expect(sent.stage).toBe("sent");
    expect(sent.failure).toBe("no_facility_response");
  });
});

describe("redirect, cannot take, and capacity", () => {
  function sentUrgent(): Referral {
    return applyReferralAction(
      createReferral({ encounterId: "enc-demo", urgent: true, by: "chp" }),
      "send",
      "chp",
      calm,
    );
  }

  it("redirects to the other demo facility when no capacity is reported", () => {
    const redirected = applyReferralAction(sentUrgent(), "redirect", "facility", calm);
    expect(redirected.facilityId).toBe("west-demo");
    expect(redirected.failure).toBe("redirected");
    expect(redirected.history.at(-1)?.reason).toBeUndefined();
  });

  it("cannot take goes through the same redirect and records why", () => {
    const declined = applyReferralAction(sentUrgent(), "decline", "facility", calm);
    expect(declined.stage).toBe("sent");
    expect(declined.facilityId).toBe("west-demo");
    expect(declined.failure).toBe("redirected");
    expect(declined.history.at(-1)).toMatchObject({
      stage: "sent",
      by: "facility",
      note: "West Demo Sub-County Hospital",
      reason: "cannot_take",
    });
  });

  it("allows cannot take exactly where redirect is allowed", () => {
    const sent = sentUrgent();
    expect(canPerform(sent, "decline")).toBe(true);
    const moving = applyReferralAction(
      applyReferralAction(sent, "accept", "facility", calm),
      "travel",
      "chp",
      calm,
    );
    expect(canPerform(moving, "redirect")).toBe(false);
    expect(canPerform(moving, "decline")).toBe(false);
  });

  it("skips closed facilities and keeps the referral when none is open", () => {
    const sent = sentUrgent();
    const kept = applyReferralAction(sent, "redirect", "facility", {
      ...calm,
      capacity: { "west-demo": "closed" },
    });
    expect(kept).toBe(sent);
    const busy = applyReferralAction(sent, "decline", "facility", {
      ...calm,
      capacity: { "west-demo": "busy" },
    });
    expect(busy.facilityId).toBe("west-demo");
  });

  it("prefers a facility accepting now over a busy one", () => {
    expect(redirectTarget("x-elsewhere", { "north-demo": "busy" })?.id).toBe("west-demo");
    expect(redirectTarget("x-elsewhere", {})?.id).toBe("north-demo");
    expect(redirectTarget("north-demo", { "west-demo": "closed" })).toBeNull();
  });
});

describe("same event, different words", () => {
  it("translates accepted for each role using the locked English phrases", () => {
    const referral = acceptedUrgent();

    const household = describeReferral("household", referral, "go_now", "en");
    expect(household.headline).toBe("Facility accepted — you can leave now");
    expect(household.action?.id).toBe("travel");

    const chp = describeReferral("chp", referral, "go_now", "en");
    expect(chp.headline).toBe("Referral accepted — patient travel not yet confirmed");

    const facility = describeReferral("facility", referral, "go_now", "en");
    expect(facility.headline).toBe("Incoming urgent referral");
    expect(facility.arrivalMinutes).toBe(42);
  });

  it("translates the same event into Kiswahili", () => {
    const referral = acceptedUrgent();

    expect(describeReferral("household", referral, "go_now", "sw").headline).toBe(
      "Kituo kimekubali — unaweza kuondoka sasa",
    );
    expect(describeReferral("chp", referral, "go_now", "sw").headline).toBe(
      "Rufaa imekubaliwa — safari ya mgonjwa haijathibitishwa",
    );
    expect(describeReferral("facility", referral, "go_now", "sw").headline).toBe(
      "Rufaa ya dharura inakuja",
    );
  });

  it("never shows an internal stage name in the stage label", () => {
    const referral = acceptedUrgent();
    for (const locale of ["en", "sw"] as const) {
      const view = describeReferral("household", referral, "go_now", locale);
      expect(view.stageLabel).not.toMatch(/_/);
      expect(view.stageLabel.length).toBeGreaterThan(0);
    }
  });

  it("carries a semantic action id instead of matching button text", () => {
    const referral = acceptedUrgent();
    const facilitySent = describeReferral(
      "facility",
      applyReferralAction(
        createReferral({ encounterId: "enc", urgent: false, by: "chp" }),
        "send",
        "chp",
        calm,
      ),
      null,
      "sw",
    );
    expect(facilitySent.action?.id).toBe("accept");
    expect(describeReferral("chp", referral, "go_now", "sw").action?.id).toBe(
      "travel",
    );
  });
});

describe("CHP tracker words", () => {
  it("names every stage in plain words in both languages, never the enum", () => {
    for (const locale of ["en", "sw"] as const) {
      const words = REFERRAL_STAGES.map((stage) => chpStepLabel(stage, locale));
      expect(new Set(words).size).toBe(REFERRAL_STAGES.length);
      for (const word of words) {
        expect(word).not.toMatch(/_/);
        expect(word.length).toBeGreaterThan(0);
      }
    }
    expect(chpStepLabel("patient_moving", "en")).toBe("The family is on the way");
    expect(chpStepLabel("patient_moving", "sw")).toBe("Familia iko njiani");
  });

  it("offers every outcome code with a label", () => {
    expect(OUTCOME_CODES).toEqual(["treated", "referred_onward", "did_not_arrive", "unknown"]);
    for (const code of OUTCOME_CODES) {
      expect(outcomeLabel(code, "en").length).toBeGreaterThan(0);
      expect(outcomeLabel(code, "sw")).not.toBe(outcomeLabel(code, "en"));
    }
  });
});
