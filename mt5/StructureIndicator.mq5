//+------------------------------------------------------------------+
//| StructureIndicator.mq5 — Market Structure Indicator              |
//| Draws market structure (spike / channel / trading range, on      |
//| closes) of a timeframe you choose — e.g. the 5-minute structure  |
//| — with the same algorithm as the Goldbot Telegram bot.           |
//| Every line is an ordinary MT5 trend line: move it, recolour it,  |
//| delete it. A line you change or delete is LOCKED: when new       |
//| candles come and the structure is recalculated, it is left as    |
//| you made it. The lines stay on the chart when you switch the     |
//| chart's timeframe (e.g. draw the 5-min structure, edit it, then  |
//| look at it on 1-min). The "Redraw" button clears your edits and  |
//| draws everything again.                                          |
//+------------------------------------------------------------------+
#property copyright "Market Structure Indicator"
#property description "Market structure (spike / channel / range) of a chosen timeframe; editable lines that stay locked."
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

input ENUM_TIMEFRAMES InpTF       = PERIOD_M5;     // Structure of which timeframe
input int             InpBars     = 500;           // Candles of that timeframe used
input bool            InpShowM1   = true;          // Show on M1
input bool            InpShowM5   = true;          // Show on M5
input bool            InpShowM15  = true;          // Show on M15
input bool            InpShowM30  = true;          // Show on M30
input bool            InpShowH1   = true;          // Show on H1
input bool            InpShowH4   = true;          // Show on H4
input bool            InpShowD1   = true;          // Show on D1 and higher
input color           InpColRange = clrSteelBlue;  // Trading range colour
input color           InpColBull  = clrSeaGreen;   // Bull channel colour
input color           InpColBear  = clrCrimson;    // Bear channel colour
input color           InpColSpike = clrDarkOrange; // Spike colour
input int             InpWidth    = 2;             // Line width
input ENUM_LINE_STYLE InpStyle    = STYLE_SOLID;   // Line style
input bool            InpLabels   = true;          // Write the structure's name
input bool            InpButton   = true;          // Show the "Redraw" button

string   PFX, BTN, LCK;
datetime lastStructBar = 0;
ENUM_TIMEFRAMES TF;
string   drawn[];          // names drawn by the last update (to notice lines the user deleted)

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


//+------------------------------------------------------------------+
//| Lines of one phase in index coordinates (bot: structure3.lines)   |
//| kind: 0 = two lines, 1 = flat box (spike / fallback)              |
//+------------------------------------------------------------------+
int PhaseLines(const double &c[], int k, double &x0[], double &y0[], double &x1[], double &y1[])
{
   ArrayResize(x0, 2); ArrayResize(y0, 2); ArrayResize(x1, 2); ArrayResize(y1, 2);
   int a = ph[k].start, b = ph[k].end;
   double top = SegMax(c, a, b), bot = SegMin(c, a, b);
   if(ph[k].type == PH_RANGE)
   {
      double bh = top - bot; if(bh == 0) bh = 1e-12;
      for(int u = 0; u < 2; u++)
      {
         bool upper = (u == 0);
         double px[], py[]; int np = 0;
         for(int q = 0; q < npv; q++)
            if(pvI[q] >= a && pvI[q] <= b && pvK[q] == (upper ? 1 : -1))
            { ArrayResize(px, np + 1); ArrayResize(py, np + 1); px[np] = pvI[q]; py[np] = pvV[q]; np++; }
         double ext = upper ? top : bot;
         double sl, ic;
         x0[u] = a; x1[u] = b; y0[u] = ext; y1[u] = ext;
         if(np >= 2 && HullEdge(px, py, np, upper, c, a, b, sl, ic))
         {
            double off = upper ? -DBL_MAX : DBL_MAX;
            for(int x = a; x <= b; x++) { double d = c[x] - (sl * x + ic); off = upper ? MathMax(off, d) : MathMin(off, d); }
            ic += off;
            if(MathAbs(sl) * (b - a) >= 0.15 * bh) { y0[u] = sl * a + ic; y1[u] = sl * b + ic; }
         }
      }
      if((y1[0] - y0[0]) * (y1[1] - y0[1]) > 0) { y0[0] = y1[0] = top; y0[1] = y1[1] = bot; }
      return 0;
   }
   if(ph[k].type == PH_CHANNEL)
   {
      bool bull = (ph[k].side == 1);
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
         x0[0] = a; y0[0] = sl * a + ic; x1[0] = b; y1[0] = sl * b + ic;
         x0[1] = a; y0[1] = sl * a + ic + par; x1[1] = b; y1[1] = sl * b + ic + par;
         return 0;
      }
   }
   x0[0] = a; x1[0] = b; y0[0] = y1[0] = top;
   x0[1] = a; x1[1] = b; y0[1] = y1[1] = bot;
   return 1;
}

//+------------------------------------------------------------------+
//| Locks (a global variable per edited / deleted line)               |
//+------------------------------------------------------------------+
string LockName(string obj) { return LCK + StringSubstr(obj, StringLen(PFX)); }
// a line you edited carries the mark in its tooltip (saved with the chart); a line you deleted is remembered in a
// terminal global variable
bool   Locked(string obj)
{
   if(ObjectFind(0, obj) >= 0 && StringFind(ObjectGetString(0, obj, OBJPROP_TOOLTIP), "edited") == 0) return true;
   return GlobalVariableCheck(LockName(obj));
}
void   Lock(string obj)
{
   if(ObjectFind(0, obj) >= 0) ObjectSetString(0, obj, OBJPROP_TOOLTIP, "edited by you (locked)");
   GlobalVariableSet(LockName(obj), 1);
}
void   ClearLocks()         { GlobalVariablesDeleteAll(LCK); }

long Visibility()
{
   long f = 0;
   if(InpShowM1)  f |= OBJ_PERIOD_M1 | OBJ_PERIOD_M2 | OBJ_PERIOD_M3 | OBJ_PERIOD_M4;
   if(InpShowM5)  f |= OBJ_PERIOD_M5 | OBJ_PERIOD_M6 | OBJ_PERIOD_M10 | OBJ_PERIOD_M12;
   if(InpShowM15) f |= OBJ_PERIOD_M15 | OBJ_PERIOD_M20;
   if(InpShowM30) f |= OBJ_PERIOD_M30;
   if(InpShowH1)  f |= OBJ_PERIOD_H1 | OBJ_PERIOD_H2 | OBJ_PERIOD_H3;
   if(InpShowH4)  f |= OBJ_PERIOD_H4 | OBJ_PERIOD_H6 | OBJ_PERIOD_H8 | OBJ_PERIOD_H12;
   if(InpShowD1)  f |= OBJ_PERIOD_D1 | OBJ_PERIOD_W1 | OBJ_PERIOD_MN1;
   return f == 0 ? OBJ_NO_PERIODS : f;
}

string TfName() { string s = EnumToString(TF); StringReplace(s, "PERIOD_", ""); return s; }

void Remember(string name) { int n = ArraySize(drawn); ArrayResize(drawn, n + 1); drawn[n] = name; }

void Line(string name, datetime t0, double p0, datetime t1, double p1, color col)
{
   Remember(name);
   if(Locked(name)) return;
   ObjectCreate(0, name, OBJ_TREND, 0, t0, p0, t1, p1);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, InpWidth);
   ObjectSetInteger(0, name, OBJPROP_STYLE, InpStyle);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, Visibility());
   ObjectSetString(0, name, OBJPROP_TOOLTIP, "drag or edit me: I stay as you leave me");
}

void Label(string name, datetime t, double p, string txt, color col)
{
   Remember(name);
   if(!InpLabels || Locked(name)) return;
   ObjectCreate(0, name, OBJ_TEXT, 0, t, p);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, Visibility());
}

//+------------------------------------------------------------------+
bool Update()
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, TF, 1, InpBars, r);            // closed candles of the structure timeframe
   if(n < 30) return false;                                   // data not loaded yet: try again on the next tick
   // lines the user deleted since the last update: lock them as deleted
   for(int i = 0; i < ArraySize(drawn); i++)
      if(!Locked(drawn[i]) && ObjectFind(0, drawn[i]) < 0 && (InpLabels || StringFind(drawn[i], "_lbl") < 0))
         Lock(drawn[i]);
   ArrayResize(drawn, 0);
   // remove our unlocked objects, keep the user's
   for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
   {
      string nm = ObjectName(0, i, 0, -1);
      if(StringFind(nm, PFX) == 0 && nm != BTN && !Locked(nm)) ObjectDelete(0, nm);
   }
   double c[]; datetime t[];
   ArrayResize(c, n); ArrayResize(t, n);
   for(int i = 0; i < n; i++) { c[i] = r[i].close; t[i] = r[i].time; }
   Segment(c, n);
   int sec = PeriodSeconds(TF);
   for(int k = 0; k < nph; k++)
   {
      double x0[], y0[], x1[], y1[];
      PhaseLines(c, k, x0, y0, x1, y1);
      color col = ph[k].type == PH_RANGE ? InpColRange : (ph[k].type == PH_SPIKE ? InpColSpike
                  : (ph[k].side > 0 ? InpColBull : InpColBear));
      string kind = ph[k].type == PH_RANGE ? "TRADING RANGE" : (ph[k].type == PH_SPIKE
                    ? (ph[k].side > 0 ? "SPIKE UP" : "SPIKE DOWN") : (ph[k].side > 0 ? "BULL CHANNEL" : "BEAR CHANNEL"));
      string base = PFX + IntegerToString((long)t[ph[k].start]) + "_" + IntegerToString(ph[k].type) + "_";
      bool lastPh = (k == nph - 1);
      for(int u = 0; u < 2; u++)
      {
         datetime ta = t[(int)x0[u]];
         datetime tb = lastPh ? t[n-1] + sec : t[(int)x1[u]];          // the last structure runs to now
         double pb = y1[u];
         if(lastPh && x1[u] != x0[u]) pb = y0[u] + (y1[u] - y0[u]) / (x1[u] - x0[u]) * (n - x0[u]);
         Line(base + (u == 0 ? "a" : "b"), ta, y0[u], tb, pb, col);
      }
      Label(base + "lbl", t[ph[k].start], MathMax(y0[0], y0[1]), TfName() + " · " + kind, col);
   }
   ChartRedraw();
   return true;
}

void MakeButton()
{
   if(!InpButton) { ObjectDelete(0, BTN); return; }
   if(ObjectFind(0, BTN) < 0) ObjectCreate(0, BTN, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, BTN, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, BTN, OBJPROP_XDISTANCE, 130);
   ObjectSetInteger(0, BTN, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, BTN, OBJPROP_XSIZE, 120);
   ObjectSetInteger(0, BTN, OBJPROP_YSIZE, 22);
   ObjectSetString(0, BTN, OBJPROP_TEXT, "Redraw " + TfName() + " structure");
   ObjectSetInteger(0, BTN, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, BTN, OBJPROP_SELECTABLE, false);
}

int OnInit()
{
   TF = (InpTF == PERIOD_CURRENT) ? (ENUM_TIMEFRAMES)_Period : InpTF;
   PFX = "GST_" + TfName() + "_";
   BTN = PFX + "btn";
   LCK = "GSTL" + IntegerToString(ChartID() % 100000) + "_" + TfName() + "_";
   IndicatorSetString(INDICATOR_SHORTNAME, "Market Structure " + TfName());
   lastStructBar = 0;
   MakeButton();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(reason == REASON_REMOVE)                  // indicator removed: take everything away, forget the edits
   { ObjectsDeleteAll(0, PFX); ClearLocks(); }
   // timeframe change / settings change: the lines and your edits stay on the chart
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   datetime b = iTime(_Symbol, TF, 0);
   if(b != 0 && b != lastStructBar && Update()) lastStructBar = b;   // once per new candle of the structure TF
   return(rates_total);
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(StringFind(sparam, PFX) != 0) return;
   if(id == CHARTEVENT_OBJECT_CLICK && sparam == BTN)
   {
      ObjectSetInteger(0, BTN, OBJPROP_STATE, false);
      ClearLocks();                              // the redraw also deletes the edited lines, so their marks go too
      for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
      { string nm = ObjectName(0, i, 0, -1); if(StringFind(nm, PFX) == 0 && nm != BTN) ObjectDelete(0, nm); }
      ArrayResize(drawn, 0);
      Update();
      return;
   }
   if((id == CHARTEVENT_OBJECT_DRAG || id == CHARTEVENT_OBJECT_CHANGE || id == CHARTEVENT_OBJECT_ENDEDIT) && sparam != BTN)
      Lock(sparam);                              // the user moved or edited this line: keep it as it is
}
//+------------------------------------------------------------------+
