// The scroll story's pacing, in screens of scroll (one screen is one viewport height).
// The story section is (STORY_SCREENS + 1) screens tall: the extra one is the sticky
// stage itself. Tune the feel here; the timeline in story-engine.tsx reads only these.

export const BEATS = {
  /** The logo and name, before anything moves. */
  hero: 0.35,
  /** The name fades, clock hands appear, the question rises. */
  ask: 0.65,
  /** The circle unwinds and the clock runs back to the first stop. */
  rewind: 1.2,
  /** Per stop: the arrow travels to it, then holds while it becomes known. */
  stopMove: 0.38,
  stopHold: 0.22,
  /** The arrow reaches the knowledge time; the answer and what came later appear. */
  horizon: 1.4,
  /** The line winds back into the logo and the clock runs forward to today. */
  return: 1.2,
  /** The name and the calls to action come back, then a short hold. */
  close: 0.5,
  hold: 0.4,
} as const;

/** Stops on the timeline before the knowledge time. */
export const STOP_COUNT = 6;

/** Facts that became public after the knowledge time. */
export const LATER_COUNT = 3;

export const STORY_SCREENS =
  BEATS.hero +
  BEATS.ask +
  BEATS.rewind +
  STOP_COUNT * (BEATS.stopMove + BEATS.stopHold) +
  BEATS.horizon +
  BEATS.return +
  BEATS.close +
  BEATS.hold;

/**
 * Slots: positions along the timeline. 0 is where the line leaves the top circle,
 * 1–6 are the stops, 7 is the knowledge time, 8–10 the later facts, and 11 the
 * line's end, where the bottom circle forms.
 */
export const SLOT = {
  firstStop: 1,
  horizon: STOP_COUNT + 1,
  firstLater: STOP_COUNT + 2,
  end: STOP_COUNT + LATER_COUNT + 2,
} as const;
