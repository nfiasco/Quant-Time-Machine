import { Skeleton } from "@/components/ui/skeleton";

// Shown on a first visit and when arriving from another page. A new search on this page
// keeps the old view (dimmed) instead, since only the search params change.
export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <span className="sr-only" role="status">
        Loading the Time Machine…
      </span>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="h-4 w-full max-w-md" />
      </div>
      <Skeleton className="h-72 rounded-xl lg:h-64" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-5 w-full max-w-sm" />
        <Skeleton className="h-4 w-full max-w-xs" />
      </div>
      {[0, 1].map((card) => (
        <div key={card} className="flex flex-col gap-3 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
          <Skeleton className="h-5 w-48" />
          <div className="@container">
            <div className="grid gap-3 @xl:grid-cols-2">
              {/* Known is solid; not yet known is dashed, in the hatched fog. */}
              <Skeleton className="h-36 rounded-xl" />
              <div className="h-36 rounded-xl border border-dashed border-future/45 bg-hatch-future" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
