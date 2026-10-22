/** V1 care-path component. Reused across household, CHP, and facility. */

import { useEffect, useRef } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { t, type Locale } from "@/lib/copy";

export type Choice = {
  id: string;
  label: string;
  /** Optional picture beside the words; the words always carry the meaning. */
  icon?: IconName;
};

export type EntryMode = "type" | "speak" | "photo";

type EntryProps = {
  mode: EntryMode;
  onMode: (mode: EntryMode) => void;
  text: string;
  onText: (text: string) => void;
  listening: boolean;
  speakAvailable: boolean;
  speakLabel?: string;
  onSpeak: () => void;
  speakMessage?: string;
  photoAttached: boolean;
  onPhoto: (attached: boolean) => void;
};

type Props = {
  locale: Locale;
  question: string;
  hint?: string;
  choices?: Choice[];
  dontKnowLabel: string;
  onDontKnow: () => void;
  onChoose?: (id: string) => void;
  action?: { label: string; disabled?: boolean; onClick: () => void };
  entry?: EntryProps;
  /** Move focus to the question whenever it changes (household flow). */
  focusOnChange?: boolean;
  /** Optional picture beside "I don't know". */
  dontKnowIcon?: IconName;
};

export function AssessmentQuestion({
  locale,
  question,
  hint,
  choices = [],
  dontKnowLabel,
  onDontKnow,
  onChoose,
  action,
  entry,
  focusOnChange = false,
  dontKnowIcon,
}: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (focusOnChange) {
      headingRef.current?.focus();
    }
  }, [focusOnChange, question]);

  return (
    <section className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-decision font-semibold tracking-tight text-ink outline-none"
        >
          {question}
        </h1>
        {hint ? <p className="text-body text-ink-soft">{hint}</p> : null}
      </header>

      {entry ? <EntryControls locale={locale} {...entry} /> : null}

      {choices.length > 0 ? (
        <div className="flex flex-col gap-2" role="group" aria-label={question}>
          {choices.map((choice) => (
            <button
              key={choice.id}
              type="button"
              className="flex min-h-16 items-center gap-3 rounded-2xl border border-line bg-raised px-4 py-3 text-left text-body font-medium text-ink shadow-[0_1px_0_rgba(28,25,22,0.04)] transition hover:border-ink/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
              onClick={() => onChoose?.(choice.id)}
            >
              {choice.icon ? <Icon name={choice.icon} className="size-7 text-ink-soft" /> : null}
              <span>{choice.label}</span>
            </button>
          ))}
        </div>
      ) : null}

      {action ? (
        <button
          type="button"
          disabled={action.disabled}
          onClick={action.onClick}
          className="min-h-14 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action disabled:cursor-not-allowed disabled:opacity-40"
        >
          {action.label}
        </button>
      ) : null}

      <button
        type="button"
        onClick={onDontKnow}
        className="flex min-h-14 items-center gap-3 rounded-2xl border border-dashed border-ink/25 bg-transparent px-4 py-3 text-left text-body font-normal text-ink-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        {dontKnowIcon ? <Icon name={dontKnowIcon} className="size-7" /> : null}
        <span>{dontKnowLabel}</span>
      </button>
    </section>
  );
}

function EntryControls({
  locale,
  mode,
  onMode,
  text,
  onText,
  listening,
  speakAvailable,
  speakLabel,
  onSpeak,
  speakMessage,
  photoAttached,
  onPhoto,
}: EntryProps & { locale: Locale }) {
  const modes: { id: EntryMode; label: string; icon: IconName }[] = [
    { id: "speak", label: t("modeSpeak", locale), icon: "mic" },
    { id: "type", label: t("modeType", locale), icon: "keyboard" },
    { id: "photo", label: t("modePhoto", locale), icon: "camera" },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div
        className="grid grid-cols-3 gap-1 rounded-xl bg-line/70 p-1"
        role="tablist"
        aria-label={t("entryAria", locale)}
      >
        {modes.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={mode === item.id}
            onClick={() => onMode(item.id)}
            className={`flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-lg text-label font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action ${
              mode === item.id ? "bg-raised text-ink shadow-sm" : "text-ink-soft"
            }`}
          >
            <Icon name={item.icon} className="size-5" />
            {item.label}
          </button>
        ))}
      </div>

      {speakMessage ? (
        <p className="text-label text-ink-soft" role="status">
          {speakMessage}
        </p>
      ) : null}

      {mode === "speak" ? (
        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={onSpeak}
            aria-pressed={listening}
            className="flex min-h-16 items-center gap-3 rounded-2xl border border-line bg-raised px-4 text-left text-body font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
          >
            <Icon name="mic" className="size-7 text-ink-soft" />
            {speakLabel ??
              (listening
                ? t("listening", locale)
                : speakAvailable
                  ? t("tapToSpeak", locale)
                  : t("speakNotAvailable", locale))}
          </button>
          {text ? (
            <p className="rounded-xl bg-raised px-3 py-2 text-body text-ink">{text}</p>
          ) : null}
        </div>
      ) : null}

      {mode === "type" ? (
        <label className="flex flex-col gap-2">
          <span className="text-label font-medium text-ink-soft">
            {t("typeWhatYouSee", locale)}
          </span>
          <textarea
            value={text}
            onChange={(event) => onText(event.target.value)}
            rows={4}
            className="resize-none rounded-2xl border border-line bg-raised px-4 py-3 text-body text-ink outline-none focus:border-action"
            placeholder={t("whatPlaceholder", locale)}
          />
        </label>
      ) : null}

      {mode === "photo" ? (
        <div className="flex flex-col gap-3">
          <label className="flex min-h-16 cursor-pointer items-center gap-3 rounded-2xl border border-line bg-raised px-4 py-3 text-body font-medium text-ink focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-action">
            <Icon name="camera" className="size-7 text-ink-soft" />
            {photoAttached ? t("photoAttachedDemo", locale) : t("photoTake", locale)}
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                onPhoto(Boolean(file));
              }}
            />
          </label>
          {photoAttached ? (
            <button
              type="button"
              className="min-h-12 text-left text-label font-medium text-ink-soft underline"
              onClick={() => onPhoto(false)}
            >
              {t("photoRemove", locale)}
            </button>
          ) : (
            <p className="text-label text-ink-soft">{t("photoHint", locale)}</p>
          )}
          <label className="flex flex-col gap-2">
            <span className="text-label font-medium text-ink-soft">
              {t("addNote", locale)}
            </span>
            <textarea
              value={text}
              onChange={(event) => onText(event.target.value)}
              rows={2}
              className="resize-none rounded-2xl border border-line bg-raised px-4 py-3 text-body text-ink outline-none focus:border-action"
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}
