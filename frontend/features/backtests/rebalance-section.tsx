import { CircleAlertIcon, InfoIcon, TriangleAlertIcon } from "lucide-react";

import { RetryButton } from "@/components/feedback/retry-button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { describeFailure } from "@/features/backtests/api-failure";
import { auditSections, newestFilings } from "@/features/backtests/audit";
import { AuditPanel } from "@/features/backtests/audit-panel";
import { formatDay } from "@/features/backtests/decisions";
import { describeCounts, holdingRows, memberRows } from "@/features/backtests/members";
import { MembersTable } from "@/features/backtests/members-table";
import { RebalancePicker } from "@/features/backtests/rebalance-picker";
import type { RunResultsData } from "@/features/backtests/results-data";
import { TradesTable } from "@/features/backtests/trades-table";
import { warningsAt } from "@/features/backtests/warnings";
import type { ApiFailure } from "@/lib/api/errors";
import type { BacktestPeriod, BacktestResult, BacktestRun } from "@/lib/api/types";
import { formatBps, formatNumber, formatPercent } from "@/lib/format";
import { etDateTimeOf, formatEtDateTime, formatEtShortDate, parseIsoDate } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * The drill-down into one rebalance (S9.6): its period, every member it held or passed
 * over and why, its trades, and the audit of what it read, each with when it became
 * public. The rebalance is the address's `?decision=`, picked here.
 */
export function RebalanceSection({
  run,
  result,
  data,
}: {
  run: BacktestRun;
  result: BacktestResult;
  data: RunResultsData;
}) {
  const { choice } = data;
  if (!choice) {
    return (
      <Card id="rebalance">
        <CardHeader>
          <CardTitle>
            <h2>Rebalances</h2>
          </CardTitle>
          <CardDescription>
            The run made no decision, so there&apos;s none to look into.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const period = result.periods.find((p) => p.decision === choice.day) ?? null;
  const warnings = warningsAt(result.warnings, choice.day);
  const members = data.members?.ok ? data.members.value.members : null;
  const holdings = data.holdings?.ok ? (data.holdings.value.holdings ?? []) : null;
  const views = data.audit?.ok ? data.audit.value.views : null;
  const sections = views ? auditSections(views, members) : null;
  const rows = members
    ? memberRows(members, holdings ?? [], run.spec, period?.end ?? null)
    : holdings
      ? holdingRows(holdings, period?.end ?? null)
      : null;

  return (
    <Card id="rebalance" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>
          <h2>Rebalance of {formatDay(choice.day)}</h2>
        </CardTitle>
        <CardDescription className="text-pretty">
          Whom this decision held and why it passed over the rest, its trades, and every input it
          read, with when each became public.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <RebalancePicker runId={run.run_id} days={data.days} selected={choice.day} />

        {/* While the picker loads another rebalance it carries data-pending, which dims this. */}
        <div className="flex flex-col gap-6 transition-opacity group-has-data-pending/results:opacity-60">
          {choice.notice ? (
            <Alert variant="info">
              <InfoIcon />
              <AlertDescription>{choice.notice}</AlertDescription>
            </Alert>
          ) : null}

          {period ? (
            <PeriodSummary period={period} benchmark={run.spec.benchmark} />
          ) : (
            <Alert variant="warning">
              <TriangleAlertIcon />
              <AlertTitle>The run ended at this decision</AlertTitle>
              <AlertDescription>
                Its trades were never made, so it has no holding period.
              </AlertDescription>
            </Alert>
          )}

          {warnings.length > 0 ? (
            <section aria-labelledby="rebalance-warnings" className="flex flex-col gap-2">
              <h3 id="rebalance-warnings" className="text-sm font-medium">
                Warnings at this decision
              </h3>
              <ul className="flex list-disc flex-col gap-1 pl-4 text-sm text-pretty marker:text-border">
                {warnings.map((warning, index) => (
                  <li key={index}>{warning.message}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="rebalance-members" className="flex flex-col gap-2">
            <h3 id="rebalance-members" className="text-sm font-medium">
              Members, held or not
            </h3>
            {data.members && !data.members.ok ? (
              <Failure what="the members" failure={data.members.failure} />
            ) : null}
            {data.members?.ok && members === null ? (
              <Alert variant="info">
                <InfoIcon />
                <AlertDescription>
                  This run was saved before runs kept every member&apos;s signals (record version
                  3), so only its holdings are listed.
                </AlertDescription>
              </Alert>
            ) : null}
            {data.holdings && !data.holdings.ok ? (
              <Failure what="the holdings" failure={data.holdings.failure} />
            ) : null}
            {rows ? (
              <>
                <p className="text-sm text-muted-foreground">
                  {members
                    ? describeCounts(rows)
                    : `${rows.length} ${rows.length === 1 ? "holding" : "holdings"}.`}
                </p>
                {rows.length > 0 ? (
                  <MembersTable
                    rows={rows}
                    spec={run.spec}
                    filings={sections ? newestFilings(sections) : new Map()}
                  />
                ) : null}
              </>
            ) : null}
          </section>

          <section aria-labelledby="rebalance-trades" className="flex flex-col gap-2">
            <h3 id="rebalance-trades" className="text-sm font-medium">
              Trades at the fill
            </h3>
            {data.trades && !data.trades.ok ? (
              <Failure what="the trades" failure={data.trades.failure} />
            ) : null}
            {data.trades?.ok ? (
              (data.trades.value.trades ?? []).length > 0 ? (
                <TradesTable trades={data.trades.value.trades ?? []} />
              ) : (
                <p className="text-sm text-muted-foreground">No trades: nothing changed.</p>
              )
            ) : null}
          </section>

          <section aria-labelledby="rebalance-audit" className="flex flex-col gap-3">
            <div className="flex flex-col gap-0.5">
              <h3 id="rebalance-audit" className="text-sm font-medium">
                Audit: every input, with when it became public
              </h3>
              <p className="text-xs text-pretty text-muted-foreground">
                What each view this rebalance opened read, by table, with its newest source one step
                away. A view only returns what was public by its time T.
              </p>
            </div>
            {data.audit && !data.audit.ok ? (
              <Failure what="the audit" failure={data.audit.failure} />
            ) : null}
            {sections ? <AuditPanel sections={sections} /> : null}
          </section>
        </div>
      </CardContent>
    </Card>
  );
}

function PeriodSummary({ period, benchmark }: { period: BacktestPeriod; benchmark: string }) {
  const decided = etDateTimeOf(period.decision_time);
  const filled = etDateTimeOf(period.fill_time);
  const end = parseIsoDate(period.end.session);
  const rows: { term: string; detail: React.ReactNode }[] = [
    { term: "Decision", detail: decided ? formatEtDateTime(decided) : period.decision_time },
    {
      term: "Fill",
      detail: `${filled ? formatEtDateTime(filled) : period.fill_time}, at the ${period.fill.price}`,
    },
    {
      term: "Held until",
      detail: `The ${period.end.price} on ${end ? formatEtShortDate(end) : period.end.session}`,
    },
    {
      term: "Members",
      detail: `${formatNumber(period.universe_size)} in the universe, ${formatNumber(period.holdings)} held, ${formatNumber(period.trades)} ${period.trades === 1 ? "trade" : "trades"}`,
    },
    {
      term: "Trading",
      detail: `${formatPercent(period.turnover)} of the portfolio traded, costing ${formatBps(period.cost * 10_000)}`,
    },
    {
      term: "Return",
      detail: (
        <>
          <Signed value={period.net_return} /> after costs;{" "}
          {period.benchmark_return === null ? (
            `${benchmark} had no return`
          ) : (
            <>
              {benchmark} <Signed value={period.benchmark_return} />
            </>
          )}
        </>
      ),
    },
    {
      term: "Risk-free rate",
      detail:
        period.risk_free_rate === null
          ? "None known, so taken as 0"
          : `${formatNumber(period.risk_free_rate)}% a year (TB3MS, as known at the decision)`,
    },
  ];
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-[7rem_1fr]">
      {rows.map((row) => (
        <div key={row.term} className="contents">
          <dt className="text-muted-foreground">{row.term}</dt>
          <dd className="min-w-0 text-pretty tabular-nums">{row.detail}</dd>
        </div>
      ))}
    </dl>
  );
}

function Signed({ value }: { value: number }) {
  const text = formatPercent(value, { signed: true });
  return (
    <span
      className={cn(
        "font-mono",
        text.startsWith("+") && "text-positive",
        text.startsWith("−") && "text-negative",
      )}
    >
      {text}
    </span>
  );
}

function Failure({ what, failure }: { what: string; failure: ApiFailure }) {
  const { title, description } = describeFailure(failure);
  return (
    <Alert variant="destructive">
      <CircleAlertIcon />
      <AlertTitle>
        Couldn&apos;t load {what}: {title}
      </AlertTitle>
      <AlertDescription>
        <p>{description}</p>
        <div className="mt-2">
          <RetryButton />
        </div>
      </AlertDescription>
    </Alert>
  );
}
