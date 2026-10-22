import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CHIP_CLASS, CHIP_TOKENS } from "../components/StatusChip";

/**
 * The color contract, enforced mechanically against the real tokens in
 * app/globals.css: every text pairing meets WCAG AA (4.5:1), component fills
 * meet non-text contrast (3:1), and the emergency red stays distinctly
 * brighter than the matte brand red so the two can never be confused.
 */

function tokens(): Record<string, string> {
  const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");
  const out: Record<string, string> = {};
  for (const match of css.matchAll(/--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})/g)) {
    out[match[1]] = match[2];
  }
  return out;
}

function luminance(hex: string): number {
  const n = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4]
    .map((i) => parseInt(n.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT_PAIRS: [string, string][] = [
  ["action-ink", "action"], // button text on the brand red
  ["action-ink", "brand-deep"], // white text on the home screen's deep end
  ["action", "raised"], // the inverted home CTA: brand text on raised
  ["action", "paper"], // the wordmark and any brand-red text
  ["ink", "paper"],
  ["ink", "raised"],
  ["ink-soft", "paper"],
  ["ink-soft", "raised"],
  ["urgent", "paper"], // the Go now verdict
  ["urgent", "raised"],
  ["urgent", "urgent-soft"], // danger panels
  ["today", "paper"],
  ["today", "today-soft"],
  ["watch", "paper"],
  ["watch", "watch-soft"],
  ["warn", "warn-soft"],
];

const FILL_PAIRS: [string, string][] = [
  ["action", "paper"], // primary button against the screen
  ["action", "raised"],
];

describe("color tokens", () => {
  const colors = tokens();

  it("finds the token table in globals.css", () => {
    for (const name of ["action", "urgent", "paper", "ink"]) {
      expect(colors[name], name).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it.each(TEXT_PAIRS)("%s on %s meets WCAG AA text contrast", (fg, bg) => {
    expect(ratio(colors[fg], colors[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(FILL_PAIRS)("%s fill against %s meets non-text contrast", (fg, bg) => {
    expect(ratio(colors[fg], colors[bg])).toBeGreaterThanOrEqual(3);
  });

  it.each(Object.entries(CHIP_TOKENS))(
    "CHP %s chip text meets WCAG AA on its fill and on the row",
    (status, [fg, bg]) => {
      expect(colors[fg], `${status} text`).toBeDefined();
      expect(colors[bg], `${status} fill`).toBeDefined();
      expect(ratio(colors[fg], colors[bg])).toBeGreaterThanOrEqual(4.5);
      expect(CHIP_CLASS[status as keyof typeof CHIP_CLASS]).toBe(`text-${fg} bg-${bg}`);
    },
  );

  it("keeps the emergency red distinctly brighter than the brand red", () => {
    expect(luminance(colors.urgent)).toBeGreaterThanOrEqual(
      luminance(colors.action) * 1.5,
    );
  });
});
