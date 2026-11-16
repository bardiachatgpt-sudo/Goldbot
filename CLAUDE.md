# Goldbot · notes for the next session

Read this first. It replaces the long conversation that built this bot.

## The user and how to work with them
- Writes in Persian (Farsi); answer in Persian. Trades gold (XAUUSD) mainly, on M5, in the Al Brooks price-action way.
- Often wants to **discuss before coding**. When they say "فعلاً کد نزن" / "بحث کنیم" / "مطالعه کنم", do not code.
- **Never deploy without an explicit "دیپلوی" / "deploy".** Build, run the tests, commit and push to the work branch, then
  ask. Deploy = fast-forward `main` to the work branch; Render auto-deploys from `main` (takes 3–5 min).
- When trying a new idea, keep the live version untouched and show pictures first; the user judges by eye.
- Explain results in plain Persian with small tables; be honest when an idea did not work.

## What the bot is now (structure only)
Telegram bot that only draws market structure. No alerts, no channel posts, no trades, no backtests (all removed
on purpose; they are in git history before commit 678dacb if ever needed).
- 📐 Structure → pair (XAUUSD, 7 majors, US30 = Dow Jones) → timeframe (M1, M5, M15, M30, H1, H4, D1) →
  two pictures: last 500 candles with the structure, and a zoom on the last two structures.
- 🔬 "M1 candles + M5 structure + gap setup" (button under the timeframes, or `/structure XAUUSD mtf`):
  white background, grey M1 candles (last ≤ 480); each M5 phase is ONE light-blue box (range flat, channel slanted
  along its lines) with its top/bottom price written on it ("M5 range top 3995.44"); the last box runs to now.
  On the M1 candles: the gap setup (bot/gap.py) — gap boxes, entry, stop, 1:1 target, exit. The M1 micro cycles
  (fine v1 detection, black) are still in the code (`mtf.render(..., layer="micro")`) but the user asked to hide
  them for now.

## Files
- `bot/structure3.py` — structure v3 (used for every timeframe picture and for the M5 layer).
- `bot/structure.py` — structure v1, fine detection; used only for the M1 micro cycles.
- `bot/mtf.py` — the M1 + M5 picture.
- `bot/telegram_bot.py` — buttons/commands; polling survives Telegram 409 during deploys (that crash used to fail
  Render deploys — keep the retry loop).
- `bot/data.py` — TradingView websocket candles. `bot/config.py` — symbols, timeframes.
- Tests: `python -m unittest discover -s tests`.

## Structure rules (v3, from the user's own drawn charts — agreed with them)
- Closes only (like a line chart); wicks do not make swings. A swing = a pullback of at least 10% of the chart height.
- Every bar is in one of three states: spike (fast straight leg), channel (higher highs + higher lows, or the
  reverse), trading range (everything else; may be a triangle). "If in doubt, it's a range."
- A range lasts until a breakout that does not come back; a poke that comes back (even a fast V) stays in the range
  and stretches its edges. A channel fully taken back by the following range was only a range leg.
- Range edges at the farthest closes (flat, or sloped only for a triangle); channel = trend line through two swings
  + parallel line. The last phase is provisional.
- v1 (M1 layer): swings on highs/lows with a 1.5 average-bar reversal; more, smaller pieces; "range (in doubt)".

## Trade setups
- All earlier setups (pin bar, key bar, range edges, MACD, Always In…) were dropped by the user. Do not bring them
  back. The structures above stay.
- The user is now describing new setups one by one. First one: the **gap** (not coded yet; rules agreed so far):
  - Sell: candle 1 low > candle 3 high, and candle 2's body overlaps that gap (candle 2 is usually red; overlap is
    enough). Buy: the mirror (candle 1 high < candle 3 low, candle 2 body overlaps).
  - Following starts as soon as the gap exists (close of candle 3): compare each candle's high with the previous
    candle's high (buy: lows).
  - Entry (sell): only when price trades strictly ABOVE the previous candle's high, by at least one pipette;
    entry price = previous high + 1 pipette (gold 0.01, 5-digit FX 0.00001, JPY 0.001, US30 0.1). Merely touching
    the previous high is not an entry. (Buy: previous low − 1 pipette.)
  - Stop: just beyond candle 1 (sell: above its high; buy: below its low). Target 1:1.
  - Runs on M1, drawn on the M1 + M5 picture. No invalidation for now (user's choice). One trade at a time; a new
    gap before entry replaces the waiting one. No spread. Stop = candle 1 + 1 pipette.
  - M5 box edges are meant as targets (user chose "b"), but the user said to leave the edges out for now — no edge
    rule is coded. Gap backtest: one tap (🧪 Gap backtest / under each pair / `/backtest XAUUSD`) runs bot/gap.py on
    up to 5000 M1 candles (bot/gap_backtest.py): trades, wins, R, buys vs sells, $1,000 at 1% and 2%, equity chart.

## Environment notes
- The cloud session cannot reach TradingView; real data is only on Render. Test with synthetic data and pictures
  (or digitise candles from the user's screenshots).
- Repo: bardiachatgpt-sudo/Goldbot. Env on Render: `BOT_TOKEN` (required), optional `STRUCTURE_PAIRS`.
