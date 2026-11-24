"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

type RunRefresherProps = {
  /** True while the run can still change, or while the API couldn't be reached. */
  active: boolean;
  intervalMs?: number;
};

/**
 * Keeps a run's page current while the run goes: it renders the page again on the server
 * every couple of seconds (`router.refresh()`), which reads the run again and keeps what's
 * on screen in the browser. It pauses while the tab is hidden, and stops once the run has
 * finished. Next's docs advise this over polling a Server Action, since actions run one at
 * a time. Renders nothing.
 */
export function RunRefresher({ active, intervalMs = 2_000 }: RunRefresherProps) {
  const router = useRouter();

  useEffect(() => {
    if (!active) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const start = () => {
      timer ??= setInterval(() => router.refresh(), intervalMs);
    };
    const stop = () => {
      clearInterval(timer);
      timer = undefined;
    };
    const onVisibilityChange = () => {
      if (document.hidden) {
        stop();
      } else {
        router.refresh();
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [active, intervalMs, router]);

  return null;
}
