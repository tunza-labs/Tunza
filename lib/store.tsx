"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  applyAnswer,
  decide,
  EMPTY_ANSWERS,
  nextQuestion,
} from "./assessment";
import { applyReferralAction, createReferral } from "./referral";
import { DESK_DEFAULT_FACILITY_ID, seedDemoCases } from "./desk";
import { DEFAULT_LOCALE, type Locale } from "./copy";
import { createId, nowIso } from "./ids";
import type {
  CareState,
  Encounter,
  FacilityCapacity,
  GatedRole,
  HouseholdView,
  NamedFailure,
  OutcomeCode,
  QuestionId,
  Referral,
  Role,
} from "./types";

const STORAGE_KEY = "tunza.v2.care";

export const INJECTABLE_FAILURES: NamedFailure[] = [
  "offline",
  "no_facility_response",
  "redirected",
  "stale_information",
  "incomplete_assessment",
  "weak_connection",
];

type Action =
  | { type: "hydrate"; state: CareState }
  | { type: "setRole"; role: Role }
  | { type: "setLocale"; locale: Locale }
  | { type: "setView"; view: HouseholdView }
  | { type: "setGateRole"; role: GatedRole | null }
  | { type: "grantRole"; role: GatedRole }
  | { type: "setOnline"; online: boolean }
  | { type: "toggleFailure"; failure: NamedFailure }
  | { type: "startEncounter"; by: Role }
  | { type: "answer"; question: QuestionId; value: string }
  | { type: "setPresentation"; text: string }
  | { type: "setPhoto"; attached: boolean }
  | { type: "prepareReferral" }
  | { type: "referralAction"; action: ReferralActionName; outcome?: OutcomeCode }
  | {
      type: "deskAction";
      referralId: string;
      action: ReferralActionName;
      outcome?: OutcomeCode;
    }
  | { type: "setCapacity"; facilityId: string; capacity: FacilityCapacity }
  | { type: "setDeskFacility"; facilityId: string }
  | { type: "goBack" }
  | { type: "continueForOneMore" }
  | { type: "reset" };

type ReferralActionName =
  | "send"
  | "receive"
  | "accept"
  | "travel"
  | "arrive"
  | "start_care"
  | "complete"
  | "return_outcome"
  | "redirect"
  | "decline"
  | "ask_more";

function newEncounter(by: Role): Encounter {
  const at = nowIso();
  return {
    id: createId("enc"),
    answers: { ...EMPTY_ANSWERS },
    asked: [],
    currentQuestion: "who",
    decision: null,
    startedBy: by,
    createdAt: at,
    updatedAt: at,
  };
}

export const initialCareState: CareState = {
  role: "household",
  locale: DEFAULT_LOCALE,
  view: "home",
  grants: { chp: false, facility: false },
  gateRole: null,
  injectedFailures: [],
  encounter: newEncounter("household"),
  referral: null,
  online: true,
  facilityCapacity: {},
  deskFacilityId: DESK_DEFAULT_FACILITY_ID,
  demoCases: seedDemoCases(nowIso()),
};

function isOffline(state: CareState): boolean {
  return !state.online || state.injectedFailures.includes("offline");
}

function reducer(state: CareState, action: Action): CareState {
  switch (action.type) {
    case "hydrate":
      return { ...action.state, online: state.online };
    case "setRole":
      // The gated surfaces open only for granted roles; anyone else is sent
      // to the sign-in gate instead. Enforced here so no caller can skip it.
      if (action.role !== "household" && !state.grants[action.role]) {
        return { ...state, role: "household", view: "gate", gateRole: action.role };
      }
      return { ...state, role: action.role };
    case "setLocale":
      return { ...state, locale: action.locale };
    case "setView":
      return { ...state, view: action.view };
    case "setGateRole":
      return { ...state, gateRole: action.role };
    case "grantRole":
      return {
        ...state,
        grants: { ...state.grants, [action.role]: true },
        role: action.role,
        view: "home",
        gateRole: null,
      };
    case "setOnline":
      return { ...state, online: action.online };
    case "toggleFailure": {
      const has = state.injectedFailures.includes(action.failure);
      const injectedFailures = has
        ? state.injectedFailures.filter((item) => item !== action.failure)
        : [...state.injectedFailures, action.failure];
      let referral = state.referral;
      if (action.failure === "no_facility_response" && !has && referral?.stage === "sent") {
        referral = { ...referral, failure: "no_facility_response" };
      }
      if (action.failure === "no_facility_response" && has && referral?.failure === "no_facility_response") {
        referral = { ...referral, failure: null };
      }
      if (action.failure === "redirected" && !has && referral) {
        referral = applyReferralAction(referral, "redirect", state.role, {
          offline: isOffline(state),
          noFacilityResponse: false,
          weakConnection: false,
        });
      }
      return { ...state, injectedFailures, referral };
    }
    case "startEncounter":
      return {
        ...state,
        encounter: newEncounter(action.by),
        referral: null,
      };
    case "setPresentation": {
      if (!state.encounter) {
        return state;
      }
      return {
        ...state,
        encounter: {
          ...state.encounter,
          answers: { ...state.encounter.answers, presentation: action.text },
          updatedAt: nowIso(),
        },
      };
    }
    case "setPhoto": {
      if (!state.encounter) {
        return state;
      }
      return {
        ...state,
        encounter: {
          ...state.encounter,
          answers: { ...state.encounter.answers, photoAttached: action.attached },
          updatedAt: nowIso(),
        },
      };
    }
    case "answer": {
      if (!state.encounter || state.encounter.currentQuestion !== action.question) {
        return state;
      }
      const answers = applyAnswer(
        state.encounter.answers,
        action.question,
        action.value,
      );
      const asked = state.encounter.asked.includes(action.question)
        ? state.encounter.asked
        : [...state.encounter.asked, action.question];
      const upcoming = nextQuestion(answers, action.question);
      const decision = upcoming ? null : decide(answers);
      return {
        ...state,
        encounter: {
          ...state.encounter,
          answers,
          asked,
          currentQuestion: upcoming,
          decision,
          updatedAt: nowIso(),
        },
      };
    }
    case "prepareReferral": {
      if (!state.encounter?.decision) {
        return state;
      }
      const kind = state.encounter.decision.kind;
      if (kind !== "go_now" && kind !== "get_care_today") {
        return state;
      }
      if (state.referral) {
        return state;
      }
      const referral = createReferral({
        encounterId: state.encounter.id,
        urgent: kind === "go_now",
        by: state.role,
      });
      return { ...state, referral };
    }
    case "referralAction": {
      if (!state.referral) {
        return state;
      }
      const referral = applyReferralAction(state.referral, action.action, state.role, {
        offline: isOffline(state),
        noFacilityResponse: state.injectedFailures.includes("no_facility_response"),
        weakConnection: state.injectedFailures.includes("weak_connection"),
        outcome: action.outcome,
        capacity: state.facilityCapacity,
      });
      return { ...state, referral };
    }
    case "deskAction": {
      // The session referral takes the same path as referralAction. Synthetic
      // demo cases move on their own copy and never touch the session one.
      if (state.referral?.id === action.referralId) {
        return reducer(state, {
          type: "referralAction",
          action: action.action,
          outcome: action.outcome,
        });
      }
      const index = state.demoCases.findIndex(
        (item) => item.referral.id === action.referralId,
      );
      if (index === -1) {
        return state;
      }
      const target = state.demoCases[index];
      const referral = applyReferralAction(target.referral, action.action, state.role, {
        offline: false,
        noFacilityResponse: false,
        weakConnection: false,
        outcome: action.outcome,
        capacity: state.facilityCapacity,
      });
      if (referral === target.referral) {
        return state;
      }
      const demoCases = [...state.demoCases];
      demoCases[index] = { ...target, referral };
      return { ...state, demoCases };
    }
    case "setCapacity":
      return {
        ...state,
        facilityCapacity: { ...state.facilityCapacity, [action.facilityId]: action.capacity },
      };
    case "setDeskFacility":
      return { ...state, deskFacilityId: action.facilityId };
    case "continueForOneMore": {
      if (!state.encounter?.decision || state.referral) {
        return state;
      }
      if (state.encounter.decision.kind !== "need_one_more_answer") {
        return state;
      }
      if (state.encounter.asked.includes("main_problem")) {
        return state;
      }
      return {
        ...state,
        encounter: {
          ...state.encounter,
          currentQuestion: "main_problem",
          decision: null,
          updatedAt: nowIso(),
        },
      };
    }
    case "goBack": {
      if (!state.encounter || state.referral) {
        return state;
      }
      if (state.encounter.decision && state.encounter.asked.length > 0) {
        const last = state.encounter.asked[state.encounter.asked.length - 1];
        return {
          ...state,
          encounter: {
            ...state.encounter,
            currentQuestion: last,
            decision: null,
            updatedAt: nowIso(),
          },
        };
      }
      if (state.encounter.asked.length === 0) {
        return state;
      }
      const asked = state.encounter.asked.slice(0, -1);
      const currentQuestion = state.encounter.asked[state.encounter.asked.length - 1];
      return {
        ...state,
        encounter: {
          ...state.encounter,
          asked,
          currentQuestion,
          decision: null,
          updatedAt: nowIso(),
        },
      };
    }
    case "reset":
      // Start over is a fresh demo: back to the household front door, grants
      // cleared, everything else at its initial state.
      return {
        ...initialCareState,
        locale: state.locale,
        online: state.online,
        encounter: newEncounter("household"),
        demoCases: seedDemoCases(nowIso()),
      };
    default:
      return state;
  }
}

type CareContextValue = {
  state: CareState;
  hydrated: boolean;
  offline: boolean;
  dispatch: {
    setRole: (role: Role) => void;
    setLocale: (locale: Locale) => void;
    setView: (view: HouseholdView) => void;
    setGateRole: (role: GatedRole | null) => void;
    grantRole: (role: GatedRole) => void;
    toggleFailure: (failure: NamedFailure) => void;
    startEncounter: () => void;
    answer: (question: QuestionId, value: string) => void;
    setPresentation: (text: string) => void;
    setPhoto: (attached: boolean) => void;
    prepareReferral: () => void;
    sendReferral: () => void;
    acceptReferral: () => void;
    redirectReferral: () => void;
    askMore: () => void;
    markTraveling: () => void;
    markArrived: () => void;
    startCare: () => void;
    completeVisit: () => void;
    returnOutcome: (outcome: OutcomeCode) => void;
    deskAction: (
      referralId: string,
      action: ReferralActionName,
      outcome?: OutcomeCode,
    ) => void;
    setCapacity: (facilityId: string, capacity: FacilityCapacity) => void;
    setDeskFacility: (facilityId: string) => void;
    goBack: () => void;
    continueForOneMore: () => void;
    reset: () => void;
  };
};

function emptySubscribe() {
  return () => {};
}

function useIsClient() {
  return useSyncExternalStore(emptySubscribe, () => true, () => false);
}

function readStoredState(): CareState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as CareState;
      if (parsed?.role) {
        const grants = {
          chp: parsed.grants?.chp === true,
          facility: parsed.grants?.facility === true,
        };
        const roleAllowed = parsed.role === "household" || grants[parsed.role];
        return {
          ...parsed,
          grants,
          gateRole: null,
          role: roleAllowed ? parsed.role : "household",
          locale: parsed.locale ?? DEFAULT_LOCALE,
          view: roleAllowed ? (parsed.view ?? "home") : "home",
          online: navigator.onLine,
          facilityCapacity: parsed.facilityCapacity ?? {},
          deskFacilityId: parsed.deskFacilityId ?? DESK_DEFAULT_FACILITY_ID,
          demoCases: Array.isArray(parsed.demoCases)
            ? parsed.demoCases
            : seedDemoCases(nowIso()),
        };
      }
    }
  } catch {
    // Demo persistence must never break the care path.
  }
  return { ...initialCareState, online: navigator.onLine };
}

function makeDispatch(
  dispatch: (action: Action) => void,
  role: Role,
): CareContextValue["dispatch"] {
  return {
    setRole: (nextRole) => dispatch({ type: "setRole", role: nextRole }),
    setLocale: (locale) => dispatch({ type: "setLocale", locale }),
    setView: (view) => dispatch({ type: "setView", view }),
    setGateRole: (role) => dispatch({ type: "setGateRole", role }),
    grantRole: (role) => dispatch({ type: "grantRole", role }),
    toggleFailure: (failure) => dispatch({ type: "toggleFailure", failure }),
    startEncounter: () => dispatch({ type: "startEncounter", by: role }),
    answer: (question, value) => dispatch({ type: "answer", question, value }),
    setPresentation: (text) => dispatch({ type: "setPresentation", text }),
    setPhoto: (attached) => dispatch({ type: "setPhoto", attached }),
    prepareReferral: () => dispatch({ type: "prepareReferral" }),
    sendReferral: () => dispatch({ type: "referralAction", action: "send" }),
    acceptReferral: () => dispatch({ type: "referralAction", action: "accept" }),
    redirectReferral: () => dispatch({ type: "referralAction", action: "redirect" }),
    askMore: () => dispatch({ type: "referralAction", action: "ask_more" }),
    markTraveling: () => dispatch({ type: "referralAction", action: "travel" }),
    markArrived: () => dispatch({ type: "referralAction", action: "arrive" }),
    startCare: () => dispatch({ type: "referralAction", action: "start_care" }),
    completeVisit: () => dispatch({ type: "referralAction", action: "complete" }),
    returnOutcome: (outcome) =>
      dispatch({ type: "referralAction", action: "return_outcome", outcome }),
    deskAction: (referralId, action, outcome) =>
      dispatch({ type: "deskAction", referralId, action, outcome }),
    setCapacity: (facilityId, capacity) =>
      dispatch({ type: "setCapacity", facilityId, capacity }),
    setDeskFacility: (facilityId) => dispatch({ type: "setDeskFacility", facilityId }),
    goBack: () => dispatch({ type: "goBack" }),
    continueForOneMore: () => dispatch({ type: "continueForOneMore" }),
    reset: () => dispatch({ type: "reset" }),
  };
}

const noopDispatch: CareContextValue["dispatch"] = makeDispatch(() => {
  // Server snapshot has no live session yet.
}, "household");

const CareContext = createContext<CareContextValue | null>(null);

export function CareProvider({ children }: { children: ReactNode }) {
  const isClient = useIsClient();
  if (!isClient) {
    return (
      <CareContext.Provider
        value={{
          state: initialCareState,
          hydrated: false,
          offline: false,
          dispatch: noopDispatch,
        }}
      >
        {children}
      </CareContext.Provider>
    );
  }
  return <CareProviderClient>{children}</CareProviderClient>;
}

function CareProviderClient({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, null, readStoredState);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Ignore quota errors; the in-memory path still works.
    }
  }, [state]);

  useEffect(() => {
    function onOnline() {
      dispatch({ type: "setOnline", online: true });
    }
    function onOffline() {
      dispatch({ type: "setOnline", online: false });
    }
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  const value = useMemo<CareContextValue>(
    () => ({
      state,
      hydrated: true,
      offline: isOffline(state),
      dispatch: makeDispatch(dispatch, state.role),
    }),
    [state],
  );

  return <CareContext.Provider value={value}>{children}</CareContext.Provider>;
}

export function useCare(): CareContextValue {
  const ctx = useContext(CareContext);
  if (!ctx) {
    throw new Error("useCare must be used inside CareProvider");
  }
  return ctx;
}

export function activeFailures(
  state: CareState,
  referral: Referral | null,
): NamedFailure[] {
  const named = new Set<NamedFailure>();
  if (!state.online || state.injectedFailures.includes("offline")) {
    named.add("offline");
  }
  if (state.injectedFailures.includes("weak_connection")) {
    named.add("weak_connection");
  }
  if (state.injectedFailures.includes("stale_information")) {
    named.add("stale_information");
  }
  if (referral?.failure === "no_facility_response") {
    named.add("no_facility_response");
  }
  if (referral?.failure === "redirected") {
    named.add("redirected");
  }
  if (
    state.encounter?.decision?.kind === "need_one_more_answer" ||
    state.injectedFailures.includes("incomplete_assessment")
  ) {
    named.add("incomplete_assessment");
  }
  return [...named];
}

export { reducer as careReducer };
export type { Action as CareAction, ReferralActionName };
