//+------------------------------------------------------------------+
//| StructureIndicator.mq5 — Market Structure Indicator              |
//| Draws the 5-MINUTE market structure (spike / channel / trading   |
//| range, on closes; same algorithm as the Goldbot Telegram bot),   |
//| visible on every chart timeframe. Optional: the 1-minute         |
//| structure too, visible only on the 1-minute chart, inside the    |
//| 5-minute one. No other structures are drawn.                     |
//| Every line is an ordinary MT5 trend line: move it, recolour it,  |
//| delete it. A line you change or delete is LOCKED: when new       |
//| candles come and the structure is recalculated, it stays as you  |
//| left it. The "Redraw" button clears your edits.                  |
//+------------------------------------------------------------------+
#property copyright "Market Structure Indicator"
#property description "5-minute market structure on every timeframe (+ optional 1-minute structure on M1); editable lines."
#property version   "1.10"
#property indicator_chart_window
#property indicator_plots 0

input int             InpBars5     = 500;           // 5-min candles used
input bool            InpShowM1    = false;         // Also draw the 1-minute structure (seen only on M1)
input int             InpBars1     = 500;           // 1-min candles used
input group           "5-minute structure"
input color           InpColRange5 = clrSteelBlue;  // Trading range
input color           InpColBull5  = clrSeaGreen;   // Bull channel
input color           InpColBear5  = clrCrimson;    // Bear channel
input color           InpColSpike5 = clrDarkOrange; // Spike
input int             InpWidth5    = 2;             // Line width
input ENUM_LINE_STYLE InpStyle5    = STYLE_SOLID;   // Line style
input group           "1-minute structure"
input color           InpColRange1 = clrLightSkyBlue; // Trading range
input color           InpColBull1  = clrMediumAquamarine; // Bull channel
input color           InpColBear1  = clrLightCoral; // Bear channel
input color           InpColSpike1 = clrSandyBrown; // Spike
input int             InpWidth1    = 1;             // Line width
input ENUM_LINE_STYLE InpStyle1    = STYLE_DASH;    // Line style
input group           "Other"
input bool            InpLabels    = true;          // Write the structure's name
input bool            InpButton    = true;          // Show the "Redraw" button

string   BTN = "GST_btn";
string   LCKBASE;
// two structures: 0 = 5-minute (all timeframes), 1 = 1-minute (only on M1)
string   PFX[2]  = {"GST_M5_", "GST_M1_"};
string   NAME[2] = {"M5", "M1"};
ENUM_TIMEFRAMES STF[2] = {PERIOD_M5, PERIOD_M1};
datetime lastBar[2] = {0, 0};
string   drawn0[], drawn1[];   // names drawn by the last update (to notice lines the user deleted)
int      S = 0;                // structure being drawn

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
//| Locks: an edited line carries "edited" in its tooltip (saved with |
//| the chart); a deleted one is remembered in a global variable      |
//+------------------------------------------------------------------+
string LockName(string obj) { return LCKBASE + obj; }
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
void   ClearLocks() { GlobalVariablesDeleteAll(LCKBASE); }

long Visibility() { return S == 0 ? OBJ_ALL_PERIODS : OBJ_PERIOD_M1; }

void Remember(string name)
{
   if(S == 0) { int n = ArraySize(drawn0); ArrayResize(drawn0, n + 1); drawn0[n] = name; }
   else       { int n = ArraySize(drawn1); ArrayResize(drawn1, n + 1); drawn1[n] = name; }
}

void Line(string name, datetime t0, double p0, datetime t1, double p1, color col)
{
   Remember(name);
   if(Locked(name)) return;
   ObjectCreate(0, name, OBJ_TREND, 0, t0, p0, t1, p1);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, S == 0 ? InpWidth5 : InpWidth1);
   ObjectSetInteger(0, name, OBJPROP_STYLE, S == 0 ? InpStyle5 : InpStyle1);
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

void DeleteOurs(bool lockedToo)
{
   for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
   {
      string nm = ObjectName(0, i, 0, -1);
      if(StringFind(nm, PFX[S]) == 0 && (lockedToo || !Locked(nm))) ObjectDelete(0, nm);
   }
}

//+------------------------------------------------------------------+
bool Update(int s)
{
   S = s;
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, STF[S], 1, S == 0 ? InpBars5 : InpBars1, r);   // closed candles only
   if(n < 30) return false;                                   // data not loaded yet: try again on the next tick
   // lines the user deleted since the last update: lock them as deleted
   int nd = S == 0 ? ArraySize(drawn0) : ArraySize(drawn1);
   for(int i = 0; i < nd; i++)
   {
      string d = S == 0 ? drawn0[i] : drawn1[i];
      if(!Locked(d) && ObjectFind(0, d) < 0 && (InpLabels || StringFind(d, "_lbl") < 0)) Lock(d);
   }
   if(S == 0) ArrayResize(drawn0, 0); else ArrayResize(drawn1, 0);
   DeleteOurs(false);                                         // our unlocked lines go; the user's stay
   double c[]; datetime t[];
   ArrayResize(c, n); ArrayResize(t, n);
   for(int i = 0; i < n; i++) { c[i] = r[i].close; t[i] = r[i].time; }
   Segment(c, n);
   int sec = PeriodSeconds(STF[S]);
   for(int k = 0; k < nph; k++)
   {
      double x0[], y0[], x1[], y1[];
      PhaseLines(c, k, x0, y0, x1, y1);
      color col;
      if(S == 0) col = ph[k].type == PH_RANGE ? InpColRange5 : (ph[k].type == PH_SPIKE ? InpColSpike5
                       : (ph[k].side > 0 ? InpColBull5 : InpColBear5));
      else       col = ph[k].type == PH_RANGE ? InpColRange1 : (ph[k].type == PH_SPIKE ? InpColSpike1
                       : (ph[k].side > 0 ? InpColBull1 : InpColBear1));
      string kind = ph[k].type == PH_RANGE ? "TRADING RANGE" : (ph[k].type == PH_SPIKE
                    ? (ph[k].side > 0 ? "SPIKE UP" : "SPIKE DOWN") : (ph[k].side > 0 ? "BULL CHANNEL" : "BEAR CHANNEL"));
      string base = PFX[S] + IntegerToString((long)t[ph[k].start]) + "_" + IntegerToString(ph[k].type) + "_";
      bool lastPh = (k == nph - 1);
      for(int u = 0; u < 2; u++)
      {
         datetime ta = t[(int)x0[u]];
         datetime tb = lastPh ? t[n-1] + sec : t[(int)x1[u]];          // the last structure runs to now
         double pb = y1[u];
         if(lastPh && x1[u] != x0[u]) pb = y0[u] + (y1[u] - y0[u]) / (x1[u] - x0[u]) * (n - x0[u]);
         Line(base + (u == 0 ? "a" : "b"), ta, y0[u], tb, pb, col);
      }
      Label(base + "lbl", t[ph[k].start], MathMax(y0[0], y0[1]), NAME[S] + " · " + kind, col);
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
   ObjectSetString(0, BTN, OBJPROP_TEXT, "Redraw structure");
   ObjectSetInteger(0, BTN, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, BTN, OBJPROP_SELECTABLE, false);
}

int OnInit()
{
   LCKBASE = "GSTL" + IntegerToString(ChartID() % 100000) + "_";
   IndicatorSetString(INDICATOR_SHORTNAME, "Market Structure");
   lastBar[0] = 0; lastBar[1] = 0;
   MakeButton();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(reason == REASON_REMOVE)                  // indicator removed: take everything away, forget the edits
   { ObjectsDeleteAll(0, "GST_"); ClearLocks(); }
   // timeframe change / settings change: the lines and your edits stay on the chart
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   for(int s = 0; s < 2; s++)
   {
      if(s == 1 && !InpShowM1)
      {
         if(lastBar[1] != -1) { S = 1; DeleteOurs(true); lastBar[1] = -1; }   // 1-min structure switched off
         continue;
      }
      datetime b = iTime(_Symbol, STF[s], 0);
      if(b != 0 && b != lastBar[s] && Update(s)) lastBar[s] = b;   // once per new candle of that timeframe
   }
   return(rates_total);
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(StringFind(sparam, "GST_") != 0) return;
   if(id == CHARTEVENT_OBJECT_CLICK && sparam == BTN)
   {
      ObjectSetInteger(0, BTN, OBJPROP_STATE, false);
      ClearLocks();
      for(int s = 0; s < 2; s++)
      {
         S = s; DeleteOurs(true);
         if(s == 0) ArrayResize(drawn0, 0); else ArrayResize(drawn1, 0);
         if(s == 0 || InpShowM1) Update(s);
      }
      return;
   }
   if((id == CHARTEVENT_OBJECT_DRAG || id == CHARTEVENT_OBJECT_CHANGE) && sparam != BTN)
      Lock(sparam);                              // the user moved or edited this line: keep it as it is
}
//+------------------------------------------------------------------+
