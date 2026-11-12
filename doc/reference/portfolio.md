# Portfolio construction and costs

> **Story S7.5.** Version 1, 2026-11-12. To change a rule, update [`app/backtest/portfolio.py`](../../backend/app/backtest/portfolio.py), the loop in [`app/backtest/simulation.py`](../../backend/app/backtest/simulation.py), the `portfolio` model in [`app/backtest/spec.py`](../../backend/app/backtest/spec.py), their tests, and this page together.

A portfolio is a weight for each stock held, set at each decision from the signals' values then ([signal library](signals.md)). Three parts of a spec decide it:

```json
"filters": [{ "signal": "rev_accel", "op": ">", "value": 0 }],
"portfolio": {
  "weighting": "equal",
  "long_only": true,
  "rank": { "signal": "mom_12_1", "quantiles": 5, "long": "top" }
},
"costs": { "bps_per_trade": 10 }
```

This holds, at equal weights, the fifth with the highest momentum among the stocks whose revenue growth is speeding up, and pays 10 basis points of everything it trades.

- **Weights are fractions of the portfolio's value.** 0.5 is half of it. A short's weight is negative.
- **`rank` is optional.** Without it, every stock that passes the filters is held, as the canonical example does.
- **Everything is decided from the decision's view,** so a ranking uses only what was known then ([time model](time-model.md)).

## From signals to weights

At each decision, in this order:

1. **Members that trade.** The universe's members at the decision, less any that had stopped trading (`stopped_trading`).
2. **Values.** A member needs a value for every filter's signal and for the ranking's. One without is left out, with the signal's reason (`missing_signal`).
3. **[Filters](#1-filters).** A member must pass all of them.
4. **[Ranking](#2-ranking),** if the spec has one. The members that passed are ranked by one signal, and only the ends of the ranking are kept.
5. **[Weights](#3-weights).** Equal weights for the members kept.

Then, at the fill, the portfolio [trades to those weights and pays its costs](#4-trades-turnover-and-costs).

## 1. Filters

```json
{ "signal": "mom_12_1", "op": ">", "value": 0 }
```

A filter compares one signal with a number, using `>`, `>=`, `<`, or `<=`. A spec can have any number of them, or none, and a stock is held only if it passes them all. A filter on a [macro change](signals.md#4-macro-change), which is the same for every stock, holds the whole portfolio or none of it.

## 2. Ranking

```json
"rank": { "signal": "mom_12_1", "quantiles": 5, "long": "top" }
```

| Field | Meaning |
| --- | --- |
| `signal` | The ID of a signal in `signals`. Not a `macro_change`, which is the same for every stock and so can't rank them. |
| `quantiles` | How many parts the ranking is split into, from 2 to 100: 5 for quintiles, 10 for deciles. |
| `long` | The end that's held long: `"top"` for the highest values, `"bottom"` for the lowest. |

- **Filters come first.** Only the members that passed every filter are ranked, so the quintiles are of those, not of the universe. A spec with no filters ranks every member that has a value.
- **The order** runs from the highest value to the lowest. Equal values go in security ID order, so a ranking is the same on every run.
- **The size of each end** is the number ranked divided by `quantiles`, rounded down, and at least one:

  ```text
  n = max(1, N // quantiles)
  ```

  | Ranked, N | `quantiles` | Each end, n | Why it's a useful case |
  | --- | --- | --- | --- |
  | 50 | 5 | 10 | A quintile of the starter universe |
  | 48 | 5 | 9 | Rounded down from 9.6 |
  | 3 | 2 | 1 | The middle stock is in neither half |
  | 4 | 5 | 1 | Fewer than the quantiles: one, with a `thin_ranking` warning |
  | 1 | 5 | 1 | Long only holds it; long-short can't, and holds cash |

- **Why round down.** The top end is the first n of the ranking and the bottom end the last n. Rounding down keeps 2n within N whenever two or more are ranked, so no stock is ever in both ends.
- **Why at least one.** With fewer members than quantiles, the formula gives none. Holding cash then would turn a thin month into a flat one, so the engine holds one at each end instead and says so.

## 3. Weights

| `weighting` | `long_only` | `rank` | Held | Weights |
| --- | --- | --- | --- | --- |
| `"equal"` | `true` | none | Every member that passed the filters | 1/n each |
| `"equal"` | `true` | set | The `long` end of the ranking | 1/n each |
| `"equal"` | `false` | set | The `long` end, and the other end short | 1/n each long, and −1/n each short |
| `"value"` | any | any | Rejected by the engine for now ([limitation 1](#known-limitations)) | |

- **Long only.** The weights add up to 1: all of the portfolio is invested.
- **Long-short.** The long weights add up to 1 and the short ones to −1, so the portfolio is long as much as it's short. `long_only: false` needs a `rank`: without one there's no other end to be short.
- **A stock that can't fill.** One with no price at the fill isn't bought, and its weight stays in cash, or isn't sold short, and the portfolio goes without it (`no_fill_price`). The others keep their weights, and the next stock in the ranking doesn't take its place.

## 4. Trades, turnover, and costs

At a fill, each stock trades from its weight just before to its target:

```text
before_i = its last target, moved by its return since, as a share of the portfolio's value now
turnover = Σ |target_i − before_i|
cost     = bps_per_trade / 10,000 × turnover
net      = (1 + gross) × (1 − cost) − 1
```

- **Turnover counts both sides.** Selling half the portfolio to buy something else is a turnover of 1. The first fill, from cash, is 1 for a long-only portfolio and 2 for a long-short one.
- **The cost is a fraction of the portfolio's value before trading,** and comes out of it: after the fill, the weights are the targets, of a portfolio worth (1 − cost) times as much. Each trade carries its share of the cost.
- **Each holding period reports** its `turnover`, `cost`, `gross_return` (from just after the fill to the period's end), and `net_return` (from just before the fill, so after costs), and each trade its weights before and after ([`HoldingPeriod`](../../backend/app/backtest/simulation.py)). Whole-run turnover is S7.6's.
- **Costs have a ceiling.** `bps_per_trade` must be less than 5,000 for a long-only portfolio, whose turnover is never more than 2. For a long-short one it must be less than 2,500, which covers swapping both ends at their targets, a turnover of 4.

## 5. Long-short portfolios

- **A short is a holding with a negative weight.** Its stock's total return counts against the portfolio: a short at −1 whose stock rises 10% costs 10% of the portfolio. `period_return` is always the stock's own return, so a short's is good when it's negative.
- **A period's return** is what the long end returned less what the short end did. Long a stock that gains 10% and short one that loses 10%: +20%.
- **Cash.** The portfolio's own value stays in cash beside the two ends, and earns nothing, like all cash here. Neither does what the shorts were sold for.
- **Weights drift.** Before a fill, a holding's weight is its target moved by its return, w(1 + r), over the portfolio's growth, 1 + R. After a loss the same positions are a bigger share of a smaller portfolio, so a long-short portfolio's weights have no limit, and neither does its turnover.
- **A portfolio can run out.** Long-only portfolios can't lose more than they hold. A short can: if a period ends with nothing left, the period is recorded with a value of 0 and returns of −100%, and the run ends there (`wiped_out`). So does a run whose next trades would cost as much as the portfolio is worth; no trade is made, and the last period's value stands.

## Worked example

Three made-up stocks, a ranking in thirds, long the top and short the bottom, at 10 bps. `test_a_hand_checked_long_short_run` checks every number.

| Month | Long | Short | Long's return | Short's return |
| --- | --- | --- | --- | --- |
| January | alpha | beta | +10% | −10% |
| February | alpha | beta | −10% | 0% |
| March | beta | alpha | +10% | 0% |
| April | gamma | alpha | +10% | +10% |

| Month | Weights before the fill | Turnover | Cost | Gross | Net | Value |
| --- | --- | --- | --- | --- | --- | --- |
| January | cash | 2 | 0.2% | +20% | +19.76% | 1.1976 |
| February | alpha 11/12, beta −3/4 | 1/3 | 0.033% | −10% | −10.03% | 1.0775 |
| March | alpha 1, beta −10/9 | 37/9 ≈ 4.11 | 0.411% | +10% | +9.55% | 1.1804 |
| April | alpha −10/11, beta 1 | 23/11 ≈ 2.09 | 0.209% | 0% | −0.21% | 1.1779 |

- **January.** Everything is bought and as much again sold short: 0.998 × (1 + 0.1 + 0.1) = 1.1976.
- **February.** The portfolio grew 20%, so both ends are under their targets: 1.1 / 1.2 and −0.9 / 1.2. Topping them up trades 1/12 + 1/4.
- **March.** The portfolio shrank to 0.9, so alpha is 0.9 / 0.9 of it and beta −1 / 0.9. Swapping them trades 2 + 19/9, more than 4.
- **April.** Beta grew with the portfolio, to 1.1 / 1.1, and alpha is −1 / 1.1. Gamma replaces beta, 1 + 1, and the short is topped up by 1/11. Both ends gain 10%, so the period only pays its costs.

## Warnings

A run doesn't stop for these. Each says what was assumed:

| Kind | When | Example |
| --- | --- | --- |
| `missing_signal` | A member has no value for a filter's signal or the ranking's | BBB was left out at the 2021-01-04 decision, because mom had no value. Fewer than 2 months of prices were known. |
| `thin_ranking` | Fewer members were ranked than the ranking has quantiles | Only 3 members of starter_large_caps could be ranked by mom at the 2021-01-04 decision, fewer than the ranking's 5 quantiles, so the top one was held. |
| `empty_portfolio` | No member was chosen, or a long-short portfolio had one to rank | Only 1 member of starter_large_caps could be ranked by mom at the 2021-02-01 decision, and a long-short portfolio needs 2, so the portfolio held cash. |
| `no_fill_price` | A chosen stock had no price at the fill | BBB had no price at the close on 2021-02-01, so it wasn't sold short, and the portfolio went without it until the next fill. |
| `delisted_exit` | A holding stopped trading before its period ended | CCC stopped trading after 2021-03-10, so it was valued at that day's close, and bought back at the next fill, on 2021-04-01. |
| `wiped_out` | The portfolio had nothing left, or couldn't pay for its trades. The run ends | The portfolio had nothing left at the close on 2021-02-01: what it held since the 2021-01-04 decision lost all of its value, so the run ended there. |

## Known limitations

1. **Value weights aren't available yet.** The spec accepts `"weighting": "value"`, and the web form still offers it, but the engine rejects it. Weighting by market cap needs each company's shares outstanding, and the cover-page count is missing for companies with several share classes, such as Alphabet, Meta, and Mastercard ([data sources](data-sources.md#sec-xbrl-reported-financials-company-facts)). S6.6 computes market cap.
2. **Shorting is free and always possible.** There's no borrow fee, no margin, no recall, and no check that shares could be borrowed, so a long-short portfolio's returns run high. A short pays its stock's dividends, since returns are total returns.
3. **Cash earns nothing,** including what the shorts were sold for.
4. **The ends round down.** The top quintile of 48 stocks is 9, or 18.75%. With few stocks ranked, an end is a much bigger share than asked: one of three for a quintile.
5. **Ties go to the lower security ID,** which is arbitrary. They're rare for momentum and revenue growth, and a signal that ties every stock, a macro change, can't rank.
6. **A ranking uses one signal.** There are no combined scores, and no ranking within sectors.
7. **A stock that can't fill isn't replaced** by the next in the ranking, so a long-short portfolio can be lopsided until the next fill.
8. **Costs are one flat rate** on everything traded, for buys, sells, and shorts alike. There's no spread, no price impact, and no minimum commission.
9. **The cost is charged on the value traded before costs.** The exact trades, on the slightly smaller portfolio, differ by about the cost times itself.
10. **The long-short cost ceiling isn't a guarantee.** After a loss, turnover can pass 4, as in March above. Each fill checks that the portfolio can pay for its trades.
11. **A portfolio is valued only at fills.** One whose shorts would have wiped it out mid-month, then recovered, carries on. Nothing forces a short to close between fills.

## Named tests

| Test | Checks |
| --- | --- |
| `test_each_end_of_a_ranking_holds_a_quantile_rounded_down` | The size of each end, for 13 pairs of N and `quantiles` |
| `test_equal_values_rank_in_security_id_order` | Ties, in whatever order the values arrive |
| `test_the_ends_of_a_long_short_ranking_never_overlap` | Two ends of the same size, adding up to 1 and −1, for 2 to 12 stocks |
| `test_swapping_a_long_and_a_short_trades_four_times_the_portfolio` | Turnover and cost with signed weights |
| `test_a_hand_checked_ranked_run` | Four stocks in halves, long only, over four months, with a filter that thins February's ranking |
| `test_a_hand_checked_long_short_run` | The worked example above |
| `test_filters_come_before_the_ranking` | The bottom of the ranking is the lowest value that passed |
| `test_a_member_missing_the_rankings_signal_is_left_out` | A ranking's signal is required, even with no filter on it |
| `test_a_ranking_with_fewer_members_than_quantiles_holds_one` | `thin_ranking`, long only and long-short |
| `test_a_long_short_portfolio_needs_two_members_to_rank` | Cash, with its own `empty_portfolio` sentence |
| `test_a_short_without_a_fill_price_isnt_opened` | `no_fill_price` for a short |
| `test_a_delisted_short_is_bought_back_at_its_last_close` | A short's `delisted_exit` |
| `test_a_short_that_loses_everything_ends_the_run` | `wiped_out` at a period's end, past zero and exactly at it |
| `test_trades_the_portfolio_cant_pay_for_end_the_run` | `wiped_out` at a fill, at 2,400 bps |
| `test_a_macro_change_cant_rank_securities` | The spec rejects a ranking by a macro change |

The first four are in [`test_portfolio.py`](../../backend/tests/test_portfolio.py), the last in [`test_spec.py`](../../backend/tests/test_spec.py), and the rest in [`test_simulation.py`](../../backend/tests/test_simulation.py).
