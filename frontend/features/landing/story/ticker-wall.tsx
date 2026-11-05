"use client";

import { PauseIcon, PlayIcon } from "lucide-react";
import { memo, useEffect, useRef, useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/button";

import {
  WALL_ROWS,
  rowDuration,
  rowTickers,
} from "./ticker-data";

/**
 * The faint market board behind the logo: rows of tickers with daily changes, drifting
 * sideways, a few updating every second. Pure decoration (the numbers are random), so
 * it's hidden from assistive tech, and it has a pause button (WCAG 2.2.2). It also
 * pauses itself when the engine hides it (data-idle), when it's off screen, and when
 * the tab is hidden.
 */
export function TickerWall() {
  const wallRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const wall = wallRef.current;
    if (!wall) return;
    const changes = Array.from(wall.querySelectorAll<HTMLElement>("[data-change]"));
    changes.forEach(writeRandomChange);

    let offscreen = false;
    const observer = new IntersectionObserver(([entry]) => {
      offscreen = !entry.isIntersecting;
      wall.dataset.offscreen = String(offscreen);
    });
    observer.observe(wall);

    const timer = window.setInterval(() => {
      if (pausedRef.current || offscreen || document.hidden) return;
      if (wall.dataset.idle === "true") return;
      for (let i = 0; i < 3; i++) {
        const change = changes[Math.floor(Math.random() * changes.length)];
        writeRandomChange(change);
        flash(change);
      }
    }, 900);

    return () => {
      window.clearInterval(timer);
      observer.disconnect();
    };
  }, []);

  function toggle() {
    pausedRef.current = !pausedRef.current;
    setPaused(pausedRef.current);
  }

  return (
    <>
      <div
        ref={wallRef}
        data-story-wall
        data-paused={paused}
        aria-hidden
        className="group/wall pointer-events-none absolute inset-0 z-0 overflow-hidden select-none mask-ticker-wall"
      >
        <div className="opacity-30">
          <TickerRows />
        </div>
      </div>
      <Button
        data-story-pause
        variant="ghost"
        size="sm"
        aria-pressed={paused}
        onClick={toggle}
        className="absolute right-3 bottom-3 z-40 text-muted-foreground focus-visible:opacity-100! sm:right-5 sm:bottom-5"
      >
        {paused ? <PlayIcon aria-hidden /> : <PauseIcon aria-hidden />}
        Pause background
      </Button>
    </>
  );
}

// Memoized: pausing re-renders the wall's root, never its hundreds of cells.
const TickerRows = memo(function TickerRows() {
  return (
    <>
      {Array.from({ length: WALL_ROWS }, (_, row) => {
        const tickers = rowTickers(row);
        return (
          <div
            key={row}
            style={{ "--ticker-duration": `${rowDuration(row)}s` } as CSSProperties}
            className="flex w-max animate-ticker-drift even:[animation-direction:reverse] group-data-[idle=true]/wall:[animation-play-state:paused] group-data-[offscreen=true]/wall:[animation-play-state:paused] group-data-[paused=true]/wall:[animation-play-state:paused]"
          >
            {[...tickers, ...tickers].map((ticker, cell) => (
              <div
                key={cell}
                className="flex w-44 shrink-0 items-baseline justify-between gap-3 border-r border-b px-4 py-3.5 font-mono text-xs"
              >
                <span className="font-medium">{ticker}</span>
                <span
                  data-change
                  className="text-muted-foreground tabular-nums data-[dir=down]:text-negative data-[dir=up]:text-positive"
                />
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
});

/** A random daily change, signed (+ or U+2212) with an arrow, so color isn't the only cue. */
function writeRandomChange(element: HTMLElement) {
  const change = (Math.random() - 0.46) * 6;
  const up = change >= 0;
  element.dataset.dir = up ? "up" : "down";
  element.textContent = `${up ? "▲" : "▼"} ${up ? "+" : "−"}${Math.abs(change).toFixed(2)}%`;
}

function flash(element: HTMLElement) {
  const cell = element.parentElement;
  if (!cell) return;
  const tint = `color-mix(in oklch, ${getComputedStyle(element).color} 22%, transparent)`;
  cell.animate([{ backgroundColor: tint }, { backgroundColor: "transparent" }], {
    duration: 900,
    easing: "ease-out",
  });
}
