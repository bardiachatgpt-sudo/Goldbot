# Goldbot · notes for the next session

Read this first. It replaces the long conversation that built this bot. **Keep it up to date after every change**
(the user asked for this so a new chat can continue without losing anything).

## The user and how to work with them
- Writes in Persian (Farsi); answer in Persian, plainly, with small tables. Trades gold (XAUUSD) mainly, the Al Brooks
  price-action way. Judges ideas by eye from pictures; sends screenshots of the bot's pictures with notes.
- Often wants to **discuss before coding**. When they say "فعلاً کاری نکن" / "کد نزن" / "بحث کنیم" / "مطالعه کنم", do not code.
- **Never deploy without an explicit "دیپلوی" / "deploy".** Build, run the tests, commit and push to the work branch
  `ccr-1ceb0688-gokag6`, then ask. Deploy = fast-forward `main` to the work branch
  (`git fetch --depth=50 origin main && git merge-base --is-ancestor origin/main HEAD && git push origin <branch>:main`);
  Render auto-deploys from `main` (3–5 min). A few Telegram 409 lines during a deploy are normal.
- Be honest about results (small samples, no spread, look-ahead). Ideas the user rejected stay rejected.

## What the bot does now
Telegram bot (`/start` shows a bottom bar: 📐 Structure · 🧪 Gap backtest · 🌍 All pairs · 24h). No alerts, no channel
posts, no live trading. Pairs: XAUUSD, EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, US30 (Dow Jones).
- **📐 Structure** → pair → timeframe (M1, M5, M15, M30, H1, H4, D1) → two pictures: last 500 candles with the
  structure, and a zoom on the last two structures. Under the timeframes:
  - **🔬 M1 candles + M5 structure + gap setup** (`/structure XAUUSD mtf`, `bot/mtf.py`): white background, grey M1
    candles (last ≤ 480). Each M5 phase = ONE light-blue box (range flat, channel slanted along its lines) with its
    top/bottom price; the last box runs to now. On the M1 candles: gap boxes, entries (L1/L2 label), stop, 1:1
    target, exits; skipped gaps dotted. (M1 micro cycles with the v1 detection still exist: `layer="micro"`, hidden.)
  - **🧪 Backtest the gap setup** → M1 / M5 / M15.
- **🧪 Gap backtest** (`/backtest XAUUSD 5`) → pair → M1, M5 or M15 → last 3 trading days (`bot/gap_backtest.py`):
  equity chart; report (trades, wins, R, sells vs buys, Leg 1 vs Leg 2+, by session, avg stop, skipped counts,
  comparisons "without the M5 filter" and "with all legs", $1,000 at 1% and 2%, latest trades); then a full list of
  stopped-out trades `#num · time · SELL/BUY · L<leg> · session · gap hh:mm–hh:mm · entry · SL · TP · exit · M5: state`
  (#num = picture number); on M1 the zoomed loser pictures (`bot/gap_pictures.py`), 5 at a time with "📷 Next 5"
  (kept in memory per chat; lost on restart). On M1 a "🏆 Winning trades: list + pictures" button sends the same
  list for the winners (same numbering as the report) and their pictures, 5 at a time (callbacks sxwl / sxw:n;
  losers sxl:n).
- **🌍 All pairs · 24h** (also in the backtest pair menu): gap setup on M1, last 1440 M1 candles, every pair, with and
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
- Stop: 1 pipette beyond candle 1. Target 1:1. One trade at a time. No spread in any backtest yet.
- **M5 filter:** no trade if the 1:1 target lies outside the M5 structure box of that moment (500 M5 candles closed
  then) — `gap.m5_target_filter`.
- **Leg filter: only Leg 1 and Leg 2** (`gap.MAX_LEG = 2`). For a sell, the move starts at the highest high since the
  last buy gap; Leg 1 = no earlier sell gap in this move, Leg 2 = one before (chained gaps count once).
- **Session** of each trade (`config.session_of`, local hours, DST-aware): Tokyo 9–18 Tokyo, London 8–17 London,
  NY 8–17 New York; overlaps joined ("London+NY"); outside all = "Off".

## Results so far (gold M1, no spread)
- 6 days: 393 trades, 52%, +13R (before same-colour/M5/leg rules). With ~0.3 spread (avg stop ~$3) ≈ −20R.
- 16–17 Nov (~30 h, same-colour + M5 filter): 39 trades, 46%, −3R; without M5 filter 47 trades, 51%, +1R; Leg 1 50% 0R,
  Leg 2+ 38% −3R (L3+ ≈ 3 losses, 0–2 wins). Losers: stops < $2 (7 of 21), stops just beyond the M5 edge (5),
  sells in the lower half / buys in the upper half of an M5 range (7), late legs (3).

## Ideas for later (do NOT code until the user asks)
- Fix "3 days" counting a Sunday with few candles (count only days with several hours of data).
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
- `bot/structure.py` = v1 fine detection (swings on highs/lows, 1.5 avg-bar reversal), only for the hidden M1 layer.

## Files
- `bot/telegram_bot.py` — buttons, commands, backtest flows, all-pairs scan; polling loop survives Telegram 409.
- `bot/gap.py` (setup), `bot/gap_backtest.py` (backtest, reports, all-pairs table), `bot/gap_pictures.py` (loser
  pictures), `bot/mtf.py` (M1 + M5 picture), `bot/structure3.py`, `bot/structure.py`, `bot/data.py` (TradingView
  candles), `bot/config.py` (symbols, timeframes, sessions), `bot/main.py`.
- Tests: `python -m unittest discover -s tests` (all in `tests/test_structure.py`).
- Old features (alerts, pin-bar/range setups, MACD, range backtest) were removed on purpose; in git history before 678dacb.

## Environment notes
- The cloud session cannot reach TradingView; real data is only on Render. Test with synthetic data and pictures.
- Repo: bardiachatgpt-sudo/Goldbot. Env on Render: `BOT_TOKEN` (required), optional `STRUCTURE_PAIRS`.
