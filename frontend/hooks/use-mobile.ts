import * as React from "react"

const MOBILE_BREAKPOINT = 768
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

// Edited from the shadcn original, which called setState inside an effect and fails
// the react-hooks/set-state-in-effect lint rule. useSyncExternalStore is React's API
// for subscribing to browser state like a media query; behavior is unchanged.
function subscribe(onChange: () => void) {
  const mql = window.matchMedia(MOBILE_QUERY)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribe,
    () => window.matchMedia(MOBILE_QUERY).matches,
    // The server can't know the viewport: assume desktop, as the original did.
    () => false
  )
}
