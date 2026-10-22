import { useId } from "react";
import type { RenderedAssessment } from "@/lib/clinical/pipeline";
import { t, type Locale } from "@/lib/copy";

type Props = {
  locale: Locale;
  rendered: RenderedAssessment | null;
};

/**
 * The ten-section clinical assessment, rendered from the existing pipeline
 * output. Section labels come from the copy table; the bodies are the
 * structured contract fields as recorded, never rewritten into prose.
 */
export function AssessmentSections({ locale, rendered }: Props) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-2xl border border-line bg-raised px-4 py-4"
    >
      <h2 id={headingId} className="text-heading font-semibold text-ink">
        {t("deskAssessmentHeading", locale)}
      </h2>
      <p className="text-label text-ink-soft">{t("deskAssessmentNote", locale)}</p>
      {rendered ? (
        <div className="mt-3 flex flex-col gap-4">
          {rendered.sections.map((section) => (
            <section key={section.key} data-section={section.key}>
              <h3 className="text-caption font-medium uppercase tracking-[0.12em] text-ink-soft">
                {section.label}
              </h3>
              <SectionBody body={section.body} label={section.label} locale={locale} />
            </section>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-body font-semibold text-ink">
          {t("deskAssessmentUnavailable", locale)}
        </p>
      )}
    </section>
  );
}

function SectionBody({
  body,
  label,
  locale,
}: {
  body: unknown;
  label: string;
  locale: Locale;
}) {
  if (Array.isArray(body)) {
    if (body.length === 0) {
      return <p className="mt-1 text-label text-ink">{t("deskSectionEmpty", locale)}</p>;
    }
    const rows = body.filter(isRecord);
    if (rows.length === 0) {
      return <p className="mt-1 text-label text-ink">{formatValue(body)}</p>;
    }
    const columns = Object.keys(rows[0]);
    return (
      <div className="mt-1 overflow-x-auto">
        <table className="w-full border-collapse text-left text-caption text-ink">
          <caption className="sr-only">{label}</caption>
          <thead>
            <tr className="border-b border-line">
              {columns.map((column) => (
                <th key={column} scope="col" className="px-1 py-1 font-medium text-ink-soft">
                  {humanize(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-line align-top last:border-b-0">
                {columns.map((column) => (
                  <td key={column} className="break-words px-1 py-1 font-mono">
                    {formatValue(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (isRecord(body)) {
    return (
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-caption">
        {Object.entries(body).map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="font-medium text-ink-soft">{humanize(key)}</dt>
            <dd className="break-words font-mono text-ink">{formatValue(value)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <p className="mt-1 text-label text-ink">{formatValue(body)}</p>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function humanize(key: string): string {
  return key.replace(/_/g, " ");
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    return value.length === 0 ? "—" : value.map(formatValue).join(", ");
  }
  if (isRecord(value)) return JSON.stringify(value);
  return String(value);
}
