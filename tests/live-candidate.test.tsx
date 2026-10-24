// @vitest-environment jsdom
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLiveCandidate } from "../lib/clinical/useLiveCandidate";
import { EMPTY_ANSWERS } from "../lib/assessment";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("useLiveCandidate", () => {
  it("does nothing and never calls the server unless the engineer view is on", async () => {
    vi.stubEnv("NEXT_PUBLIC_TUNZA_ENGINEER_VIEW", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveCandidate("case-1", EMPTY_ANSWERS));
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns the server candidate in the engineer view", async () => {
    vi.stubEnv("NEXT_PUBLIC_TUNZA_ENGINEER_VIEW", "1");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ candidate: { disposition: "go_now", model_id: "tunza-v1" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveCandidate("case-1", EMPTY_ANSWERS));
    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current).toEqual({ disposition: "go_now", model_id: "tunza-v1" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("stays null when the server fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_TUNZA_ENGINEER_VIEW", "1");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    const { result } = renderHook(() => useLiveCandidate("case-1", EMPTY_ANSWERS));
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current).toBeNull();
  });
});
