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

### H2 · day 4 — Tue 20 Jan 2026 (backtest #407–#438): 32 trades, 17 wins, +2R
Tokyo 10/16 +4R · London 2/3 +1R · London+NY 4/8 0R · NY 1/5 −3R (late NY spread 0.7–0.9 pip).
- **H2c against the M1 trend — repeated (4th day):** #5 (buy as the 05:30 fall began), #15–#16 (buys in the
  10:50–11:30 fall), #24 (sell in the 17:50–18:40 rally), #29 (sell in the 22:20–23:30 rally): all lost. With-trend
  gaps in the 08:00–09:45 rally (#9, #11, #12) and the 15:10–15:50 fall (#18) won.
- **H2b climax — repeated:** fading won: #3–#4 buys after the 04:25–04:40 drop, #13–#14 sells after the 10:00–10:40
  spike up, #27 sell after the 20:05 spike. Trading in the climax direction at the extreme lost: #2 sell at the
  04:41 low, #25 buy at the 18:59 top, #30 buy at the 23:45 top. One counter-example: #17 buy at 13:25 after the
  12:00–13:10 fall lost (price made one more low first).
- **H2a tight range — repeated:** #7–#8 in the 07:00–08:00 chop; #22–#23 sells at the bottom of the 16:20–17:10
  range (157.75–157.92) lost.
- Tokyo good again (10/16): Tokyo best on 3 of 4 days. Late NY (after ~22:30 Tehran) weak: 0/4 this day.

Summary after 4 days: **H2c** held every day with almost no exception; **H2b** (fade the climax / don't trade in its
direction at the extreme) held every day with one exception; **H2a** held every day.

### H2 · days 5–7 — Wed 21, Thu 22, Fri 23 Jan 2026 (backtest #439–#543)
| day | trades | wins | R | Tokyo | London part | NY part |
|---|---|---|---|---|---|---|
| Wed 21 | 35 | 19 | +3 | 10/13 +7 | T+L 0/3, L 3/4 | L+NY 1/7 −5, NY 5/8 +2 |
| Thu 22 | 32 | 14 | −4 | 8/17 −1 | T+L 1/3, L 1/3 | L+NY 4/7 +1, NY 0/2 |
| Fri 23 | 38 | 18 | −2 | 7/13 +1 | T+L 1/2, L 7/8 +6 | L+NY 3/10 −4, NY 0/5 −5 |
- **H2c against the M1 trend — held again on all three days, the strongest pattern:** Wed: #8 (sell in the
  06:35–07:00 rally), #11–#12 and #14 (buys in the 09:40–11:40 fall), #17, #22, #24 (sells in rallies) lost.
  Thu: a clean M1/M5 bull channel 05:10–10:40 — every sell inside it lost (#5, #8, #10, #14, #15) while the buys
  with it won (#6, #9, #12, #13, #16). Fri: the 19:50 → 01:00 crash 158.2 → 155.7 (~250 pips) — all five buys inside
  it lost (#34–#38), the sells with it won (#31, #32).
- **H2b climax — mostly held:** selling the low right after a sharp fall lost (Wed #15 11:45, #21 16:36; Thu #30–#32
  20:17–20:42 after the 18:40–20:00 fall; #32 stayed open overnight); buying right after the spike top lost
  (Wed #23 17:56). Fading won (Wed #4 05:14, #19–#20 at the 16:20 low, #33–#34 after the 23:00 spike). Counter-example:
  Wed #32 sold right after the 23:00 spike and lost before #33–#34 won.
- **New · H2i late trend:** after a long M1 channel, gaps in its direction near the top/end lose — Thu #17, #18,
  #20 (buys 11:20–12:23 as the 05:10–10:40 bull channel topped and rolled over), Thu #11 (buy at a spike top inside
  the channel).
- **H2a tight range — mixed this time:** Fri 03:40–10:00 Tokyo range only 158.45–158.75: 7 wins / 6 losses (not
  all losses); Fri 13:00–19:30 quiet range 158.0–158.3: about even. So a tight range is not always a loss — it seems
  to cost most when the gaps alternate direction every few minutes (chop), as on days 1–4.
- **Sessions:** Tokyo best on Wed only; Thu −1, Fri +1. London alone was good on Wed and Fri. The London+NY overlap
  and late NY were weak on all three days (L+NY −5, +1, −4; NY after ~22:30 Tehran usually losing, spread 0.7–1.2).
- **News / big moves:** Fri 11:10 a spike 159.2 → 157.4 in minutes, and the 19:50–01:00 crash: gaps against these
  moves were the worst losses of the week.

Summary after 7 days (15–23 Jan, 243 trades, 121 wins, −1R): H2c (against the M1 trend loses) held on every day and
is the clearest; H2b (don't trade in the climax direction at the extreme; fading it tends to win) held most days;
H2i (late in a long channel) new; H2a only when the range is choppy; session effects are not stable (London+NY
overlap weakest overall).

### H2 · week summary (15–23 Jan, my count from the pictures — approximate, not automated)
Losses (~122): against the M1 trend ≈ 40 (biggest); choppy tight M1 range with gaps alternating ≈ 30; in the climax
direction at the extreme (sell the low right after a sharp fall / buy the top right after a spike) ≈ 15; late in a
long channel ≈ 5; news spikes (23 Jan) — the worst single losses, mostly counted under "against the trend".
Wins (~121): with the M1 trend / M5 channel ≈ 25+; fading a climax (after a sharp move, in the turn direction) ≈ 17;
from the edge of a range (sell its top, buy its bottom) ≈ 12; the rest in normal swings with room for 1:1.

### H2 · week 2 — 26–30 Jan 2026 (backtest #544–#727): 184 trades, 89 wins (48%), −6R
| day | trades | wins | R | Tokyo | T+London | London | London+NY | NY |
|---|---|---|---|---|---|---|---|---|
| Mon 26 | 44 | 24 | +4 | 6/16 −4 | 1/1 | 6/12 0 | 5/7 +3 | 6/8 +4 |
| Tue 27 | 38 | 14 | −10 | 6/16 −4 | 1/3 | 2/6 −2 | 4/7 +1 | 1/6 −4 |
| Wed 28 | 33 | 18 | +3 | 5/11 −1 | 1/2 | 4/5 +3 | 4/8 0 | 4/7 +1 |
| Thu 29 | 29 | 17 | +5 | 8/15 +1 | 1/1 | 2/4 0 | 4/5 +3 | 2/4 0 |
| Fri 30 | 40 | 16 | −8 | 1/12 −10 | 3/3 | 3/7 −1 | 5/5 +5 | 4/13 −5 |
| week | 184 | 89 | −6 | 26/70 −18 | 7/10 +4 | 17/34 0 | 22/32 +12 | 17/38 −4 |
- **Sessions flipped vs week 1:** Tokyo was the worst this week (37%, −18R) and London+NY the best (+12R) — the
  opposite of week 1. Session is NOT a usable filter.
- **H2c against the M1 trend — held again every day** (e.g. Tue sells in the 06:15–08:30 rally, Tue buys after the
  13:20 crash, Thu buys in the 03:50 and 06:00–07:00 falls, Fri sell against the 04:00 rally, Mon buys in the
  16:40–19:00 fall). With-trend gaps in the Mon morning fall and afternoon rallies, Tue afternoon fall, Fri
  15:40–18:50 rally mostly won.
- **H2a choppy tight range — strongly held this week:** Mon 06:00–09:30 and 10:20–11:30 (≈9 losses), Fri the whole
  Tokyo session inside 153.75–154.00 (1 win in 12 — the worst block of the two weeks).
- **H2b climax — held mostly:** selling the low / buying the top right after a sharp move lost (Thu #2 04:06,
  Fri #34 22:25, Wed #23 19:12, Tue #19 12:04); fading after it often won (Mon #30, Wed #22, #27–#28, Thu #25 19:20).
- **News spikes again:** Tue 13:20 (154.5 → 153.3 in a minute), Wed 18:40 (152.9 → 153.7), Thu 19:10 crash; gaps
  against them lost.

Two weeks together (15–30 Jan): 427 trades, 210 wins, −7R. Stable patterns: **H2c** (every day), **H2a** when choppy,
**H2b** mostly, news spikes. Unstable: sessions, stop size, entry candle.

### H2 · week 3 — 2–6 Feb 2026 (backtest #728–#925): 198 trades, 96 wins, −6R
Mon +8 (24/40), Tue −6 (20/46), Wed +3 (14/25), Thu 0 (19/38), Fri −11 (19/49). Sessions: Tokyo 29/70 −12R,
London 23/38 +8R, London+NY 17/37 −3R, NY 21/40 +2R. Three weeks: 625 trades, −13R.

### H2 · first NUMERIC test of the patterns (17 Nov) — important correction
Features measured at entry from candles closed BEFORE the entry candle (no look-ahead): `tr30` = move of the last 30
M1 closes in the trade's direction / ATR(14) (+ = the trade goes the same way as the recent move, − = against it);
`er30` = efficiency ratio of the last 30 closes (chop ≈ 0); `mv10` = last 10-bar move in the trade direction / ATR;
`bigbar` = biggest range of the last 15 bars / 60-bar median range (news proxy).
In-sample 15 Jan–6 Feb (622 trades, 48.7%, −16R):
- `tr30 > 3` (trade in the direction of a big recent move — the "climax" case): 130 trades, 41.5%, **−22R**.
  `tr30 < −3` (trade against a big recent move — fading it): 110 trades, 59%, **+20R**.
- So the **eye-review "H2c: against the M1 trend loses" is NOT confirmed by numbers** — looking at the whole picture
  shows the trend AFTER the entry too (hindsight). Measured only with past candles, trading against the recent move
  did better, and with it worse — i.e. it is the climax rule H2b, not H2c.
- `er30` (chop) and `bigbar` (news proxy) showed no clean, monotonic effect.
Out-of-sample check of the ONE rule fixed in-sample ("skip if tr30 > 3"), 9 Feb–17 Jun (3,163 trades, 47.2%, −179R):
the skipped trades were again worse (45%, −68R) but the kept ones still lose (47.8%, −111R); fading (`tr30 < −3`) was
only 49% there. → The climax effect is real but small; no single filter found so far makes USDJPY M1 gaps profitable.

### Same numeric test on EURUSD (17 Nov) — current bot rules incl. no Off session, 2 Jan–17 Jun
3,967 trades, 45.8%, −331R (no costs). In-sample 15 Jan–6 Feb: 570 trades, 43.3%, −76R; out-of-sample 9 Feb–17 Jun:
3,083 trades, 46.6%, −211R. `tr30 > 3` (with a big recent move) 43% / 44% (−18R / −83R) — the same climax effect as
USDJPY, small. Fading (`tr30 < −3`) only 50% / 48%. `er30`, `bigbar`, `mv10`: every bucket under 50%. → On EURUSD M1
no bucket of any of these filters reaches 50%; the setup is worse than on USDJPY.

### Does the M5 filter help? (17 Nov, broker data 2 Jan–17 Jun, current rules, no Off)
All broker-data backtests above DO use the M5 structure filter (M5 built by resampling the broker M1; 500 M5 bars
closed at each entry). Same data without it:
| pair | with M5 filter | without M5 filter |
|---|---|---|
| USDJPY | 4,088 trades, 47.4%, −214R (1,795 gaps rejected by M5) | 4,342 trades, 48.1%, −162R |
| EURUSD | 3,967 trades, 45.8%, −331R (2,042 rejected by M5) | 4,359 trades, 47.2%, −243R |
→ The M5 filter (1:1 target must be inside the M5 box) makes results WORSE on both pairs over 5½ months.

### Filter search: can the losing situations be filtered out in advance? (17 Nov)
Base: broker data, current rules WITHOUT the M5 filter (it was worse), no Off. 18 features measured only from candles
closed before the entry: tr15/30/60 (move in trade direction / ATR), er15/30/60 (straightness), mv10, bigbar,
stop/ATR, gap height/ATR, candle-1 range/ATR, pos60 (place in the 60-bar range, 1 = good edge), room60 (room to the
60-bar extreme in R), ATR vs its 60-bar median, entry candle, leg, side, hour. Learned on 15 Jan–31 Mar, checked on
1 Apr–17 Jun (never used for choosing).
- USDJPY: train 2,169 trades 47.2% −123R; test 1,865 trades 49.2% −31R. The worst train buckets mostly did NOT stay
  bad (e.g. small candle 1: 41% train → 52% test). Held in both: tiny gap (gap ≤ 0.2 ATR) 44.5%/44.5%; big 60-bar
  move in the trade direction (tr60 > 2) 45.5%/45.5%; very straight last 30 bars (er30 > 0.29) 46%/45%. Best kept set
  (skip gap ≤ 0.58 ATR): test 756 trades, 49.6%, −6R — about break-even BEFORE spread/commission.
- EURUSD: train 46.9% −124R; test 48.2% −70R. Fairly consistent: entry on candle 4 (first candle after the gap)
  44%/47%. Best train rule (skip tr30 ≤ 2.4) → test 47.4%, −42R. No profitable subset.
→ With these measurable features, losing trades cannot be filtered out well enough: the best honest result is about
  50% at 1:1 (break-even before costs). The patterns seen by eye do not survive as rules. Next idea must change the
  setup itself (exit / target, entry, higher-timeframe direction), or another market (gold).

### Bigger target: 1.5R and 2R (17 Nov) — broker data 15 Jan–17 Jun, no M5 filter, no Off, stop unchanged
"After spread" = minus the broker spread at the entry candle (SPREAD column) / stop, per trade; commission not known.
| pair | target | trades | win % (break-even) | R | after spread | Jan–Mar | Apr–Jun |
|---|---|---|---|---|---|---|---|
| USDJPY | 1R | 4,034 | 48.1% (50%) | −154 | −419 | −123 | −31 |
| USDJPY | 1.5R | 3,204 | 38.0% (40%) | −159 | −369 | −121 | −38 |
| USDJPY | 2R | 2,493 | 33.6% (33.3%) | **+21** | −145 | −17 | +38 |
| EURUSD | 1R | 3,972 | 47.6% (50%) | −194 | −329 | −124 | −70 |
| EURUSD | 1.5R | 2,791 | 37.5% (40%) | −171 | −254 | −71 | −100 |
| EURUSD | 2R | 2,473 | 31.5% (33.3%) | −136 | −217 | −71 | −65 |
USDJPY 2R by month: Jan +39, Feb −51, Mar −5, Apr +53, May +14, Jun −29 (big swings). → 2R on USDJPY is about
break-even before costs (+21R over 2,493 trades ≈ +0.01R/trade) and clearly negative after spread. EURUSD negative at
every target. Changing the target alone does not create an edge.
