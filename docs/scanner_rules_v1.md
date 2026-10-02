# JARVIS Scanner Rules v1

## 1. Scope and separation

The first scanner version is an independent analytics module for NSE equities.
It reads market data, calculates indicators, evaluates scanner rules, and returns
ranked results.

It must not:

- place orders;
- generate executable trading signals;
- call the risk or execution engines;
- modify orders, positions, strategies, or portfolio data.

Connecting scanner results to strategies and execution is explicitly deferred to
a later version.

## 2. Market and instrument universe

The v1 universe contains active NSE cash-market ordinary equity shares.

The universe excludes:

- indices;
- futures and options;
- ETFs and mutual funds;
- preference shares, warrants, and bonds;
- suspended, delisted, or inactive instruments;
- instruments without enough valid historical data for the selected scanner.

The universe builder will map the market-data provider's instrument metadata to
these rules. The exact provider-field mapping belongs to Task 3.

## 3. Timeframe and evaluation time

- All v1 scanners use daily candles.
- Trading dates and display times use `Asia/Kolkata` (IST).
- Only completed daily candles may be evaluated.
- While the NSE session is open, the current incomplete candle is excluded.
- Every scan result includes a `data_as_of` trading date.
- A stock whose latest completed candle is older than the most recent expected
  NSE trading session is skipped and reported as stale.

This makes a scan reproducible: the same universe and completed-candle snapshot
must produce the same result.

## 4. Data-quality rules

A candle must have a unique trading date and valid OHLCV values. A stock is
skipped for a scanner when a required value is missing or invalid.

The scanner should use corporate-action-adjusted historical data when the data
provider supplies it. If adjusted data is unavailable, apparent split or bonus
share discontinuities must be flagged rather than silently ranked as breakouts.

Required history is based on the selected scanner:

| Scanner | Minimum completed history |
| --- | ---: |
| 52-week high/low | 253 sessions |
| Volume breakout | 21 sessions |
| SMA 20/50/200 | 200 sessions |
| RSI 14 | 15 sessions |

The first row needs 252 prior sessions plus the evaluation session. A full scan
may load at least 253 sessions once and reuse that dataset for all five scanners.

## 5. Indicator definitions

### Price

`price` means the closing price of the evaluation candle.

### Simple moving average

`SMA(n)` is the arithmetic mean of the most recent `n` closing prices, including
the evaluation candle.

### Average volume

`AVG_VOLUME_20` is the arithmetic mean of the 20 completed sessions immediately
before the evaluation candle. The evaluation candle's volume is excluded.

`VOLUME_RATIO = evaluation_volume / AVG_VOLUME_20`.

### RSI

`RSI_14` uses Wilder's 14-period smoothing over closing-price changes.

- If average loss is zero and average gain is positive, RSI is 100.
- If average gain is zero and average loss is positive, RSI is 0.
- If both are zero, RSI is 50.

### Prior 52-week range

For v1, 52 weeks means the 252 completed trading sessions immediately before the
evaluation candle.

- `PRIOR_52W_HIGH` is the maximum high in those 252 sessions.
- `PRIOR_52W_LOW` is the minimum low in those 252 sessions.

The evaluation candle is excluded from both reference ranges.

## 6. Preset scanner rules

### 6.1 52-week high breakout

A stock matches when:

```text
price > PRIOR_52W_HIGH
```

The comparison is strict. A close exactly equal to the prior high is not a new
breakout.

Primary ranking, highest first:

```text
BREAKOUT_PERCENT = ((price / PRIOR_52W_HIGH) - 1) * 100
```

### 6.2 52-week low

A stock matches when:

```text
price < PRIOR_52W_LOW
```

This preset therefore identifies a new 52-week closing low. A close exactly equal
to the prior low does not match.

Primary ranking, largest breakdown first:

```text
BREAKDOWN_PERCENT = ((PRIOR_52W_LOW / price) - 1) * 100
```

### 6.3 Volume breakout

A stock matches when:

```text
evaluation_volume >= 2.0 * AVG_VOLUME_20
```

The default multiplier is `2.0`. It will be configurable in the API and UI,
subject to validation, without changing the preset default.

Primary ranking: `VOLUME_RATIO`, highest first.

### 6.4 Price above SMA 20/50/200

The default trend preset requires all three conditions:

```text
price > SMA(20)
AND price > SMA(50)
AND price > SMA(200)
```

The comparison is strict. The result includes the percentage distance between
price and each moving average.

Primary ranking: percentage above SMA 200, highest first.

### 6.5 RSI-based scanner

The default RSI preset identifies bullish momentum:

```text
RSI_14 >= 55
```

The RSI comparator and threshold will be configurable so the same scanner can
support common views such as overbought (`RSI_14 >= 70`) and oversold
(`RSI_14 <= 30`). The default remains `RSI_14 >= 55`.

Primary ranking is highest RSI first for `>=`/`>` rules and lowest RSI first for
`<=`/`<` rules.

## 7. Custom-condition rules

The v1 custom scanner supports conditions over a controlled field list:

- `price`;
- `volume`;
- `avg_volume_20`;
- `volume_ratio`;
- `sma20`, `sma50`, and `sma200`;
- `rsi14`;
- `prior_52w_high` and `prior_52w_low`;
- `breakout_percent` and `breakdown_percent`.

Supported comparison operators are `>`, `>=`, `<`, `<=`, and `==`.

Conditions are combined with `AND` in v1. A right-hand operand may be a validated
number, another allowed field, or a validated numeric multiplier of an allowed
field. Arbitrary Python, SQL, or user-supplied executable expressions are not
permitted.

Example:

```text
price > sma50
AND sma50 > sma200
AND volume > 2 * avg_volume_20
AND rsi14 > 55
```

All conditions for one stock are evaluated against the same market-data snapshot.
If any required field cannot be calculated, the stock does not match and its
skip reason is recorded.

## 8. Result and ranking contract

Every matching row contains at least:

- instrument key;
- trading symbol;
- company name;
- exchange and segment;
- `data_as_of`;
- closing price;
- volume;
- scanner-specific indicator values;
- primary rank value.

Every scan summary contains:

- total eligible instruments;
- instruments evaluated;
- matches found;
- instruments skipped;
- grouped skip reasons;
- scan completion time in IST.

Results are ordered by the scanner's primary rank. Equal rank values are resolved
by trading symbol in ascending alphabetical order so pagination is stable.

Only matching stocks are returned by default. Diagnostic skip details may be
requested separately and should not be mixed into the ranked result rows.

## 9. Boundary examples

| Rule | Inputs | Expected result |
| --- | --- | --- |
| 52-week high | price 100, prior high 100 | No match |
| 52-week high | price 100.01, prior high 100 | Match |
| 52-week low | price 99, prior low 100 | Match |
| Volume breakout | volume 2,000,000, average 1,000,000 | Match |
| Trend | price is above SMA 20 and 50 but below SMA 200 | No match |
| RSI default | RSI 55 | Match |
| RSI default | RSI 54.99 | No match |

## 10. Task 1 acceptance criteria

Task 1 is complete when:

- all five presets have an exact formula and boundary behavior;
- timeframe, evaluation date, and lookback inclusion rules are unambiguous;
- eligible NSE instruments and data-quality behavior are defined;
- default ranking and deterministic tie-breaking are defined;
- the custom-condition grammar is constrained and safe;
- scanner evaluation remains independent of strategies and order execution.

## 11. Deferred from v1

- intraday scanners;
- fundamental-data filters;
- OR groups and nested custom-condition logic;
- alerts;
- saved scanner definitions;
- automatic signal generation;
- automatic order execution.
