/**
 * Small line icons that sit beside words, never instead of them. Every icon is
 * decorative (aria-hidden): the label next to it carries the meaning, in both
 * languages, so low-literacy readers get a picture and screen readers get the
 * words once.
 */

export type IconName =
  | "person"
  | "home"
  | "child"
  | "question"
  | "eye"
  | "moon"
  | "eye-closed"
  | "wind"
  | "wind-fast"
  | "alert"
  | "cup"
  | "cup-half"
  | "cup-empty"
  | "sun"
  | "calendar"
  | "clock"
  | "thermometer"
  | "bandage"
  | "stomach"
  | "dots"
  | "mic"
  | "keyboard"
  | "camera"
  | "pin"
  | "arrow"
  | "share"
  | "info";

const PATHS: Record<IconName, string[]> = {
  person: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M4 21a8 8 0 0 1 16 0"],
  home: ["M3 11 12 4l9 7", "M5 10v10h14V10", "M10 20v-5h4v5"],
  child: ["M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M7 20a5 5 0 0 1 10 0", "M9 14l-2 2", "M15 14l2 2"],
  question: [
    "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
    "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6",
    "M12 17h.01",
  ],
  eye: ["M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"],
  moon: ["M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"],
  "eye-closed": ["M3 10c2.5 3 5.5 4.5 9 4.5s6.5-1.5 9-4.5", "M7 13.5 5.5 16", "M12 14.5V17", "M17 13.5l1.5 2.5"],
  wind: ["M3 9h11a3 3 0 1 0-3-3", "M3 15h15a3 3 0 1 1-3 3"],
  "wind-fast": ["M3 7h10a2.5 2.5 0 1 0-2.5-2.5", "M2 12h17", "M3 17h11a2.5 2.5 0 1 1-2.5 2.5"],
  alert: ["M12 3 2 20h20L12 3Z", "M12 10v4", "M12 17h.01"],
  cup: ["M5 4h14l-1.5 16h-11L5 4Z", "M5.5 8h13"],
  "cup-half": ["M5 4h14l-1.5 16h-11L5 4Z", "M6.2 13h11.6"],
  "cup-empty": ["M5 4h14l-1.5 16h-11L5 4Z", "M4 21 20 3"],
  sun: [
    "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
    "M12 2v2",
    "M12 20v2",
    "M4.9 4.9l1.4 1.4",
    "M17.7 17.7l1.4 1.4",
    "M2 12h2",
    "M20 12h2",
    "M4.9 19.1l1.4-1.4",
    "M17.7 6.3l1.4-1.4",
  ],
  calendar: ["M4 6h16v14H4V6Z", "M4 10h16", "M8 3v4", "M16 3v4"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  thermometer: ["M10 14V5a2 2 0 1 1 4 0v9a4 4 0 1 1-4 0Z", "M12 9v6"],
  bandage: ["m4.5 14.5 10-10a3.5 3.5 0 0 1 5 5l-10 10a3.5 3.5 0 0 1-5-5Z", "M10 10h.01", "M14 14h.01", "M12 12h.01"],
  stomach: ["M8 3v4a4 4 0 0 0 4 4h1a5 5 0 0 1 0 10H9a4 4 0 0 1-4-4"],
  dots: ["M6 12h.01", "M12 12h.01", "M18 12h.01"],
  mic: ["M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z", "M5 11a7 7 0 0 0 14 0", "M12 18v3"],
  keyboard: ["M3 6h18v12H3V6Z", "M7 10h.01", "M11 10h.01", "M15 10h.01", "M8 14h8"],
  camera: ["M4 7h3l2-3h6l2 3h3v13H4V7Z", "M12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"],
  pin: ["M12 21s7-6 7-12a7 7 0 1 0-14 0c0 6 7 12 7 12Z", "M12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"],
  arrow: ["M5 12h14", "m13 6 6 6-6 6"],
  share: [
    "M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "m8.6 13.5 6.8 4",
    "m15.4 6.5-6.8 4",
  ],
  info: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 11v5", "M12 8h.01"],
};

export function Icon({ name, className = "size-6" }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className}`}
      data-icon={name}
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
