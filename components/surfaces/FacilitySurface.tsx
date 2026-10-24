"use client";

import { useEffect, useState } from "react";
import { AttentionNeeded } from "@/components/AttentionNeeded";
import { CapacityControl } from "@/components/facility/CapacityControl";
import { CaseView } from "@/components/facility/CaseView";
import { DeskInbox } from "@/components/facility/DeskInbox";
import { missingInfo } from "@/lib/assessment";
import { useLiveCandidate } from "@/lib/clinical/useLiveCandidate";
import { t } from "@/lib/copy";
import {
  askedOfFacility,
  caseSummary,
  deskCapacity,
  deskCases,
  deskRow,
  reviewCase,
  sortDeskCases,
  timeline,
} from "@/lib/desk";
import { DEMO_FACILITIES } from "@/lib/facilities";
import { handoffFacts, whyComing } from "@/lib/handoff";
import { canPerform, describeReferral, outcomeLabel } from "@/lib/referral";
import { activeFailures, useCare } from "@/lib/store";

const FACILITY_OPTIONS = DEMO_FACILITIES.map(({ id, name }) => ({ id, name }));

/**
 * The professional surface for clinicians and facility staff: an inbox of
 * incoming referrals and a case view. Reached only through the demo access
 * gate (RoleGate); there is no real authentication or audit log yet.
 */
export function FacilitySurface() {
  const { state, dispatch } = useCare();
  const locale = state.locale;
  const [openId, setOpenId] = useState<string | null>(null);
  const [lastOpenedId, setLastOpenedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const deskId = state.deskFacilityId;
  const cases = sortDeskCases(deskCases(state), deskId);
  const rows = cases.map((item) =>
    deskRow(item, deskId, state.facilityCapacity, locale, now),
  );

  const capacity = (
    <CapacityControl
      locale={locale}
      facilities={FACILITY_OPTIONS}
      deskFacilityId={deskId}
      capacity={deskCapacity(state, deskId)}
      onDeskFacility={dispatch.setDeskFacility}
      onCapacity={(next) => dispatch.setCapacity(deskId, next)}
    />
  );

  const openIndex = openId ? cases.findIndex((item) => item.id === openId) : -1;
  const openCase = openIndex === -1 ? null : cases[openIndex];
  const liveCandidate = useLiveCandidate(
    openCase ? openCase.id : null,
    openCase ? openCase.encounter.answers : null,
  );

  if (openIndex === -1) {
    if (rows.length === 0) {
      return (
        <div className="flex flex-col gap-4">
          {capacity}
          <AttentionNeeded
            title={t("incomingTitle", locale)}
            items={[
              {
                id: "none",
                label: t("noIncoming", locale),
                detail: t("noIncomingDetail", locale),
              },
            ]}
          />
        </div>
      );
    }
    return (
      <DeskInbox
        locale={locale}
        rows={rows}
        focusRowId={lastOpenedId}
        onOpen={(id) => {
          setOpenId(id);
          setLastOpenedId(id);
        }}
        onAccept={(id) => dispatch.deskAction(id, "accept")}
        onRedirect={(id) => dispatch.deskAction(id, "redirect")}
        onDecline={(id) => dispatch.deskAction(id, "decline")}
      >
        {capacity}
      </DeskInbox>
    );
  }

  const item = cases[openIndex];
  const row = rows[openIndex];
  const { encounter, referral } = item;
  const review = reviewCase(item, locale, liveCandidate);
  const kind = review.rulesKind;
  // The stale marker follows the demo's named condition for the session case.
  // Synthetic cases carry their own assessment time.
  const stale =
    item.source === "session" &&
    activeFailures(state, referral).includes("stale_information");
  const view = describeReferral("facility", referral, kind, locale);
  const stageStep =
    row.atDesk &&
    view.action &&
    (view.action.id === "arrive" ||
      view.action.id === "start_care" ||
      view.action.id === "complete")
      ? view.action
      : null;
  const act = (action: Parameters<typeof dispatch.deskAction>[1]) =>
    dispatch.deskAction(item.id, action);

  return (
    <CaseView
      locale={locale}
      role={state.role}
      row={row}
      summary={caseSummary(row, locale)}
      asked={askedOfFacility(kind, locale)}
      handoff={{
        why: whyComing(encounter.answers, kind, locale),
        known: handoffFacts(encounter.answers, stale, encounter.updatedAt, locale),
        missing: missingInfo(encounter.answers, referral.askMore, locale).map(
          (entry) => entry.label,
        ),
      }}
      review={review}
      timeline={timeline(referral, locale)}
      stageAction={
        stageStep
          ? { label: stageStep.label, onClick: () => act(stageStep.id) }
          : undefined
      }
      askMore={
        row.atDesk && canPerform(referral, "ask_more") && !referral.askMore
          ? () => act("ask_more")
          : undefined
      }
      outcomeDue={row.atDesk && referral.stage === "completed" && !referral.outcome}
      outcomeText={referral.outcome ? outcomeLabel(referral.outcome, locale) : null}
      onBack={() => setOpenId(null)}
      onAccept={() => act("accept")}
      onRedirect={() => act("redirect")}
      onDecline={() => act("decline")}
      onOutcome={(outcome) => dispatch.deskAction(item.id, "return_outcome", outcome)}
    />
  );
}
