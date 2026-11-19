import { describe, expectTypeOf, it } from "vitest";

import type {
  CatalogCompany,
  CatalogSeries,
  GetPath,
  GetResponse,
  Snapshot,
  V1Response,
} from "@/lib/api/types";

// Checks on types: Vitest runs them as no-ops, and `next build` type-checks them. They fail
// the build if GetResponse stops resolving to a route's body. Nothing else would notice:
// `never` and `any` are assignable to every type, so the helpers would still compile.
describe("GetResponse", () => {
  it("is the body of a route's 200 response", () => {
    expectTypeOf<GetResponse<"/v1/snapshot">>().not.toBeAny();
    expectTypeOf<Snapshot>().not.toBeAny();
    expectTypeOf<GetResponse<"/v1/snapshot">["data"]>().toEqualTypeOf<Snapshot>();
    expectTypeOf<GetResponse<"/v1/catalog/series">["data"]>().toEqualTypeOf<CatalogSeries[]>();
    expectTypeOf<GetResponse<"/v1/catalog/companies">["data"]>().toEqualTypeOf<CatalogCompany[]>();
  });

  it("is an envelope for a data route", () => {
    expectTypeOf<GetResponse<"/v1/snapshot">>().toExtend<V1Response<Snapshot>>();
  });

  it("names only routes with a GET", () => {
    expectTypeOf<"/v1/backtests/{run_id}">().toExtend<GetPath>();
    // Submitting a backtest is the one POST.
    expectTypeOf<"/v1/backtests">().not.toExtend<GetPath>();
  });
});
