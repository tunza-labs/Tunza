import { t, type CopyKey, type Locale } from "./copy";
import type {
  AskMoreCode,
  AssessmentAnswers,
  Decision,
  DecisionKind,
  QuestionId,
} from "./types";

export const EMPTY_ANSWERS: AssessmentAnswers = {
  who: null,
  presentation: "",
  photoAttached: false,
  awake: null,
  breathing: null,
  drinking: null,
  duration: null,
  mainProblem: null,
};

export const QUESTION_ORDER: QuestionId[] = [
  "who",
  "what",
  "awake",
  "breathing",
  "drinking",
  "duration",
  "main_problem",
];

/**
 * Demonstration triage rules, deliberately conservative. Danger patterns
 * listen in English and Kiswahili. Not clinically validated — the deterministic
 * safety layer described in the README replaces this before real use.
 */
const DANGER_PATTERNS: { re: RegExp; key: CopyKey }[] = [
  {
    re: /unconscious|not waking|won'?t wake|hajitambui|haamki/,
    key: "dangerNotWaking",
  },
  { re: /seizure|convulsion|fitting|kifafa|degedege/, key: "dangerSeizure" },
  { re: /not breathing|stopped breathing|hapumui/, key: "dangerNotBreathing" },
  { re: /blue lips|blue face|midomo ya bluu/, key: "dangerBlueLips" },
  {
    re: /bleeding (a lot|heavily|won'?t stop)|heavy bleeding|damu nyingi/,
    key: "dangerHeavyBleeding",
  },
];

const WATCH_SIGN_KEYS: CopyKey[] = [
  "watchNotWaking",
  "watchBreathingHard",
  "watchCannotDrink",
  "watchSeizureBleeding",
];

const NEGATORS = new Set([
  "no",
  "not",
  "never",
  "without",
  "hakuna",
  "hana",
  "haina",
  "hakuwa",
  "hajawahi",
  "bila",
  "si",
]);
const CONTRASTS = new Set(["but", "lakini", "ila", "however", "though"]);

/**
 * True when the pattern matches somewhere that is not negated. A match counts
 * as negated only when a negator sits within the three words before it, in
 * the same clause, with no "but" between them. Any unnegated match wins, so
 * a stray "no" can never hide a real danger word. Engineering shakedown rule;
 * a clinician has not reviewed it.
 */
export function hasUnnegatedMatch(re: RegExp, lower: string): boolean {
  const global = new RegExp(re.source, "g");
  for (const m of lower.matchAll(global)) {
    const before = lower.slice(0, m.index ?? 0);
    const clause = before.split(/[.,;:!?\n]/).pop() ?? "";
    const words = clause.trim().split(/\s+/).filter(Boolean).slice(-3);
    let negatedAt = -1;
    words.forEach((word, index) => {
      if (NEGATORS.has(word)) negatedAt = index;
    });
    const contrasted =
      negatedAt >= 0 && words.slice(negatedAt + 1).some((w) => CONTRASTS.has(w));
    if (negatedAt < 0 || contrasted) return true;
  }
  return false;
}

export function presentationDangerSigns(text: string): CopyKey[] {
  const lower = text.toLowerCase();
  return DANGER_PATTERNS.filter((item) => hasUnnegatedMatch(item.re, lower)).map(
    (item) => item.key,
  );
}

export function hasFever(text: string): boolean {
  return /fever|hot body|temperature|homa/.test(text.toLowerCase());
}

export function hasInjury(text: string): boolean {
  return /wound|cut|bleed|injury|burn|fall|jeraha|ajali|damu/.test(
    text.toLowerCase(),
  );
}

function tooIncomplete(answers: AssessmentAnswers): boolean {
  const critical = [answers.awake, answers.breathing, answers.drinking];
  const unknownCount = critical.filter(
    (value) => value === "unknown" || value === null,
  ).length;
  const noStory = answers.presentation.trim().length === 0 && !answers.photoAttached;
  return unknownCount >= 2 && noStory;
}

function confidentHomeWatch(answers: AssessmentAnswers): boolean {
  return (
    answers.awake === "alert" &&
    answers.breathing === "fine" &&
    answers.drinking === "yes"
  );
}

export function decide(answers: AssessmentAnswers): Decision {
  const dangerSignKeys: CopyKey[] = [
    ...presentationDangerSigns(answers.presentation),
  ];
  const reasonKeys: CopyKey[] = [];

  if (answers.awake === "not_waking") {
    dangerSignKeys.push("dangerNotWaking");
  }
  if (answers.breathing === "severe") {
    dangerSignKeys.push("dangerStrugglingBreathe");
  }
  if (answers.drinking === "no" && answers.who === "child") {
    dangerSignKeys.push("dangerChildNoDrink");
  }
  if (answers.mainProblem === "injury" && hasInjury(answers.presentation)) {
    if (hasUnnegatedMatch(/heavy|won'?t stop|a lot|nyingi/, answers.presentation.toLowerCase())) {
      dangerSignKeys.push("dangerHeavyBleeding");
    }
  }

  const uniqueDanger = [...new Set(dangerSignKeys)];

  if (uniqueDanger.length > 0) {
    return {
      kind: "go_now",
      reasonKeys: uniqueDanger,
      dangerSignKeys: uniqueDanger,
      watchSignKeys: WATCH_SIGN_KEYS,
    };
  }

  if (answers.breathing === "difficult" && answers.awake === "sleepy") {
    return {
      kind: "go_now",
      reasonKeys: ["reasonSleepyHardBreathing"],
      dangerSignKeys: uniqueDanger,
      watchSignKeys: WATCH_SIGN_KEYS,
    };
  }

  if (tooIncomplete(answers) && answers.mainProblem !== null) {
    return {
      kind: "need_one_more_answer",
      reasonKeys: ["reasonTooLittleKnown"],
      dangerSignKeys: uniqueDanger,
      watchSignKeys: WATCH_SIGN_KEYS,
    };
  }

  if (tooIncomplete(answers) && answers.duration !== null) {
    return {
      kind: "need_one_more_answer",
      reasonKeys: ["reasonOneMoreSafer"],
      dangerSignKeys: uniqueDanger,
      watchSignKeys: WATCH_SIGN_KEYS,
    };
  }

  let kind: DecisionKind = "monitor_at_home";

  if (answers.breathing === "difficult") {
    kind = "get_care_today";
    reasonKeys.push("reasonBreathingHarder");
  }
  if (answers.drinking === "little") {
    kind = "get_care_today";
    reasonKeys.push("reasonDrinkingLittle");
  }
  if (answers.drinking === "no") {
    kind = "get_care_today";
    reasonKeys.push("reasonNotDrinking");
  }
  if (answers.awake === "sleepy") {
    kind = "get_care_today";
    reasonKeys.push("reasonSleepy");
  }
  if (answers.who === "child" && hasFever(answers.presentation)) {
    kind = "get_care_today";
    reasonKeys.push("reasonChildFever");
  }
  if (answers.mainProblem === "fever" && answers.who === "child") {
    kind = "get_care_today";
    reasonKeys.push("reasonChildFever");
  }
  if (answers.mainProblem === "injury") {
    kind = "get_care_today";
    reasonKeys.push("reasonInjurySeen");
  }
  if (answers.mainProblem === "breathing") {
    kind = "get_care_today";
    reasonKeys.push("reasonBreathingMain");
  }
  if (
    answers.duration === "longer" &&
    (hasFever(answers.presentation) || answers.mainProblem === "fever")
  ) {
    kind = "get_care_today";
    reasonKeys.push("reasonTooLongHome");
  }

  if (kind === "monitor_at_home") {
    if (!confidentHomeWatch(answers) && answers.mainProblem === null) {
      return {
        kind: "need_one_more_answer",
        reasonKeys: ["reasonOneMoreSafer"],
        dangerSignKeys: uniqueDanger,
        watchSignKeys: WATCH_SIGN_KEYS,
      };
    }
    if (!confidentHomeWatch(answers) && tooIncomplete(answers)) {
      return {
        kind: "need_one_more_answer",
        reasonKeys: ["reasonTooLittleKnown"],
        dangerSignKeys: uniqueDanger,
        watchSignKeys: WATCH_SIGN_KEYS,
      };
    }
    reasonKeys.push("reasonNoDanger");
  }

  return {
    kind,
    reasonKeys: [...new Set(reasonKeys)],
    dangerSignKeys: uniqueDanger,
    watchSignKeys: WATCH_SIGN_KEYS,
  };
}

export function shouldStopForDecision(
  answers: AssessmentAnswers,
  lastAsked: QuestionId,
): boolean {
  const decision = decide(answers);

  if (lastAsked === "what" && decision.kind === "go_now") {
    return true;
  }
  if (lastAsked === "awake" && answers.awake === "not_waking") {
    return true;
  }
  if (lastAsked === "breathing" && answers.breathing === "severe") {
    return true;
  }
  if (
    lastAsked === "drinking" &&
    answers.drinking === "no" &&
    answers.who === "child"
  ) {
    return true;
  }
  if (lastAsked === "duration") {
    return true;
  }
  if (lastAsked === "main_problem") {
    return true;
  }
  return false;
}

export function nextQuestion(
  answers: AssessmentAnswers,
  lastAsked: QuestionId,
): QuestionId | null {
  if (shouldStopForDecision(answers, lastAsked)) {
    return null;
  }

  switch (lastAsked) {
    case "who":
      return "what";
    case "what":
      return "awake";
    case "awake":
      return "breathing";
    case "breathing":
      return "drinking";
    case "drinking":
      return "duration";
    case "duration":
      return "main_problem";
    case "main_problem":
      return null;
  }
}

export function applyAnswer(
  answers: AssessmentAnswers,
  question: QuestionId,
  value: string,
): AssessmentAnswers {
  const next = { ...answers };
  switch (question) {
    case "who":
      next.who = value as AssessmentAnswers["who"];
      break;
    case "what":
      next.presentation = value;
      break;
    case "awake":
      next.awake = value as AssessmentAnswers["awake"];
      break;
    case "breathing":
      next.breathing = value as AssessmentAnswers["breathing"];
      break;
    case "drinking":
      next.drinking = value as AssessmentAnswers["drinking"];
      break;
    case "duration":
      next.duration = value as AssessmentAnswers["duration"];
      break;
    case "main_problem":
      next.mainProblem = value as AssessmentAnswers["mainProblem"];
      break;
  }
  return next;
}

export type MissingItem = {
  id: string;
  label: string;
  detail?: string;
};

export function missingInfo(
  answers: AssessmentAnswers,
  askMore: AskMoreCode | null,
  locale: Locale,
): MissingItem[] {
  const items: MissingItem[] = [];

  if (!answers.who || answers.who === "unknown") {
    items.push({
      id: "who",
      label: t("missingWho", locale),
      detail: t("missingWhoDetail", locale),
    });
  }
  if (!answers.presentation.trim() && !answers.photoAttached) {
    items.push({ id: "what", label: t("missingWhat", locale) });
  }
  if (!answers.awake || answers.awake === "unknown") {
    items.push({ id: "awake", label: t("missingAwake", locale) });
  }
  if (!answers.breathing || answers.breathing === "unknown") {
    items.push({ id: "breathing", label: t("missingBreathing", locale) });
  }
  if (!answers.drinking || answers.drinking === "unknown") {
    items.push({ id: "drinking", label: t("missingDrinking", locale) });
  }
  if (askMore === "can_walk") {
    items.push({
      id: "ask-more",
      label: t("askMoreCanWalk", locale),
      detail: t("missingAskMoreDetail", locale),
    });
  }
  return items;
}

export function decisionHeadline(kind: DecisionKind, locale: Locale): string {
  switch (kind) {
    case "go_now":
      return t("goNow", locale);
    case "get_care_today":
      return t("getCareToday", locale);
    case "monitor_at_home":
      return t("monitorAtHome", locale);
    case "need_one_more_answer":
      return t("needOneMore", locale);
  }
}

export function decisionStatus(kind: DecisionKind, locale: Locale): string {
  switch (kind) {
    case "go_now":
      return t("goNowStatus", locale);
    case "get_care_today":
      return t("getCareStatus", locale);
    case "monitor_at_home":
      return t("monitorStatus", locale);
    case "need_one_more_answer":
      return t("needOneMoreStatus", locale);
  }
}
