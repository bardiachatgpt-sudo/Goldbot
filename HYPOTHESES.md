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
