# Goldbot · notes for the next session

Read this first. It replaces the long conversation that built this bot. **Keep it up to date after every change**
(the user asked for this so a new chat can continue without losing anything).

## The user and how to work with them
- Writes in Persian (Farsi); answer in Persian, plainly, with small tables. Trades gold (XAUUSD) mainly, the Al Brooks
  price-action way. Judges ideas by eye from pictures; sends screenshots of the bot's pictures with notes.
- Often wants to **discuss before coding**. When they say "فعلاً کاری نکن" / "کد نزن" / "بحث کنیم" / "مطالعه کنم", do not code.
- **Never deploy without an explicit "دیپلوی" / "deploy".** Build, run the tests, commit and push to the work branch
  `ccr-e78c1662-kly1ee` (the session's branch; earlier `ccr-1ceb0688-gokag6`), then ask. Deploy = fast-forward `main` to the work branch
  (`git fetch --depth=50 origin main && git merge-base --is-ancestor origin/main HEAD && git push origin <branch>:main`);
  Render auto-deploys from `main` (3–5 min). A few Telegram 409 lines during a deploy are normal.
- Be honest about results (small samples, no spread, look-ahead). Ideas the user rejected stay rejected.
- **Data files the user sends (CSV etc.): just keep them. Do NOT run a backtest or analysis until the user asks**
  (17 Nov: "I don't want a backtest now, just keep these until I tell you").

## What the bot does now
Telegram bot (`/start` shows a bottom bar: 📐 Structure · 🧪 Gap backtest · 🌍 All pairs). No alerts, no channel
posts, no live trading. Pairs on the buttons: **only XAUUSD, USDJPY, EURUSD** (user, 17 Nov: "only three pairs, not
crowded"; `config.STRUCTURE_PAIRS` default). The others (GBPUSD, USDCHF, USDCAD, AUDUSD, NZDUSD, US30) stay in
`config.ALL_SYMBOLS` and can come back by adding them to that default or to `STRUCTURE_PAIRS` on Render (if that env
var is set on Render it overrides the default — it must then be changed there too).
- **📐 Structure** → pair → timeframe (M1, M5, M15, M30, H1, H4, D1) → two pictures: last 500 candles with the
  structure, and a zoom on the last two structures. Under the timeframes:
  - **🔬 M1 candles + M5 structure + gap setup** (`/structure XAUUSD mtf`, `bot/mtf.py`): white background, grey M1
    candles (last ≤ 480). Each M5 phase = ONE light-blue box (range flat, channel slanted along its lines) with its
    top/bottom price; the last box runs to now. On the M1 candles: gap boxes, entries (L1/L2 label), stop, 1:1
    target, exits; skipped gaps dotted. (M1 micro cycles with the v1 detection still exist: `layer="micro"`, hidden.)
  - **🧪 Backtest the gap setup** → M1 / M5 / M15.
- **Backtest period** (asked after the timeframe, and for 🌍): 🇯🇵 since the last Tokyo open · 🇬🇧 since the last
  London open · 🇺🇸 since the last New York open — nothing else (the user removed "last 72 hours") (`config.PERIODS`,
  `config.last_session_start`: local opens Tokyo 09:00, London 08:00, NY 08:00, weekdays, DST-aware, "now" = last
  candle). This replaced the old "3 days" (which wrongly counted a Sunday with a few candles as a day).
- **🧪 Gap backtest** (`/backtest XAUUSD 1 L`; codes T/L/N) → pair → M1, M5 or M15 → period (`bot/gap_backtest.py`):
  equity chart; report (trades, wins, R, sells vs buys, Leg 1 vs Leg 2+, by session, avg stop, skipped counts,
  comparisons "without the M5 filter" and "with all legs", $1,000 at 1% and 2%, latest trades); then a full list of
  stopped-out trades `#num · time · SELL/BUY · L<leg> · session · gap hh:mm–hh:mm · entry · SL · TP · exit · M5: state`
  (#num = picture number); on M1 the zoomed loser pictures (`bot/gap_pictures.py`), 5 at a time with "📷 Next 5"
  (kept in memory per chat; lost on restart). Every trade picture has a table under the chart: each candle from 3
  before candle 1 to the entry with exact H / L (Tehran time), the price needed for entry (orange tick on the chart)
  and why it was not an entry (pipettes short, gap candle 1/2/3, chained gap, another trade open, skipped M5/leg).
  Comes from `t["watch"]` filled in `gap.trades`. On M1 a "🏆 Winning trades: list + pictures" button sends the same
  list for the winners (same numbering as the report) and their pictures, 5 at a time (callbacks sxwl / sxw:n;
  losers sxl:n).
- **🌍 All pairs** (also in the backtest pair menu) → period → gap setup on M1 for every pair, with and
  without the M5 filter; one summary table per variant: trades, win %, R, and a separate $1,000 account per pair at
  2% risk (final $ and growth %), totals, best/worst pair.

## The gap setup (bot/gap.py) — rules agreed with the user
- Gap = exactly 3 candles. Sell: candle 1 low > candle 3 high, candle 2's body overlaps that space, and **all three
  candles bearish** (buy: mirror, all bullish). Same-direction gaps that keep forming right behind it (2-3-4, 3-4-5 …)
  are ignored: candle 1, the box and the stop stay those of the FIRST gap. A separate or opposite gap replaces a
  waiting one. No invalidation (user's choice).
- From the close of candle 3, compare each candle's high with the previous candle's high (buy: lows). Entry when
  price trades strictly beyond it by ≥ 1 pipette: sell at previous high + 1 pipette (gold 0.01, FX 0.00001,
  JPY 0.001, US30 0.1). Touching is not an entry.
- Levels (entry, SL, TP) are rounded to 8 decimals (`gap._r`): before this, float error (1.09977 − 0.00001 =
  1.0997599999…) made ~30% of exactly-1-pipette entries/stops miss (EURUSD #10 late entry, 17 Nov fix).
- Stop: 1 pipette beyond candle 1. Target 1:1. One trade at a time. No spread in any backtest yet.
- **M5 filter:** no trade if the 1:1 target lies outside the M5 structure box of that moment (500 M5 candles closed
  then) — `gap.m5_target_filter`.
- **Leg filter: only Leg 1 and Leg 2** (`gap.MAX_LEG = 2`). For a sell, the move starts at the highest high since the
  last buy gap; Leg 1 = no earlier sell gap in this move, Leg 2 = one before (chained gaps count once).
- **Session** of each trade (`config.session_of`, local hours, DST-aware): Tokyo 9–18 Tokyo, London 8–17 London,
  NY 8–17 New York; overlaps joined ("London+NY"); outside all = "Off".
- **No trades in the "Off" session** (outside Tokyo/London/NY: spread is high; the user does not trade it — 17 Nov).
  Bot rule: `gap.trades(session_ok=gap.in_session(times))` — an entry whose candle is Off is skipped (reason "off",
  pending gap dropped like the other skips); used in the backtest (all variants), the all-pairs table and the
  M1+M5 picture. Report line "🚫 Not taken (Off session …)". Also leave Off out of broker-data analyses.
- **Weekday** of each trade (Tehran time, e.g. "Mon 16 Nov 02:48") in every list, caption and picture title; the
  report has "📅 By weekday (Tehran)". The user wants session / weekday / leg per trade for later data analysis.

## Results so far (gold M1, no spread)
- 6 days: 393 trades, 52%, +13R (before same-colour/M5/leg rules). With ~0.3 spread (avg stop ~$3) ≈ −20R.
- 16–17 Nov (~30 h, same-colour + M5 filter): 39 trades, 46%, −3R; without M5 filter 47 trades, 51%, +1R; Leg 1 50% 0R,
  Leg 2+ 38% −3R (L3+ ≈ 3 losses, 0–2 wins). Losers: stops < $2 (7 of 21), stops just beyond the M5 edge (5),
  sells in the lower half / buys in the upper half of an M5 range (7), late legs (3).

- 16 Nov 16:30 → 17 Nov ~13:35 Tehran (since NY open, ~21 h, M5 filter, legs 1–2, with the setup 2 rule that was later removed), from the live bot:
  | pair | trades | win | R | old rule (fixed 1:1) | Leg 1 | Leg 2 | avg stop |
  | XAUUSD | 41 | 51% | +0.3 | 40, +0.0 | −3R | +3R | $3.38 |
  | USDJPY | 37 | 57% | +5.0 | 37, +5.0 | +9R | −4R | 4.3 pips |
  | EURUSD | 46 | 57% | +6.6 | 44, +8.0 | +7R | 0R | 2.4 pips |
  Setup 2 happened 1 / 1 / 3 times (+0.26R; −1R; +1.6R). Leg and session effects flip between pairs → no rule
  change from one day. Spread kills it on FX: EURUSD stop 2.4 pips (1 pip spread ≈ 0.4R per trade), USDJPY 4.3 pips;
  gold ≈ 0.07R per trade. Waiting for the 6-month broker CSVs.

- **EURUSD broker CSV (user's MT5 export, 17 Nov):** M1, 2026-01-01 → 06-17 plus 16–17 Nov (Jul–Oct missing in the
  file), server time = New York + 7 h (GMT+2/+3), tab-separated `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL>
  <VOL> <SPREAD>` (spread in points; 0 in 75% of bars → raw/ECN account, commission not in the file). Current rules
  (M5 filter from resampled M1, legs 1–2, fixed 1:1): **4,269 trades, 46.3%, −313R before any cost**. Every month
  negative (Jan −90, Feb −92, Mar −60, Apr −21, May −11, Jun −43); Leg 1 −218 / Leg 2 −95; every session negative
  except Off (+7); sells −182 / buys −131; every stop-size bucket negative. Without M5 filter −258R (4,596), all legs
  −371R. Spread at entry ≈ −519R more (0.12R/trade); avg stop 3.1 pips (median 2.5). 16–17 Nov part matches the live
  bot (24 trades, +4R). → The one-day +6.6R was luck; the setup has no edge on EURUSD M1 as defined.
  Scripts were in the session scratchpad (load: tz_localize(server − 7 h, America/New_York) → UTC; M5 = resample).

## Ideas for later (do NOT code until the user asks)
- **`HYPOTHESES.md`** — parked hypotheses, kept apart at the user's request ("keep it separately until I say").
  H1: win/loss sequence on EURUSD (after a win next trade 44%, after a loss 75%) → "wait after a win?". Use only
  when the user asks.
- Broker data (planned, user will send later): ~6 months of M1 CSV per pair exported from their broker
  (MT5 Symbols → Bars → Export preferred; keep the Spread column but do not use it yet). Needed from the user: broker
  server time zone (GMT+2/+3), broker symbol names, digits. Plan: gold first to settle the format; build M5/M15 from
  M1; run the gap backtest here in the cloud session (no TradingView needed); report month by month and first vs
  second 3 months; optionally keep compressed copies in `data/` (repo should then be private).
- **Setup 2 during an open trade — TRIED AND REMOVED (user, 17 Nov):** rule was: one position; a same-direction
  Leg 2 gap during a Leg 1 trade, once its entry triggered, moved the TP to setup 2's TP, and after half of setup 2's
  profit moved the SL to 1 pipette beyond entry2. Coded in 35b3a7f, deployed, one day on 3 pairs (table above), then
  the user said "go back to the previous state" → reverted in 244ee0d (fixed 1:1 TP, gaps during an open trade are
  ignored again). Do not bring it back unless the user asks; the code is in git history.
- Spread: the user will handle it later — do NOT add it now. Minimum stop size (~$2 gold, or ATR-based); ATR(14) at entry in the report.
- In an M5 range: sell only in the upper half, buy only in the lower half; stop a little beyond the M5 edge.
- Entry on candle 4 tends to be best (report by entry candle 4/5/6+).
- The user does NOT want a sell-stop entry. Wanted later: a LIVE simulator following bid/ask ticks — after price trades
  beyond the previous candle, follow it and enter the moment it turns (forward paper trading; check TradingView
  bid/ask for gold; define the "turn"; Render must stay on). A "floating" entry offset (ATR / wick / step-down) was
  discussed but parked.

## Structure rules (v3, `bot/structure3.py`, from the user's own drawn charts)
- Closes only (line chart); a swing = a pullback ≥ 10% of the chart height.
- Every bar is a spike (fast straight leg), a channel (HH+HL or LH+LL) or a trading range (everything else; may be a
  triangle). A range lasts until a breakout that does not come back; a channel fully taken back by the next range was
  a range leg. If the last close breaks the last swing against a channel, the final leg gets its own provisional label.
- Chart start (17 Nov fix, GBPUSD M1 was one expanding range): if the first real leg (ignoring a tiny first wiggle)
  is ≥ 30% of the chart height, it is a channel/spike, not a range. A pullback taking back ≥ 60% of the channel
  move ends it. A leg that STARTS with a sharp spike and then ranges is split: SPIKE then RANGE (`_spike_head`).
- Price axis on every picture shows full prices (matplotlib offset off in `bot/__init__.py`).
- `bot/structure.py` = v1 fine detection (swings on highs/lows, 1.5 avg-bar reversal), only for the hidden M1 layer.

## Files
- `bot/telegram_bot.py` — buttons, commands, backtest flows, all-pairs scan; polling loop survives Telegram 409.
- `bot/gap.py` (setup), `bot/gap_backtest.py` (backtest, reports, all-pairs table), `bot/gap_pictures.py` (loser
  pictures), `bot/mtf.py` (M1 + M5 picture), `bot/structure3.py`, `bot/structure.py`, `bot/data.py` (TradingView
  candles), `bot/config.py` (symbols, timeframes, sessions), `bot/main.py`.
- `HYPOTHESES.md` — parked hypotheses (not rules, not coded).
- `data/` — the user's broker CSVs (gzip), list in `data/README.md`. Keep every file the user sends there; do not
  analyse until asked. The repo should be private (user confirmed, 17 Nov).
- Tests: `python -m unittest discover -s tests` (all in `tests/test_structure.py`).
- Old features (alerts, pin-bar/range setups, MACD, range backtest) were removed on purpose; in git history before 678dacb.

## Environment notes
- The cloud session cannot reach TradingView; real data is only on Render. Test with synthetic data and pictures.
- Repo: bardiachatgpt-sudo/Goldbot. Env on Render: `BOT_TOKEN` (required), optional `STRUCTURE_PAIRS`.
