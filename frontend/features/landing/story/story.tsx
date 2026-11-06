import { ArrowDownIcon } from "lucide-react";
import Link from "next/link";

import { LogoMark } from "@/components/layout/logo-mark";
import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";

import { StoryLogo } from "../logo";
import { STORY_QUERY } from "./events";
import { StoryStage } from "./story-stage";
import { StoryTimeline } from "./story-timeline";

// Below the logo circle, where the intro, the question, and the calls to action take turns.
const belowCircle =
  "story-animated:absolute story-animated:inset-x-0 story-animated:top-[calc(var(--story-anchor-y)+var(--story-r)+2rem)] story-animated:z-30";

/** A soft pool of background color that keeps text clear of the ticker wall behind it. */
function TextGlow() {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute inset-x-[8%] -inset-y-10 -z-10 hidden bg-[radial-gradient(closest-side,var(--color-background)_50%,transparent)] story-animated:block"
    />
  );
}

/**
 * The scroll story: the logo unwinds into a timeline of what was public before
 * June 5, 2020, 9:30 AM ET, then winds back into the logo. See features/landing/story/.
 */
export function Story() {
  return (
    <StoryStage
      hero={<StoryHero />}
      ask={<StoryAsk />}
      timeline={<StoryTimeline />}
      close={<StoryClose />}
    />
  );
}

function StoryHero() {
  return (
    <div
      data-story-hero
      className="relative h-svh min-h-[34rem] story-animated:absolute story-animated:inset-x-0 story-animated:top-0 story-animated:z-20 story-animated:min-h-0"
    >
      <StoryLogo />
      <h1
        data-story-name
        className="absolute top-(--story-anchor-y) left-1/2 -translate-x-1/2 -translate-y-1/2 text-center text-[length:calc(var(--story-r)*0.34)] leading-[0.92] font-semibold tracking-[-0.045em]"
      >
        <span className="block">Quant</span>{" "}
        <span className="block">Time</span>{" "}
        <span className="block">Machine</span>
      </h1>
      <div
        data-story-intro
        className="absolute inset-x-0 top-[calc(var(--story-anchor-y)+var(--story-r)+2.25rem)] flex flex-col items-center gap-5 px-6 text-center"
      >
        <TextGlow />
        <p className="max-w-sm text-base text-balance text-muted-foreground sm:max-w-md sm:text-lg">
          {siteConfig.description}
        </p>
        <div className="flex items-center gap-5 text-sm">
          <span className="hidden items-center gap-1.5 text-muted-foreground story-animated:inline-flex">
            <ArrowDownIcon className="size-4" aria-hidden />
            Scroll to rewind
          </span>
          <a
            href="#features"
            className="rounded-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:opacity-100!"
          >
            Skip the story
          </a>
        </div>
      </div>
    </div>
  );
}

function StoryAsk() {
  return (
    <div
      data-story-ask
      className={`mx-auto w-full max-w-xl px-6 py-16 story-animated:py-0 ${belowCircle}`}
    >
      <p className="font-mono text-xs text-muted-foreground">
        A question, asked in the past
      </p>
      <div className="mt-2 rounded-2xl border bg-card p-4 shadow-xs sm:p-5">
        <h2
          id="story-title"
          className="text-base font-medium text-balance sm:text-lg"
        >
          {STORY_QUERY.question}
        </h2>
        <p className="mt-2 font-mono text-xs break-words text-muted-foreground">
          {STORY_QUERY.params}
        </p>
      </div>
    </div>
  );
}

function StoryClose() {
  return (
    <div
      data-story-close
      className={`mx-auto flex max-w-xl flex-col items-center gap-5 px-6 pt-10 pb-28 text-center focus-within:opacity-100! story-animated:pt-0 story-animated:pb-0 ${belowCircle}`}
    >
      <TextGlow />
      <LogoMark className="size-10 story-animated:hidden" />
      <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
        Test ideas without seeing the future.
      </h2>
      <div className="flex flex-wrap justify-center gap-3">
        <Button asChild size="xl">
          <Link href={routes.dashboard.href}>Enter workspace</Link>
        </Button>
        <Button asChild size="xl" variant="outline">
          <Link href={routes.signUp.href}>Create account</Link>
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Accounts aren&apos;t live yet. The workspace works without one.
      </p>
    </div>
  );
}
