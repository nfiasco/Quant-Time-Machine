import { routes, type AppRoute } from "@/config/navigation";

const FEATURES: { route: AppRoute; endpoint?: string }[] = [
  { route: routes.timeMachine, endpoint: "GET /v1/snapshot" },
  { route: routes.revisions, endpoint: "GET /v1/macro/{series}/revisions" },
  { route: routes.filings, endpoint: "GET /v1/filings/{ticker}" },
  { route: routes.backtestBuilder },
  { route: routes.assistant },
];

/** A route's status in words: live, being built this semester, or next semester. */
function statusLabel(route: AppRoute): string {
  if (route.status === "live") return "Live";
  const milestone = route.story?.milestone;
  return milestone === "M7" || milestone === "M9" ? "Spring 2027" : "In progress";
}

export function FeaturesSection() {
  return (
    <section
      id="features"
      tabIndex={-1}
      aria-labelledby="features-title"
      className="border-t outline-none"
    >
      <div className="mx-auto w-full max-w-6xl px-4 py-24 sm:px-6 lg:px-8">
        <h2
          id="features-title"
          className="text-3xl font-semibold tracking-tight sm:text-4xl"
        >
          What&apos;s inside
        </h2>
        <p className="mt-3 max-w-2xl text-base text-pretty text-muted-foreground sm:text-lg">
          The point-in-time data layer and its API are built. The pages that use
          them are on the way.
        </p>
        <ul className="mt-12 grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ route, endpoint }) => (
            <li key={route.href} className="flex flex-col gap-3 bg-background p-6">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold tracking-tight">{route.title}</h3>
                <span className="rounded-full border px-2 py-0.5 font-mono text-xs text-muted-foreground">
                  {statusLabel(route)}
                </span>
              </div>
              <p className="text-sm text-pretty text-muted-foreground">
                {route.description}
              </p>
              {endpoint ? (
                <code className="mt-auto font-mono text-xs text-brand-ink">
                  {endpoint}
                </code>
              ) : null}
            </li>
          ))}
          <li className="flex flex-col gap-3 bg-background p-6">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold tracking-tight">Point-in-time API</h3>
              <span className="rounded-full border px-2 py-0.5 font-mono text-xs text-muted-foreground">
                Built · not hosted yet
              </span>
            </div>
            <p className="text-sm text-pretty text-muted-foreground">
              Every endpoint takes a knowledge time and returns only what was public by
              then, with when and where each fact came from.
            </p>
            <code className="mt-auto font-mono text-xs text-brand-ink">as_of=…</code>
          </li>
        </ul>
      </div>
    </section>
  );
}
