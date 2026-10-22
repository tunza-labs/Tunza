// @vitest-environment jsdom
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssessmentQuestion } from "../components/AssessmentQuestion";
import { DecisionResult } from "../components/DecisionResult";
import { DangerStrip, HOUSEHOLD_WATCH_KEYS } from "../components/household/DangerStrip";
import { DemoNotice } from "../components/household/DemoNotice";
import { ShareHandoff } from "../components/household/ShareHandoff";
import { NearbyFacilities } from "../components/NearbyFacilities";
import { HouseholdSurface } from "../components/surfaces/HouseholdSurface";
import { decide, decisionHeadline, decisionStatus, EMPTY_ANSWERS } from "../lib/assessment";
import { t, type Locale } from "../lib/copy";
import { DEMO_FACILITIES } from "../lib/facilities";
import { householdShareText, smsHref } from "../lib/householdShare";
import { CareProvider } from "../lib/store";

const LOCALES: Locale[] = ["en", "sw"];
const noop = () => {};

function clearStorage() {
  try {
    localStorage.clear();
  } catch {
    // Storage unavailable in this runtime; the app tolerates that too.
  }
}

beforeEach(clearStorage);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DangerStrip", () => {
  it("mirrors the watch signs decide() returns", () => {
    expect(HOUSEHOLD_WATCH_KEYS).toEqual(decide(EMPTY_ANSWERS).watchSignKeys);
  });

  it.each(LOCALES)("is calm and polite when no danger sign is present (%s)", (locale) => {
    const { container, getByRole } = render(<DangerStrip locale={locale} danger={null} />);
    expect(container.querySelector('[data-danger-strip="calm"]')).toBeTruthy();
    expect(getByRole("status").textContent).toContain(t("watchTitle", locale));
    for (const key of HOUSEHOLD_WATCH_KEYS) {
      expect(container.textContent).toContain(t(key, locale));
    }
  });

  it.each(LOCALES)("turns assertive and names the sign when one is present (%s)", (locale) => {
    const { getByRole, container } = render(
      <DangerStrip locale={locale} danger={["dangerSeizure"]} />,
    );
    const alert = getByRole("alert");
    expect(alert.textContent).toContain(t("dangerTitle", locale));
    expect(alert.textContent).toContain(t("dangerSeizure", locale));
    expect(alert.getAttribute("data-named-state")).toBe("danger_sign");
    expect(container.querySelector('[data-danger-strip="alert"]')).toBeTruthy();
  });
});

describe("DemoNotice", () => {
  it.each(LOCALES)("states the honest limits in plain words (%s)", (locale) => {
    const onDismiss = vi.fn();
    const { getByRole, getByText } = render(<DemoNotice locale={locale} onDismiss={onDismiss} />);
    expect(getByRole("heading", { level: 2 }).textContent).toBe(t("noticeTitle", locale));
    expect(getByText(t("noticeBody", locale))).toBeTruthy();
    fireEvent.click(getByRole("button", { name: t("noticeDismiss", locale) }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

describe("AssessmentQuestion with icons", () => {
  it.each(LOCALES)("keeps the words as the accessible name beside the picture (%s)", (locale) => {
    const { getByRole, container } = render(
      <AssessmentQuestion
        locale={locale}
        question={t("whoQuestion", locale)}
        choices={[{ id: "child", label: t("whoChild", locale), icon: "child" }]}
        dontKnowLabel={t("whoUnknown", locale)}
        dontKnowIcon="question"
        onDontKnow={noop}
        onChoose={noop}
        focusOnChange
      />,
    );
    expect(getByRole("button", { name: t("whoChild", locale) })).toBeTruthy();
    expect(getByRole("button", { name: t("whoUnknown", locale) })).toBeTruthy();
    const icons = container.querySelectorAll("svg[data-icon]");
    expect(icons.length).toBe(2);
    icons.forEach((icon) => expect(icon.getAttribute("aria-hidden")).toBe("true"));
    expect(document.activeElement).toBe(getByRole("heading", { level: 1 }));
  });
});

describe("DecisionResult lead slot", () => {
  it.each(LOCALES)("puts support between the verdict and the action (%s)", (locale) => {
    const { getByRole, getByText } = render(
      <DecisionResult
        locale={locale}
        kind="get_care_today"
        headline={decisionHeadline("get_care_today", locale)}
        status={decisionStatus("get_care_today", locale)}
        action={{ label: t("prepareFacility", locale), onClick: noop }}
        lead={<p>{t("waitToday", locale)}</p>}
        autoFocus
      />,
    );
    const heading = getByRole("heading", { level: 1 });
    expect(document.activeElement).toBe(heading);
    const lead = getByText(t("waitToday", locale));
    const action = getByRole("button", { name: t("prepareFacility", locale) });
    expect(heading.compareDocumentPosition(lead) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(lead.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("household share", () => {
  const answers = {
    ...EMPTY_ANSWERS,
    who: "child" as const,
    presentation: "private words typed at home",
    awake: "alert" as const,
  };

  it.each(LOCALES)("shares structured facts only, ending with the honest limit (%s)", (locale) => {
    const text = householdShareText({
      locale,
      kind: "get_care_today",
      reasonKeys: ["reasonChildFever"],
      facilityName: "North Demo Health Centre",
      answers,
    });
    expect(text).toContain(decisionHeadline("get_care_today", locale));
    expect(text).toContain(t("reasonChildFever", locale));
    expect(text).toContain("North Demo Health Centre");
    expect(text).toContain(t("awakeAlert", locale));
    expect(text).not.toContain("private words typed at home");
    expect(text).not.toContain("38.6");
    expect(text.trim().endsWith(t("demoNotDiagnosisShort", locale))).toBe(true);
  });

  it("encodes the SMS body", () => {
    expect(smsHref("Go now\nNorth & co")).toBe("sms:?&body=Go%20now%0ANorth%20%26%20co");
  });

  it.each(LOCALES)("renders one share link that falls back to SMS (%s)", (locale) => {
    const { getByRole } = render(<ShareHandoff locale={locale} text="hello" />);
    const link = getByRole("link", { name: t("shareChp", locale) });
    expect(link.getAttribute("href")).toBe(smsHref("hello"));
  });

  it("uses the phone's share sheet when it has one", () => {
    const share = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, share });
    const { getByRole } = render(<ShareHandoff locale="en" text="hello" />);
    fireEvent.click(getByRole("link"));
    expect(share).toHaveBeenCalledWith({ text: "hello" });
  });
});

describe("NearbyFacilities offline-first", () => {
  it.each(LOCALES)("shows the demo list at once and skips the lookup offline (%s)", (locale) => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });
    const { getByText } = render(<NearbyFacilities locale={locale} offline />);
    expect(getByText(t("nearbyDemoFallback", locale))).toBeTruthy();
    expect(getByText(DEMO_FACILITIES[0].name)).toBeTruthy();
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it("still shows the demo list while locating online", () => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });
    const { getByText } = render(<NearbyFacilities locale="en" />);
    expect(getByText(t("nearbyLocating", "en"))).toBeTruthy();
    expect(getByText(DEMO_FACILITIES[0].name)).toBeTruthy();
    expect(getCurrentPosition).toHaveBeenCalledOnce();
  });
});

function renderHousehold() {
  const fetchSpy = vi.fn(() => Promise.reject(new Error("no network in this test")));
  vi.stubGlobal("fetch", fetchSpy);
  const view = render(
    <CareProvider>
      <HouseholdSurface />
    </CareProvider>,
  );
  fireEvent.click(view.getByText(t("homeGetStarted", "en")));
  return { ...view, fetchSpy };
}

describe("household flow", () => {
  it("shows the honest limits once, then keeps them behind the help link", () => {
    const { getByText, queryByText, getByRole } = renderHousehold();
    expect(getByText(t("noticeTitle", "en"))).toBeTruthy();
    fireEvent.click(getByRole("button", { name: t("noticeDismiss", "en") }));
    expect(queryByText(t("noticeTitle", "en"))).toBeNull();

    const help = getByRole("button", { name: t("helpLink", "en") });
    expect(help.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(help);
    expect(help.getAttribute("aria-expanded")).toBe("true");
    expect(getByText(t("noticeTitle", "en"))).toBeTruthy();
  });

  it("switches to go now the moment a danger sign is typed, with nothing competing", () => {
    const { getByText, getByRole, container, queryByText, fetchSpy } = renderHousehold();
    expect(container.querySelector('[data-danger-strip="calm"]')).toBeTruthy();
    fireEvent.click(getByText(t("whoChild", "en")));
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, {
      target: { value: "she had a seizure" },
    });

    const heading = getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe(t("goNow", "en"));
    expect(document.activeElement).toBe(heading);
    expect(getByRole("alert").textContent).toContain(t("dangerSeizure", "en"));
    expect(getByText(t("waitGoNow", "en"))).toBeTruthy();
    expect(getByText(DEMO_FACILITIES[0].name)).toBeTruthy();
    expect(getByRole("link", { name: t("shareChp", "en") })).toBeTruthy();
    expect(container.querySelector("[data-why-line]")).toBeNull();
    expect(container.querySelector('[data-danger-strip="calm"]')).toBeNull();
    expect(queryByText(t("noticeTitle", "en"))).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("leads a calm result with one action, why in one line, and what to do", () => {
    const { getByText, getByRole, container, queryByRole, fetchSpy } = renderHousehold();
    fireEvent.click(getByText(t("whoSelf", "en")));
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, {
      target: { value: "headache" },
    });
    fireEvent.click(getByRole("button", { name: t("whatContinue", "en") }));
    fireEvent.click(getByText(t("awakeAlert", "en")));
    fireEvent.click(getByText(t("breathingFine", "en")));
    fireEvent.click(getByText(t("drinkingYes", "en")));
    fireEvent.click(getByText(t("durationToday", "en")));

    expect(getByRole("heading", { level: 1 }).textContent).toBe(t("monitorAtHome", "en"));
    const why = container.querySelector("[data-why-line]") as HTMLElement;
    expect(why.textContent).toContain(t("reasonNoDanger", "en"));
    expect(getByText(t("waitMonitor", "en"))).toBeTruthy();
    const strip = container.querySelector('[data-danger-strip="calm"]') as HTMLElement;
    expect(within(strip).getByText(t("watchTitle", "en"))).toBeTruthy();
    expect(queryByRole("alert")).toBeNull();
    expect(getByRole("link", { name: t("shareChp", "en") })).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("household boundary", () => {
  it("never imports the clinical model layer", () => {
    const root = join(__dirname, "..");
    const files = [
      "components/surfaces/HouseholdSurface.tsx",
      "components/AssessmentFlow.tsx",
      "lib/householdShare.ts",
      ...readdirSync(join(root, "components/household")).map(
        (name) => `components/household/${name}`,
      ),
    ];
    for (const file of files) {
      const source = readFileSync(join(root, file), "utf8");
      expect(source, file).not.toMatch(/lib\/clinical/);
    }
  });
});
