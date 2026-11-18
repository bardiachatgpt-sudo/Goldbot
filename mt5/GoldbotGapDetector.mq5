//+------------------------------------------------------------------+
//| GoldbotGapDetector.mq5                                           |
//| Draws the gaps of the chart's own timeframe (any timeframe).     |
//| Same rule as the Goldbot bot and the GoldbotGapEA expert:        |
//|  Bearish gap: 3 bearish candles, candle 1 low > candle 3 high,   |
//|  and the body of candle 2 crosses that space.                    |
//|  Bullish gap: 3 bullish candles, candle 1 high < candle 3 low,   |
//|  body of candle 2 crosses that space.                            |
//| Chained gaps right behind the first one (2-3-4, 3-4-5 ...) can   |
//| be hidden or shown.                                              |
//+------------------------------------------------------------------+
#property copyright "Goldbot"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

input int    InpLastGaps    = 5;               // How many of the latest gaps to show (0 = all in the scanned candles)
input int    InpBars        = 3000;            // How many candles back to scan
input color  InpBearColor   = clrMistyRose;    // Bearish gap colour
input color  InpBullColor   = clrHoneydew;     // Bullish gap colour
input color  InpBearBorder  = clrTomato;       // Bearish gap border
input color  InpBullBorder  = clrMediumSeaGreen; // Bullish gap border
input bool   InpFill        = true;            // Fill the gap box
input int    InpExtend      = 0;               // Extend the box to the right (candles, 0 = only candles 1-3)
input bool   InpShowChained = false;           // Also draw chained gaps (2-3-4, 3-4-5 ...)
input bool   InpLabels      = false;           // Write "Bearish gap" / "Bullish gap" next to the box
input color  InpLabelColor  = clrDimGray;      // Label colour
input bool   InpAlert       = false;           // Alert when a new gap forms (popup)
input bool   InpPush        = false;           // Push notification to MT5 mobile

string   PFX;
datetime lastAlert = 0;

int OnInit()
{
   PFX = "GGD_" + IntegerToString(ChartID()) + "_" + EnumToString(_Period) + "_";
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, PFX);
}

// side of the gap whose candle 3 is at chronological index i: -1 bearish, +1 bullish, 0 none
int Gap(const double &o[], const double &h[], const double &l[], const double &c[], int i, double &hi, double &lo)
{
   if(i < 2) return 0;
   double bLo = MathMin(o[i-1], c[i-1]), bHi = MathMax(o[i-1], c[i-1]);
   bool red   = (c[i-2] < o[i-2] && c[i-1] < o[i-1] && c[i] < o[i]);
   bool green = (c[i-2] > o[i-2] && c[i-1] > o[i-1] && c[i] > o[i]);
   if(red && l[i-2] > h[i])
   { lo = h[i]; hi = l[i-2]; if(MathMax(lo, bLo) < MathMin(hi, bHi)) return -1; }
   if(green && h[i-2] < l[i])
   { lo = h[i-2]; hi = l[i]; if(MathMax(lo, bLo) < MathMin(hi, bHi)) return 1; }
   return 0;
}

void Draw(int side, datetime t1, datetime t2, double hi, double lo)
{
   string name = PFX + TimeToString(t1, TIME_DATE | TIME_MINUTES);
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, hi, t2, lo);
   else
   { ObjectMove(0, name, 0, t1, hi); ObjectMove(0, name, 1, t2, lo); }
   ObjectSetInteger(0, name, OBJPROP_COLOR, InpFill ? (side < 0 ? InpBearColor : InpBullColor)
                                                    : (side < 0 ? InpBearBorder : InpBullBorder));
   ObjectSetInteger(0, name, OBJPROP_FILL, InpFill);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   if(InpFill)                                      // a thin border in the stronger colour
   {
      string b = name + "_b";
      if(ObjectFind(0, b) < 0) ObjectCreate(0, b, OBJ_RECTANGLE, 0, t1, hi, t2, lo);
      else { ObjectMove(0, b, 0, t1, hi); ObjectMove(0, b, 1, t2, lo); }
      ObjectSetInteger(0, b, OBJPROP_COLOR, side < 0 ? InpBearBorder : InpBullBorder);
      ObjectSetInteger(0, b, OBJPROP_FILL, false);
      ObjectSetInteger(0, b, OBJPROP_BACK, false);
      ObjectSetInteger(0, b, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, b, OBJPROP_HIDDEN, true);
   }
   if(InpLabels)
   {
      string t = name + "_t";
      if(ObjectFind(0, t) < 0) ObjectCreate(0, t, OBJ_TEXT, 0, t2, side < 0 ? lo : hi);
      else ObjectMove(0, t, 0, t2, side < 0 ? lo : hi);
      ObjectSetString(0, t, OBJPROP_TEXT, side < 0 ? " Bearish gap" : " Bullish gap");
      ObjectSetInteger(0, t, OBJPROP_COLOR, InpLabelColor);
      ObjectSetInteger(0, t, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, t, OBJPROP_ANCHOR, side < 0 ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
      ObjectSetInteger(0, t, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, t, OBJPROP_HIDDEN, true);
   }
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   if(rates_total < 4) return(rates_total);
   // redraw only when a candle has closed (or on the first run); the forming candle (rates_total-1) is ignored
   if(prev_calculated == rates_total) return(rates_total);
   int last = rates_total - 2;
   int from = MathMax(2, last - InpBars);
   int sec = PeriodSeconds(_Period);
   // every gap in the scanned candles, oldest first
   int gi[]; int gs[]; double gh[]; double gl[]; int n = 0;
   int lastSide[2] = {-100, -100};                  // [0] bearish, [1] bullish: candle 3 of the last gap
   for(int i = from; i <= last; i++)
   {
      double hi, lo;
      int side = Gap(open, high, low, close, i, hi, lo);
      if(side == 0) continue;
      int k = side < 0 ? 0 : 1;
      bool chained = (i - 2 <= lastSide[k]);
      lastSide[k] = i;
      if(chained && !InpShowChained) continue;
      ArrayResize(gi, n + 1); ArrayResize(gs, n + 1); ArrayResize(gh, n + 1); ArrayResize(gl, n + 1);
      gi[n] = i; gs[n] = side; gh[n] = hi; gl[n] = lo; n++;
   }
   // draw only the latest N gaps (counted back from the live market)
   ObjectsDeleteAll(0, PFX);
   int first = (InpLastGaps > 0) ? MathMax(0, n - InpLastGaps) : 0;
   for(int g = first; g < n; g++)
   {
      int i = gi[g];
      int endIdx = MathMin(i + InpExtend, rates_total - 1);
      datetime t2 = time[endIdx] + (endIdx == i ? sec : 0);
      Draw(gs[g], time[i-2], t2, gh[g], gl[g]);
   }
   // alert when the candle that just closed completed a gap
   if(prev_calculated > 0 && n > 0 && gi[n-1] == last && time[last] != lastAlert)
   {
      lastAlert = time[last];
      string msg = StringFormat("%s %s: %s gap", _Symbol, EnumToString(_Period), gs[n-1] < 0 ? "Bearish" : "Bullish");
      if(InpAlert) Alert(msg);
      if(InpPush) SendNotification(msg);
   }
   return(rates_total);
}
//+------------------------------------------------------------------+
