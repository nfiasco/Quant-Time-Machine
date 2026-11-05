"use client";

import dynamic from "next/dynamic";
import { useRef, type CSSProperties, type ReactNode } from "react";

import { useAllowsMotion } from "@/hooks/use-allows-motion";

import { STORY_SCREENS } from "./beats";

// The engine (GSAP, Lenis, the drawing, the ticker wall) is its own chunk, loaded only
// in the browser and only when motion is allowed.
const StoryEngine = dynamic(
  () => import("./story-engine").then((mod) => mod.StoryEngine),
  { ssr: false },
);

type StoryStageProps = {
  hero: ReactNode;
  ask: ReactNode;
  timeline: ReactNode;
  close: ReactNode;
};

/**
 * The scroll story's frame. The server-rendered pieces are laid out statically, which
 * is the whole experience with reduced motion or without JavaScript. When motion is
 * allowed, the engine loads after hydration, switches the layout to a sticky stage,
 * and drives it from the scroll position.
 */
export function StoryStage({ hero, ask, timeline, close }: StoryStageProps) {
  const rootRef = useRef<HTMLElement>(null);
  const allowsMotion = useAllowsMotion();

  return (
    <section
      ref={rootRef}
      id="story"
      aria-labelledby="story-title"
      style={{ "--story-screens": STORY_SCREENS } as CSSProperties}
      className="relative [--story-anchor-y:42svh] [--story-r:clamp(120px,min(34vw,25svh),220px)] story-animated:h-[calc((var(--story-screens)+1)*100svh)]"
    >
      <div
        data-story-stage
        className="relative story-animated:sticky story-animated:top-0 story-animated:h-svh story-animated:overflow-clip"
      >
        {hero}
        {ask}
        <div
          data-story-world
          className="story-animated:absolute story-animated:inset-x-0 story-animated:top-0 story-animated:z-20 story-animated:will-change-transform"
        >
          {timeline}
        </div>
        {close}
        {allowsMotion ? <StoryEngine rootRef={rootRef} /> : null}
      </div>
    </section>
  );
}
