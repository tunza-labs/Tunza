/** V1 care-path component. Reused across household, CHP, and facility. */

import type { NamedWarning } from "@/lib/failures";

type Props = {
  named: NamedWarning;
  eyebrow: string;
  title: string;
  body?: string;
  /** Interrupt assistive tech (role="alert") — reserved for danger signs. */
  assertive?: boolean;
};

const TONE: Record<NamedWarning, string> = {
  offline: "bg-warn-soft text-warn",
  no_facility_response: "bg-today-soft text-today",
  redirected: "bg-watch-soft text-watch",
  stale_information: "bg-warn-soft text-warn",
  incomplete_assessment: "bg-warn-soft text-warn",
  weak_connection: "bg-warn-soft text-warn",
  danger_sign: "bg-urgent-soft text-urgent",
  watch_sign: "bg-watch-soft text-watch",
};

export function Warning({ named, eyebrow, title, body, assertive = false }: Props) {
  return (
    <aside
      className={`rounded-2xl px-4 py-3 ${TONE[named]}`}
      role={assertive ? "alert" : "status"}
      data-named-state={named}
    >
      <p className="text-caption font-medium uppercase tracking-[0.12em]">{eyebrow}</p>
      <p className="mt-1 text-body font-semibold">{title}</p>
      {body ? <p className="mt-1 text-label font-normal opacity-90">{body}</p> : null}
    </aside>
  );
}
