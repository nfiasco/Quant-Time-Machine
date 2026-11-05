import { useSyncExternalStore } from "react";

const MOTION_QUERY = "(prefers-reduced-motion: no-preference)";

function subscribe(onChange: () => void) {
  const query = window.matchMedia(MOTION_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * Whether the visitor allows motion (hasn't asked for reduced motion). Always false
 * on the server and during hydration, so motion-only components mount only after
 * hydration, and never for visitors who asked for less motion.
 */
export function useAllowsMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(MOTION_QUERY).matches,
    () => false,
  );
}
