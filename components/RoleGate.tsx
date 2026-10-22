"use client";

import { useEffect, useState } from "react";
import { t } from "@/lib/copy";
import { useCare } from "@/lib/store";
import type { GatedRole } from "@/lib/types";

/**
 * The health-worker gate: choose CHP or facility, enter the access code.
 * Codes are verified server-side (/api/access) and never shipped to the
 * client; while the server runs on demo codes, the screen says so. This is
 * the placeholder for real worker sign-up and identity.
 *
 * This is a DEMO gate, not authentication: a shared code unlocks a surface
 * on this device, with no accounts, sessions, or per-worker identity. Do not
 * treat a grant as proof of who someone is. Real CHP identity (for example a
 * registry-issued login) is a separate product decision, not built here.
 */
export function RoleGate() {
  const { state, dispatch } = useCare();
  const locale = state.locale;
  const chosen = state.gateRole;
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "checking" | "error">("idle");
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/api/access")
      .then((res) => (res.ok ? res.json() : { demo: false }))
      .then((data: { demo?: boolean }) => {
        if (active) setDemo(!!data.demo);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  function choose(role: GatedRole) {
    if (state.grants[role]) {
      dispatch.setRole(role);
      return;
    }
    setStatus("idle");
    setCode("");
    dispatch.setGateRole(role);
  }

  async function submit() {
    if (!chosen || status === "checking" || code.trim().length === 0) {
      return;
    }
    setStatus("checking");
    try {
      const res = await fetch("/api/access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: chosen, code: code.trim() }),
      });
      if (!res.ok) throw new Error(`access check failed (${res.status})`);
      const data = (await res.json()) as { granted?: boolean };
      if (data.granted) {
        dispatch.grantRole(chosen);
        return;
      }
      setStatus("error");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={() => dispatch.setView("home")}
        className="self-start text-label font-medium text-ink-soft"
      >
        {t("back", locale)}
      </button>

      <section className="flex flex-col gap-5">
        <header className="flex flex-col gap-2">
          <h1 className="text-decision font-semibold tracking-tight text-ink">
            {t("gateHeading", locale)}
          </h1>
          <p className="text-body text-ink-soft">{t("gateBody", locale)}</p>
        </header>

        <div className="flex flex-col gap-2" role="group" aria-label={t("gateHeading", locale)}>
          <button
            type="button"
            onClick={() => choose("chp")}
            aria-pressed={chosen === "chp"}
            className={`min-h-14 rounded-2xl border px-4 py-3 text-left text-body font-medium shadow-[0_1px_0_rgba(28,25,22,0.04)] ${
              chosen === "chp"
                ? "border-action text-ink"
                : "border-line bg-raised text-ink"
            }`}
          >
            {t("gateChooseChp", locale)}
          </button>
          <button
            type="button"
            onClick={() => choose("facility")}
            aria-pressed={chosen === "facility"}
            className={`min-h-14 rounded-2xl border px-4 py-3 text-left text-body font-medium shadow-[0_1px_0_rgba(28,25,22,0.04)] ${
              chosen === "facility"
                ? "border-action text-ink"
                : "border-line bg-raised text-ink"
            }`}
          >
            {t("gateChooseFacility", locale)}
          </button>
        </div>

        {chosen ? (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-2">
              <span className="text-label font-medium text-ink-soft">
                {t("gateCodeLabel", locale)}
              </span>
              <input
                type="text"
                autoCapitalize="characters"
                autoComplete="off"
                value={code}
                onChange={(event) => {
                  setCode(event.target.value);
                  if (status === "error") setStatus("idle");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void submit();
                }}
                className="min-h-12 rounded-2xl border border-line bg-raised px-4 text-body text-ink outline-none focus:border-action"
              />
            </label>
            {status === "error" ? (
              <p className="text-label font-medium text-urgent" role="alert">
                {t("gateWrongCode", locale)}
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => void submit()}
              disabled={status === "checking" || code.trim().length === 0}
              className="min-h-14 rounded-2xl bg-action px-4 text-body font-semibold text-action-ink disabled:cursor-not-allowed disabled:opacity-40"
            >
              {status === "checking" ? t("gateChecking", locale) : t("gateSubmit", locale)}
            </button>
          </div>
        ) : null}

        {demo ? (
          <p className="text-caption text-ink-soft">{t("gateDemoHint", locale)}</p>
        ) : null}
      </section>
    </div>
  );
}
