"use client";

import { useEffect, useMemo, useReducer, useState } from "react";
import { CarePath } from "@/components/CarePath";
import { ChpIntake } from "@/components/ChpIntake";
import { ChpResult, type HandoffState } from "@/components/ChpResult";
import { DailySummary } from "@/components/DailySummary";
import { HouseholdList } from "@/components/HouseholdList";
import { ReferralTracker } from "@/components/ReferralTracker";
import { StatusChip } from "@/components/StatusChip";
import { decisionHeadline, missingInfo } from "@/lib/assessment";
import {
  canSendHandoff,
  dailySummary,
  fromCarePath,
  handoffFor,
  hasQueued,
  householdLabel,
  householdReason,
  householdStatus,
  intakeStart,
  memberLabel,
  parseRoster,
  rosterReducer,
  seedHouseholds,
  SHARED_CASE_ID,
  sortHouseholds,
  statusCounts,
  type Household,
  type RosterAction,
  type SendConditions,
} from "@/lib/chp";
import { t, type Locale } from "@/lib/copy";
import { facilityById } from "@/lib/facilities";
import { chpHandoffFacts, whyComing } from "@/lib/handoff";
import { useCare } from "@/lib/store";
import type { OutcomeCode } from "@/lib/types";

/**
 * The CHP work surface: a synthetic demo roster of households, ordered by
 * what needs the CHP now. The roster lives on this phone only (its own
 * localStorage key); nothing typed here is logged or sent for analytics.
 * The clinical answer is always decide() from lib/assessment.ts.
 */

export const CHP_STORAGE_KEY = "tunza.v2.chp-demo";

type Screen =
  | { name: "list" }
  | { name: "household"; id: string }
  | { name: "intake"; id: string }
  | { name: "result"; id: string };

/** Wall clock for event handlers; render reads the `now` state instead. */
function clock(): number {
  return Date.now();
}

function readRoster(): Household[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(CHP_STORAGE_KEY);
  } catch {
    // Storage blocked: fall back to fresh demo households.
  }
  return parseRoster(raw, Date.now());
}

export function ChpSurface() {
  const { state, offline } = useCare();
  const locale = state.locale;
  const [roster, dispatch] = useReducer(rosterReducer, undefined, readRoster);
  const [screen, setScreen] = useState<Screen>({ name: "list" });
  const [now, setNow] = useState(() => Date.now());

  const noFacilityResponse = state.injectedFailures.includes("no_facility_response");
  const weakConnection = state.injectedFailures.includes("weak_connection");
  const conditions = useMemo<SendConditions>(
    () => ({ offline, noFacilityResponse, weakConnection }),
    [offline, noFacilityResponse, weakConnection],
  );

  useEffect(() => {
    try {
      localStorage.setItem(CHP_STORAGE_KEY, JSON.stringify(roster));
    } catch {
      // Quota or blocked storage: the in-memory roster still works.
    }
  }, [roster]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  // Back online: send everything that was queued on this phone.
  const queued = hasQueued(roster);
  useEffect(() => {
    if (queued && !conditions.offline) {
      dispatch({ type: "flushQueued", conditions });
    }
  }, [queued, conditions]);

  function act(action: RosterAction) {
    dispatch(action);
    setNow(clock());
  }

  const shared = fromCarePath(state.encounter, state.referral);
  const all = shared ? [...roster, shared] : roster;
  const find = (id: string) => all.find((household) => household.id === id) ?? null;
  const toList = () => setScreen({ name: "list" });

  if (screen.name === "household" && screen.id === SHARED_CASE_ID) {
    return (
      <div className="flex flex-col gap-4">
        <BackButton locale={locale} onClick={toList} />
        <CarePath role="chp" />
      </div>
    );
  }

  const current = screen.name === "list" ? null : find(screen.id);

  if (screen.name === "intake" && current) {
    return (
      <ChpIntake
        locale={locale}
        householdLabel={householdLabel(current, locale)}
        initial={intakeStart(current)}
        onCancel={() => setScreen({ name: "household", id: current.id })}
        onSubmit={(answers) => {
          act({ type: "assess", id: current.id, answers, now: clock() });
          setScreen({ name: "result", id: current.id });
        }}
      />
    );
  }

  if (screen.name === "result" && current?.decision && current.answers) {
    const kind = current.decision.kind;
    const stage = handoffFor(current);
    const handoff: HandoffState =
      stage === "sent" && current.referral
        ? { kind: "sent", facility: facilityById(current.referral.facilityId).name }
        : stage === "queued"
          ? { kind: "queued" }
          : { kind: "none" };
    return (
      <ChpResult
        locale={locale}
        householdLabel={householdLabel(current, locale)}
        decision={current.decision}
        why={whyComing(current.answers, kind, locale)}
        facts={chpHandoffFacts(current.answers, current.decision, locale)}
        missing={missingInfo(current.answers, null, locale).map((item) => item.label)}
        handoff={handoff}
        canSend={canSendHandoff(current)}
        onSend={() => act({ type: "sendHandoff", id: current.id, conditions })}
        onTrack={() => setScreen({ name: "household", id: current.id })}
        onFinishAnswers={() => setScreen({ name: "intake", id: current.id })}
        onBack={toList}
      />
    );
  }

  if (screen.name !== "list" && current) {
    return (
      <HouseholdDetail
        locale={locale}
        household={current}
        now={now}
        onBack={toList}
        onAssess={() => setScreen({ name: "intake", id: current.id })}
        onSeeResult={() => setScreen({ name: "result", id: current.id })}
        onSend={() => {
          act({ type: "sendHandoff", id: current.id, conditions });
          setScreen({ name: "result", id: current.id });
        }}
        onRetrySend={() => act({ type: "flushQueued", conditions })}
        onTheyLeft={() => act({ type: "confirmTravel", id: current.id })}
        onOutcome={(outcome) =>
          act({ type: "recordOutcome", id: current.id, outcome, now: clock() })
        }
        onMarkWell={() => act({ type: "clearFollowUp", id: current.id })}
        onDemoAdvance={() => act({ type: "demoAdvance", id: current.id })}
      />
    );
  }

  const sorted = sortHouseholds(all, now);
  const counts = statusCounts(all, now);
  const rows = sorted.map((household) => ({
    id: household.id,
    label: householdLabel(household, locale),
    member: memberLabel(household.member, locale),
    status: householdStatus(household, now),
    reason: householdReason(household, now, locale),
  }));

  return (
    <div className="flex flex-col gap-4">
      <HouseholdList
        locale={locale}
        rows={rows}
        attentionCount={counts.attention}
        onOpen={(id) => setScreen({ name: "household", id })}
      />
      <DailySummary locale={locale} counts={dailySummary(all, now)} />
      <details className="rounded-xl border border-dashed border-line px-3 py-2">
        <summary className="min-h-10 cursor-pointer py-2 text-label font-medium text-ink-soft">
          {t("chpDemoControls", locale)}
        </summary>
        <button
          type="button"
          onClick={() => act({ type: "reset", households: seedHouseholds(clock()) })}
          className="mt-2 min-h-12 w-full rounded-xl border border-line px-3 text-left text-label font-medium text-ink"
        >
          {t("chpDemoReset", locale)}
        </button>
      </details>
    </div>
  );
}

function BackButton({ locale, onClick }: { locale: Locale; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="min-h-12 self-start text-label font-medium text-ink-soft"
    >
      {t("chpBackToList", locale)}
    </button>
  );
}

type DetailProps = {
  locale: Locale;
  household: Household;
  now: number;
  onBack: () => void;
  onAssess: () => void;
  onSeeResult: () => void;
  onSend: () => void;
  onRetrySend: () => void;
  onTheyLeft: () => void;
  onOutcome: (outcome: OutcomeCode) => void;
  onMarkWell: () => void;
  onDemoAdvance: () => void;
};

function HouseholdDetail({
  locale,
  household,
  now,
  onBack,
  onAssess,
  onSeeResult,
  onSend,
  onRetrySend,
  onTheyLeft,
  onOutcome,
  onMarkWell,
  onDemoAdvance,
}: DetailProps) {
  const status = householdStatus(household, now);
  const referral = household.referral;
  const activeReferral = !!referral && referral.stage !== "outcome_returned";
  const sendable = canSendHandoff(household);
  const followUp = status === "followup" && !activeReferral && !!household.decision;

  const primary = sendable
    ? { label: t("chpSendHandoff", locale), onClick: onSend }
    : followUp
      ? { label: t("chpFollowUpVisit", locale), onClick: onAssess }
      : activeReferral
        ? null
        : { label: t("chpStartAssessment", locale), onClick: onAssess };

  const secondary = [
    sendable || activeReferral
      ? { id: "assess", label: t("chpStartAssessment", locale), onClick: onAssess }
      : null,
    followUp ? { id: "well", label: t("chpMarkWell", locale), onClick: onMarkWell } : null,
  ].filter((item): item is { id: string; label: string; onClick: () => void } => !!item);

  const assessedAt = household.assessedAt
    ? new Date(household.assessedAt).toLocaleString(locale === "sw" ? "sw-KE" : "en-KE", {
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="flex flex-col gap-4">
      <BackButton locale={locale} onClick={onBack} />

      <header className="flex flex-col gap-2">
        <h1 className="text-decision font-bold tracking-tight text-ink">
          {householdLabel(household, locale)}
        </h1>
        <p className="text-label text-ink-soft">
          {memberLabel(household.member, locale)} · {t("demoLabel", locale)}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={status} locale={locale} />
          <span className="text-label font-medium text-ink">
            {householdReason(household, now, locale)}
          </span>
        </div>
      </header>

      {primary ? (
        <button
          type="button"
          onClick={primary.onClick}
          className="min-h-14 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink"
        >
          {primary.label}
        </button>
      ) : null}

      {referral ? (
        <ReferralTracker
          locale={locale}
          referral={referral}
          decisionKind={household.decision?.kind ?? null}
          onSend={onRetrySend}
          onTheyLeft={onTheyLeft}
          onOutcome={onOutcome}
          onDemoAdvance={onDemoAdvance}
        />
      ) : null}

      <section className="rounded-2xl border border-line bg-raised px-4 py-3">
        <h2 className="text-caption font-medium uppercase tracking-[0.12em] text-ink-soft">
          {t("chpLastAssessment", locale)}
        </h2>
        {household.decision ? (
          <div className="mt-2 flex flex-col gap-2">
            <p className="text-body font-semibold text-ink">
              {decisionHeadline(household.decision.kind, locale)}
              {assessedAt ? (
                <span className="font-normal text-ink-soft tabular-nums"> · {assessedAt}</span>
              ) : null}
            </p>
            <button
              type="button"
              onClick={onSeeResult}
              className="min-h-12 self-start rounded-xl border border-line px-3 text-label font-medium text-ink"
            >
              {t("chpSeeResult", locale)}
            </button>
          </div>
        ) : (
          <p className="mt-2 text-body text-ink-soft">{t("chpNotAssessed", locale)}</p>
        )}
      </section>

      {secondary.length > 0 ? (
        <div className="flex flex-col gap-2">
          {secondary.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={item.onClick}
              className="min-h-12 rounded-2xl border border-line px-4 text-body font-medium text-ink"
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
