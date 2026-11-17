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
  - Sell: candle 1 low > candle 3 high, and candle 2's body overlaps that gap. **All three gap candles must be the
    same colour** (sell: all three bearish; buy: all three bullish) — the user called this "very, very important".
    Buy: the mirror (candle 1 high < candle 3 low, candle 2 body overlaps).
  - Following starts as soon as the gap exists (close of candle 3): compare each candle's high with the previous
    candle's high (buy: lows).
  - Entry (sell): only when price trades strictly ABOVE the previous candle's high, by at least one pipette;
    entry price = previous high + 1 pipette (gold 0.01, 5-digit FX 0.00001, JPY 0.001, US30 0.1). Merely touching
    the previous high is not an entry. (Buy: previous low − 1 pipette.)
  - Stop: just beyond candle 1 (sell: above its high; buy: below its low). Target 1:1.
  - Runs on M1, drawn on the M1 + M5 picture. No invalidation for now (user's choice). One trade at a time. No spread. Stop = candle 1 + 1 pipette.
  - M5 filter: if the 1:1 target lies outside the current M5 structure box (sell: below the box bottom; buy: above
    the box top), the trade is not taken (the user saw those mostly fail). The box comes from the 500 M5 candles
    closed at that moment (gap.m5_target_filter). Used on the M1 + M5 picture (skipped gaps drawn dotted) and in the
    M1/M5 backtests, which also report the same data without the filter.
  - Leg label (user: "we usually take the first leg"): each trade is labelled Leg 1 / Leg 2 / … — for a sell, the
    move starts at the highest high since the last buy gap; Leg 1 = no earlier sell gap in this move, Leg 2 = one
    before, etc. (gap.gap_heads / gap.leg_number; chained gaps count once). Shown in pictures, captions, the trade
    list and a Leg 1 vs Leg 2+ line in the report. Label only — no filter yet.
  - Idea to discuss later (do NOT code until the user brings it up): the user notices the best setups, when inside
    the structure, usually enter on candle 4 (right after the gap). Possible later: report results by entry candle
    (4 / 5 / 6+) and an "entry on candle 4 only" comparison; maybe require the entry inside the M5 box.
  - A gap is always exactly 3 candles. Same-direction gaps that keep forming right behind it (2-3-4, 3-4-5 … each
    overlapping the previous one) are ignored: candle 1, the gap box and the stop stay those of the FIRST gap, and
    following starts after its candle 3 (user's screenshots of trades #10 and #8). A separate or opposite gap
    replaces the waiting one.
  - First real result, gold M1, 6 days: 393 trades, 52% wins, +13R without spread; with a ~0.3 spread (avg stop
    ~3) it would be roughly −20R. Sells won because gold fell that week. Suggested next: add spread, then try the
    M5 direction filter, the M5 edges as targets, or a minimum gap/stop size.

## Environment notes
- The cloud session cannot reach TradingView; real data is only on Render. Test with synthetic data and pictures
  (or digitise candles from the user's screenshots).
- Repo: bardiachatgpt-sudo/Goldbot. Env on Render: `BOT_TOKEN` (required), optional `STRUCTURE_PAIRS`.
