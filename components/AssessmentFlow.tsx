"use client";

import { useEffect, useRef, useState } from "react";
import { AssessmentQuestion, type EntryMode } from "@/components/AssessmentQuestion";
import type { IconName } from "@/components/Icon";
import { Warning } from "@/components/Warning";
import { presentationDangerSigns } from "@/lib/assessment";
import { t } from "@/lib/copy";
import { warningCopy } from "@/lib/failures";
import { questionContent, dontKnowValue } from "@/lib/questions";
import { startVoice, voiceAvailable, type VoiceHandle, type VoiceState } from "@/lib/voice";
import { activeFailures, useCare } from "@/lib/store";
import type { QuestionId } from "@/lib/types";

/** Pictures beside the household answers. The words still carry the meaning. */
const CHOICE_ICONS: Partial<Record<QuestionId, Record<string, IconName>>> = {
  who: { self: "person", household_adult: "home", child: "child" },
  awake: { alert: "eye", sleepy: "moon", not_waking: "eye-closed" },
  breathing: { fine: "wind", difficult: "wind-fast", severe: "alert" },
  drinking: { yes: "cup", little: "cup-half", no: "cup-empty" },
  duration: { today: "sun", two_days: "calendar", longer: "clock" },
  main_problem: {
    breathing: "wind",
    fever: "thermometer",
    injury: "bandage",
    stomach: "stomach",
    other: "dots",
  },
};

/**
 * `household` turns on the household treatment: icons beside answers, focus
 * that follows the question, and the danger switch — the moment a danger sign
 * newly appears in what is typed or spoken, the answer is committed so the
 * existing decide() rules move the screen straight to their go-now state.
 */
export function AssessmentFlow({ household = false }: { household?: boolean }) {
  const { state, dispatch } = useCare();
  const encounter = state.encounter;
  const question = encounter?.currentQuestion;
  const locale = state.locale;
  const [mode, setMode] = useState<EntryMode>("type");
  const [voiceState, setVoiceState] = useState<Exclude<VoiceState, "unavailable" | "stopped"> | "idle">("idle");
  const [speakMessage, setSpeakMessage] = useState<string | undefined>();
  const voiceRef = useRef<VoiceHandle | null>(null);

  useEffect(() => {
    return () => {
      voiceRef.current?.stop();
    };
  }, []);

  if (!encounter || !question) {
    return null;
  }

  const content = questionContent(question, encounter.answers.who, locale);
  const currentQuestion = question;
  const currentEncounter = encounter;
  const canGoBack = currentEncounter.asked.length > 0 || Boolean(currentEncounter.decision);
  const failures = activeFailures(state, null).filter(
    (named) =>
      named === "offline" ||
      named === "weak_connection" ||
      named === "incomplete_assessment",
  );
  const offline = failures.includes("offline");

  function updatePresentation(next: string) {
    dispatch.setPresentation(next);
    if (!household || currentQuestion !== "what") {
      return;
    }
    const before = new Set(presentationDangerSigns(currentEncounter.answers.presentation));
    if (presentationDangerSigns(next).some((key) => !before.has(key))) {
      dispatch.answer("what", next.trim());
    }
  }

  function onDontKnow() {
    dispatch.answer(currentQuestion, dontKnowValue(currentQuestion));
  }

  function onSpeak() {
    if (voiceState === "transcribing") {
      return;
    }
    if (voiceState === "listening") {
      voiceRef.current?.stop();
      return;
    }
    if (!voiceAvailable()) {
      setSpeakMessage(t("speakUnavailable", locale));
      setMode("type");
      return;
    }
    setSpeakMessage(undefined);
    voiceRef.current = startVoice({
      locale,
      online: !offline,
      onText: (text) => {
        const current = currentEncounter.answers.presentation;
        updatePresentation(current ? `${current} ${text}` : text);
      },
      onState: (next) => {
        if (next === "listening" || next === "transcribing") {
          setVoiceState(next);
          return;
        }
        setVoiceState("idle");
        if (next === "unavailable") {
          setSpeakMessage(t("speakUnavailable", locale));
          setMode("type");
        }
      },
    });
  }

  const speakLabel =
    voiceState === "listening"
      ? t("listening", locale)
      : voiceState === "transcribing"
        ? t("transcribing", locale)
        : voiceAvailable()
          ? t("tapToSpeak", locale)
          : t("speakNotAvailable", locale);

  return (
    <div className="flex flex-col gap-4">
      {failures.map((named) => {
        const copy = warningCopy(named, locale);
        return (
          <Warning
            key={named}
            named={named}
            eyebrow={copy.eyebrow}
            title={copy.title}
            body={copy.body}
          />
        );
      })}
      {canGoBack ? (
        <button
          type="button"
          onClick={dispatch.goBack}
          className="min-h-12 self-start text-label font-medium text-ink-soft"
        >
          {t("back", locale)}
        </button>
      ) : null}

      <AssessmentQuestion
        locale={locale}
        question={content.question}
        hint={content.hint}
        choices={
          household
            ? content.choices.map((choice) => ({
                ...choice,
                icon: CHOICE_ICONS[currentQuestion]?.[choice.id],
              }))
            : content.choices
        }
        focusOnChange={household}
        dontKnowIcon={household ? "question" : undefined}
        dontKnowLabel={
          currentQuestion === "who" ? t("whoUnknown", locale) : t("dontKnow", locale)
        }
        onDontKnow={onDontKnow}
        onChoose={(id) => dispatch.answer(currentQuestion, id)}
        action={
          currentQuestion === "what"
            ? {
                label: t("whatContinue", locale),
                disabled:
                  currentEncounter.answers.presentation.trim().length === 0 &&
                  !currentEncounter.answers.photoAttached,
                onClick: () =>
                  dispatch.answer("what", currentEncounter.answers.presentation.trim()),
              }
            : undefined
        }
        entry={
          currentQuestion === "what"
            ? {
                mode,
                onMode: setMode,
                text: currentEncounter.answers.presentation,
                onText: updatePresentation,
                listening: voiceState !== "idle",
                speakAvailable: voiceAvailable(),
                speakLabel,
                onSpeak,
                speakMessage,
                photoAttached: currentEncounter.answers.photoAttached,
                onPhoto: dispatch.setPhoto,
              }
            : undefined
        }
      />
    </div>
  );
}
