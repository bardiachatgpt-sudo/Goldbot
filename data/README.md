# Broker data (user's MT5 exports)

Kept here at the user's request. **Do not run backtests or analysis on these until the user asks.**
Not used by the bot (the bot reads TradingView). Files are gzip-compressed MT5 "Symbols → Bars → Export" CSVs:
tab-separated `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>` (spread in points),
time = broker server time = New York time + 7 h (GMT+2 winter / GMT+3 summer). Read with
`pandas.read_csv(path, sep="\t")` (pandas opens .gz directly).

| file | pair | TF | from → to (server time) | note |
|---|---|---|---|---|
| EURUSD_M1_202601010000_202611171258.csv.gz | EURUSD | M1 | 2026-01-01 → 2026-11-17 12:58 | Jul–Oct missing in the export (data ends 06-17, then 11-16/17) |
| USDJPY_M1_202601020010_202606172241.csv.gz | USDJPY | M1 | 2026-01-02 00:10 → 2026-06-17 22:41 | |
| XAUUSD_M1_202601020102_202611171252.csv.gz | XAUUSD | M1 | 2026-01-02 01:02 → 2026-11-17 12:52 | complete Jan–Nov; spread column in points (gold digits 2) |
