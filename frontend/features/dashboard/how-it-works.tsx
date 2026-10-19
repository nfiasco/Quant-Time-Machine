import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { routes, type AppRoute } from "@/config/navigation";

const steps: { title: string; body: React.ReactNode; route: AppRoute; cta: string }[] = [
  {
    title: "Pick a moment",
    body: "Choose a knowledge time. Every query is bound to it, so nothing published later can leak in.",
    route: routes.timeMachine,
    cta: "Open the time machine",
  },
  {
    title: "Test an idea",
    body: (
      <>
        Each monthly decision sees only data whose{" "}
        <code className="font-mono text-xs">available_at</code> is at or before that
        decision.
      </>
    ),
    route: routes.backtests,
    cta: "Go to backtests",
  },
  {
    title: "Check the evidence",
    body: "Every input records when it became public and where it came from, so any result can be audited and re-run.",
    route: routes.methodology,
    cta: "Read the methodology",
  },
];

export function HowItWorks() {
  return (
    <section aria-labelledby="how-it-works" className="flex flex-col gap-3">
      <h2 id="how-it-works" className="text-base font-semibold tracking-tight">
        How it works
      </h2>
      <ol className="grid gap-4 md:grid-cols-3">
        {steps.map((step, index) => {
          const Icon = step.route.icon;
          return (
            <li key={step.title} className="flex">
              <Card size="sm" className="flex-1">
                <CardHeader>
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <Icon className="size-3.5" aria-hidden />
                    </span>
                    Step {index + 1}
                  </span>
                  <CardTitle>{step.title}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-between gap-3">
                  <p className="text-pretty text-muted-foreground">{step.body}</p>
                  <Link
                    href={step.route.href}
                    className="flex w-fit items-center gap-1 rounded-sm text-sm font-medium underline-offset-4 hover:underline"
                  >
                    {step.cta}
                    <ArrowRightIcon className="size-3.5" aria-hidden />
                  </Link>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
