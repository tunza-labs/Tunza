import { fetchCandidate } from "@/lib/clinical/model-client";

const KEYS = ["who", "awake", "breathing", "drinking", "duration", "mainProblem", "presentation"] as const;
const MAX_PRESENTATION = 2000;

// Shadow candidate for the safety floor. Off unless TUNZA_MODEL_URL is set.
// The presentation text is forwarded to the model server and never logged here.
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON." }, { status: 400 });
  }
  if (typeof body !== "object" || body === null) {
    return Response.json({ error: "Invalid intake." }, { status: 400 });
  }
  const intake: Record<string, unknown> = {};
  for (const key of KEYS) {
    const value = (body as Record<string, unknown>)[key];
    if (value !== undefined && value !== null) intake[key] = value;
  }
  if (typeof intake.presentation === "string" && intake.presentation.length > MAX_PRESENTATION) {
    return Response.json({ error: "Presentation too long." }, { status: 400 });
  }
  const baseUrl = process.env.TUNZA_MODEL_URL ?? null;
  if (!baseUrl) return Response.json({ candidate: null, reason: "model_disabled" });
  const candidate = await fetchCandidate(intake, {
    baseUrl,
    modelId: process.env.TUNZA_MODEL_ID ?? undefined,
  });
  return Response.json({ candidate, reason: candidate ? "ok" : "model_unavailable" });
}
