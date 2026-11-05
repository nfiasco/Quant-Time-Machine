"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import type { RefObject } from "react";

import { toEtDateTime } from "@/lib/time";

import { BEATS, SLOT, STOP_COUNT } from "./beats";
import { KNOWLEDGE_TIME, STORY_STOPS } from "./events";
import {
  LOGO_SWEEP,
  LOGO_VIEWBOX_SIZE,
  STORY_CHEVRON,
  chevronPath,
  chevronTransform,
  lineEnd,
  lineQAtY,
  lineY,
  pointAt,
  snakePath,
  type StrokeLayout,
} from "./geometry";
import { formatDial, formatReadout, toMinutes } from "./readout";
import { StoryDecor } from "./story-decor";
import { TickerWall } from "./ticker-wall";

// This module loads only in the browser (see story-stage.tsx).
gsap.registerPlugin(ScrollTrigger, useGSAP);
ScrollTrigger.config({ ignoreMobileResize: true });

/**
 * Drives the scroll story: draws the stroke, moves the camera, and fades the story's
 * pieces in and out along one scrubbed timeline. Everything it changes is reverted on
 * unmount (and when the visitor turns on reduced motion), leaving the static layout.
 */
export function StoryEngine({
  rootRef,
}: {
  rootRef: RefObject<HTMLElement | null>;
}) {
  useGSAP(
    () => {
      const root = rootRef.current;
      if (!root) return;
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => buildStory(root));
      return () => media.revert();
    },
    { scope: rootRef },
  );

  return (
    <>
      <TickerWall />
      <StoryDecor />
    </>
  );
}

type Measured = {
  stroke: StrokeLayout;
  /** Screen y of the circles' centers when they're framed (top at the start, bottom at the end). */
  anchorY: number;
  /** Screen y the arrow keeps while the camera follows it. */
  followY: number;
  /** How far the camera looks past the knowledge time, in px. */
  peekMax: number;
  pixelRatio: number;
};

function buildStory(root: HTMLElement): (() => void) | undefined {
  const one = <T extends Element>(selector: string) =>
    root.querySelector<T>(selector);

  const stage = one<HTMLElement>("[data-story-stage]");
  const world = one<HTMLElement>("[data-story-world]");
  const logo = one<SVGSVGElement>("[data-story-logo]");
  const name = one<HTMLElement>("[data-story-name]");
  const intro = one<HTMLElement>("[data-story-intro]");
  const ask = one<HTMLElement>("[data-story-ask]");
  const close = one<HTMLElement>("[data-story-close]");
  const camera = one<SVGGElement>("[data-story-camera]");
  const snake = one<SVGPathElement>("[data-story-snake]");
  const chevron = one<SVGPathElement>("[data-story-chevron]");
  const future = one<SVGPathElement>("[data-story-future]");
  const topClock = one<SVGGElement>('[data-story-clock="top"]');
  const bottomClock = one<SVGGElement>('[data-story-clock="bottom"]');
  const dial = one<HTMLElement>("[data-story-dial]");
  const hud = one<HTMLElement>("[data-story-hud]");
  const readout = one<HTMLElement>("[data-story-readout]");
  const wall = one<HTMLElement>("[data-story-wall]");
  const pause = one<HTMLElement>("[data-story-pause]");
  if (
    !stage || !world || !logo || !name || !intro || !ask || !close || !camera ||
    !snake || !chevron || !future || !topClock || !bottomClock || !dial || !hud ||
    !readout || !wall || !pause
  ) {
    return undefined;
  }

  const items = Array.from(root.querySelectorAll<HTMLElement>("[data-stop]")).sort(
    (a, b) => Number(a.dataset.stop) - Number(b.dataset.stop),
  );
  const stops = items.slice(0, STOP_COUNT);
  const horizon = items[STOP_COUNT];
  const later = items.slice(STOP_COUNT + 1);
  const hands = (clock: SVGGElement) => ({
    hour: clock.querySelector<SVGLineElement>('[data-hand="hour"]'),
    minute: clock.querySelector<SVGLineElement>('[data-hand="minute"]'),
  });
  const topHands = hands(topClock);
  const bottomHands = hands(bottomClock);

  // Switch to the animated layout first, so everything below measures it.
  root.dataset.storyMode = "animated";
  const restoration = history.scrollRestoration;
  history.scrollRestoration = "manual";

  // "Now" is read here, in the browser after hydration, never while rendering.
  const now = toEtDateTime(new Date());
  const nowMinutes = toMinutes(now);
  const minuteAngle = now.minute * 6;
  const hourAngle = (now.hour % 12) * 30 + now.minute * 0.5;

  let m = measure();

  function measure(): Measured {
    const stageBox = stage!.getBoundingClientRect();
    const logoBox = logo!.getBoundingClientRect();
    const height = stage!.clientHeight;
    const r = (logoBox.width / LOGO_VIEWBOX_SIZE) * 100;
    const cx = logoBox.left - stageBox.left + logoBox.width / 2;
    const anchorY = logoBox.top - stageBox.top + logoBox.height / 2;
    root.style.setProperty("--line-x", `${cx - r}px`);

    // Where each item's tick sits inside it, so the arrow stops exactly on the tick.
    const ticks = items.map((item) => {
      const marker = item.querySelector<HTMLElement>("[data-marker]");
      if (!marker) return 0;
      const box = marker.getBoundingClientRect();
      return box.top - item.getBoundingClientRect().top + box.height / 2;
    });
    const heights = items.map((item) => item.offsetHeight);
    // Space from one tick to the next: the rest of this item, a gap, the top of the next.
    const gapAfter = (index: number, gap: number) =>
      heights[index] - ticks[index] + gap + ticks[index + 1];

    const slots = [0];
    // The first stop starts just below the screen while the top circle is framed.
    slots[SLOT.firstStop] = Math.max(height - anchorY + 48, r + 120);
    for (let slot = SLOT.firstStop + 1; slot <= SLOT.horizon; slot++) {
      const previous = slot - 1 - SLOT.firstStop;
      slots[slot] = slots[slot - 1] + Math.max(height * 0.42, gapAfter(previous, 56));
    }
    // Later facts sit close together under the knowledge time and its answer.
    slots[SLOT.firstLater] = slots[SLOT.horizon] + gapAfter(STOP_COUNT, 48);
    for (let slot = SLOT.firstLater + 1; slot < SLOT.end; slot++) {
      slots[slot] = slots[slot - 1] + gapAfter(slot - 1 - SLOT.firstStop, 24);
    }
    const lastIndex = items.length - 1;
    // The line's end is the bottom circle's center: clear of the last fact.
    slots[SLOT.end] = slots[SLOT.end - 1] + heights[lastIndex] - ticks[lastIndex] + r + 72;

    items.forEach((item, index) => {
      item.style.setProperty("--y", `${slots[index + 1] - ticks[index]}px`);
    });

    const stroke: StrokeLayout = { cx, r, slots };
    const followY = height * 0.55;
    // Look far enough past T to show the last later fact.
    const lastBottom = slots[SLOT.end - 1] - ticks[lastIndex] + heights[lastIndex];
    const peekMax = Math.max(0, followY + lastBottom - slots[SLOT.horizon] - (height - 40));

    const x = cx - r;
    future!.setAttribute(
      "d",
      `M${x} ${slots[SLOT.horizon] + 10} L${x} ${slots[SLOT.end - 1] + 12}`,
    );
    chevron!.setAttribute("d", chevronPath(r * STORY_CHEVRON));
    topClock!.setAttribute("transform", `translate(${cx} 0)`);
    bottomClock!.setAttribute("transform", `translate(${cx} ${slots[SLOT.end]})`);
    for (const set of [topHands, bottomHands]) {
      set.hour?.setAttribute("y2", String(-r * 0.4));
      set.minute?.setAttribute("y2", String(-r * 0.6));
    }

    return {
      stroke,
      anchorY,
      followY,
      peekMax,
      pixelRatio: window.devicePixelRatio || 1,
    };
  }

  // Everything the timeline tweens, in semantic units; render() turns it into pixels.
  const state = {
    tail: 0,
    head: LOGO_SWEEP,
    /** 0: frame the top circle. 1: follow the arrow. 2: frame the bottom circle. */
    cam: 0,
    /** 0 to 1: how far the camera looks past the knowledge time. */
    peek: 0,
    /** Clock turns: back during the rewind, forward again on the return. */
    rewindTurns: 0,
    returnTurns: 0,
    /** The knowledge-time readout, in New York wall-clock minutes. */
    minute: nowMinutes,
  };

  function headWorldY(): number {
    const end = lineEnd(m.stroke);
    return lineY(Math.min(Math.max(state.head, 1), end) - 1, m.stroke);
  }

  function cameraY(): number {
    const follow = headWorldY() - m.followY + state.peek * m.peekMax;
    if (state.cam <= 1) return -m.anchorY + (follow + m.anchorY) * state.cam;
    const framed = lineY(lineEnd(m.stroke) - 1, m.stroke) - m.anchorY;
    return follow + (framed - follow) * (state.cam - 1);
  }

  const drawn = { shift: Number.NaN, d: "", tip: "", readout: "", dial: "", hands: "" };

  function render() {
    const shift = Math.round(-cameraY() * m.pixelRatio) / m.pixelRatio;
    if (shift !== drawn.shift) {
      drawn.shift = shift;
      world!.style.transform = `translate3d(0, ${shift}px, 0)`;
      camera!.setAttribute("transform", `translate(0 ${shift})`);
    }
    const d = snakePath(state.tail, state.head, m.stroke);
    if (d !== drawn.d) {
      drawn.d = d;
      snake!.setAttribute("d", d);
    }
    const tip = chevronTransform(pointAt(state.head, m.stroke));
    if (tip !== drawn.tip) {
      drawn.tip = tip;
      chevron!.setAttribute("transform", tip);
    }
    const handKey = `${state.rewindTurns.toFixed(4)} ${state.returnTurns.toFixed(4)}`;
    if (handKey !== drawn.hands) {
      drawn.hands = handKey;
      setHands(topHands, state.rewindTurns);
      setHands(bottomHands, state.rewindTurns + state.returnTurns);
    }
    const text = formatReadout(state.minute);
    if (text !== drawn.readout) {
      drawn.readout = text;
      readout!.textContent = text;
    }
    const day = formatDial(state.minute);
    if (day !== drawn.dial) {
      drawn.dial = day;
      dial!.textContent = day;
    }
  }

  function setHands(set: ReturnType<typeof hands>, turns: number) {
    set.minute?.setAttribute("transform", `rotate(${minuteAngle + turns * 360})`);
    set.hour?.setAttribute("transform", `rotate(${hourAngle + turns * 30})`);
  }

  // The starting picture: the logo (drawn by the engine from here on), nothing else.
  gsap.set(logo, { opacity: 0 });
  gsap.set([ask, close, world, horizon, ...later], { opacity: 0 });
  gsap.set([topClock, bottomClock, dial, hud, future], { opacity: 0 });
  gsap.set(
    stops.filter((item) => item.dataset.kind === "known"),
    { attr: { "data-state": "pending" } },
  );
  // Attributes the timeline flips need a starting value, or scrolling back can't restore it.
  gsap.set(readout, { attr: { "data-at-t": "false" } });
  gsap.set(wall, { attr: { "data-idle": "false" } });

  const stopMinutes = STORY_STOPS.map((stop) => toMinutes(stop.at));
  const knowledgeMinutes = toMinutes(KNOWLEDGE_TIME);

  const timeline = gsap.timeline({
    defaults: { ease: "none" },
    onUpdate: render,
    scrollTrigger: {
      trigger: root,
      start: "top top",
      end: () => `+=${root.offsetHeight - stage.offsetHeight}`,
      scrub: true,
      onRefresh: render,
    },
  });

  let at = BEATS.hero;

  // Ask: the name and the clock cross-fade in place, then the question rises.
  // The name only ever fades: it's centered with CSS `translate`, which GSAP would fold
  // into its own transform (in pixels) the moment it animated x or y.
  timeline
    .addLabel("ask", at)
    .to(name, { opacity: 0, duration: 0.35 }, at)
    .to([topClock, dial], { opacity: 1, duration: 0.35 }, at)
    .to(intro, { opacity: 0, duration: 0.25 }, at)
    .fromTo(
      ask,
      { opacity: 0, y: 20 },
      { opacity: 1, y: 0, duration: 0.35, ease: "power2.out", immediateRender: false },
      at + 0.25,
    );
  at += BEATS.ask;

  // Rewind: the tail chases the arrowhead round until only the arrowhead is left,
  // pointing down, while the clock runs back to the first stop.
  timeline
    .addLabel("rewind", at)
    .to(state, { tail: 1, duration: BEATS.rewind, ease: "power1.inOut" }, at)
    .to(state, { head: 1, duration: BEATS.rewind - 0.25, ease: "power1.inOut" }, at + 0.25)
    .to(state, { rewindTurns: -3, duration: BEATS.rewind, ease: "power2.inOut" }, at)
    .to(state, { minute: stopMinutes[0], duration: BEATS.rewind, ease: "power2.inOut" }, at)
    .to([wall, pause], { opacity: 0, duration: 0.4 }, at + 0.3)
    .set(wall, { attr: { "data-idle": "true" } }, at + 0.7)
    .to(ask, { opacity: 0, y: -12, duration: 0.3 }, at + 0.55)
    .to(hud, { opacity: 1, duration: 0.3 }, at + 0.7)
    .to([topClock, dial], { opacity: 0, duration: 0.25 }, at + BEATS.rewind - 0.3);
  at += BEATS.rewind;

  // Replay: the arrow draws the line down and each stop becomes known as it arrives.
  timeline
    .addLabel("replay", at)
    .to(world, { opacity: 1, duration: 0.25 }, at)
    .to(state, { cam: 1, duration: 0.45, ease: "power1.inOut" }, at);
  stops.forEach((stop, index) => {
    timeline.to(
      state,
      {
        head: 1 + SLOT.firstStop + index,
        minute: stopMinutes[index],
        duration: BEATS.stopMove,
        ease: "power2.inOut",
      },
      at,
    );
    at += BEATS.stopMove;
    if (stop.dataset.kind === "known") {
      timeline.set(stop, { attr: { "data-state": "known" } }, at);
    }
    at += BEATS.stopHold;
  });

  // Horizon: the knowledge time, its answer, then a look at what came later.
  timeline
    .addLabel("horizon", at)
    .to(
      state,
      { head: 1 + SLOT.horizon, minute: knowledgeMinutes, duration: 0.4, ease: "power2.inOut" },
      at,
    )
    .set(readout, { attr: { "data-at-t": "true" } }, at + 0.4)
    .to(horizon, { opacity: 1, duration: 0.3 }, at + 0.3)
    .to(future, { opacity: 1, duration: 0.3 }, at + 0.5)
    .to(later, { opacity: 1, duration: 0.3, stagger: 0.08 }, at + 0.5)
    .to(state, { peek: 1, duration: 0.55, ease: "power1.inOut" }, at + 0.6);
  at += BEATS.horizon;

  // Return: the text fades, the arrow runs down the rest of the line with the camera
  // following, then wraps the bottom circle while the camera settles on it and the
  // clock runs forward to today. The tail starts just above the screen and is reeled in.
  const end = SLOT.end + 1;
  const run = BEATS.return * 0.45;
  const wrap = BEATS.return - run;
  // These two depend on the layout, so they tween a 0-to-1 proxy and read the layout
  // as they draw; every other tween is in layout-free units. That's what lets the
  // timeline skip invalidateOnRefresh, which would re-record start values mid-story.
  const reel = { p: 0 };
  const runner = { p: 0 };
  timeline
    .addLabel("return", at)
    .to([...stops, horizon, ...later], { opacity: 0, duration: 0.3 }, at)
    .to(future, { opacity: 0, duration: 0.3 }, at)
    .set(readout, { attr: { "data-at-t": "false" } }, at)
    .fromTo(
      reel,
      { p: 0 },
      {
        p: 1,
        duration: BEATS.return,
        ease: "power1.inOut",
        immediateRender: false,
        onUpdate: () => {
          if (reel.p <= 0) {
            state.tail = 1;
            return;
          }
          // The tail starts just above the screen as the camera returns to the arrow
          // (the peek may have carried T itself off screen), so it's reeled in on view.
          const top = m.stroke.slots[SLOT.horizon] - m.followY - 24;
          const from = Math.max(1, lineQAtY(top, m.stroke));
          state.tail = from + (end - from) * reel.p;
        },
      },
      at,
    )
    .to(state, { peek: 0, duration: run, ease: "power1.inOut" }, at)
    .fromTo(
      runner,
      { p: 0 },
      {
        p: 1,
        duration: run,
        ease: "power1.in",
        immediateRender: false,
        // In world pixels, so the arrow moves evenly however the slots are spaced.
        onUpdate: () => {
          const { slots } = m.stroke;
          const y = slots[SLOT.horizon] + (slots[SLOT.end] - slots[SLOT.horizon]) * runner.p;
          state.head = lineQAtY(y, m.stroke);
        },
      },
      at,
    )
    .to(state, { head: end + LOGO_SWEEP, duration: wrap, ease: "power2.out" }, at + run)
    .to(state, { cam: 2, duration: wrap, ease: "power1.inOut" }, at + run - 0.05)
    .to(state, { minute: nowMinutes, duration: BEATS.return, ease: "power2.inOut" }, at)
    .to(bottomClock, { opacity: 1, duration: 0.3 }, at + run)
    .to(state, { returnTurns: 3, duration: wrap, ease: "power2.inOut" }, at + run);
  at += BEATS.return;

  // Close: the clock and the name cross-fade back, and the calls to action appear.
  timeline
    .addLabel("close", at)
    .to(bottomClock, { opacity: 0, duration: 0.35 }, at)
    .to(name, { opacity: 1, duration: 0.35 }, at)
    .to(hud, { opacity: 0, duration: 0.25 }, at)
    .fromTo(
      close,
      { opacity: 0, y: 16 },
      { opacity: 1, y: 0, duration: 0.35, ease: "power2.out", immediateRender: false },
      at + 0.2,
    )
    .set(wall, { attr: { "data-idle": "false" } }, at)
    .to([wall, pause], { opacity: 1, duration: 0.4 }, at + 0.1);
  at += BEATS.close;
  // Hold the final picture until the stage scrolls away.
  timeline.to({}, { duration: BEATS.hold }, at);

  // Smooth wheel scrolling on GSAP's clock, so the scrubbed timeline never lags the page.
  const lenis = new Lenis({
    autoRaf: false,
    anchors: { immediate: true },
    stopInertiaOnNavigate: true,
  });
  lenis.on("scroll", ScrollTrigger.update);
  const tick = (time: number) => lenis.raf(time * 1000);
  gsap.ticker.add(tick);
  gsap.ticker.lagSmoothing(0);

  // Re-measure before ScrollTrigger recomputes (resizes, fonts), then redraw.
  const remeasure = () => {
    m = measure();
  };
  ScrollTrigger.addEventListener("refreshInit", remeasure);

  // Tabbing to the calls to action jumps to the end, where they're visible.
  const onFocusIn = (event: FocusEvent) => {
    const scroller = timeline.scrollTrigger;
    if (!scroller || !(event.target instanceof Node)) return;
    if (!close.contains(event.target) || scroller.progress > 0.97) return;
    lenis.scrollTo(scroller.end - 2, { immediate: true, force: true });
  };
  root.addEventListener("focusin", onFocusIn);

  let disposed = false;
  void document.fonts.ready.then(() => {
    if (!disposed) ScrollTrigger.refresh();
  });
  ScrollTrigger.refresh();
  render();

  // The story just grew: if the page was opened at an anchor below it, go there again.
  if (location.hash.length > 1) {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target && !root.contains(target)) target.scrollIntoView();
  }

  return () => {
    disposed = true;
    root.removeEventListener("focusin", onFocusIn);
    ScrollTrigger.removeEventListener("refreshInit", remeasure);
    gsap.ticker.remove(tick);
    gsap.ticker.lagSmoothing(500, 33);
    lenis.destroy();
    history.scrollRestoration = restoration;
    delete root.dataset.storyMode;
    root.style.removeProperty("--line-x");
    world.style.removeProperty("transform");
    items.forEach((item) => item.style.removeProperty("--y"));
  };
}
