import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BacktestTrade } from "@/lib/api/types";
import { formatBps, formatPercent } from "@/lib/format";

/**
 * One rebalance's trades at its fill (S9.6): each security's weight before and after, the
 * value traded, and its cost, the biggest trade first.
 */
export function TradesTable({ trades }: { trades: readonly BacktestTrade[] }) {
  const rows = trades.toSorted(
    (a, b) => b.traded - a.traded || (a.ticker ?? "").localeCompare(b.ticker ?? ""),
  );
  return (
    <Table className="min-w-[30rem]">
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Security</TableHead>
          <TableHead scope="col" className="text-right">
            Before (%)
          </TableHead>
          <TableHead scope="col" className="text-right">
            After (%)
          </TableHead>
          <TableHead scope="col" className="text-right">
            Traded (%)
          </TableHead>
          <TableHead scope="col" className="text-right">
            Cost (bps)
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((trade, index) => (
          <TableRow key={`${trade.ticker ?? "closed"}-${index}`}>
            <TableHead scope="row" className="font-mono font-medium">
              {trade.ticker ?? "—"}
            </TableHead>
            <TableCell className="text-right font-mono tabular-nums">
              {formatPercent(trade.weight_before)}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums">
              {trade.weight_after === 0 ? "Closed" : formatPercent(trade.weight_after)}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums">
              {formatPercent(trade.traded)}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums">
              {formatBps(trade.cost * 10_000)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
