import { decisionHeadline } from "./assessment";
import { fill, t, type CopyKey, type Locale } from "./copy";
import { handoffFacts } from "./handoff";
import type { AssessmentAnswers, DecisionKind } from "./types";

/**
 * The plain-text handoff a household shares with its community health
 * promoter. Built only from structured answers and existing copy: it leaves
 * out what the person typed (free text stays on the phone) and the demo
 * temperature value, and always ends with the honest-limits line.
 */
export function householdShareText(input: {
  locale: Locale;
  kind: DecisionKind;
  reasonKeys: CopyKey[];
  facilityName: string;
  answers: AssessmentAnswers;
}): string {
  const { locale, kind, reasonKeys, facilityName, answers } = input;
  const lines = [fill(t("shareHeaderTpl", locale), { d: decisionHeadline(kind, locale) })];
  if (reasonKeys.length > 0) {
    lines.push(`${t("whyThis", locale)} ${reasonKeys.map((key) => t(key, locale)).join(" · ")}`);
  }
  lines.push(fill(t("shareFacilityTpl", locale), { f: facilityName }));
  const skip = new Set([t("handoffDescribed", locale), t("handoffTemp", locale)]);
  for (const fact of handoffFacts(answers, false, new Date().toISOString(), locale)) {
    if (!skip.has(fact.label)) {
      lines.push(`${fact.label}: ${fact.value}`);
    }
  }
  lines.push(t("demoNotDiagnosisShort", locale));
  return lines.join("\n");
}

/** An SMS link that opens the phone's own messaging app; works without data. */
export function smsHref(text: string): string {
  return `sms:?&body=${encodeURIComponent(text)}`;
}
