// Every page in the app, registered once. The sidebar, page metadata, and the
// placeholder pages all read from here. Adding a page? Add it here first
// (see GUIDELINES.md, "Adding a page").

import type { Metadata, Route } from "next";
import {
  BookOpenIcon,
  CalendarClockIcon,
  ChartLineIcon,
  Columns3Icon,
  FileTextIcon,
  FlaskConicalIcon,
  FolderOpenIcon,
  LayersIcon,
  LayoutDashboardIcon,
  LogInIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserPlusIcon,
  type LucideIcon,
} from "lucide-react";

import { siteConfig } from "@/config/site";

/** Milestones that planned pages are scheduled for (doc/roadmap.md §5.2). */
export const milestones = {
  M3: { name: "Point-in-time data v1", target: "Nov 8, 2026" },
  M4: { name: "Backtester v1", target: "Nov 22, 2026" },
  M5: { name: "Web UI and CISC 498 demo", target: "Dec 2026" },
  M7: { name: "AI research assistant alpha", target: "Mar 2027" },
  M9: { name: "Comparison and robustness", target: "May 2027" },
} as const;

export type MilestoneId = keyof typeof milestones;

/** The roadmap story that builds a page. `title` is the story's heading in doc/roadmap.md. */
export type RoadmapStory = {
  id: string;
  title: string;
  milestone: MilestoneId;
};

export type AppRoute = {
  title: string;
  href: Route;
  icon: LucideIcon;
  /** One sentence on what the page is for: page metadata and placeholder subtitle. */
  description: string;
  status: "live" | "planned";
  story?: RoadmapStory;
  /** What the finished page will do, from the story's acceptance criteria. */
  highlights?: readonly string[];
  requiresAccount?: boolean;
};

export const routes = {
  dashboard: {
    title: "Dashboard",
    href: "/",
    icon: LayoutDashboardIcon,
    description:
      "Start from a moment in time, the featured experiment, or your recent runs.",
    status: "live",
  },
  timeMachine: {
    title: "Time Machine",
    href: "/time-machine",
    icon: CalendarClockIcon,
    description: "Pick a moment and see what was known, and what wasn't yet.",
    status: "planned",
    story: { id: "S9.2", title: "Time Machine explorer", milestone: "M3" },
    highlights: [
      "Pick a moment (09:30 ET by default), companies, and economic series.",
      "Known: the last close, the latest 10-K, 10-Q, and 8-K with acceptance times and links, and the latest macro values with release times.",
      "Not yet known: upcoming filings and later revisions, clearly marked.",
      "The URL holds the moment, companies, and series, so every view can be shared.",
    ],
  },
  backtests: {
    title: "Backtests",
    href: "/backtests",
    icon: ChartLineIcon,
    description:
      "Run strategies on point-in-time data and inspect the evidence behind every result.",
    status: "planned",
    story: { id: "S9.6", title: "Backtest results page", milestone: "M5" },
    highlights: [
      "Equity curve against the benchmark, drawdown chart, metrics table, and holdings at each rebalance.",
      "Assumptions (decision time, fill rule, costs, data version) and warnings shown up front.",
      "Audit drill-down: every input used at a rebalance, with its available_at.",
      "A permanent link for every run.",
    ],
  },
  backtestBuilder: {
    title: "New backtest",
    href: "/backtests/new",
    icon: FlaskConicalIcon,
    description: "Build a backtest with a form, no code or AI required.",
    status: "planned",
    story: { id: "S9.5", title: "Backtest builder", milestone: "M5" },
    highlights: [
      "Choose the universe, period, rebalance frequency, signals and their parameters, filters, weighting, benchmark, and costs.",
      "The canonical example as a one-click preset.",
      "Validation errors from the API next to the right fields.",
      "Submitting starts a run and shows its progress.",
    ],
  },
  revisions: {
    title: "Revisions",
    href: "/revisions",
    icon: LayersIcon,
    description:
      "See how an economic data point changed from its first release to today.",
    status: "planned",
    story: { id: "S9.3", title: "Macro revision viewer", milestone: "M4" },
    highlights: [
      "Choose a series and an observation period to see every published value over time, as a chart and a table.",
      "The value that was visible at the Time Machine's moment is highlighted.",
      "Works for January 1990 unemployment, first reported as 5.3% and later revised to 5.4%.",
    ],
  },
  filings: {
    title: "Filings",
    href: "/filings",
    icon: FileTextIcon,
    description:
      "Compare when a quarter ended with when its filing actually became public.",
    status: "planned",
    story: { id: "S9.4", title: "Company filing timeline", milestone: "M5" },
    highlights: [
      "A timeline of fiscal period ends against EDGAR acceptance times, with amendments flagged.",
      'The reporting lag for every filing, for example "published 34 days after quarter end".',
    ],
  },
  experiments: {
    title: "Experiments",
    href: "/experiments",
    icon: FolderOpenIcon,
    description: "Your saved experiments and runs, private to your account.",
    status: "planned",
    story: { id: "S16.5", title: "Save and reopen experiments", milestone: "M5" },
    highlights: [
      "Save a spec from the backtest builder and run it again later.",
      "Each saved run keeps its spec, data version, and metric summary, so it can be reproduced.",
      "Signed-out users can still run the canonical example; saving asks you to sign in.",
    ],
    requiresAccount: true,
  },
  methodology: {
    title: "Methodology",
    href: "/methodology",
    icon: BookOpenIcon,
    description:
      "The timing rules behind every number, and what the results do and don't prove.",
    status: "planned",
    story: { id: "S9.7", title: "Methodology page", milestone: "M5" },
    highlights: [
      "The timing rule for each source: daily prices, SEC filings, XBRL facts, and macro vintages.",
      "Why the store is append-only, and how data versions make runs reproducible.",
      "Known limitations: survivorship gaps, fundamentals starting in 2009–2011, and conservative defaults.",
    ],
  },
  privacy: {
    title: "Privacy",
    href: "/privacy",
    icon: ShieldCheckIcon,
    description: "What the app stores about you, and how to delete it.",
    status: "planned",
    story: {
      id: "S16.6",
      title: "Privacy page and account deletion",
      milestone: "M5",
    },
    highlights: [
      "What the app stores (email address, saved experiments, runs), why, and where (Supabase).",
      "How to delete your account and all of your data.",
    ],
  },
  assistant: {
    title: "AI assistant",
    href: "/assistant",
    icon: SparklesIcon,
    description:
      "Ask a research question in plain English and get an experiment you can review, run, and audit.",
    status: "planned",
    story: { id: "S11.5", title: "Chat interface", milestone: "M7" },
    highlights: [
      "Turns a hypothesis into a validated experiment spec, asking clarifying questions when terms are ambiguous.",
      "You review and confirm the spec before anything runs.",
      "The conversation, plan, run status, and results on one page.",
      "Every number comes from the engine, with run IDs cited; the assistant never computes returns itself.",
    ],
  },
  compare: {
    title: "Compare",
    href: "/compare",
    icon: Columns3Icon,
    description:
      "Put two to four runs side by side to see which idea actually holds up.",
    status: "planned",
    story: { id: "S14.1", title: "Compare strategies side by side", milestone: "M9" },
    highlights: [
      "A metrics table, overlaid equity curves, and a diff of the specs.",
      "The difference in monthly returns, with its mean, t-statistic, and correlation.",
    ],
  },
  signIn: {
    title: "Sign in",
    href: "/sign-in",
    icon: LogInIcon,
    description: "Sign in to keep your experiments and runs.",
    status: "planned",
    story: { id: "S16.3", title: "Sign-up, sign-in, and sign-out", milestone: "M4" },
  },
  signUp: {
    title: "Create account",
    href: "/sign-up",
    icon: UserPlusIcon,
    description: "Create an account to save experiments and runs.",
    status: "planned",
    story: { id: "S16.3", title: "Sign-up, sign-in, and sign-out", milestone: "M4" },
  },
} satisfies Record<string, AppRoute>;

export type NavSection = { label: string; items: readonly AppRoute[] };

/** The sidebar, top to bottom. */
export const navSections: readonly NavSection[] = [
  {
    label: "Research",
    items: [
      routes.dashboard,
      routes.timeMachine,
      routes.backtests,
      routes.revisions,
      routes.filings,
    ],
  },
  { label: "Workspace", items: [routes.experiments] },
  { label: "Learn", items: [routes.methodology] },
  { label: "Spring 2027", items: [routes.assistant, routes.compare] },
];

/** Title and description for a page's `metadata` export. */
export function routeMetadata(route: AppRoute): Metadata {
  return { title: route.title, description: route.description };
}

/** Link to a story's section of doc/roadmap.md on GitHub, using GitHub's heading anchors. */
export function storyUrl(story: RoadmapStory): string {
  const anchor = `${story.id} ${story.title}`
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, "")
    .replace(/ /g, "-");
  return `${siteConfig.roadmapUrl}#${anchor}`;
}
