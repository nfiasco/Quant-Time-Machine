"use client";

import { useState, useTransition } from "react";
import { ChevronsUpDownIcon, PlusIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Spinner } from "@/components/ui/spinner";
import { loadCompanyOptions } from "@/features/time-machine/actions";
import { MAX_ENTRIES, TICKER_PATTERN } from "@/features/time-machine/params";
import type { CompanyOptions } from "@/features/time-machine/picker-options";
import { formatEtDate, parseAsOf } from "@/lib/time";

type TickerPickerProps = {
  /** The trigger's id, so the field's label names it. */
  id: string;
  value: string[];
  onChange: (tickers: string[]) => void;
  /** The form's knowledge time as an `as_of`, or null while its date is blank or invalid. */
  draftAsOf: string | null;
  /** The suggestions the page loaded, for the URL's moment. */
  initialCompanies: CompanyOptions;
  invalid?: boolean;
  describedBy?: string;
};

/**
 * Picks up to 10 tickers: search the universe at the moment being picked, or type any
 * ticker (the snapshot also knows companies outside the universe, such as TSLA before
 * it joined). shadcn's combobox recipe for Radix: a Popover around a Command.
 */
export function TickerPicker({
  id,
  value,
  onChange,
  draftAsOf,
  initialCompanies,
  invalid,
  describedBy,
}: TickerPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState<Record<string, CompanyOptions>>({});
  const [isLoading, startLoading] = useTransition();

  // Suggestions follow the date in the form: the page's list, or one loaded for the draft.
  const asOf = draftAsOf ?? initialCompanies.asOf;
  const companies = asOf === initialCompanies.asOf ? initialCompanies : (loaded[asOf] ?? null);
  const listMoment = companies ? parseAsOf(companies.asOf) : null;
  const atMax = value.length >= MAX_ENTRIES;
  const typed = search.trim().toUpperCase();
  // Offer free entry only when no listed company already answers the search, so typing
  // "apple" finds AAPL instead of offering a ticker called APPLE.
  const canAdd =
    TICKER_PATTERN.test(typed) &&
    !atMax &&
    !value.includes(typed) &&
    !companies?.options.some((option) => matchCompany(option.ticker, search, [option.name]) >= 0.7);

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setSearch("");
      return;
    }
    if (companies || !draftAsOf) return;
    const wanted = draftAsOf;
    startLoading(async () => {
      let result: CompanyOptions | null;
      try {
        result = await loadCompanyOptions(wanted);
      } catch {
        result = {
          asOf: wanted,
          options: [],
          note: "Couldn't load the companies for that moment. You can still type a ticker.",
        };
      }
      if (result) {
        const options = result;
        setLoaded((current) => ({ ...current, [wanted]: options }));
      }
    });
  }

  function toggle(ticker: string) {
    if (value.includes(ticker)) onChange(value.filter((item) => item !== ticker));
    else if (!atMax) onChange([...value, ticker]);
  }

  return (
    <div className="flex flex-col gap-2">
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            className="w-full justify-between font-normal text-muted-foreground aria-invalid:border-destructive"
          >
            {value.length === 0
              ? "Search companies or type a ticker"
              : atMax
                ? `${MAX_ENTRIES} chosen, the most a view can hold`
                : "Add another company"}
            <ChevronsUpDownIcon data-icon="inline-end" className="opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-72 p-0">
          <Command label="Search companies" filter={matchCompany}>
            <CommandInput
              placeholder="Ticker or company name"
              value={search}
              onValueChange={setSearch}
            />
            <CommandList>
              <CommandEmpty>
                {companies?.options.length ? "No company in the list matches." : "No suggestions."}
              </CommandEmpty>
              {companies && companies.options.length > 0 ? (
                <CommandGroup
                  heading={
                    listMoment
                      ? `In the universe on ${formatEtDate(listMoment)}`
                      : "In the universe"
                  }
                >
                  {companies.options.map((option) => {
                    const selected = value.includes(option.ticker);
                    return (
                      <CommandItem
                        key={option.ticker}
                        value={option.ticker}
                        keywords={[option.name]}
                        data-checked={selected}
                        disabled={!selected && atMax}
                        onSelect={() => toggle(option.ticker)}
                      >
                        <span className="w-14 shrink-0 font-mono text-xs font-medium">
                          {option.ticker}
                        </span>
                        <span className="min-w-0 truncate text-muted-foreground">
                          {option.name}
                        </span>
                        {selected ? <span className="sr-only">, chosen</span> : null}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              ) : null}
              {canAdd ? (
                <CommandGroup forceMount heading="Not in the list?">
                  <CommandItem
                    forceMount
                    value={`add ${typed}`}
                    onSelect={() => {
                      onChange([...value, typed]);
                      setSearch("");
                    }}
                  >
                    <PlusIcon />
                    Add <span className="font-mono font-medium">{typed}</span>
                  </CommandItem>
                </CommandGroup>
              ) : null}
            </CommandList>
            {isLoading ? (
              <p className="flex items-center gap-2 border-t px-3 py-2 text-xs text-muted-foreground">
                <Spinner aria-hidden className="size-3.5" />
                Loading the companies for that moment…
              </p>
            ) : companies?.note ? (
              <p className="border-t px-3 py-2 text-xs text-pretty text-muted-foreground">
                {companies.note}
              </p>
            ) : null}
          </Command>
        </PopoverContent>
      </Popover>

      {value.length > 0 ? (
        <ul aria-label="Chosen companies" className="flex flex-wrap gap-1.5">
          {value.map((ticker) => (
            <li key={ticker}>
              <Button
                type="button"
                variant="outline"
                size="xs"
                id={`${id}-chip-${ticker}`}
                className="font-mono"
                aria-label={`Remove ${ticker}`}
                onClick={() => {
                  // Keep keyboard focus nearby: the next chip, the previous one, or the search.
                  const index = value.indexOf(ticker);
                  const neighbor = value[index + 1] ?? value[index - 1];
                  onChange(value.filter((item) => item !== ticker));
                  requestAnimationFrame(() =>
                    document.getElementById(neighbor ? `${id}-chip-${neighbor}` : id)?.focus(),
                  );
                }}
              >
                {ticker}
                <XIcon data-icon="inline-end" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * How well a suggestion matches the search, for cmdk (0 hides it). Stricter than cmdk's
 * fuzzy default, which matched "spy" to "Wells Fargo & Company": a ticker matches from
 * its start, and a name from the start of one of its words.
 */
function matchCompany(value: string, search: string, keywords?: string[]): number {
  const query = search.trim().toLowerCase();
  if (!query) return 1;
  const ticker = value.toLowerCase();
  if (ticker === query) return 1;
  if (ticker.startsWith(query)) return 0.9;
  const words = (keywords ?? []).join(" ").toLowerCase().split(/[^a-z0-9&.]+/);
  if (words.some((word) => word.startsWith(query))) return 0.7;
  return (keywords ?? []).join(" ").toLowerCase().includes(query) ? 0.4 : 0;
}
