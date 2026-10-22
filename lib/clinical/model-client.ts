import { isDisposition } from "./contract";
import type { CandidateInput } from "./reconcile";

/**
 * Candidate client for the Tunza model server (tools/tunza-train/serve).
 * Shadow path only: it returns a candidate for reconcile(), which keeps
 * decide() as the answer. Any failure returns null. It never throws, so a
 * down or slow model cannot change what a person is told.
 */

export const MODEL_CLIENT_MODULE = "model-client/v1";
export const DEFAULT_TIMEOUT_MS = 8000;

export type ModelClientOptions = {
  baseUrl?: string | null;
  timeoutMs?: number;
  modelId?: string;
  fetchImpl?: typeof fetch;
};

export async function fetchCandidate(
  intake: Record<string, unknown>,
  options: ModelClientOptions = {},
): Promise<CandidateInput | null> {
  const base = options.baseUrl?.trim();
  if (!base) return null;
  const doFetch = options.fetchImpl ?? fetch;
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );
  try {
    const response = await doFetch(`${base.replace(/\/+$/, "")}/v1/triage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(intake),
      signal: controller.signal,
    });
    if (!response.ok) return null;
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null) return null;
    const answer = (body as { model_answer?: unknown }).model_answer;
    if (typeof answer !== "object" || answer === null) return null;
    const disposition = (answer as { disposition?: unknown }).disposition;
    if (typeof disposition !== "string" || !isDisposition(disposition)) return null;
    return { disposition, model_id: options.modelId ?? "tunza-model/unversioned" };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
