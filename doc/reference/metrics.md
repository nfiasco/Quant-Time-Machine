# Performance metrics and the benchmark

> **Story S7.6.** Version 1, 2026-11-12. To change a formula, update [`app/backtest/metrics.py`](../../backend/app/backtest/metrics.py), the risk-free rate's read in [`app/backtest/simulation.py`](../../backend/app/backtest/simulation.py), their tests, and this page together.

A run's metrics say how its portfolio did, and whether it beat the benchmark the spec names. They come from the run's holding periods, one for each monthly decision ([portfolio construction](portfolio.md)):

```python
from app.backtest.metrics import equity_curve, summarize

metrics = summarize(result)  # result = simulate(spec, views)
metrics.cagr, metrics.sharpe, metrics.excess_return
equity_curve(result)  # the portfolio's value beside the benchmark's
```

- **Everything is after costs.** The metrics use each period's net return.
- **Returns and rates are fractions.** 0.05 is 5%. The one exception is a period's `risk_free_rate`, which is in percent a year, as the Federal Reserve publishes it.
- **The metrics only do arithmetic** on what the loop recorded. They read no data, so the same run always gives the same metrics.
- **A metric that can't be computed is `None`,** never a number that looks like one ([when a metric has no value](#when-a-metric-has-no-value)).

## What each period gives

Each holding period runs from one fill to the next, and has three numbers for that stretch:

```text
r = net_return               the portfolio's return, after costs
b = benchmark_return         the benchmark's total return between the same prices
f = risk_free_rate / 1,200   what Treasury bills paid in a month
```

n is the number of periods, and V the portfolio's value, which starts at 1. `mean`, `stdev`, `var`, and `cov` are over the periods, and the last three divide by n − 1 (a spreadsheet's `STDEV.S`, `VAR.S`, and `COVARIANCE.S`).

**A period counts as a month,** because decisions are monthly. So volatility and the Sharpe ratio annualize by √12, and alpha by 12. Only CAGR uses the calendar.

## 1. The risk-free rate

The risk-free rate is TB3MS, the 3-month Treasury bill rate: a monthly average, in percent a year ([data sources](data-sources.md)).

- **It's the rate the decision knew.** Each decision reads TB3MS through its own view, like every signal, so it gets the latest value published by then ([time model](time-model.md)). The period's record carries it as `risk_free_rate`.
- **That's the rate from two months back.** The Federal Reserve publishes a month's average at 16:15 ET on the next month's first business day, which is the day of the decision, at 09:30.

  | Decision, at 09:30 ET | Knows | Published that afternoon |
  | --- | --- | --- |
  | January 2, 2020 | November 2019's 1.54% | December's 1.54% |
  | April 1, 2020 | February's 1.52% | March's 0.29% |
  | May 1, 2020 | March's 0.29% | April's 0.14% |

  A backtest that used April's 0.14% for May would be using a number nobody had that morning.
- **A month's share** is the rate over 1,200: 1.2% a year is 0.1% a month.
- **Without a rate,** the period's is `None` and counts as 0, with a `missing_risk_free` warning. TB3MS's archive of what was published starts on December 3, 1996.

## 2. Growth

```text
years        = days from the first fill's session to the last period's end / 365.25
total_return = V − 1
cagr         = V ^ (1 / years) − 1
```

- **CAGR** is the yearly rate that compounds to the total return. It's −1 for a portfolio with nothing left.
- **It counts days, not periods,** so a run that ends mid-month isn't stretched to a whole one.

## 3. Risk

```text
volatility   = stdev(r) × √12
sharpe       = mean(r − f) / stdev(r − f) × √12
max_drawdown = the lowest V_t / peak_t − 1, where peak_t = max(1, V_1, …, V_t)
```

- **Volatility** is how much the monthly returns vary, as a yearly figure.
- **The Sharpe ratio** is the return over the risk-free rate for each unit of that variation. Each period uses its own rate.
- **Maximum drawdown** is the deepest fall from an earlier peak, as a return: −0.25 fell by a quarter, and 0 never fell. The 1 the portfolio starts with is the first peak.

## 4. Trading

```text
turnover = mean of each period's turnover, after the first
```

A period's turnover is the value traded at its fill, as a share of the portfolio, and counts both sides ([trades, turnover, and costs](portfolio.md#4-trades-turnover-and-costs)). The first fill is left out: it buys the whole portfolio from cash, which says nothing about how much the strategy trades.

## 5. Against the benchmark

```text
benchmark_total_return = (1 + b_1) × … × (1 + b_n) − 1
benchmark_cagr         = (1 + benchmark_total_return) ^ (1 / years) − 1
excess_return          = cagr − benchmark_cagr
hit_rate               = the share of periods with r > b
beta                   = cov(r − f, b − f) / var(b − f)
alpha                  = (mean(r − f) − beta × mean(b − f)) × 12
mean_excess_return     = mean(r − b)
excess_t_stat          = mean(r − b) / (stdev(r − b) / √n)
```

- **Excess return** is how much more the portfolio grew a year than the benchmark did.
- **Hit rate** is how often the portfolio beat the benchmark. A period that only matched it isn't a hit.
- **Beta and alpha** are the slope and the intercept of a regression of the portfolio's return over the risk-free rate on the benchmark's (`SLOPE` and `INTERCEPT`). Beta is how much the portfolio moved with the benchmark, and alpha, a year, the return the benchmark doesn't explain.
- **The t-statistic** is the mean monthly excess return, in standard errors from zero. One near 0 means the difference could easily be chance. As a rule of thumb, it takes more than 2 to say otherwise, and many months.
- **Two kinds of excess.** `excess_return` is a yearly rate, from compounding. `mean_excess_return` is the plain average of the monthly differences, which is what the t-statistic tests.

## When a metric has no value

| Metric | `None` when |
| --- | --- |
| `cagr`, `benchmark_cagr` | The run starts and ends in one session, or is so short that the yearly rate is too big for a number |
| `volatility` | The run has one period |
| `sharpe`, `excess_t_stat` | The run has one period, or the returns they divide by don't vary |
| `turnover` | The run has one period, so no rebalance after the first fill |
| `beta`, `alpha` | The run has one period, or the benchmark's return over the risk-free rate doesn't vary |
| Every benchmark metric | A period has no benchmark return (`missing_benchmark`) |

- **"Doesn't vary"** means the highest and lowest are within 10⁻¹² of each other. Returns that are equal on paper differ near 10⁻¹⁶ once they come from prices, and dividing by so small a spread gives a huge ratio that means nothing. Their volatility is 0.
- **One gap is enough.** A benchmark's growth can't be compounded over a period it has no return for, so the run is compared with all of it or none.
- **A run with no periods** has no metrics, and `summarize` raises `ValueError`. `simulate` never returns one.

## The equity curve

`equity_curve(result)` gives a point at the first fill, where the portfolio and the benchmark are both 1, and one at each period's end: the portfolio's `value`, and what 1 in the benchmark would be worth. From the first period without a benchmark return, the benchmark's is `None`.

## Worked example

The three made-up stocks of the loop's hand-checked run, over four months of 2021, at 10 bps, against a made-up SPY and Treasury bill rate. `test_a_hand_checked_runs_metrics_match_the_worked_example` checks every number, to six places.

| Month | Held | Turnover | Gross | Net, r | Value, V |
| --- | --- | --- | --- | --- | --- |
| January | alpha, beta | 1 | 0% | −0.1000% | 0.999000 |
| February | alpha, gamma | 1 | 0% | −0.1000% | 0.998001 |
| March | alpha, beta, gamma | 2/3 | +3.3333% | +3.2644% | 1.030580 |
| April | gamma | 42/31 ≈ 1.3548 | +10% | +9.8510% | 1.132102 |

| Month | SPY, b | TB3MS known | f | r − f | b − f | r − b | SPY's value |
| --- | --- | --- | --- | --- | --- | --- | --- |
| January | +2% | 1.2 | 0.10% | −0.2000% | +1.90% | −2.1000% | 1.020000 |
| February | −1% | 2.4 | 0.20% | −0.3000% | −1.20% | +0.9000% | 1.009800 |
| March | +3% | 0.6 | 0.05% | +3.2144% | +2.95% | +0.2644% | 1.040094 |
| April | +1% | 3.6 | 0.30% | +9.5510% | +0.70% | +8.8510% | 1.050495 |

- **Net returns.** Each is (1 + gross) × (1 − 0.001 × turnover) − 1: March's is 1469/45000, and April's 15269/155000.
- **The rates.** November's 1.2% came out on December 1. December's 2.4% came out at 16:15 on January 4, after that morning's decision, so January uses 1.2% and February 2.4%. March's 12% came out on April 1 the same way, and no decision ever knew it.
- **The dates.** The first fill is January 4's close and the run ends at April 30's: 116 days, or 0.317591 years.

| Metric | Arithmetic | Value |
| --- | --- | --- |
| `total_return` | 1.132102 − 1 | 0.132102 |
| `cagr` | 1.132102 ^ (1 / 0.317591) − 1 | 0.477986 |
| `volatility` | stdev(r) = 0.046910, × √12 | 0.162501 |
| `sharpe` | mean(r − f) = 0.030664 and stdev(r − f) = 0.046215: 0.663504 × √12 | 2.298444 |
| `max_drawdown` | 0.998001 / 1 − 1, after February | −0.001999 |
| `turnover` | (1 + 2/3 + 42/31) / 3 = 281/279 | 1.007168 |
| `hit_rate` | February, March, and April, of 4 | 0.75 |
| `benchmark_total_return` | 1.02 × 0.99 × 1.03 × 1.01 − 1 | 0.050495 |
| `benchmark_cagr` | 1.050495 ^ (1 / 0.317591) − 1 | 0.167786 |
| `excess_return` | 0.477986 − 0.167786, before rounding | 0.310199 |
| `beta` | cov(r − f, b − f) = 0.0000936551, over var(b − f) = 0.0003170625 | 0.295384 |
| `alpha` | (0.030664 − 0.295384 × 0.010875) × 12 = 0.027451 × 12 | 0.329415 |
| `mean_excess_return` | mean(r − b) | 0.019789 |
| `excess_t_stat` | stdev(r − b) = 0.047598: 0.019789 / (0.047598 / √4) | 0.831492 |

- **The arithmetic shows rounded numbers,** and each value comes from the unrounded ones, so redoing a row from what it shows can differ in the last place.
- **Four months say very little.** A CAGR of 48% is 13% in 116 days, stretched to a year, and a t-statistic of 0.83 is what chance looks like. The example checks the arithmetic, not the strategy.
- **The drawdown** is only two months of costs. It shows that the 1 at the start counts as a peak.

## Warnings

A run doesn't stop for these. Each says what was assumed:

| Kind | When | Example |
| --- | --- | --- |
| `missing_risk_free` | TB3MS had no value known at a decision | TB3MS, the 3-month Treasury bill rate, had no value known at the 2021-01-04 decision, so the risk-free rate for the period to 2021-02-01 was taken as 0. |
| `missing_benchmark` | The benchmark had no price for a period | SPY, the benchmark, had no price for the period from the 2009-01-02 decision to 2009-02-02, so the period has no benchmark return. |

## Known limitations

1. **Every period counts as a month.** The first starts at the first fill and the last ends with the spec's period, so one can be shorter. A two-week last period weighs as much as a month in the volatility, the Sharpe ratio, alpha, and the t-statistic. CAGR isn't affected.
2. **The portfolio is seen only at fills.** A fall within a month that recovers by the next fill isn't in the drawdown, and volatility is of monthly returns, not daily ones.
3. **The risk-free rate is two months old,** by the time model, and approximate: TB3MS is a discount rate on a 360-day year, so dividing by 1,200 understates what a bill yields, by about 0.13 points a year at 5%.
4. **Cash earns nothing** ([portfolio limitation 3](portfolio.md#known-limitations)), so a portfolio that holds cash trails the risk-free rate, and one that holds only cash has a negative Sharpe ratio.
5. **One period without a benchmark return empties the benchmark's metrics,** even in a long run. A benchmark that started trading after the spec's period did compares with nothing.
6. **Short runs give extreme yearly rates,** as in the example. A run of a few months is better read by its total return.
7. **The t-statistic treats the months as independent,** with no correction for returns that follow each other. Confidence intervals, a placebo test, and a deflated Sharpe ratio are S14.4's.
8. **Alpha and beta are against the one benchmark.** There are no size, value, or momentum factors, so alpha is what SPY doesn't explain, not skill. A long-short portfolio's beta is often near zero or negative, and its excess return over a long-only index says little.
9. **Turnover counts both sides,** so 1 is selling half the portfolio to buy something else. Some sources report half of that.
10. **CAGR's last digit can differ between machines.** It's the engine's only power, which each system's maths library rounds its own way. Everything else is sums, products, and one square root.

## Named tests

| Test | Checks |
| --- | --- |
| `test_a_hand_checked_runs_metrics_match_the_worked_example` | The worked example above, and its equity curve |
| `test_each_period_carries_the_risk_free_rate_its_decision_knew` | A rate published at 16:15 on a decision's day isn't the one its period uses |
| `test_a_rate_counts_from_its_release_time` | A decision at 16:15 does know that day's rate |
| `test_a_period_without_a_risk_free_rate_is_warned_about` | `missing_risk_free`, for the one period whose decision knew no rate |
| `test_a_published_rate_of_zero_isnt_missing` | A rate of 0 is a rate |
| `test_cagr_annualizes_the_days_from_the_first_fill_to_the_end` | 364 days of doubling |
| `test_excess_return_is_the_difference_between_the_yearly_rates` | The benchmark's total return and CAGR, and the excess |
| `test_a_run_that_starts_and_ends_in_one_session_has_no_cagr` | No time, no yearly rate |
| `test_a_yearly_rate_too_big_for_a_number_is_left_out` | Tenfold in a day |
| `test_volatility_and_the_sharpe_ratio_annualize_monthly_returns` | √12, and a month's share of the rate |
| `test_the_sharpe_ratio_uses_each_periods_own_rate` | Rates that change during the run |
| `test_a_missing_risk_free_rate_counts_as_zero` | The same metrics as a published 0 |
| `test_max_drawdown_is_the_deepest_fall_from_a_peak` | The deepest of two falls, a fall from the start, and none |
| `test_turnover_leaves_out_the_first_fill` | The mean of the rebalances after it |
| `test_the_hit_rate_is_the_share_of_periods_that_beat_the_benchmark` | A tie isn't a hit |
| `test_beta_and_alpha_regress_returns_over_the_risk_free_rate` | A slope of 2 and 0.1% a month, with changing rates |
| `test_the_t_statistic_is_the_mean_excess_return_over_its_standard_error` | Three months, ahead by 1%, 2%, and 3% |
| `test_one_period_has_no_statistics` | What one period can and can't say |
| `test_returns_that_dont_vary_have_no_sharpe_ratio` | 1% a month from prices: a volatility of 0 |
| `test_a_benchmark_that_never_varies_has_no_beta` | No beta or alpha; the rest stands |
| `test_excess_returns_that_dont_vary_have_no_t_statistic` | Always 1% ahead |
| `test_a_period_without_a_benchmark_return_leaves_no_benchmark_metrics` | Eight metrics empty, and the curve's benchmark after the gap |
| `test_a_wiped_out_run_loses_everything` | A period of −100%: CAGR and drawdown of −1 |
| `test_a_run_without_periods_has_no_metrics` | `ValueError`, and an empty curve |
| `test_the_equity_curve_starts_at_one_at_the_first_fill` | Both curves, point by point |

The first five are in [`test_simulation.py`](../../backend/tests/test_simulation.py), and the rest in [`test_backtest_metrics.py`](../../backend/tests/test_backtest_metrics.py).
