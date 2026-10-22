// @vitest-environment jsdom
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssessmentSections } from "../components/facility/AssessmentSections";
import { CapacityControl } from "../components/facility/CapacityControl";
import { DeskInbox } from "../components/facility/DeskInbox";
import { EngineeringPanel } from "../components/facility/EngineeringPanel";
import { OutcomeForm } from "../components/facility/OutcomeForm";
import { FacilitySurface } from "../components/surfaces/FacilitySurface";
import { t, type Locale } from "../lib/copy";
import { deskCases, deskRow, reviewCase, seedDemoCases, sortDeskCases } from "../lib/desk";
import { CareProvider, initialCareState } from "../lib/store";
import type { CareState } from "../lib/types";

const LOCALES: Locale[] = ["en", "sw"];
const NOW = Date.now();
const noop = () => {};

function facilityState(locale: Locale): CareState {
  return {
    ...initialCareState,
    role: "facility",
    locale,
    grants: { chp: false, facility: true },
    demoCases: seedDemoCases(new Date(NOW).toISOString()),
  };
}

function rowsFor(locale: Locale, capacity = {}) {
  const state = facilityState(locale);
  return sortDeskCases(deskCases(state), "north-demo").map((item) =>
    deskRow(item, "north-demo", capacity, locale, NOW),
  );
}

afterEach(cleanup);

describe("DeskInbox", () => {
  it.each(LOCALES)("is a real table with caption, column and row headers (%s)", (locale) => {
    const rows = rowsFor(locale);
    const { getByRole, getAllByRole } = render(
      <DeskInbox
        locale={locale}
        rows={rows}
        onOpen={noop}
        onAccept={noop}
        onRedirect={noop}
        onDecline={noop}
      />,
    );
    const table = getByRole("table");
    expect(table.querySelector("caption")?.textContent).toBe(t("deskTableCaption", locale));
    expect(getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      t("deskColPatient", locale),
      t("deskColAnswer", locale),
      t("deskColStage", locale),
      t("deskColActions", locale),
    ]);
    expect(getAllByRole("rowheader")).toHaveLength(rows.length);
    expect(getByRole("heading", { level: 1 }).textContent).toBe(t("deskTitle", locale));
    expect(table.textContent).not.toMatch(/go_now|get_care_today|patient_moving/);
  });

  it.each(LOCALES)("labels every row as demo (%s)", (locale) => {
    const { getAllByText, getByText } = render(
      <DeskInbox
        locale={locale}
        rows={rowsFor(locale)}
        onOpen={noop}
        onAccept={noop}
        onRedirect={noop}
        onDecline={noop}
      />,
    );
    expect(getAllByText(t("deskSourceSynthetic", locale))).toHaveLength(5);
    expect(getByText(t("deskDemoNotice", locale))).toBeTruthy();
  });

  it("wires accept, redirect, cannot take and open to the row id", () => {
    const onOpen = vi.fn();
    const onAccept = vi.fn();
    const onRedirect = vi.fn();
    const onDecline = vi.fn();
    const rows = rowsFor("en");
    const { container } = render(
      <DeskInbox
        locale="en"
        rows={rows}
        onOpen={onOpen}
        onAccept={onAccept}
        onRedirect={onRedirect}
        onDecline={onDecline}
      />,
    );
    const rowA = container.querySelector('tr[data-row-id="demo-ref-a"]') as HTMLElement;
    const scoped = within(rowA);
    fireEvent.click(scoped.getByRole("button", { name: /^Accept/ }));
    fireEvent.click(scoped.getByRole("button", { name: /^Redirect/ }));
    fireEvent.click(scoped.getByRole("button", { name: /^Cannot take/ }));
    fireEvent.click(scoped.getByRole("button", { name: rows.find((r) => r.id === "demo-ref-a")!.patientLabel }));
    expect(onAccept).toHaveBeenCalledWith("demo-ref-a");
    expect(onRedirect).toHaveBeenCalledWith("demo-ref-a");
    expect(onDecline).toHaveBeenCalledWith("demo-ref-a");
    expect(onOpen).toHaveBeenCalledWith("demo-ref-a");
  });

  it("says why redirect is missing when no other facility is open", () => {
    const { container } = render(
      <DeskInbox
        locale="en"
        rows={rowsFor("en", { "west-demo": "closed" })}
        onOpen={noop}
        onAccept={noop}
        onRedirect={noop}
        onDecline={noop}
      />,
    );
    const rowA = within(container.querySelector('tr[data-row-id="demo-ref-a"]') as HTMLElement);
    expect(rowA.queryByRole("button", { name: /^Redirect/ })).toBeNull();
    expect(rowA.getByText(t("deskNoOpenFacility", "en"))).toBeTruthy();
  });
});

describe("EngineeringPanel", () => {
  const item = deskCases(facilityState("en")).find((c) => c.id === "demo-ref-b")!;

  it("renders nothing for the household and CHP roles", () => {
    for (const role of ["household", "chp"] as const) {
      const { container, unmount } = render(
        <EngineeringPanel locale="en" role={role} review={reviewCase(item, "en")} />,
      );
      expect(container.innerHTML).toBe("");
      unmount();
    }
  });

  it.each(LOCALES)("is collapsed by default and always labels the candidate (%s)", (locale) => {
    const { container } = render(
      <EngineeringPanel locale={locale} role="facility" review={reviewCase(item, locale)} />,
    );
    const details = container.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.querySelector("summary")?.textContent).toBe(t("engPanelSummary", locale));
    expect(details.textContent).toContain(t("engPanelLabel", locale));
    expect(details.textContent).toContain("go_now");
    expect(details.textContent).toContain(t("engReasonNotApproved", locale));
    expect(details.textContent).toContain(t("getCareToday", locale));
  });

  it("says when there is no shadow candidate", () => {
    const none = deskCases(facilityState("en")).find((c) => c.id === "demo-ref-c")!;
    const { getByText } = render(
      <EngineeringPanel locale="en" role="facility" review={reviewCase(none, "en")} />,
    );
    expect(getByText(t("engPanelNoCandidate", "en"))).toBeTruthy();
  });
});

describe("OutcomeForm", () => {
  it.each(LOCALES)("sends one outcome code and has no free-text field (%s)", (locale) => {
    const onSubmit = vi.fn();
    const { getByRole, getAllByRole, container } = render(
      <OutcomeForm locale={locale} onSubmit={onSubmit} />,
    );
    expect(getAllByRole("radio")).toHaveLength(4);
    expect(container.querySelector("textarea, input[type=text]")).toBeNull();
    const submit = getByRole("button", { name: t("outcomeFormSubmit", locale) });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(getByRole("radio", { name: t("outcomeHigher", locale) }));
    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith("referred_onward");
  });
});

describe("CapacityControl", () => {
  it.each(LOCALES)("offers accepting, busy and closed as one radio group (%s)", (locale) => {
    const onCapacity = vi.fn();
    const onDesk = vi.fn();
    const { getByRole, getAllByRole } = render(
      <CapacityControl
        locale={locale}
        facilities={[
          { id: "north-demo", name: "North Demo Health Centre" },
          { id: "west-demo", name: "West Demo Sub-County Hospital" },
        ]}
        deskFacilityId="north-demo"
        capacity="accepting"
        onDeskFacility={onDesk}
        onCapacity={onCapacity}
      />,
    );
    expect(getByRole("group", { name: t("deskCapacityLegend", locale) })).toBeTruthy();
    expect(getAllByRole("radio")).toHaveLength(3);
    fireEvent.click(getByRole("radio", { name: t("capacityClosed", locale) }));
    expect(onCapacity).toHaveBeenCalledWith("closed");
    fireEvent.change(getByRole("combobox"), { target: { value: "west-demo" } });
    expect(onDesk).toHaveBeenCalledWith("west-demo");
  });
});

describe("AssessmentSections", () => {
  it.each(LOCALES)("renders the ten pipeline sections with their labels (%s)", (locale) => {
    const item = deskCases(facilityState(locale))[0];
    const review = reviewCase(item, locale);
    const { container } = render(<AssessmentSections locale={locale} rendered={review.rendered} />);
    const headings = [...container.querySelectorAll("h3")].map((h) => h.textContent);
    expect(headings).toEqual(review.rendered!.sections.map((s) => s.label));
    expect(headings).toHaveLength(10);
    expect(container.textContent).toContain(t("deskSectionEmpty", locale));
  });

  it("says so when the assessment could not be built", () => {
    const { getByText } = render(<AssessmentSections locale="en" rendered={null} />);
    expect(getByText(t("deskAssessmentUnavailable", "en"))).toBeTruthy();
  });
});

describe("FacilitySurface", () => {
  // Node's own experimental localStorage global can shadow jsdom's, so the
  // store gets a small in-memory one for these tests.
  beforeEach(() => {
    const data = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => void data.set(key, value),
      removeItem: (key: string) => void data.delete(key),
      clear: () => data.clear(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mount(locale: Locale) {
    localStorage.setItem("tunza.v2.care", JSON.stringify(facilityState(locale)));
    return render(
      <CareProvider>
        <FacilitySurface />
      </CareProvider>,
    );
  }

  it.each(LOCALES)("opens a case that leads with the summary and the ask (%s)", (locale) => {
    const view = mount(locale);
    const table = view.getByRole("table");
    const rowB = within(table.querySelector('tr[data-row-id="demo-ref-b"]') as HTMLElement);
    fireEvent.click(rowB.getAllByRole("button")[0]);

    const heading = view.getByRole("heading", { level: 1 });
    expect(heading.textContent).toContain(t("getCareToday", locale));
    expect(document.activeElement).toBe(heading);
    expect(view.getByText(t("askedToday", locale))).toBeTruthy();
    expect(view.getByText(t("deskTimelineHeading", locale))).toBeTruthy();
    expect(view.getByText(t("deskAssessmentHeading", locale))).toBeTruthy();
    expect(view.getByText(t("handoffEyebrow", locale))).toBeTruthy();
  });

  it("keeps the shadow candidate inside the engineering panel only", () => {
    const view = mount("en");
    const rowB = within(view.container.querySelector('tr[data-row-id="demo-ref-b"]') as HTMLElement);
    fireEvent.click(rowB.getAllByRole("button")[0]);

    const panel = view.container.querySelector("[data-engineering-panel]") as HTMLDetailsElement;
    expect(panel).toBeTruthy();
    expect(panel.open).toBe(false);
    const outside = view.container.textContent!.replace(panel.textContent!, "");
    expect(outside).not.toContain(t("goNow", "en"));
    expect(outside).toContain(t("getCareToday", "en"));
    expect(outside).not.toContain(t("engPanelLabel", "en"));
  });

  it("accepts from the case view and returns focus to the row on back", () => {
    const view = mount("en");
    const rowA = within(view.container.querySelector('tr[data-row-id="demo-ref-a"]') as HTMLElement);
    const open = rowA.getAllByRole("button")[0];
    fireEvent.click(open);
    fireEvent.click(view.getByRole("button", { name: t("actionAccept", "en") }));
    expect(view.getByRole("heading", { level: 1 }).textContent).toContain(
      t("stageAccepted", "en"),
    );
    fireEvent.click(view.getByRole("button", { name: t("deskBackToInbox", "en") }));
    const backRow = view.container.querySelector('tr[data-row-id="demo-ref-a"]') as HTMLElement;
    expect(document.activeElement).toBe(within(backRow).getAllByRole("button")[0]);
    expect(within(backRow).queryByRole("button", { name: /^Accept/ })).toBeNull();
  });

  it("closes the loop with an outcome on a completed case", () => {
    const view = mount("en");
    const rowD = within(view.container.querySelector('tr[data-row-id="demo-ref-d"]') as HTMLElement);
    fireEvent.click(rowD.getAllByRole("button")[0]);
    fireEvent.click(view.getByRole("radio", { name: t("outcomeTreated", "en") }));
    fireEvent.click(view.getByRole("button", { name: t("outcomeFormSubmit", "en") }));
    expect(view.queryByRole("button", { name: t("outcomeFormSubmit", "en") })).toBeNull();
    expect(view.getByText(`Outcome returned: ${t("outcomeTreated", "en")}`)).toBeTruthy();
  });
});
