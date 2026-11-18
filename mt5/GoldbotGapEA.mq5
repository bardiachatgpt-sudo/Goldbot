//+------------------------------------------------------------------+
//| GoldbotGapEA.mq5                                                 |
//| Gap setup on M1 (same rules as the Goldbot Telegram bot).        |
//|                                                                  |
//| SELL gap: 3 bearish candles, candle 1 low > candle 3 high, the   |
//| body of candle 2 crosses that space (BUY: mirror).               |
//| Chained gaps right behind the first one (2-3-4, 3-4-5 ...) are   |
//| ignored; a separate or opposite gap replaces a waiting one.      |
//| Entry: after candle 3 closes, SELL when the chart price (Bid)    |
//| trades 1 pipette above the previous candle's high (BUY: 1        |
//| pipette below the previous low). Market order at that moment.    |
//| SL: 1 pipette beyond candle 1. TP: risk x RR. One trade at once. |
//| Lot: risk % of the balance.                                      |
//| Filters (each can be switched on/off):                           |
//|  - Trend: MACD(48,104,36) main line on M5 (the grey bars in MT5) |
//|    < 0 -> only sells, > 0 -> only buys (checked when candle 3    |
//|    closes).                                                      |
//|  - M5 structure: the TP must lie inside the M5 structure box     |
//|    of that moment (500 closed M5 candles; same algorithm as the  |
//|    bot: spike / channel / trading range on closes).              |
//|  - Max leg, trading hours (all / sessions / first 90 minutes).   |
//| Attach to an M1 chart.                                           |
//+------------------------------------------------------------------+
#property copyright "Goldbot"
#property version   "1.00"

#include <Trade\Trade.mqh>

enum ENUM_SL { SL_CANDLE1 = 0,    // Beyond candle 1 (the setup)
               SL_CANDLE2 = 1,    // Beyond candle 2
               SL_GAP_EDGE = 2,   // Beyond the gap edge (candle 1 low / high)
               SL_FRACTION = 3,   // Fraction of the candle-1 stop (SL value = 0.5 -> half)
               SL_FIXED = 4 };    // Fixed price distance from entry (SL value = e.g. 3.0 dollars)

enum ENUM_HOURS { HOURS_ALL = 0,          // All hours
                  HOURS_SESSIONS = 1,     // Tokyo / London / New York (no Off)
                  HOURS_FIRST90 = 2 };    // First 90 minutes of each session

input double     InpRiskPct      = 2.0;              // Risk per trade (% of balance)
input double     InpRR           = 1.0;              // Reward : risk (1 = 1:1)
input ENUM_SL    InpSLMode       = SL_CANDLE1;       // Where the stop-loss goes
input double     InpSLValue      = 0.5;              // SL value (fraction or price distance, see SL mode)
input bool       InpUseTrend     = true;             // Trend filter (MACD 48,104,36 on M5)
input bool       InpShowMACD     = true;             // Show the M5 MACD(48,104,36) under the chart
input bool       InpUseStructure = false;            // M5 structure filter (TP inside the M5 box)
input int        InpMaxLeg       = 0;                // Max leg (0 = all legs)
input ENUM_HOURS InpHours        = HOURS_SESSIONS;   // Trading hours
input int        InpServerMinusNY = 99;              // Server time minus New York time (hours; 99 = auto-detect)
input double     InpPipette      = 0.0;              // Pipette (0 = auto: gold 0.01, else Point)
input bool       InpDraw         = true;             // Draw gaps and trades on the chart
input int        InpLegLookback  = 1500;             // M1 candles used to count legs
input long       InpMagic        = 20261118;         // Magic number
input int        InpDeviation    = 30;               // Max slippage (points)
input group      "Colours"
input color      InpColSellGap   = clrMistyRose;     // Sell gap box
input color      InpColBuyGap    = clrHoneydew;      // Buy gap box
input color      InpColEntry     = clrBlack;         // Entry line
input color      InpColSL        = clrRed;           // Stop-loss line
input color      InpColTP        = clrGreen;         // Take-profit line
input color      InpColWin       = clrGreen;         // Result text: win
input color      InpColLoss      = clrRed;           // Result text: loss
input color      InpColSellArrow = clrRed;           // Sell arrow
input color      InpColBuyArrow  = clrBlue;          // Buy arrow
input color      InpColRange     = clrSteelBlue;     // M5 structure: range edges
input color      InpColBullCh    = clrSeaGreen;      // M5 structure: bull channel edges
input color      InpColBearCh    = clrCrimson;       // M5 structure: bear channel edges
input color      InpColSpike     = clrDarkOrange;    // M5 structure: spike edges
input bool       InpDrawStructure = true;            // Draw the M5 box used by the structure filter

CTrade trade;
// server-time model: server = New York + gNY (gUTC = false) or server = UTC + gUTCoff (gUTC = true)
int    gNY = 7;
bool   gUTC = false;
int    gUTCoff = 0;
int    macdHandle = INVALID_HANDLE;
double pp;                       // pipette
datetime lastBar = 0;

// waiting gap
bool     pend = false;
int      pSide;                  // -1 sell, +1 buy
datetime pT1, pT3, pChain;
double   pC1High, pC1Low, pC2High, pC2Low, pGapHi, pGapLo;
int      pLeg;
bool     pTrendOk;

// open trade bookkeeping (for drawing the result)
ulong    lastTicket = 0;
datetime lastEntryTime = 0;
double   lastEntry = 0, lastSL = 0, lastTP = 0;
int      lastSide = 0;
int      tradeNo = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   if(_Period != PERIOD_M1)
      Print("GoldbotGapEA: attach to an M1 chart (the setup is defined on M1).");
   pp = InpPipette;
   if(pp <= 0)
      pp = (StringFind(_Symbol, "XAU") >= 0 || StringFind(_Symbol, "GOLD") >= 0) ? 0.01 : _Point;
   DetectServerTime();
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviation);
   if(InpUseTrend || InpShowMACD)
   {
      macdHandle = iMACD(_Symbol, PERIOD_M5, 48, 104, 36, PRICE_CLOSE);
      if(macdHandle == INVALID_HANDLE) { Print("iMACD failed"); return(INIT_FAILED); }
      if(InpShowMACD)                        // the same M5 MACD the filter uses, in a window under the M1 chart
         ChartIndicatorAdd(0, (int)ChartGetInteger(0, CHART_WINDOWS_TOTAL), macdHandle);
   }
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(macdHandle != INVALID_HANDLE) IndicatorRelease(macdHandle);
}

//+------------------------------------------------------------------+
double R8(double x) { return NormalizeDouble(x, 8); }

bool HasPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
   }
   return false;
}

// gap with candle 3 at index i of chronological arrays: -1 sell, +1 buy, 0 none
int FindGap(const double &o[], const double &h[], const double &l[], const double &c[], int i,
            double &zhi, double &zlo)
{
   if(i < 2) return 0;
   double bLo = MathMin(o[i-1], c[i-1]), bHi = MathMax(o[i-1], c[i-1]);
   bool red   = (c[i-2] < o[i-2] && c[i-1] < o[i-1] && c[i] < o[i]);
   bool green = (c[i-2] > o[i-2] && c[i-1] > o[i-1] && c[i] > o[i]);
   if(l[i-2] > h[i] && red)
   {
      double lo = h[i], hi = l[i-2];
      if(MathMax(lo, bLo) < MathMin(hi, bHi)) { zhi = hi; zlo = lo; return -1; }
   }
   if(h[i-2] < l[i] && green)
   {
      double lo = h[i-2], hi = l[i];
      if(MathMax(lo, bLo) < MathMin(hi, bHi)) { zhi = hi; zlo = lo; return 1; }
   }
   return 0;
}

// leg of the gap whose candle 1 is the 3rd last bar of the arrays (same as gap.leg_number)
int LegNumber(const double &o[], const double &h[], const double &l[], const double &c[], int n, int side)
{
   int i1 = n - 3;
   int headIdx[]; int headSide[];
   int lastS = -10, lastB = -10, cnt = 0;
   double zh, zl;
   for(int i = 2; i < n; i++)
   {
      int s = FindGap(o, h, l, c, i, zh, zl);
      if(s == 0) continue;
      int last = (s < 0) ? lastS : lastB;
      if(i - 2 > last)
      {
         ArrayResize(headIdx, cnt + 1); ArrayResize(headSide, cnt + 1);
         headIdx[cnt] = i - 2; headSide[cnt] = s; cnt++;
      }
      if(s < 0) lastS = i; else lastB = i;
   }
   int a = 0;
   for(int k = 0; k < cnt; k++) if(headSide[k] == -side && headIdx[k] < i1) a = headIdx[k];
   int start = a;
   for(int j = a; j <= i1; j++)
   {
      if(side < 0 && h[j] > h[start]) start = j;
      if(side > 0 && l[j] < l[start]) start = j;
   }
   int leg = 1;
   for(int k = 0; k < cnt; k++) if(headSide[k] == side && headIdx[k] >= start && headIdx[k] < i1) leg++;
   return leg;
}

//+------------------------------------------------------------------+
//| Sessions (broker time zone found by DetectServerTime)              |
//+------------------------------------------------------------------+
int NthSunday(int year, int month, int nth)      // day of month of the nth Sunday (nth = -1: last)
{
   MqlDateTime d; d.year = year; d.mon = month; d.day = 1; d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   MqlDateTime x; TimeToStruct(t, x);
   int first = 1 + (7 - x.day_of_week) % 7;
   if(nth > 0) return first + 7 * (nth - 1);
   int days = (month == 3 || month == 10) ? 31 : 30;
   int last = first;
   while(last + 7 <= days) last += 7;
   return last;
}

bool USDst(datetime ny)               // US daylight saving time at this New York local time
{
   MqlDateTime d; TimeToStruct(ny, d);
   if(d.mon < 3 || d.mon > 11) return false;
   if(d.mon > 3 && d.mon < 11) return true;
   if(d.mon == 3) { int s = NthSunday(d.year, 3, 2); return (d.day > s) || (d.day == s && d.hour >= 2); }
   int s = NthSunday(d.year, 11, 1); return (d.day < s) || (d.day == s && d.hour < 2);
}

datetime ToNY(datetime server)
{
   if(!gUTC) return server - gNY * 3600;
   datetime utc = server - gUTCoff * 3600;
   datetime ny = utc - 5 * 3600;                 // EST first, then correct for DST
   return USDst(ny + 3600) ? utc - 4 * 3600 : ny;
}

//+------------------------------------------------------------------+
//| Broker time zone: from the weekly market open in the history.     |
//| The week opens Sunday 17:00 New York (metals 18:00). If the       |
//| server hour of every weekly open - that NY hour is the same       |
//| number, server = NY + that number (most MT5 brokers: 7). If       |
//| instead server - UTC is constant, server = UTC + that number.     |
//+------------------------------------------------------------------+
void DetectServerTime()
{
   if(InpServerMinusNY != 99) { gNY = InpServerMinusNY; gUTC = false;
                                PrintFormat("server time: New York + %d h (manual)", gNY); return; }
   datetime t[];
   int n = CopyTime(_Symbol, PERIOD_M1, 0, 200000, t);
   if(n < 1000) n = CopyTime(_Symbol, PERIOD_M5, 0, 50000, t);
   bool metal = StringFind(_Symbol, "XAU") >= 0 || StringFind(_Symbol, "XAG") >= 0 || StringFind(_Symbol, "GOLD") >= 0;
   int openNY = metal ? 18 : 17;
   int cntNY[24], cntUTC[24], samples = 0;
   ArrayInitialize(cntNY, 0); ArrayInitialize(cntUTC, 0);
   for(int i = 1; i < n; i++)
   {
      if(t[i] - t[i-1] < 36 * 3600) continue;    // first candle after a weekend
      MqlDateTime d; TimeToStruct(t[i], d);
      int k = ((d.hour - openNY) % 24 + 24) % 24;
      cntNY[k]++;
      // the same open as UTC: NY 17/18 + 4 (summer) or + 5 (winter); summer judged from the date
      datetime approxNY = t[i] - k * 3600;
      int utcOpen = openNY + (USDst(approxNY) ? 4 : 5);
      cntUTC[((d.hour - utcOpen) % 24 + 24) % 24]++;
      samples++;
   }
   if(samples < 4) { gNY = 7; gUTC = false; Print("server time: not enough weekends in the history, using New York + 7 h"); return; }
   int bNY = ArrayMaximum(cntNY), bUTC = ArrayMaximum(cntUTC);
   if(cntUTC[bUTC] > cntNY[bNY])
   { gUTC = true; gUTCoff = bUTC > 12 ? bUTC - 24 : bUTC;
     PrintFormat("server time: UTC %+d h (auto, %d weekends)", gUTCoff, samples); }
   else
   { gNY = bNY; gUTC = false; PrintFormat("server time: New York + %d h (auto, %d weekends)", gNY, samples); }
}

datetime ToUTC(datetime server)
{
   if(gUTC) return server - gUTCoff * 3600;
   datetime ny = server - gNY * 3600;
   MqlDateTime d; TimeToStruct(ny, d);
   bool dst;
   if(d.mon < 3 || d.mon > 11) dst = false;
   else if(d.mon > 3 && d.mon < 11) dst = true;
   else if(d.mon == 3) { int s = NthSunday(d.year, 3, 2); dst = (d.day > s) || (d.day == s && d.hour >= 2); }
   else { int s = NthSunday(d.year, 11, 1); dst = (d.day < s) || (d.day == s && d.hour < 2); }
   return ny + (dst ? 4 : 5) * 3600;
}

bool UKSummer(datetime utc)
{
   MqlDateTime d; TimeToStruct(utc, d);
   if(d.mon < 3 || d.mon > 10) return false;
   if(d.mon > 3 && d.mon < 10) return true;
   int s = NthSunday(d.year, d.mon, -1);
   if(d.mon == 3) return (d.day > s) || (d.day == s && d.hour >= 1);
   return (d.day < s) || (d.day == s && d.hour < 1);
}

// minutes since the session's open in local time, or -1 if outside [open, close) / weekend
int SessionMinutes(datetime local, int openH, int closeH)
{
   MqlDateTime d; TimeToStruct(local, d);
   if(d.day_of_week == 0 || d.day_of_week == 6) return -1;
   if(d.hour < openH || d.hour >= closeH) return -1;
   return (d.hour - openH) * 60 + d.min;
}

bool HoursOk(datetime server)
{
   if(InpHours == HOURS_ALL) return true;
   datetime utc = ToUTC(server);
   int m[3];
   m[0] = SessionMinutes(utc + 9 * 3600, 9, 18);                               // Tokyo
   m[1] = SessionMinutes(utc + (UKSummer(utc) ? 3600 : 0), 8, 17);             // London
   m[2] = SessionMinutes(ToNY(server), 8, 17);                                   // New York
   for(int k = 0; k < 3; k++)
   {
      if(m[k] < 0) continue;
      if(InpHours == HOURS_SESSIONS) return true;
      if(m[k] < 90) return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Trend: MACD(48,104,36) main line on the M5 candle closed at t     |
//+------------------------------------------------------------------+
int TrendAt(datetime t)              // +1 up, -1 down, 0 unknown
{
   if(macdHandle == INVALID_HANDLE || !InpUseTrend) return 0;
   double b[];
   if(CopyBuffer(macdHandle, 0, t - 300, 1, b) != 1) return 0;
   if(b[0] > 0) return 1;
   if(b[0] < 0) return -1;
   return 0;
}

//+------------------------------------------------------------------+
//| M5 structure (port of bot/structure3.py segment + mtf._edges)     |
//+------------------------------------------------------------------+
#define PH_RANGE   0
#define PH_CHANNEL 1
#define PH_SPIKE   2
#define PV_S 2
#define PV_E 3
// structure config (same as the bot)
#define C_T 0.10
#define C_TOL 0.15
#define C_RET 0.15
#define C_MG 0.5
#define C_RT 0.9
#define C_SPIKE_SIZE 0.12
#define C_SPIKE_EFF 0.45
#define C_SPIKE_SPEED 2.5
#define C_SPIKE_MAXBARS 25
#define C_FIRST_LEG 0.30
#define C_DEEP 0.60

struct Phase { int type; int side; int start; int end; };
Phase ph[];
int   nph = 0;
int   pvI[]; int pvK[]; double pvV[]; int npv = 0;     // zigzag pivots: index, kind (+1 H / -1 L), close

void AddPivot(int i, int k, double v)
{ ArrayResize(pvI, npv + 1); ArrayResize(pvK, npv + 1); ArrayResize(pvV, npv + 1);
  pvI[npv] = i; pvK[npv] = k; pvV[npv] = v; npv++; }

void Zigzag(const double &c[], int n, double T)
{
   npv = 0;
   int d = 0, ext = 0, lo = 0, hi = 0;
   for(int i = 1; i < n; i++)
   {
      if(d == 0)
      {
         if(c[i] > c[hi]) hi = i;
         if(c[i] < c[lo]) lo = i;
         if(c[hi] - c[lo] >= T)
         {
            if(hi > lo) { AddPivot(lo, -1, c[lo]); d = 1; ext = hi; }
            else        { AddPivot(hi, 1, c[hi]); d = -1; ext = lo; }
         }
      }
      else if(d == 1)
      {
         if(c[i] > c[ext]) ext = i;
         else if(c[ext] - c[i] >= T) { AddPivot(ext, 1, c[ext]); d = -1; ext = i; }
      }
      else
      {
         if(c[i] < c[ext]) ext = i;
         else if(c[i] - c[ext] >= T) { AddPivot(ext, -1, c[ext]); d = 1; ext = i; }
      }
   }
   if(d != 0) AddPivot(ext, d == 1 ? 1 : -1, c[ext]);
}

bool IsSpike(const double &c[], int a, int b, double hgt, double mad)
{
   int n = b - a;
   if(n < 1 || n > C_SPIKE_MAXBARS) return false;
   double mv = MathAbs(c[b] - c[a]);
   double path = 1e-12;
   for(int j = a; j < b; j++) path += MathAbs(c[j+1] - c[j]);
   return mv >= C_SPIKE_SIZE * hgt && mv / path >= C_SPIKE_EFF && mv / n >= C_SPIKE_SPEED * mad;
}

int Sign(double x) { return x > 0 ? 1 : (x < 0 ? -1 : 0); }

int SpikeHead(const double &c[], int a, int b, double hgt, double mad)
{
   int best = -1, sgn = Sign(c[b] - c[a]);
   int lim = MathMin(b, a + C_SPIKE_MAXBARS);
   for(int j = a + 1; j <= lim; j++)
      if(Sign(c[j] - c[a]) == sgn && IsSpike(c, a, j, hgt, mad))
         if(best < 0 || (c[j] - c[best]) * sgn > 0) best = j;
   return best;
}

void Add(int typ, int side, int s, int e)
{
   if(e <= s) return;
   if(nph > 0 && ph[nph-1].type == typ && ph[nph-1].side == side && typ != PH_SPIKE) { ph[nph-1].end = e; return; }
   ArrayResize(ph, nph + 1);
   ph[nph].type = typ; ph[nph].side = side; ph[nph].start = s; ph[nph].end = e; nph++;
}

double SegMin(const double &c[], int a, int b) { double m = c[a]; for(int j = a; j <= b; j++) m = MathMin(m, c[j]); return m; }
double SegMax(const double &c[], int a, int b) { double m = c[a]; for(int j = a; j <= b; j++) m = MathMax(m, c[j]); return m; }

void FoldRetraced(const double &c[])
{
   bool changed = true;
   while(changed)
   {
      changed = false;
      for(int i = 0; i < nph - 1; i++)
      {
         if(ph[i].type != PH_CHANNEL || ph[i+1].type != PH_RANGE) continue;
         double mv = c[ph[i].end] - c[ph[i].start];
         if(mv == 0) continue;
         double back = (mv > 0) ? (c[ph[i].end] - SegMin(c, ph[i+1].start, ph[i+1].end)) / mv
                                : (SegMax(c, ph[i+1].start, ph[i+1].end) - c[ph[i].end]) / -mv;
         if(back >= C_RT) { ph[i].type = PH_RANGE; ph[i].side = 0; changed = true; }
      }
      Phase m[]; int nm = 0;
      for(int i = 0; i < nph; i++)
      {
         if(nm > 0 && ph[i].type == PH_RANGE && m[nm-1].type == PH_RANGE) { m[nm-1].end = ph[i].end; continue; }
         ArrayResize(m, nm + 1); m[nm] = ph[i]; nm++;
      }
      ArrayResize(ph, nm); for(int i = 0; i < nm; i++) ph[i] = m[i]; nph = nm;
   }
}

void RemovePhase(int i)
{
   for(int j = i; j < nph - 1; j++) ph[j] = ph[j+1];
   nph--; ArrayResize(ph, nph);
}

void MergeTiny(int minBars = 8)
{
   int i = 0;
   while(i < nph && nph > 1)
   {
      if(ph[i].type != PH_SPIKE && ph[i].end - ph[i].start < minBars)
      {
         if(i + 1 < nph && ph[i+1].type != PH_SPIKE) ph[i+1].start = ph[i].start;
         else if(i > 0) ph[i-1].end = ph[i].end;
         else { i++; continue; }
         RemovePhase(i);
         i = MathMax(i - 1, 0);
         continue;
      }
      i++;
   }
   Phase m[]; int nm = 0;
   for(int k = 0; k < nph; k++)
   {
      if(nm > 0 && ph[k].type == PH_RANGE && m[nm-1].type == PH_RANGE) { m[nm-1].end = ph[k].end; continue; }
      ArrayResize(m, nm + 1); m[nm] = ph[k]; nm++;
   }
   ArrayResize(ph, nm); for(int k = 0; k < nm; k++) ph[k] = m[k]; nph = nm;
}

double Median(const double &a[], int n)
{
   double b[]; ArrayResize(b, n); for(int i = 0; i < n; i++) b[i] = a[i];
   ArraySort(b);
   return (n % 2 == 1) ? b[n/2] : (b[n/2-1] + b[n/2]) / 2.0;
}

void Segment(const double &c[], int n)
{
   nph = 0; ArrayResize(ph, 0);
   double cmax = SegMax(c, 0, n - 1), cmin = SegMin(c, 0, n - 1);
   double hgt = cmax - cmin; if(hgt == 0) hgt = 1e-12;
   double dif[]; ArrayResize(dif, n - 1);
   for(int i = 0; i < n - 1; i++) dif[i] = MathAbs(c[i+1] - c[i]);
   double mad = Median(dif, n - 1) + 1e-12;
   Zigzag(c, n, C_T * hgt);
   // P = start + inner pivots + end
   int Pi[]; int Pk[]; double Pv[]; int m = 0;
   ArrayResize(Pi, npv + 2); ArrayResize(Pk, npv + 2); ArrayResize(Pv, npv + 2);
   Pi[m] = 0; Pk[m] = PV_S; Pv[m] = c[0]; m++;
   for(int k = 0; k < npv; k++) if(pvI[k] > 0 && pvI[k] < n - 1) { Pi[m] = pvI[k]; Pk[m] = pvK[k]; Pv[m] = pvV[k]; m++; }
   Pi[m] = n - 1; Pk[m] = PV_E; Pv[m] = c[n-1]; m++;

   bool range = true; int side = 0, start = 0, tstart = 0;
   double lo = MathMin(Pv[0], Pv[1]), hi = MathMax(Pv[0], Pv[1]);
   double lastH = 0, lastL = 0;
   int k = 1;
   int f = (m >= 4 && MathAbs(Pv[1] - Pv[0]) < C_T * hgt) ? 2 : 1;
   if(m >= f + 2 && MathAbs(Pv[f] - Pv[f-1]) >= C_FIRST_LEG * hgt)
   {
      range = false; side = (Pv[f] > Pv[f-1]) ? 1 : -1;
      lastH = MathMax(Pv[f-1], Pv[f]); lastL = MathMin(Pv[f-1], Pv[f]);
      if(IsSpike(c, Pi[f-1], Pi[f], hgt, mad)) Add(PH_SPIKE, side, 0, Pi[f]);
      k = f + 1;
   }
   if(range && m >= 5)
   {
      double hs[2], ls[2]; int nh = 0, nl = 0;
      for(int q = 1; q < 5; q++)
      {
         if(Pk[q] == 1 && nh < 2) hs[nh++] = Pv[q];
         if(Pk[q] == -1 && nl < 2) ls[nl++] = Pv[q];
      }
      int nh4 = 0, nl4 = 0;
      for(int q = 1; q < 5; q++) { if(Pk[q] == 1) nh4++; if(Pk[q] == -1) nl4++; }
      if(nh4 >= 2 && nl4 >= 2 && (hs[1] - hs[0]) * (ls[1] - ls[0]) > 0)
      {
         range = false; side = (hs[1] > hs[0]) ? 1 : -1;
         for(int q = 1; q < 3; q++) { if(Pk[q] == 1) lastH = Pv[q]; if(Pk[q] == -1) lastL = Pv[q]; }
      }
   }
   while(k < m)
   {
      bool hasNxt = (k + 1 < m && Pk[k+1] != PV_E);
      if(range)
      {
         double bh = MathMax(hi - lo, 1e-12), tol = C_TOL * bh;
         if(lo - tol <= Pv[k] && Pv[k] <= hi + tol) { k++; continue; }
         bool up = Pv[k] > hi;
         if(Pk[k] == PV_E) { Add(PH_RANGE, 0, start, Pi[k]); k++; continue; }
         bool back = hasNxt && (up ? (Pv[k+1] < hi - C_RET * bh) : (Pv[k+1] > lo + C_RET * bh));
         if(back) { hi = MathMax(hi, Pv[k]); lo = MathMin(lo, Pv[k]); k++; continue; }
         int b0 = Pi[k-1];
         Add(PH_RANGE, 0, start, b0);
         side = up ? 1 : -1;
         if(IsSpike(c, b0, Pi[k], hgt, mad)) Add(PH_SPIKE, side, b0, Pi[k]);
         else
         {
            int j = SpikeHead(c, b0, Pi[k], hgt, mad);
            if(j >= 0 && Pi[k] - j >= 8) Add(PH_SPIKE, side, b0, j);
         }
         range = false; tstart = b0;
         lastH = up ? Pv[k] : Pv[k-1];
         lastL = up ? Pv[k-1] : Pv[k];
         k++; continue;
      }
      // channel
      if(Pk[k] == PV_E)
      {
         int s0 = (nph > 0 && ph[nph-1].type == PH_SPIKE) ? ph[nph-1].end : tstart;
         bool broke = (side == 1) ? (Pv[k] < lastL) : (Pv[k] > lastH);
         double base = (side == 1) ? MathMin(c[s0], lastL) : MathMax(c[s0], lastH);
         double top = (side == 1) ? lastH : lastL;
         bool deep = MathAbs(top - base) > 0 && (top - Pv[k]) * side >= C_DEEP * MathAbs(top - base);
         int e = Pi[k-1];
         int j = ((broke || deep) && e > s0) ? SpikeHead(c, e, Pi[k], hgt, mad) : -1;
         if(j >= 0 && Pi[k] - j >= 8)
         { Add(PH_CHANNEL, side, s0, e); Add(PH_SPIKE, -side, e, j); Add(PH_RANGE, 0, j, Pi[k]); k++; continue; }
         if(broke && e > s0 && Pi[k] - e >= 2)
         {
            Add(PH_CHANNEL, side, s0, e);
            if(IsSpike(c, e, Pi[k], hgt, mad)) Add(PH_SPIKE, -side, e, Pi[k]);
            else Add(PH_CHANNEL, -side, e, Pi[k]);
         }
         else Add(PH_CHANNEL, side, s0, Pi[k]);
         k++; continue;
      }
      bool withTrend = (Pk[k] == (side == 1 ? 1 : -1));
      bool ok;
      if(withTrend)
      {
         double mg = C_MG * C_T * hgt;
         ok = (side == 1) ? (Pv[k] > lastH + mg) : (Pv[k] < lastL - mg);
      }
      else
      {
         ok = (side == 1) ? (Pv[k] > lastL) : (Pv[k] < lastH);
         int s0 = (nph > 0 && ph[nph-1].type == PH_SPIKE) ? ph[nph-1].end : tstart;
         double base = (side == 1) ? MathMin(c[s0], lastL) : MathMax(c[s0], lastH);
         double top = (side == 1) ? lastH : lastL;
         if(ok && MathAbs(top - base) > 0 && MathAbs(top - Pv[k]) >= C_DEEP * MathAbs(top - base)) ok = false;
      }
      if(ok) { if(Pk[k] == 1) lastH = Pv[k]; else lastL = Pv[k]; k++; continue; }
      int e = Pi[k-1];
      int s0 = (nph > 0 && ph[nph-1].type == PH_SPIKE) ? ph[nph-1].end : tstart;
      Add(PH_CHANNEL, side, s0, e);
      range = true; start = e;
      lo = MathMin(Pv[k-1], Pv[k]); hi = MathMax(Pv[k-1], Pv[k]);
      int j = SpikeHead(c, e, Pi[k], hgt, mad);
      if(j >= 0 && Pi[k] - j >= 8)
      {
         Add(PH_SPIKE, -side, e, j); start = j;
         lo = SegMin(c, j, Pi[k]); hi = SegMax(c, j, Pi[k]);
      }
      k++;
   }
   if(range && (nph == 0 || ph[nph-1].end < n - 1)) Add(PH_RANGE, 0, start, n - 1);
   FoldRetraced(c);
   MergeTiny(8);
}

// hull edge (bot: structure3._hull_edge with xs/seg): returns false if none; slope and intercept
bool HullEdge(double &px[], double &py[], int np, bool upper, const double &c[], int a, int b,
              double &slope, double &icpt)
{
   // sort by x then y, unique
   for(int i = 0; i < np; i++)
      for(int j = i + 1; j < np; j++)
         if(px[j] < px[i] || (px[j] == px[i] && py[j] < py[i]))
         { double t = px[i]; px[i] = px[j]; px[j] = t; t = py[i]; py[i] = py[j]; py[j] = t; }
   double ux[], uy[]; int nu = 0;
   for(int i = 0; i < np; i++)
   {
      if(nu > 0 && ux[nu-1] == px[i] && uy[nu-1] == py[i]) continue;
      ArrayResize(ux, nu + 1); ArrayResize(uy, nu + 1); ux[nu] = px[i]; uy[nu] = py[i]; nu++;
   }
   if(nu < 2) return false;
   double hx[], hy[]; int nhl = 0;
   for(int i = 0; i < nu; i++)
   {
      while(nhl >= 2)
      {
         double cross = (hx[nhl-1] - hx[nhl-2]) * (uy[i] - hy[nhl-2]) - (hy[nhl-1] - hy[nhl-2]) * (ux[i] - hx[nhl-2]);
         if(upper ? (cross >= 0) : (cross <= 0)) nhl--; else break;
      }
      ArrayResize(hx, nhl + 1); ArrayResize(hy, nhl + 1); hx[nhl] = ux[i]; hy[nhl] = uy[i]; nhl++;
   }
   int ne = nhl - 1;
   if(ne < 1) return false;
   double span = ux[nu-1] - ux[0];
   bool anyLong = false;
   for(int e = 0; e < ne; e++) if(hx[e+1] - hx[e] >= 0.3 * span) anyLong = true;
   int longest = 0;
   for(int e = 1; e < ne; e++) if(hx[e+1] - hx[e] > hx[longest+1] - hx[longest]) longest = e;
   double bestGap = DBL_MAX; bool found = false;
   for(int e = 0; e < ne; e++)
   {
      bool isLong = anyLong ? (hx[e+1] - hx[e] >= 0.3 * span) : (e == longest);
      if(!isLong) continue;
      double sl = (hy[e+1] - hy[e]) / (hx[e+1] - hx[e]);
      double ic = hy[e] - sl * hx[e];
      double ext = upper ? -DBL_MAX : DBL_MAX;
      for(int x = a; x <= b; x++) { double d = c[x] - (sl * x + ic); ext = upper ? MathMax(ext, d) : MathMin(ext, d); }
      double g = 0;
      for(int x = a; x <= b; x++) g += MathAbs(c[x] - (sl * x + ic) - ext);
      g /= (b - a + 1);
      if(g < bestGap) { bestGap = g; slope = sl; icpt = ic; found = true; }
   }
   return found;
}

// top/bottom of the last M5 phase at position pos (bot: mtf._edges with structure3.lines)
bool PhaseBox(const double &c[], int n, double pos, double &top, double &bot)
{
   if(nph == 0) return false;
   Phase p = ph[nph-1];
   int a = p.start, b = p.end;
   if(p.type == PH_RANGE)
   {
      double x0[2], y0[2], x1[2], y1[2];
      double bh = SegMax(c, a, b) - SegMin(c, a, b); if(bh == 0) bh = 1e-12;
      for(int u = 0; u < 2; u++)
      {
         bool upper = (u == 0);
         double px[], py[]; int np = 0;
         for(int q = 0; q < npv; q++)
            if(pvI[q] >= a && pvI[q] <= b && pvK[q] == (upper ? 1 : -1))
            { ArrayResize(px, np + 1); ArrayResize(py, np + 1); px[np] = pvI[q]; py[np] = pvV[q]; np++; }
         double ext = upper ? SegMax(c, a, b) : SegMin(c, a, b);
         double sl, ic;
         if(np >= 2 && HullEdge(px, py, np, upper, c, a, b, sl, ic))
         {
            double off = upper ? -DBL_MAX : DBL_MAX;
            for(int x = a; x <= b; x++) { double d = c[x] - (sl * x + ic); off = upper ? MathMax(off, d) : MathMin(off, d); }
            ic += off;
            if(MathAbs(sl) * (b - a) < 0.15 * bh) { x0[u] = a; y0[u] = ext; x1[u] = b; y1[u] = ext; }
            else { x0[u] = a; y0[u] = sl * a + ic; x1[u] = b; y1[u] = sl * b + ic; }
         }
         else { x0[u] = a; y0[u] = ext; x1[u] = b; y1[u] = ext; }
      }
      if((y1[0] - y0[0]) * (y1[1] - y0[1]) > 0)
      { y0[0] = y1[0] = SegMax(c, a, b); y0[1] = y1[1] = SegMin(c, a, b); }
      double v[2];
      for(int u = 0; u < 2; u++)
      {
         double sl = (x1[u] != x0[u]) ? (y1[u] - y0[u]) / (x1[u] - x0[u]) : 0.0;
         v[u] = y0[u] + sl * (pos - x0[u]);
      }
      top = MathMax(v[0], v[1]); bot = MathMin(v[0], v[1]);
      return true;
   }
   if(p.type == PH_CHANNEL)
   {
      bool bull = (p.side == 1);
      double px[], py[]; int np = 0;
      for(int q = 0; q < npv; q++)
         if(pvI[q] >= a && pvI[q] <= b && pvK[q] == (bull ? -1 : 1))
         { ArrayResize(px, np + 1); ArrayResize(py, np + 1); px[np] = pvI[q]; py[np] = pvV[q]; np++; }
      ArrayResize(px, np + 2); ArrayResize(py, np + 2);
      px[np] = a; py[np] = c[a]; px[np+1] = b; py[np+1] = c[b]; np += 2;
      double sl, ic;
      if(HullEdge(px, py, np, !bull, c, a, b, sl, ic))
      {
         double off = bull ? DBL_MAX : -DBL_MAX;
         for(int x = a; x <= b; x++) { double d = c[x] - (sl * x + ic); off = bull ? MathMin(off, d) : MathMax(off, d); }
         ic += off;
         double par = bull ? -DBL_MAX : DBL_MAX;
         for(int x = a; x <= b; x++) { double d = c[x] - (sl * x + ic); par = bull ? MathMax(par, d) : MathMin(par, d); }
         double v0 = sl * pos + ic, v1 = sl * pos + ic + par;
         top = MathMax(v0, v1); bot = MathMin(v0, v1);
         return true;
      }
   }
   top = SegMax(c, a, b); bot = SegMin(c, a, b);
   return true;
}

// TP inside the M5 box of time t (entry candle open)? true if not enough data (like the bot)
bool StructureOk(datetime t, int side, double tp)
{
   double c5[]; datetime t5[];
   int got = CopyClose(_Symbol, PERIOD_M5, t - 300, 500, c5);
   if(got < 100 || CopyTime(_Symbol, PERIOD_M5, t - 300, got, t5) != got) return true;
   Segment(c5, got);
   double pos = (got - 1) + (double)(t - t5[got-1]) / 300.0;
   double top, bot;
   if(!PhaseBox(c5, got, pos, top, bot)) return true;
   if(InpDraw && InpDrawStructure)
   {
      Phase p = ph[nph-1];
      double top0, bot0;
      PhaseBox(c5, got, p.start, top0, bot0);
      color col = p.type == PH_RANGE ? InpColRange : (p.type == PH_SPIKE ? InpColSpike
                  : (p.side > 0 ? InpColBullCh : InpColBearCh));
      string nm = "GBS" + TimeToString(t, TIME_DATE | TIME_MINUTES);
      string kind = p.type == PH_RANGE ? "M5 range" : (p.type == PH_SPIKE ? "M5 spike"
                    : (p.side > 0 ? "M5 bull channel" : "M5 bear channel"));
      ObjectCreate(0, nm + "_t", OBJ_TREND, 0, t5[p.start], top0, t, top);
      ObjectCreate(0, nm + "_b", OBJ_TREND, 0, t5[p.start], bot0, t, bot);
      for(int q = 0; q < 2; q++)
      {
         string o = nm + (q == 0 ? "_t" : "_b");
         ObjectSetInteger(0, o, OBJPROP_COLOR, col);
         ObjectSetInteger(0, o, OBJPROP_WIDTH, 2);
         ObjectSetInteger(0, o, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(0, o, OBJPROP_BACK, true);
      }
      DrawText(nm + "_k", t5[p.start], top0, kind, col);
   }
   return side < 0 ? (tp >= bot) : (tp <= top);
}

//+------------------------------------------------------------------+
//| Drawing                                                          |
//+------------------------------------------------------------------+
void DrawBox(string name, datetime t1, datetime t2, double p1, double p2, color col)
{
   if(!InpDraw) return;
   ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
}

void DrawLine(string name, datetime t1, datetime t2, double p, color col, ENUM_LINE_STYLE st)
{
   if(!InpDraw) return;
   ObjectCreate(0, name, OBJ_TREND, 0, t1, p, t2, p);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, st);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
}

void DrawText(string name, datetime t, double p, string txt, color col)
{
   if(!InpDraw) return;
   ObjectCreate(0, name, OBJ_TEXT, 0, t, p);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
}

//+------------------------------------------------------------------+
void CheckClosedTrade()
{
   if(lastTicket == 0 || HasPosition()) return;
   if(!HistorySelectByPosition(lastTicket)) return;
   double profit = 0, exitPrice = 0; datetime exitTime = 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT)
      { exitPrice = HistoryDealGetDouble(d, DEAL_PRICE); exitTime = (datetime)HistoryDealGetInteger(d, DEAL_TIME); }
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_SWAP);
   }
   if(exitTime > 0)
   {
      double r = MathAbs(lastEntry - lastSL) > 0 ? (exitPrice - lastEntry) * lastSide / MathAbs(lastEntry - lastSL) : 0;
      string n = "GBT" + IntegerToString(tradeNo);
      DrawLine(n + "_sl", lastEntryTime, exitTime, lastSL, InpColSL, STYLE_DASH);
      DrawLine(n + "_tp", lastEntryTime, exitTime, lastTP, InpColTP, STYLE_DASH);
      DrawLine(n + "_en", lastEntryTime, exitTime, lastEntry, InpColEntry, STYLE_DOT);
      DrawText(n + "_res", exitTime, exitPrice, StringFormat(" #%d %+.2fR %s", tradeNo, r, profit >= 0 ? "WIN" : "LOSS"),
               profit >= 0 ? InpColWin : InpColLoss);
   }
   lastTicket = 0;
}

//+------------------------------------------------------------------+
void OnNewBar()
{
   // closed M1 candles, oldest first; the last one (index n-1) = the candle that just closed
   int n = MathMax(InpLegLookback, 50);
   double o[], h[], l[], c[]; datetime t[];
   if(CopyOpen(_Symbol, PERIOD_M1, 1, n, o) != n || CopyHigh(_Symbol, PERIOD_M1, 1, n, h) != n ||
      CopyLow(_Symbol, PERIOD_M1, 1, n, l) != n || CopyClose(_Symbol, PERIOD_M1, 1, n, c) != n ||
      CopyTime(_Symbol, PERIOD_M1, 1, n, t) != n)
      return;
   if(HasPosition()) return;                      // one trade at a time: gaps during a trade are ignored
   double zhi, zlo;
   int i = n - 1;
   int side = FindGap(o, h, l, c, i, zhi, zlo);
   if(side == 0) return;
   if(pend && pSide == side && t[i-2] <= pChain) { pChain = t[i]; return; }   // chained gap: same gap
   pend = true; pSide = side; pT1 = t[i-2]; pT3 = t[i]; pChain = t[i];
   pC1High = h[i-2]; pC1Low = l[i-2]; pC2High = h[i-1]; pC2Low = l[i-1]; pGapHi = zhi; pGapLo = zlo;
   pLeg = LegNumber(o, h, l, c, n, side);
   int tr = InpUseTrend ? TrendAt(t[i] + 60) : side;
   pTrendOk = !InpUseTrend || tr == side;
   DrawBox("GBG" + TimeToString(pT1, TIME_DATE | TIME_MINUTES), pT1, pT3 + 60, pGapHi, pGapLo,
           side < 0 ? InpColSellGap : InpColBuyGap);
}

void OnTick()
{
   CheckClosedTrade();
   datetime bar = iTime(_Symbol, PERIOD_M1, 0);
   if(bar != lastBar) { lastBar = bar; OnNewBar(); }
   if(!pend || HasPosition() || bar <= pT3) return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double prevH = iHigh(_Symbol, PERIOD_M1, 1), prevL = iLow(_Symbol, PERIOD_M1, 1);
   double level = R8(pSide < 0 ? prevH + pp : prevL - pp);
   bool hit = pSide < 0 ? (bid >= level) : (bid <= level);    // the chart price (Bid) reaches the level
   if(!hit) return;

   double entry = pSide < 0 ? bid : ask;                       // sell at Bid, buy at Ask
   double sl1 = R8(pSide < 0 ? pC1High + pp : pC1Low - pp);    // the setup's stop (beyond candle 1)
   double sl = sl1;
   if(InpSLMode == SL_CANDLE2)  sl = R8(pSide < 0 ? pC2High + pp : pC2Low - pp);
   if(InpSLMode == SL_GAP_EDGE) sl = R8(pSide < 0 ? pGapHi + pp : pGapLo - pp);
   if(InpSLMode == SL_FRACTION) sl = R8(entry - pSide * InpSLValue * MathAbs(sl1 - entry));
   if(InpSLMode == SL_FIXED)    sl = R8(entry - pSide * InpSLValue);
   double risk = MathAbs(sl - entry);
   if(risk <= 0 || (sl - entry) * pSide > 0) return;           // entry beyond the stop: wait (like the bot)
   double tp = R8(entry + pSide * InpRR * risk);

   string why = "";
   if(InpMaxLeg > 0 && pLeg > InpMaxLeg) why = "leg";
   else if(!HoursOk(bar)) why = "hours";
   else if(!pTrendOk) why = "trend";
   else if(InpUseStructure && !StructureOk(bar, pSide, tp)) why = "M5 structure";
   if(why != "")
   {
      Print(StringFormat("gap %s %s skipped: %s", TimeToString(pT1), pSide < 0 ? "SELL" : "BUY", why));
      pend = false;
      return;
   }

   // lot from risk %
   double loss1;
   if(!OrderCalcProfit(pSide < 0 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY, _Symbol, 1.0, entry, sl, loss1) || loss1 >= 0)
   { pend = false; return; }
   double money = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lots = MathFloor(money / -loss1 / step) * step;
   if(lots < vmin) { Print("lot below minimum, skipped"); pend = false; return; }
   lots = MathMin(lots, vmax);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   sl = NormalizeDouble(sl, digits); tp = NormalizeDouble(tp, digits);

   bool ok = pSide < 0 ? trade.Sell(lots, _Symbol, 0, sl, tp, StringFormat("gap L%d", pLeg))
                       : trade.Buy(lots, _Symbol, 0, sl, tp, StringFormat("gap L%d", pLeg));
   pend = false;
   if(!ok) { Print("order failed: ", trade.ResultRetcode(), " ", trade.ResultComment()); return; }
   tradeNo++;
   lastTicket = trade.ResultOrder();
   if(PositionSelectByTicket(lastTicket)) lastEntry = PositionGetDouble(POSITION_PRICE_OPEN); else lastEntry = entry;
   lastEntryTime = TimeCurrent(); lastSL = sl; lastTP = tp; lastSide = pSide;
   if(InpDraw)
   {
      string nm = "GBT" + IntegerToString(tradeNo) + "_in";
      ObjectCreate(0, nm, pSide < 0 ? OBJ_ARROW_SELL : OBJ_ARROW_BUY, 0, lastEntryTime, lastEntry);
      ObjectSetInteger(0, nm, OBJPROP_COLOR, pSide < 0 ? InpColSellArrow : InpColBuyArrow);
   }
}
//+------------------------------------------------------------------+
