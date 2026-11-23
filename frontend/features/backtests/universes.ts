// The universes a spec can name. The API has no catalog of them: universe v1 is the only one
// (D3, doc/reference/data-sources.md). A spec that names another gets a 422 at `universe.id`,
// which the builder shows beside its universe field.

export type Universe = {
  /** As a spec writes it. */
  id: string;
  label: string;
  /** One sentence on who's in it, for the builder. */
  description: string;
};

export const UNIVERSES: readonly Universe[] = [
  {
    id: "starter_large_caps",
    label: "Starter large caps",
    description:
      "Universe v1: 50 large US companies, each a member only while it was in the S&P 500, from 2010 on. It's the only universe for now.",
  },
];

/** A universe's name for people, or its ID if it's one we don't know. */
export function universeLabel(id: string): string {
  return UNIVERSES.find((universe) => universe.id === id)?.label ?? id;
}
