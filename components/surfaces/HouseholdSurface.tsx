"use client";

import { useId, useState, type ReactNode } from "react";
import { AssessmentFlow } from "@/components/AssessmentFlow";
import { CarePath } from "@/components/CarePath";
import { DecisionResult } from "@/components/DecisionResult";
import { FacilityCard } from "@/components/FacilityCard";
import { HomeScreen } from "@/components/HomeScreen";
import { Icon } from "@/components/Icon";
import { NearbyFacilities } from "@/components/NearbyFacilities";
import { RoleGate } from "@/components/RoleGate";
import { Warning } from "@/components/Warning";
import { DangerStrip } from "@/components/household/DangerStrip";
import { DemoNotice, useNoticeSeen } from "@/components/household/DemoNotice";
import { ShareHandoff } from "@/components/household/ShareHandoff";
import { decisionHeadline, decisionStatus } from "@/lib/assessment";
import { t, type CopyKey } from "@/lib/copy";
import { warningCopy } from "@/lib/failures";
import { facilityById, pickFacility } from "@/lib/facilities";
import { householdShareText } from "@/lib/householdShare";
import { stageLabel } from "@/lib/referral";
import { activeFailures, useCare } from "@/lib/store";
import type { Decision, DecisionKind } from "@/lib/types";

/**
 * The household surface. Everything here runs on the phone: the decision comes
 * from the local rules, the facility from the demo list, so an answer is never
 * waiting on the network. Only the household-safe decide() output is shown —
 * this surface never imports the clinical model layer.
 */
export function HouseholdSurface() {
  const { state, dispatch, offline } = useCare();
  const encounter = state.encounter;
  const referral = state.referral;
  const locale = state.locale;

  if (state.view === "home") {
    const continueDetail = referral
      ? `${t("referralEyebrow", locale)} · ${stageLabel(referral.stage, locale)}`
      : encounter?.decision
        ? decisionHeadline(encounter.decision.kind, locale)
        : encounter && encounter.asked.length > 0
          ? t("homeCardAssessTitle", locale)
          : null;
    return (
      <HomeScreen
        locale={locale}
        continueDetail={continueDetail}
        onStart={() => dispatch.setView("path")}
        onNearby={() => dispatch.setView("nearby")}
        onContinue={() => dispatch.setView("path")}
        onHealthWorker={() => {
          dispatch.setGateRole(null);
          dispatch.setView("gate");
        }}
      />
    );
  }

  if (state.view === "gate") {
    return <RoleGate />;
  }

  if (state.view === "nearby") {
    return (
      <HouseholdFrame showNoticeOnce={false}>
        <button
          type="button"
          onClick={() => dispatch.setView("home")}
          className="min-h-12 self-start text-label font-medium text-ink-soft"
        >
          {t("back", locale)}
        </button>
        <h1 className="text-decision font-semibold tracking-tight text-ink">
          {t("nearbyTitle", locale)}
        </h1>
        <NearbyFacilities key={offline ? "offline" : "online"} locale={locale} offline={offline} />
      </HouseholdFrame>
    );
  }

  const decision = encounter?.decision ?? null;

  if (referral && encounter) {
    return (
      <HouseholdFrame showNoticeOnce={false}>
        <DangerStrip
          locale={locale}
          danger={dangerFor(decision)}
          watchKeys={decision?.watchSignKeys}
        />
        <CarePath role="household" />
        {decision ? (
          <ShareHandoff
            locale={locale}
            text={householdShareText({
              locale,
              kind: decision.kind,
              reasonKeys: decision.reasonKeys,
              facilityName: facilityById(referral.facilityId).name,
              answers: encounter.answers,
            })}
          />
        ) : null}
      </HouseholdFrame>
    );
  }

  if (decision && !encounter?.currentQuestion) {
    return (
      <HouseholdFrame showNoticeOnce={false}>
        <DecisionView />
      </HouseholdFrame>
    );
  }

  return (
    <HouseholdFrame showNoticeOnce={(encounter?.asked.length ?? 0) === 0}>
      <DangerStrip locale={locale} danger={null} />
      <AssessmentFlow household />
    </HouseholdFrame>
  );
}

/** Danger signs present, or null when calm. Driven only by decide() output. */
function dangerFor(decision: Decision | null): CopyKey[] | null {
  if (!decision || decision.kind !== "go_now") {
    return null;
  }
  return decision.dangerSignKeys.length > 0 ? decision.dangerSignKeys : decision.reasonKeys;
}

/**
 * Wraps every working household screen: the honest-limits notice (shown once,
 * then behind the help link) and the help link itself, quiet at the bottom.
 */
function HouseholdFrame({
  showNoticeOnce,
  children,
}: {
  showNoticeOnce: boolean;
  children: ReactNode;
}) {
  const { state } = useCare();
  const locale = state.locale;
  const { seen, markSeen } = useNoticeSeen();
  const [helpOpen, setHelpOpen] = useState(false);
  const helpId = useId();

  return (
    <div className="flex flex-col gap-4">
      {showNoticeOnce && !seen && !helpOpen ? (
        <DemoNotice locale={locale} onDismiss={markSeen} />
      ) : null}
      {children}
      <div className="mt-2 flex flex-col gap-3">
        <button
          type="button"
          aria-expanded={helpOpen}
          aria-controls={helpId}
          onClick={() => setHelpOpen((open) => !open)}
          className="flex min-h-12 items-center gap-2 self-start text-label font-medium text-ink-soft underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
        >
          <Icon name="info" className="size-5" />
          {t("helpLink", locale)}
        </button>
        <div id={helpId}>
          {helpOpen ? (
            <DemoNotice
              locale={locale}
              onDismiss={() => {
                markSeen();
                setHelpOpen(false);
              }}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

const WAIT_KEY: Record<DecisionKind, CopyKey> = {
  go_now: "waitGoNow",
  get_care_today: "waitToday",
  monitor_at_home: "waitMonitor",
  need_one_more_answer: "waitOneMore",
};

/**
 * The result: one action sentence, why in one line, what to do now, then the
 * nearest facility and a one-tap handoff to the CHP. On go now, the danger
 * strip replaces the why and nothing else competes with the action.
 */
function DecisionView() {
  const { state, dispatch } = useCare();
  const encounter = state.encounter;
  const decision = encounter?.decision;
  const locale = state.locale;
  if (!encounter || !decision) {
    return null;
  }

  const kind = decision.kind;
  const goNow = kind === "go_now";
  const failures = activeFailures(state, null);
  const askedMain = encounter.asked.includes("main_problem");
  const action =
    kind === "go_now" || kind === "get_care_today"
      ? { label: t("prepareFacility", locale), onClick: dispatch.prepareReferral }
      : kind === "need_one_more_answer" && !askedMain
        ? { label: t("answerTheQuestion", locale), onClick: dispatch.continueForOneMore }
        : undefined;

  const facility = pickFacility(goNow);
  const reasons = decision.reasonKeys.map((key) => t(key, locale));
  const whatToDoId = `what-to-do-${kind}`;
  const offlineCopy = warningCopy("offline", locale);
  const incomplete = warningCopy("incomplete_assessment", locale);

  const lead = (
    <>
      {goNow ? (
        <DangerStrip locale={locale} danger={dangerFor(decision)} />
      ) : reasons.length > 0 ? (
        <p className="text-body text-ink" data-why-line>
          <span className="font-medium text-ink-soft">{t("whyThis", locale)}</span>{" "}
          {reasons.join(" · ")}
        </p>
      ) : null}
      <section aria-labelledby={whatToDoId} className="flex flex-col gap-1">
        <h2 id={whatToDoId} className="text-label font-medium text-ink-soft">
          {t("whatToDoNow", locale)}
        </h2>
        <p className="text-body text-ink">{t(WAIT_KEY[kind], locale)}</p>
      </section>
      {goNow ? null : (
        <DangerStrip locale={locale} danger={null} watchKeys={decision.watchSignKeys} />
      )}
      {kind === "need_one_more_answer" ? null : (
        <FacilityCard
          locale={locale}
          eyebrow={t("nearestFacility", locale)}
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
      )}
    </>
  );

  return (
    <DecisionResult
      locale={locale}
      kind={kind}
      headline={decisionHeadline(kind, locale)}
      status={decisionStatus(kind, locale)}
      action={action}
      lead={lead}
      autoFocus
    >
      <ShareHandoff
        locale={locale}
        text={householdShareText({
          locale,
          kind,
          reasonKeys: decision.reasonKeys,
          facilityName: facility.name,
          answers: encounter.answers,
        })}
      />
      {!goNow && failures.includes("offline") ? (
        <Warning
          named="offline"
          eyebrow={offlineCopy.eyebrow}
          title={offlineCopy.title}
          body={offlineCopy.body}
        />
      ) : null}
      {!goNow && kind !== "need_one_more_answer" && failures.includes("incomplete_assessment") ? (
        <Warning
          named="incomplete_assessment"
          eyebrow={incomplete.eyebrow}
          title={incomplete.title}
          body={incomplete.body}
        />
      ) : null}
    </DecisionResult>
  );
}
