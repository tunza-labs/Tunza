import { describe, expect, it } from "vitest";
import { copyTables, fill, t, type CopyKey } from "../lib/copy";

describe("copy parity", () => {
  it("has a Kiswahili string for every English key, and none extra", () => {
    const enKeys = Object.keys(copyTables.en).sort();
    const swKeys = Object.keys(copyTables.sw).sort();
    expect(swKeys).toEqual(enKeys);
  });

  it("never leaves a translation empty", () => {
    for (const key of Object.keys(copyTables.en) as CopyKey[]) {
      expect(copyTables.en[key].trim(), `en.${key}`).not.toBe("");
      expect(copyTables.sw[key].trim(), `sw.${key}`).not.toBe("");
    }
  });

  it("keeps template placeholders identical across languages", () => {
    for (const key of Object.keys(copyTables.en) as CopyKey[]) {
      const placeholders = (text: string) =>
        [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
      expect(placeholders(copyTables.sw[key]), key).toEqual(
        placeholders(copyTables.en[key]),
      );
    }
  });
});

describe("the four decisions", () => {
  it("holds the locked wording in English", () => {
    expect(t("goNow", "en")).toBe("Go now");
    expect(t("getCareToday", "en")).toBe("Get care today");
    expect(t("monitorAtHome", "en")).toBe("Monitor at home");
    expect(t("needOneMore", "en")).toBe("I need one more answer");
  });

  it("holds the locked wording in Kiswahili", () => {
    expect(t("goNow", "sw")).toBe("Nenda sasa");
    expect(t("getCareToday", "sw")).toBe("Pata matibabu leo");
    expect(t("monitorAtHome", "sw")).toBe("Angalia nyumbani");
    expect(t("needOneMore", "sw")).toBe("Nahitaji jibu moja zaidi");
  });
});

describe("facility desk copy", () => {
  const deskKeys = (Object.keys(copyTables.en) as CopyKey[]).filter((key) =>
    /^(desk|eng|capacity|asked|outcomeForm|outcomeReturned|age|sex)/.test(key),
  );

  it("covers every new desk, engineering, capacity and outcome-form key in both languages", () => {
    expect(deskKeys.length).toBeGreaterThanOrEqual(60);
    for (const key of deskKeys) {
      expect(copyTables.sw[key], key).not.toBe(copyTables.en[key]);
    }
  });

  it("marks the shadow candidate as not applied and not validated", () => {
    expect(t("engPanelLabel", "en")).toBe(
      "Shadow candidate, not applied, not clinically validated",
    );
    expect(t("engPanelLabel", "sw")).toContain("halijatumika");
    expect(t("engPanelLabel", "sw")).toContain("halijathibitishwa");
  });

  it("labels the desk as demo with no real patients", () => {
    expect(t("deskDemoNotice", "en")).toContain("No real patients");
    expect(t("deskDemoNotice", "sw")).toContain("Hakuna wagonjwa halisi");
    expect(t("deskSourceSynthetic", "en")).toContain("demo");
  });
});

describe("fill", () => {
  it("replaces named placeholders and leaves unknown ones visible", () => {
    expect(fill("Go to {f}.", { f: "North Demo Health Centre" })).toBe(
      "Go to North Demo Health Centre.",
    );
    expect(fill("expected arrival {m} min", { m: 42 })).toBe(
      "expected arrival 42 min",
    );
    expect(fill("{who} is here", {})).toBe("{who} is here");
  });
});
