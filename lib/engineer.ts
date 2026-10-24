/**
 * Engineer-only view. The shadow model panel is for the people building
 * Tunza, not for clinicians or families. It is off unless the build sets
 * NEXT_PUBLIC_TUNZA_ENGINEER_VIEW=1. There is no real authentication yet,
 * so this is a build setting, not an access control.
 */
export function isEngineerView(): boolean {
  return process.env.NEXT_PUBLIC_TUNZA_ENGINEER_VIEW === "1";
}
