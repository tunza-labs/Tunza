// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChpIntake } from "../components/ChpIntake";
import { ChpResult } from "../components/ChpResult";
import { DailySummary } from "../components/DailySummary";
import { HouseholdList } from "../components/HouseholdList";
import { ReferralTracker } from "../components/ReferralTracker";
import { ReferralStatus } from "../components/ReferralStatus";
import { StatusChip } from "../components/StatusChip";
import { CHP_STORAGE_KEY, ChpSurface } from "../components/surfaces/ChpSurface";
import { decide, decisionHeadline, EMPTY_ANSWERS } from "../lib/assessment";
import { seedHouseholds, STATUS_ORDER } from "../lib/chp";
import { copyTables, fill, t, type CopyKey, type Locale } from "../lib/copy";
import { chpHandoffFacts } from "../lib/handoff";
import { applyReferralAction, chpStepLabel, createReferral, outcomeLabel } from "../lib/referral";
import { CareProvider, initialCareState, useCare } from "../lib/store";

const LOCALES: Locale[] = ["en", "sw"];
const noop = () => {};
const calm = { offline: false, noFacilityResponse: false, weakConnection: false };

afterEach(cleanup);

describe("StatusChip", () => {
  it.each(LOCALES)("names every status in words (%s)", (locale) => {
    for (const status of STATUS_ORDER) {
      const { container, unmount } = render(<StatusChip status={status} locale={locale} />);
      const chip = container.querySelector("[data-status]");
      expect(chip?.getAttribute("data-status")).toBe(status);
      expect(chip?.textContent?.length).toBeGreaterThan(0);
      expect(chip?.textContent).not.toContain("_");
      unmount();
    }
  });
});

describe("HouseholdList", () => {
  it.each(LOCALES)("shows the count, the attention count, and a chip per row (%s)", (locale) => {
    const onOpen = vi.fn();
    const { getByText, container } = render(
      <HouseholdList
        locale={locale}
        attentionCount={1}
        onOpen={onOpen}
        rows={[
          { id: "a", label: "Demo household 1", member: "x", status: "attention", reason: "r1" },
          { id: "b", label: "Demo household 2", member: "y", status: "stable", reason: "r2" },
        ]}
      />,
    );
    expect(getByText(fill(t("chpCountTpl", locale), { n: 2 }))).toBeTruthy();
    expect(getByText(fill(t("chpAttentionCountTpl", locale), { n: 1 }))).toBeTruthy();
    expect(getByText(t("chpDemoNotice", locale))).toBeTruthy();
    expect(container.querySelectorAll("[data-status]")).toHaveLength(2);
    fireEvent.click(getByText("Demo household 2"));
    expect(onOpen).toHaveBeenCalledWith("b");
  });

  it("hides the attention count when nothing needs attention", () => {
    const { queryByText } = render(
      <HouseholdList locale="en" attentionCount={0} onOpen={noop} rows={[]} />,
    );
    expect(queryByText(fill(t("chpAttentionCountTpl", "en"), { n: 0 }))).toBeNull();
  });
});

describe("DailySummary", () => {
  it.each(LOCALES)("shows three numbers and the no-names promise (%s)", (locale) => {
    const { container, getByText } = render(
      <DailySummary locale={locale} counts={{ seen: 5, referred: 2, followUps: 3 }} />,
    );
    expect(getByText(t("chpSummaryTitle", locale))).toBeTruthy();
    expect(getByText(t("chpSummaryPrivacy", locale))).toBeTruthy();
    const value = (id: string) =>
      container.querySelector(`[data-summary="${id}"] dd`)?.textContent;
    expect(value("seen")).toBe("5");
    expect(value("referred")).toBe("2");
    expect(value("followups")).toBe("3");
  });
});

describe("ChpIntake", () => {
  it.each(LOCALES)("shows six fields, I don't know on each, and a note (%s)", (locale) => {
    const { container, getByText } = render(
      <ChpIntake
        locale={locale}
        householdLabel="Demo household 1"
        initial={{ ...EMPTY_ANSWERS, who: "child" }}
        onSubmit={noop}
        onCancel={noop}
      />,
    );
    const fields = container.querySelectorAll("fieldset[data-field]");
    expect(fields).toHaveLength(6);
    for (const field of fields) {
      expect(within(field as HTMLElement).getByText(t("dontKnow", locale))).toBeTruthy();
    }
    expect(getByText(t("chpNoteLabel", locale))).toBeTruthy();
    expect(
      getByText(fill(t("chpIntakeAnsweredTpl", locale), { n: 1, total: 6 })),
    ).toBeTruthy();
  });

  it("submits the structured answers and the note", () => {
    const onSubmit = vi.fn();
    const { getByLabelText, getByRole } = render(
      <ChpIntake
        locale="en"
        householdLabel="Demo household 1"
        initial={{ ...EMPTY_ANSWERS, who: "child" }}
        onSubmit={onSubmit}
        onCancel={noop}
      />,
    );
    fireEvent.click(getByLabelText(t("awakeNotWaking", "en")));
    fireEvent.click(getByLabelText(t("mainFever", "en")));
    fireEvent.change(getByLabelText(t("chpNoteLabel", "en")), {
      target: { value: "Hot body since morning" },
    });
    fireEvent.click(getByRole("button", { name: t("chpSeeResult", "en") }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const answers = onSubmit.mock.calls[0][0];
    expect(answers.who).toBe("child");
    expect(answers.awake).toBe("not_waking");
    expect(answers.mainProblem).toBe("fever");
    expect(answers.presentation).toBe("Hot body since morning");
  });
});

describe("ChpResult", () => {
  const answers = { ...EMPTY_ANSWERS, who: "child" as const, awake: "not_waking" as const };
  const decision = decide(answers);

  it.each(LOCALES)("shows the decide() answer, danger signs, and one-tap send (%s)", (locale) => {
    const onSend = vi.fn();
    const { getByRole, getByText } = render(
      <ChpResult
        locale={locale}
        householdLabel="Demo household 1"
        decision={decision}
        why="why"
        facts={chpHandoffFacts(answers, decision, locale)}
        missing={[]}
        handoff={{ kind: "none" }}
        canSend
        onSend={onSend}
        onTrack={noop}
        onFinishAnswers={noop}
        onBack={noop}
      />,
    );
    expect(getByRole("heading", { level: 1 }).textContent).toBe(
      decisionHeadline("go_now", locale),
    );
    expect(getByText(t("chpDangerFound", locale))).toBeTruthy();
    fireEvent.click(getByRole("button", { name: t("chpSendHandoff", locale) }));
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it.each(LOCALES)("says queued, will send when online (%s)", (locale) => {
    const { getByText, queryByRole } = render(
      <ChpResult
        locale={locale}
        householdLabel="Demo household 1"
        decision={decision}
        why="why"
        facts={[]}
        missing={[]}
        handoff={{ kind: "queued" }}
        canSend={false}
        onSend={noop}
        onTrack={noop}
        onFinishAnswers={noop}
        onBack={noop}
      />,
    );
    expect(getByText(t("chpQueuedNotice", locale))).toBeTruthy();
    expect(getByText(t("chpQueuedDetail", locale))).toBeTruthy();
    expect(queryByRole("button", { name: t("chpSendHandoff", locale) })).toBeNull();
  });

  it("offers tracking once sent, and no danger panel without danger signs", () => {
    const calmAnswers = {
      ...EMPTY_ANSWERS,
      who: "child" as const,
      awake: "alert" as const,
      breathing: "fine" as const,
      drinking: "little" as const,
      mainProblem: "fever" as const,
    };
    const today = decide(calmAnswers);
    expect(today.kind).toBe("get_care_today");
    const onTrack = vi.fn();
    const { getByText, getByRole, queryByText } = render(
      <ChpResult
        locale="en"
        householdLabel="Demo household 3"
        decision={today}
        why="why"
        facts={[]}
        missing={[]}
        handoff={{ kind: "sent", facility: "North Demo Health Centre" }}
        canSend={false}
        onSend={noop}
        onTrack={onTrack}
        onFinishAnswers={noop}
        onBack={noop}
      />,
    );
    expect(getByText(fill(t("chpSentTpl", "en"), { f: "North Demo Health Centre" }))).toBeTruthy();
    expect(getByText(t("chpNoDangerFound", "en"))).toBeTruthy();
    expect(queryByText(t("chpDangerFound", "en"))).toBeNull();
    fireEvent.click(getByRole("button", { name: t("chpTrackReferral", "en") }));
    expect(onTrack).toHaveBeenCalled();
  });
});

describe("ReferralTracker", () => {
  function referralAt(steps: Parameters<typeof applyReferralAction>[1][]) {
    let referral = createReferral({ encounterId: "enc", urgent: false, by: "chp" });
    for (const step of steps) {
      referral = applyReferralAction(referral, step, "facility", calm);
    }
    return referral;
  }

  it.each(LOCALES)("lists every stage in plain words and marks the current one (%s)", (locale) => {
    const referral = referralAt(["send", "accept"]);
    const { container, getByText } = render(
      <ReferralTracker
        locale={locale}
        referral={referral}
        decisionKind="get_care_today"
        onSend={noop}
        onTheyLeft={noop}
        onOutcome={noop}
      />,
    );
    expect(container.querySelectorAll("li[data-stage]")).toHaveLength(9);
    const now = container.querySelector('[aria-current="step"]');
    expect(now?.getAttribute("data-stage")).toBe("accepted");
    expect(getByText(chpStepLabel("patient_moving", locale))).toBeTruthy();
    expect(container.textContent).not.toContain("patient_moving");
  });

  it("lets the CHP confirm the family has left", () => {
    const onTheyLeft = vi.fn();
    const { getByRole } = render(
      <ReferralTracker
        locale="en"
        referral={referralAt(["send", "accept"])}
        decisionKind="get_care_today"
        onSend={noop}
        onTheyLeft={onTheyLeft}
        onOutcome={noop}
      />,
    );
    fireEvent.click(getByRole("button", { name: t("actionTheyLeft", "en") }));
    expect(onTheyLeft).toHaveBeenCalled();
  });

  it.each(LOCALES)("prompts for the outcome once the visit is finished (%s)", (locale) => {
    const onOutcome = vi.fn();
    const { getByText, getByRole } = render(
      <ReferralTracker
        locale={locale}
        referral={referralAt(["send", "accept", "travel", "arrive", "start_care", "complete"])}
        decisionKind="get_care_today"
        onSend={noop}
        onTheyLeft={noop}
        onOutcome={onOutcome}
      />,
    );
    expect(getByText(t("chpOutcomePrompt", locale))).toBeTruthy();
    fireEvent.click(getByRole("button", { name: outcomeLabel("did_not_arrive", locale) }));
    expect(onOutcome).toHaveBeenCalledWith("did_not_arrive");
  });

  it("shows no outcome prompt before the visit is finished", () => {
    const { queryByText } = render(
      <ReferralTracker
        locale="en"
        referral={referralAt(["send"])}
        decisionKind="get_care_today"
        onSend={noop}
        onTheyLeft={noop}
        onOutcome={noop}
      />,
    );
    expect(queryByText(t("chpOutcomePrompt", "en"))).toBeNull();
  });
});

describe("ReferralStatus heading level", () => {
  it("can sit under a page heading as an h2", () => {
    const { getByRole, queryByRole } = render(
      <ReferralStatus
        locale="en"
        role="chp"
        stage="sent"
        stageLabel={t("stageSent", "en")}
        headline={t("refSentChpHeadline", "en")}
        status="s"
        arrivalMinutes={null}
        headingLevel={2}
      />,
    );
    expect(getByRole("heading", { level: 2 }).textContent).toBe(t("refSentChpHeadline", "en"));
    expect(queryByRole("heading", { level: 1 })).toBeNull();
  });
});

function OfflineToggle() {
  const { dispatch } = useCare();
  return (
    <button type="button" onClick={() => dispatch.toggleFailure("offline")}>
      toggle-offline
    </button>
  );
}

function renderSurface(options: { offline?: boolean; locale?: Locale } = {}) {
  localStorage.setItem(
    "tunza.v2.care",
    JSON.stringify({
      ...initialCareState,
      role: "chp",
      grants: { chp: true, facility: false },
      locale: options.locale ?? "en",
      injectedFailures: options.offline ? ["offline"] : [],
    }),
  );
  return render(
    <CareProvider>
      <OfflineToggle />
      <ChpSurface />
    </CareProvider>,
  );
}

/** Node 26 shadows jsdom's localStorage with an undefined global; stub it. */
function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => {
      data.delete(key);
    },
    setItem: (key, value) => {
      data.set(key, String(value));
    },
  };
}

describe("ChpSurface", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each(LOCALES)("opens on the household list, most urgent first, with a summary (%s)", (locale) => {
    const { container, getByText } = renderSurface({ locale });
    const rows = [...container.querySelectorAll("button[data-household]")];
    expect(rows).toHaveLength(7);
    expect(rows[0].getAttribute("data-household")).toBe("demo-hh-1");
    expect(within(rows[0] as HTMLElement).getByText(t("chpStatusAttention", locale))).toBeTruthy();
    expect(getByText(t("chpSummaryTitle", locale))).toBeTruthy();
    expect(getByText(fill(t("chpCountTpl", locale), { n: 7 }))).toBeTruthy();
  });

  it("starts an assessment in two taps", () => {
    const { getByText, getByRole } = renderSurface();
    fireEvent.click(getByText(fill(t("chpHouseholdTpl", "en"), { n: 6 })));
    fireEvent.click(getByRole("button", { name: t("chpStartAssessment", "en") }));
    expect(getByRole("heading", { level: 1 }).textContent).toBe(t("chpIntakeTitle", "en"));
  });

  it("queues the handoff offline, then sends it when the connection returns", () => {
    const { getByText, getByRole, queryByText } = renderSurface({ offline: true });
    fireEvent.click(getByText(fill(t("chpHouseholdTpl", "en"), { n: 1 })));
    fireEvent.click(getByRole("button", { name: t("chpSendHandoff", "en") }));
    expect(getByText(t("chpQueuedNotice", "en"))).toBeTruthy();

    fireEvent.click(getByText("toggle-offline"));
    expect(queryByText(t("chpQueuedNotice", "en"))).toBeNull();
    expect(getByRole("button", { name: t("chpTrackReferral", "en") })).toBeTruthy();
  });

  it("assesses, decides with decide(), and keeps the roster on this phone only", () => {
    const { container, getByText, getByRole, getByLabelText } = renderSurface();
    fireEvent.click(getByText(fill(t("chpHouseholdTpl", "en"), { n: 6 })));
    fireEvent.click(getByRole("button", { name: t("chpStartAssessment", "en") }));
    fireEvent.click(getByLabelText(t("breathingSevere", "en")));
    fireEvent.click(getByRole("button", { name: t("chpSeeResult", "en") }));
    expect(getByRole("heading", { level: 1 }).textContent).toBe(t("goNow", "en"));
    const danger = container.querySelector('[data-named-state="danger_sign"]');
    expect(danger?.textContent).toContain(t("dangerStrugglingBreathe", "en"));
    const stored = JSON.parse(localStorage.getItem(CHP_STORAGE_KEY) ?? "[]");
    expect(stored.every((household: { demo: boolean }) => household.demo === true)).toBe(true);
  });

  it("records the outcome so the loop closes", () => {
    const { getByText, getByRole, queryByText } = renderSurface();
    fireEvent.click(getByText(fill(t("chpHouseholdTpl", "en"), { n: 4 })));
    fireEvent.click(getByRole("button", { name: outcomeLabel("treated", "en") }));
    expect(queryByText(t("chpOutcomePrompt", "en"))).toBeNull();
    expect(getByText(t("refOutcomeChpHeadline", "en"))).toBeTruthy();
  });

  it("never shows the shadow model's answer or contract to a CHP", () => {
    const source = readFileSync(
      join(__dirname, "..", "components", "surfaces", "ChpSurface.tsx"),
      "utf8",
    );
    expect(source).not.toMatch(/lib\/clinical/);
    const { container } = renderSurface();
    const contractKeys = (Object.keys(copyTables.en) as CopyKey[]).filter((key) =>
      key.startsWith("contract"),
    );
    for (const key of contractKeys) {
      expect(container.textContent).not.toContain(t(key, "en"));
    }
  });

  it("keeps household labels out of the daily summary", () => {
    const { container } = renderSurface();
    const summary = container.querySelector('[aria-labelledby="chp-summary-title"]');
    for (const household of seedHouseholds(Date.now())) {
      expect(summary?.textContent).not.toContain(
        fill(t("chpHouseholdTpl", "en"), { n: household.number }),
      );
    }
  });
});
