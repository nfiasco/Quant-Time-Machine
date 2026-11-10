import { PageHeader } from "@/components/layout/page-header";
import { routeMetadata, routes } from "@/config/navigation";
import { demoMoment } from "@/features/time-machine/example-moment";
import { ExplorerEmpty } from "@/features/time-machine/explorer-empty";
import { ExplorerForm } from "@/features/time-machine/explorer-form";
import {
  catalogAsOf,
  explorerHref,
  fieldErrorsFromFailure,
  parseExplorerUrl,
  snapshotParamsOf,
  valuesKey,
  type ExplorerUrl,
} from "@/features/time-machine/params";
import { toCompanyOptions, toSeriesOptions } from "@/features/time-machine/picker-options";
import { buildSnapshotView, type SnapshotView } from "@/features/time-machine/snapshot-events";
import { SnapshotFailure } from "@/features/time-machine/snapshot-failure";
import { SnapshotResults } from "@/features/time-machine/snapshot-results";
import { getCatalogCompanies, getCatalogSeries } from "@/lib/api/catalog";
import { apiUrl } from "@/lib/api/client";
import { settle } from "@/lib/api/errors";
import { getSnapshot, snapshotPath } from "@/lib/api/snapshot";
import { formatEtDateTime } from "@/lib/time";

export const metadata = routeMetadata(routes.timeMachine);

/**
 * The Time Machine explorer (S9.2). The URL holds the view (`as_of`, `tickers`,
 * `series`); the page reads it, asks the API on the server, and shows what was known at
 * that moment and what wasn't yet. API failures render in place, so the form stays usable.
 */
export default async function TimeMachinePage(props: PageProps<"/time-machine">) {
  const url = parseExplorerUrl(await props.searchParams);
  // The pickers list what existed on the URL's date, or on the example's when it has none.
  const catalogAt = catalogAsOf(url.moment ?? demoMoment);
  const request = url.query ? snapshotParamsOf(url.query) : null;

  const [companies, series, snapshot] = await Promise.all([
    settle(getCatalogCompanies(catalogAt)),
    settle(getCatalogSeries(catalogAt)),
    request ? settle(getSnapshot(request)) : null,
  ]);

  const apiFieldErrors = snapshot?.ok === false ? fieldErrorsFromFailure(snapshot.failure) : {};
  const view = snapshot?.ok
    ? buildSnapshotView(snapshot.value, series.ok ? series.value.data : [])
    : null;

  let results: React.ReactNode;
  if (url.query && request && snapshot) {
    results = snapshot.ok && view ? (
      <SnapshotResults
        view={view}
        href={explorerHref(url.query)}
        requestUrl={apiUrl(snapshotPath(request))}
      />
    ) : !snapshot.ok ? (
      <SnapshotFailure
        failure={snapshot.failure}
        onField={Object.keys(apiFieldErrors).length > 0}
      />
    ) : null;
  } else if (url.state === "moment-only" && url.moment) {
    results = <ExplorerEmpty kind="moment-only" moment={url.moment} />;
  } else if (url.state === "invalid") {
    results = <ExplorerEmpty kind="invalid" />;
  } else {
    results = <ExplorerEmpty kind="blank" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={routes.timeMachine.title} description={routes.timeMachine.description} />

      {/* While the form loads the next view it carries data-pending, which dims the results. */}
      <div className="group/explorer flex flex-col gap-6">
        <ExplorerForm
          urlKey={valuesKey(url.values)}
          initialValues={url.values}
          serverErrors={{ ...url.issues, ...apiFieldErrors }}
          companies={toCompanyOptions(catalogAt, companies)}
          series={toSeriesOptions(series)}
          status={statusLine(url, view, snapshot?.ok === false)}
        />
        <div className="flex flex-col gap-6 transition-opacity group-has-data-pending/explorer:opacity-60">
          {results}
        </div>
      </div>
    </div>
  );
}

/** What the form's status line says once the page has loaded. */
function statusLine(url: ExplorerUrl, view: SnapshotView | null, failed: boolean): string {
  if (view) return `Showing what was known at ${formatEtDateTime(view.knowledgeTime)}.`;
  if (failed) return "No snapshot to show: see the message below.";
  if (url.state === "moment-only" && url.moment) {
    return `Add a company or a series to see what was known at ${formatEtDateTime(url.moment)}.`;
  }
  if (url.state === "invalid") return "This link has a problem: see the highlighted fields.";
  return "Pick a moment, then companies or series.";
}
