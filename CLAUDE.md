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
- 🔬 "M1 candles + M5 structure + M1 micro cycles" (button under the timeframes, or `/structure XAUUSD mtf`):
  white background, grey M1 candles; each M5 phase is ONE light-blue box (range flat, channel slanted along its
  lines) with its top/bottom price written on it ("M5 range top 3995.44"); the last box runs to now. Inside,
  the M1 micro cycles are drawn in **black** with the fine version-1 detection (box per piece, dotted when "in
  doubt", lines, "M1 · …" labels, small swing markers).

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

## What was tried and the results (do not repeat blindly)
- Range trading backtest on gold M5 (buy when price reaches the range bottom, sell at the top, stop ½ range,
  target the other edge), 10 days: ≈ break-even (+0.65R, 20 trades). Losses were buys inside falling markets:
  in real time the bot saw short pauses in a bear channel as "ranges".
- Filters that did NOT help: direction of the move before the range; pin bar entry; key bar; 4× MACD (48,104,36)
  histogram; fixed 1:1 or 1:2 targets (all ≈ 0). Sells won only because gold fell in that period.
- Open ideas the user may come back to: (a) two-level structure — channels inside a big range; buy the range bottom
  only after the inner bear channel has ended; (b) confirmed range (2 touches each side, ≥ ~50 bars) and no re-entry
  on the same side after a stop. The user said they want to study first.

## Environment notes
- The cloud session cannot reach TradingView; real data is only on Render. Test with synthetic data and pictures
  (or digitise candles from the user's screenshots).
- Repo: bardiachatgpt-sudo/Goldbot. Env on Render: `BOT_TOKEN` (required), optional `STRUCTURE_PAIRS`.
