# Hypotheses (parked — use ONLY when the user says so)

Ideas drawn from backtest results, kept apart from the rules. Nothing here is coded. When the user asks for one,
first measure it (report lines, no rule change), then test as a rule against the current one.

## H1 · Win / loss sequence: "wait a little after a win" (17 Nov, from EURUSD M1)
Source: EURUSD M1 gap backtest, 16 Nov 16:30 → 17 Nov 13:33 Tehran (since NY open, M5 filter, legs 1–2,
numbering from the run that still had the setup 2 rule), 46 trades, 26 wins (57%).
Sequence by picture number (✅ win, ❌ loss):
```
 1 ❌  2 ✅  3 ❌  4 ❌  5 ✅  6 ✅  7 ❌  8 ✅  9 ❌ 10 ✅ 11 ✅ 12 ✅ 13 ✅ 14 ✅ 15 ❌ 16 ✅
17 ❌ 18 ✅ 19 ❌ 20 ✅ 21 ❌ 22 ✅ 23 ✅ 24 ❌ 25 ✅ 26 ✅ 27 ❌ 28 ✅ 29 ❌ 30 ❌ 31 ✅ 32 ❌
33 ❌ 34 ✅ 35 ✅ 36 ✅ 37 ❌ 38 ❌ 39 ✅ 40 ✅ 41 ❌ 42 ❌ 43 ✅ 44 ✅ 45 ❌ 46 ✅
```
| after … | cases | next trade won | win % |
|---|---|---|---|
| a win  | 25 | 11 | 44% |
| a loss | 20 | 15 | 75% |
| overall | 46 | 26 | 57% |

Three never came in a row as losses. 23 of 26 winners had M5 = TRADING RANGE.

Hypotheses:
- **H1a (user's):** after a win, wait before the next setup — in an M5 range a 1:1 win has used the room to the
  range edge, so the next setup right after has little room.
- **H1b:** after a loss, the next setup is stronger — the stopped gap was a failed breakout of the range; the next
  (often opposite) setup catches the move back into the range (Brooks: most range breakouts fail).
- **H1c:** what matters is time since the previous exit, not win/loss (e.g. #41–#42 both lost 8 min apart;
  #34–#36 all won with gaps between them).

Caution: one day, one pair, 46 trades — 44% vs 75% can be chance (plain alternation gives the same picture).
Losers' side and M5 state were not in the data, so same-side vs opposite could not be checked.

How to use when asked: add report lines only (win % after a win / after a loss; same side vs opposite to the
previous trade; time since previous exit < 5 / 5–15 / > 15 min), check on gold, USDJPY, EURUSD over several days and
on the 6-month broker CSVs. Only if it repeats, test a rule ("skip / wait N minutes after a win") against the
current one.

## H2 · USDJPY behaviour: why gap trades lose / win (17 Nov, from the user's broker data) — **USDJPY only**
Applies to **USDJPY** (yen) behaviour; not checked on gold or EURUSD — do not assume it holds there.
Source: `data/USDJPY_M1_…csv.gz`, Thu 15 Jan 2026 (server day), current bot rules (M5 filter with full 500-bar M5
history from 2 Jan, legs 1–2, no Off session, fixed 1:1). 30 trades, 17 wins, +4R (day numbers 1–30 = backtest
#304–#333). Tokyo 12/18 +6R, London 0/2, London+NY 2/6, NY 3/4. Spread 0.1 pip almost all day.

Plain numbers did NOT separate winners from losers that day: stop 5.5 vs 5.0 pips, place in the M5 box 77 vs 80
(0 = bottom, 100 = top), entry candle 4/5/6+ and minutes since the previous trade about the same. The M5 box was
45–65 pips tall vs stops of 2–5 pips, so the M5 filter rejected almost nothing (the 1:1 target was always inside).
What differed was the **M1 context** (read from pictures):

Losses:
- **H2a · tight M1 range:** gaps inside a small M1 range between nearby highs/lows are small breakouts that fail;
  buys and sells alternate and all lose (#9–#12 07:00–07:40, #20–#23 15:40–16:50 Tehran).
- **H2b · selling the low right after a climax:** a sell gap at the bottom right after a sharp spike down → the
  market reverses (#6 05:11, #19 12:57 after the big 12:44 bar; the afternoon then turned into a bull channel).
- **H2c · against the M1 trend:** sells during the afternoon M1 bull channel 158.35 → 158.88 lost (#21, #22, #24).
- **H2d · selling before the range top is reached:** #13 sold under the range top (158.63); price tagged the top,
  stopped it, and #14 then sold the top and won.

Wins:
- **H2e · sell at the top of the M5 range** (price tagged the edge and turned): #8, #14, #15, #17.
- **H2f · big swings inside the Tokyo range** with room for 1:1 (20–30-pip swings): #2–#5, #7.
- **H2g · with the M5 channel:** in the late M5 bear channel, sells won 4 of 5 (#26, #28–#30).

One day only. To use when the user asks: check the same patterns day by day on USDJPY; candidates to measure
later are an "M1 range width / recent swing size" measure (H2a, H2f), "bars since a climactic spike" (H2b), M1 trend
direction (H2c), and distance to the M5 edge in pips rather than as % of a huge box (H2d, H2e).
Pictures were made in the session scratchpad (overview: M1 candles + M5 box edges at each moment + numbered trades).

### H2 · day 2 — Fri 16 Jan 2026 (backtest #334–#367): 34 trades, 16 wins, −2R
Tokyo 9/13 +5R · Tokyo+London 1/4 −2R · London 2/7 −3R · London+NY 3/6 0R · NY 1/4 −2R. Plain numbers again did not
separate wins and losses (stop 4.7 vs 4.4 pips; entry candle not consistent with day 1).
- **H2c against the M1 trend — repeated strongly:** #4 (buy in the 04:30–05:00 fall), #8 and #11 (sells in the
  07:30–10:15 M1 bull channel), #13 (buy in the 10:20–11:10 fall), #25 and #26 (buys in the 16:00–18:00 fall): all 6
  lost. With-trend gaps in the same legs won (#9, #10, #12 buys in the bull channel).
- **H2a tight M1 range — repeated:** 11:00–14:30 choppy range 158.00–158.25 → #14–#22: 2 wins, 7 losses.
- **H2b climax — repeated, and its mirror:** fading a climax won: #3 sell after the 04:25 spike up, #5 buy after the
  06:10 spike down to 157.96, #27 buy after the 18:30 low, #28 sell after the 19:10 spike up. Trading in the climax
  direction at the extreme lost: #30 sell at the 20:15 low, #32–#33 buys late in the 21:30–22:30 rally.
- **New · H2h Tokyo vs London:** Tokyo was best both days (12/18, then 9/13); the London open part was weak both
  days (day 1 London + London/NY 2/8; day 2 Tokyo+London + London 3/11).

### H2 · day 3 — Mon 19 Jan 2026 (backtest #368–#406): 39 trades, 17 wins, −5R
Tokyo 4/12 −4R · Tokyo+London 2/2 +2R · London 5/9 +1R · London+NY 4/12 −4R · NY 2/4 0R.
- **H2c against the M1 trend — repeated a third time, strongest pattern:** #2 (buy in the 04:00–05:00 fall),
  #3–#4 (sells in the 05:00–06:15 rally), #16–#17 (buys in the 13:20–14:20 fall), #30–#34 (five sells in the
  18:50–20:00 rally): 10 losses out of 10.
- **H2a tight M1 range — repeated:** 06:30–08:30 chop 157.80–157.92 (#6–#8 lost), 09:30–10:20 (#10–#11 lost),
  17:00–18:10 chop 157.87–157.95 (#26–#28 lost).
- **H2b fade the climax — repeated:** #1 sell after the 03:45 spike up won; #18 and #29 buys at the bottom after a
  fall won.
- **H2h Tokyo best — NOT repeated:** Tokyo 4/12 this day (choppy ranges + against-trend gaps). Treat as unproven.
- Stops ≤ 2 pips: 4 wins / 10 losses this day, 29% over the 3 days — but over all Jan 15 → Jun 17 trades the
  ≤ 2-pip bucket wins 47%, same as every other bucket, so stop size alone is NOT the reason.

Summary after 3 days: the two patterns that repeated every day are **H2c (gap against the M1 trend loses)** and
**H2a (gaps inside a tight M1 range lose)**, plus **H2b (fading a climax wins)**. Session effects did not hold.
