//+------------------------------------------------------------------+
//|                   Elite Autonomous Quantum Trading System        |
//|                          ForexTradingSystemEA.mq5                 |
//|                                  EA with Real-time HUD Display   |
//+------------------------------------------------------------------+
#property copyright "Elite Autonomous Quantum Trading System"
#property version   "3.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\SymbolInfo.mqh>

//+------------------------------------------------------------------+
//| Inputs — User-configurable parameters with VIBRANT COLORS          |
//+------------------------------------------------------------------+
input string  Prefix            = "EA_HUD_";      // HUD label prefix
input int     HUDEX_X           = 10;             // HUD X position
input int     HUDEX_Y           = 25;             // HUD Y position
input int     FontSize          = 10;             // HUD font size
input string  FontName          = "Consolas";     // HUD font

// Vibrant color inputs for each HUD field (all distinguishable)
input color   ColorTitle        = clrGold;         // Title bar color
input color   ColorSymbol       = clrAqua;         // Symbol name color
input color   ColorTicket       = clrMagenta;      // Ticket number color
input color   ColorType         = clrOrange;       // Buy/Sell type color
input color   ColorVolume        = clrYellow;      // Volume color
input color   ColorEntry         = clrLimeGreen;   // Entry price color
input color   ColorCurrent       = clrDeepSkyBlue;  // Current price color
input color   ColorSL            = clrTomato;      // Stop loss color
input color   ColorTP            = clrSpringGreen;  // Take profit color
input color   ColorPnLProfit     = clrLime;        // PnL when in profit (GREEN)
input color   ColorPnLLoss       = clrRed;         // PnL when in loss (RED)
input color   ColorSwap          = clrThistle;    // Swap color
input color   ColorDuration      = clrPink;        // Duration color
input color   ColorSession       = clrCyan;       // Session name color
input color   ColorSpread        = clrKhaki;      // Spread color
input color   ColorBgProfit      = clrDarkGreen;   // Background when profitable
input color   ColorBgLoss        = clrDarkRed;     // Background when losing
input color   ColorBgNeutral     = clrDarkSlateGray;// Background when flat

// Connection / Trading params
input string  PythonHost         = "127.0.0.1";
input int     HttpPort           = 8000;
input string  ZeroMQEndpoint     = "tcp://127.0.0.1:5555";
input bool    UseZeroMQ          = false;
input int     HeartbeatInterval  = 5;
input int     MaxReconnectAttempts = 10;
input int     ReconnectDelay     = 5000;
input int     ReconnectAttempts  = 3;
input int     MaxSpreadMultiplier = 3;
input double  MaxDailyLoss       = 0.05;
input double  MaxDrawdown        = 0.15;
input int     MaxOpenPositions   = 10;

//+------------------------------------------------------------------+
//| Global variables                                                 |
//+------------------------------------------------------------------+
CTrade        trade;
CPositionInfo positionInfo;
CAccountInfo  accountInfo;
CSymbolInfo   symbolInfo;

bool    g_connected      = false;
int     g_reconnectCount  = 0;
bool    g_riskLimitHit    = false;
double  g_dailyStartEquity = 0;
double  g_peakEquity       = 0;
datetime g_lastHeartbeat   = 0;
datetime g_lastDataSend    = 0;

// Session tracking
struct SessionInfo {
   string name;
   int    startHour;
   int    endHour;
   bool   active;
};
SessionInfo g_forexSessions[20];
SessionInfo g_cryptoSessions[5];
int g_forexSessionCount  = 0;
int g_cryptoSessionCount = 0;

// Symbol management
string g_allowedSymbols[100];
int    g_symbolsCount = 0;

//+------------------------------------------------------------------+
//| OnInit — EA initialization                                       |
//+------------------------------------------------------------------+
int OnInit()
{
   // Initialize account
   if(!accountInfo.Update()) {
      Print("Failed to update account info");
      return INIT_FAILED;
   }
   g_dailyStartEquity = accountInfo.Equity();
   g_peakEquity = g_dailyStartEquity;

   // Setup trade
   trade.SetExpertMagicNumber(60022138);
   trade.SetMarginMode();
   trade.SetTypeFillingBySymbol(_Symbol);

   // Load allowed symbols
   g_allowedSymbols[0] = "EURUSD"; g_allowedSymbols[1] = "GBPUSD";
   g_allowedSymbols[2] = "USDJPY"; g_allowedSymbols[3] = "XAUUSD";
   g_allowedSymbols[4] = "BTCUSD"; g_allowedSymbols[5] = "ETHUSD";
   g_symbolsCount = 6;

   // Setup forex sessions
   g_forexSessions[0].name = "Wellington"; g_forexSessions[0].startHour = 20; g_forexSessions[0].endHour = 5; g_forexSessions[0].active = false;
   g_forexSessions[1].name = "Sydney";    g_forexSessions[1].startHour = 22; g_forexSessions[1].endHour = 7;  g_forexSessions[1].active = false;
   g_forexSessions[2].name = "Tokyo";     g_forexSessions[2].startHour = 23; g_forexSessions[2].endHour = 8;  g_forexSessions[2].active = false;
   g_forexSessions[3].name = "London";   g_forexSessions[3].startHour = 7;  g_forexSessions[3].endHour = 16; g_forexSessions[3].active = false;
   g_forexSessions[4].name = "New York"; g_forexSessions[4].startHour = 12; g_forexSessions[4].endHour = 21; g_forexSessions[4].active = false;
   g_forexSessions[5].name = "Frankfurt"; g_forexSessions[5].startHour = 6; g_forexSessions[5].endHour = 15; g_forexSessions[5].active = false;
   g_forexSessions[6].name = "Hong Kong"; g_forexSessions[6].startHour = 1; g_forexSessions[6].endHour = 10; g_forexSessions[6].active = false;
   g_forexSessionCount = 7;

   // Crypto always open
   g_cryptoSessions[0].name = "Crypto 24/7"; g_cryptoSessions[0].startHour = 0; g_cryptoSessions[0].endHour = 24; g_cryptoSessions[0].active = true;
   g_cryptoSessionCount = 1;

   // Connect to Python
   if(UseZeroMQ) {
      ConnectZeroMQ();
   } else {
      ConnectHTTP();
   }

   EventSetTimer(HeartbeatInterval);
   Print("Elite Autonomous Quantum Trading System EA initialized");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnDeinit — Cleanup                                               |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   CleanupHUD();
   Disconnect();
   Print("EA deinitialized, reason: ", reason);
}

//+------------------------------------------------------------------+
//| OnTick — Main tick handler                                       |
//+------------------------------------------------------------------+
void OnTick()
{
   // Update session status
   UpdateSessions();

   // Update peak equity
   if(accountInfo.Update()) {
      double eq = accountInfo.Equity();
      if(eq > g_peakEquity) g_peakEquity = eq;
   }

   // Check risk limits
   g_riskLimitHit = !CheckRiskLimits();

   // Send market data for each tracked symbol
   datetime now = TimeCurrent();
   if(now - g_lastDataSend >= 1) {
      for(int i = 0; i < g_symbolsCount; i++) {
         SendMarketData(g_allowedSymbols[i]);
      }
      g_lastDataSend = now;
   }

   // Send positions
   SendPositions();

   // Send account info
   SendAccountInfo();

   // Draw the HUD on chart
   DrawHUD();

   // Heartbeat
   if(now - g_lastHeartbeat >= HeartbeatInterval) {
      SendHeartbeat();
      g_lastHeartbeat = now;
   }
}

//+------------------------------------------------------------------+
//| OnTimer — Heartbeat / command polling                           |
//+------------------------------------------------------------------+
void OnTimer()
{
   // Check for commands from Python
   if(UseZeroMQ) {
      CheckZeroMQCommands();
   } else {
      CheckHTTPCommands();
   }
}

//+------------------------------------------------------------------+
//| OnChartEvent — Handle chart interactions                        |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_CLICK) {
      Print("Chart clicked at: ", dparam);
   }
}

//+------------------------------------------------------------------+
//| ═════════════════════════════════════════════════════════════════ |
//|                    HUD DRAWING — VIBRANT ON-CHART DISPLAY         |
//| ═════════════════════════════════════════════════════════════════ |
//+------------------------------------------------------------------+

// Functions to create/edit labels on the chart
void CreateLabel(string name, string text, int x, int y, color clr, int fontSize, string font)
{
   string objName = Prefix + name;
   if(ObjectFind(0, objName) < 0) {
      ObjectCreate(0, objName, OBJ_LABEL, 0, 0, 0);
   }
   ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, objName, OBJPROP_TEXT, text);
   ObjectSetInteger(0, objName, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, objName, OBJPROP_FONTSIZE, fontSize);
   ObjectSetString(0, objName, OBJPROP_FONT, font);
   ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
}

// Create a rectangle (background panel)
void CreatePanel(string name, int x, int y, int width, int height, color bgClr)
{
   string objName = Prefix + name;
   if(ObjectFind(0, objName) < 0) {
      ObjectCreate(0, objName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   }
   ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, objName, OBJPROP_XSIZE, width);
   ObjectSetInteger(0, objName, OBJPROP_YSIZE, height);
   ObjectSetInteger(0, objName, OBJPROP_BGCOLOR, bgClr);
   ObjectSetInteger(0, objName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, objName, OBJPROP_COLOR, clrDarkGray);
   ObjectSetInteger(0, objName, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, objName, OBJPROP_BACK, false);
}

// Remove all HUD objects
void CleanupHUD()
{
   int total = ObjectsTotal(0, -1, OBJ_LABEL) + ObjectsTotal(0, -1, OBJ_RECTANGLE_LABEL);
   for(int i = total - 1; i >= 0; i--) {
      string name = ObjectName(0, i, -1, OBJ_LABEL);
      if(StringFind(name, Prefix) == 0) ObjectDelete(0, name);
      name = ObjectName(0, i, -1, OBJ_RECTANGLE_LABEL);
      if(StringFind(name, Prefix) == 0) ObjectDelete(0, name);
   }
}

// Get active session name
string GetActiveSession()
{
   for(int i = 0; i < g_forexSessionCount; i++) {
      if(g_forexSessions[i].active) return g_forexSessions[i].name;
   }
   for(int i = 0; i < g_cryptoSessionCount; i++) {
      if(g_cryptoSessions[i].active) return g_cryptoSessions[i].name;
   }
   return "NONE";
}

// Format time duration
string FormatDuration(datetime startTime)
{
   datetime now = TimeCurrent();
   int totalSec = (int)(now - startTime);
   int days = totalSec / 86400;
   int hours = (totalSec % 86400) / 3600;
   int mins = (totalSec % 3600) / 60;
   int secs = totalSec % 60;
   string result = "";
   if(days > 0) result += IntegerToString(days) + "d ";
   if(hours > 0) result += IntegerToString(hours) + "h ";
   if(mins > 0) result += IntegerToString(mins) + "m ";
   result += IntegerToString(secs) + "s";
   return result;
}

//+------------------------------------------------------------------+
//| DrawHUD — Main HUD drawing function with VIBRANT COLORS         |
//+------------------------------------------------------------------+
void DrawHUD()
{
   if(!accountInfo.Update()) return;

   double equity   = accountInfo.Equity();
   double balance  = accountInfo.Balance();
   double margin   = accountInfo.Margin();
   double freeMarg = accountInfo.FreeMargin();
   double marginLvl = accountInfo.MarginLevel();
   double profit   = accountInfo.Profit();
   double dailyPnL = equity - g_dailyStartEquity;

   // Determine overall PnL color
   color pnlColor  = (profit >= 0) ? ColorPnLProfit : ColorPnLLoss;
   color dailyColor = (dailyPnL >= 0) ? ColorPnLProfit : ColorPnLLoss;
   color bgColor    = (profit > 0) ? ColorBgProfit : (profit < 0 ? ColorBgLoss : ColorBgNeutral);

   int panelY = HUDEX_Y;
   int panelH = 0;
   int panelW = 380;

   // ── Title bar ─────────────────────────────────────────────────────
   panelH += 28;
   CreatePanel("TitlePanel", HUDEX_X, panelY, panelW, 28, clrNavy);
   CreateLabel("L_Title", "🧠 ELITE AUTONOMOUS QUANTUM TRADING SYSTEM", HUDEX_X + 8, panelY + 6, ColorTitle, 11, FontName);
   panelY += 30;

   // ── Account overview line ────────────────────────────────────────
   panelH += 24;
   CreatePanel("AcctPanel", HUDEX_X, panelY, panelW, 24, clrBlack);
   CreateLabel("L_Equity", "Equity: $" + DoubleToString(equity, 2),
      HUDEX_X + 8, panelY + 5, ColorPnLProfit if equity >= balance else ColorPnLLoss, FontSize, FontName);
   CreateLabel("L_Balance", "Bal: $" + DoubleToString(balance, 2),
      HUDEX_X + 180, panelY + 5, clrPaleGreen, FontSize, FontName);
   panelY += 26;

   // ── Daily PnL ──────────────────────────────────────────────────────
   panelH += 22;
   CreatePanel("DailyPanel", HUDEX_X, panelY, panelW, 22, bgColor);
   CreateLabel("L_DailyPnL",
      "Daily PnL: $" + DoubleToString(dailyPnL, 2) + " (" + DoubleToString(dailyPnL / g_dailyStartEquity * 100, 2) + "%)",
      HUDEX_X + 8, panelY + 3, dailyColor, FontSize, FontName);
   panelY += 24;

   // ── Floating PnL ──────────────────────────────────────────────────
   panelH += 22;
   CreatePanel("FloatPanel", HUDEX_X, panelY, panelW, 22, bgColor);
   CreateLabel("L_FloatPnL",
      "Floating PnL: $" + DoubleToString(profit, 2),
      HUDEX_X + 8, panelY + 3, pnlColor, FontSize, FontName);
   panelY += 24;

   // ── Margin info ───────────────────────────────────────────────────
   panelH += 22;
   CreatePanel("MarginPanel", HUDEX_X, panelY, panelW, 22, clrDarkSlateBlue);
   CreateLabel("L_Margin",
      "Margin: $" + DoubleToString(margin, 2) + "  Free: $" + DoubleToString(freeMarg, 2) +
      "  Level: " + DoubleToString(marginLvl, 1) + "%",
      HUDEX_X + 8, panelY + 3, clrLightBlue, FontSize, FontName);
   panelY += 24;

   // ── Active session ────────────────────────────────────────────────
   panelH += 22;
   string activeSession = GetActiveSession();
   CreatePanel("SessionPanel", HUDEX_X, panelY, panelW, 22, clrDarkCyan);
   CreateLabel("L_Session",
      "Session: " + activeSession + "  |  Positions: " + IntegerToString(PositionsTotal()) + "/" + IntegerToString(MaxOpenPositions),
      HUDEX_X + 8, panelY + 3, ColorSession, FontSize, FontName);
   panelY += 24;

   // ── Divider ───────────────────────────────────────────────────────
   panelH += 4;
   panelY += 4;

   // ── Positions list with INDIVIDUAL FIELD COLORS ────────────────────
   int posCount = PositionsTotal();
   for(int i = 0; i < posCount && i < 10; i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!positionInfo.SelectByTicket(ticket)) continue;

      string sym      = positionInfo.Symbol();
      string posType  = (positionInfo.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      double vol      = positionInfo.Volume();
      double entry    = positionInfo.PriceOpen();
      double current  = positionInfo.PriceCurrent();
      double sl       = positionInfo.StopLoss();
      double tp       = positionInfo.TakeProfit();
      double posPnL   = positionInfo.Profit();
      double posSwap  = positionInfo.Swap();
      datetime timeO  = positionInfo.TimeOpen();
      string durStr   = FormatDuration(timeO);

      // PnL color for this position
      color posPnLClr = (posPnL >= 0) ? ColorPnLProfit : ColorPnLLoss;
      color posBgClr  = (posPnL > 0) ? ColorBgProfit : (posPnL < 0 ? ColorBgLoss : ColorBgNeutral);

      panelH += 18;
      CreatePanel("PosPanel" + IntegerToString(i), HUDEX_X, panelY, panelW, 18, posBgClr);

      int xOff = HUDEX_X + 5;

      // Ticket number (Magenta)
      CreateLabel("L_T" + IntegerToString(i), "#" + IntegerToString((int)ticket),
         xOff, panelY + 2, ColorTicket, 9, FontName);
      xOff += 50;

      // Symbol name (Aqua)
      CreateLabel("L_Sym" + IntegerToString(i), sym,
         xOff, panelY + 2, ColorSymbol, 9, FontName);
      xOff += 55;

      // Type (Orange)
      CreateLabel("L_Type" + IntegerToString(i), posType,
         xOff, panelY + 2, ColorType, 9, FontName);
      xOff += 35;

      // Volume (Yellow)
      CreateLabel("L_Vol" + IntegerToString(i), DoubleToString(vol, 2),
         xOff, panelY + 2, ColorVolume, 9, FontName);
      xOff += 35;

      // Entry price (LimeGreen)
      CreateLabel("L_Ent" + IntegerToString(i), DoubleToString(entry, 5),
         xOff, panelY + 2, ColorEntry, 9, FontName);
      xOff += 55;

      // PnL (Green/Red based on profit/loss)
      CreateLabel("L_PnL" + IntegerToString(i),
         "$" + DoubleToString(posPnL, 2),
         xOff, panelY + 2, posPnLClr, 9, FontName);
      xOff += 50;

      // Duration (Pink)
      CreateLabel("L_Dur" + IntegerToString(i), durStr,
         xOff, panelY + 2, ColorDuration, 9, FontName);

      panelY += 20;

      // Detail row: SL/TP/Current/Swap
      panelH += 14;
      CreatePanel("PosDetail" + IntegerToString(i), HUDEX_X, panelY, panelW, 14, clrBlack);

      int xOff2 = HUDEX_X + 5;
      // Entry (LimeGreen)
      CreateLabel("L_DEnt" + IntegerToString(i), "E:" + DoubleToString(entry, 5),
         xOff2, panelY + 1, ColorEntry, 8, FontName);
      xOff2 += 52;

      // Current (DeepSkyBlue)
      CreateLabel("L_DCurr" + IntegerToString(i), "C:" + DoubleToString(current, 5),
         xOff2, panelY + 1, ColorCurrent, 8, FontName);
      xOff2 += 52;

      // SL (Tomato)
      CreateLabel("L_DSL" + IntegerToString(i), "SL:" + DoubleToString(sl, 5),
         xOff2, panelY + 1, ColorSL, 8, FontName);
      xOff2 += 52;

      // TP (SpringGreen)
      CreateLabel("L_DTP" + IntegerToString(i), "TP:" + DoubleToString(tp, 5),
         xOff2, panelY + 1, ColorTP, 8, FontName);
      xOff2 += 52;

      // Swap (Thistle)
      CreateLabel("L_DSwap" + IntegerToString(i), "S:" + DoubleToString(posSwap, 2),
         xOff2, panelY + 1, ColorSwap, 8, FontName);

      panelY += 16;
      panelH += 14;
   }

   // ── No positions state ───────────────────────────────────────────
   if(posCount == 0) {
      panelH += 22;
      CreatePanel("NoPosPanel", HUDEX_X, panelY, panelW, 22, clrDarkViolet);
      CreateLabel("L_NoPos", "📊 No Active Positions — AI Brain Monitoring",
         HUDEX_X + 8, panelY + 3, clrLavender, FontSize, FontName);
      panelY += 24;
   }

   // ── Footer: status + risk ──────────────────────────────────────────
   panelH += 18;
   color footerBg = g_riskLimitHit ? clrMaroon : clrDarkGreen;
   CreatePanel("FooterPanel", HUDEX_X, panelY, panelW, 18, footerBg);

   string statusStr = "● CONNECTED";
   if(!g_connected) statusStr = "● DISCONNECTED";
   if(g_riskLimitHit) statusStr = "⚠ RISK LIMIT HIT";
   if(UseZeroMQ) statusStr += " [ZMQ]"; else statusStr += " [HTTP]";

   CreateLabel("L_Status", statusStr,
      HUDEX_X + 8, panelY + 2,
      g_riskLimitHit ? ColorPnLLoss : ColorPnLProfit, 9, FontName);
}

//+------------------------------------------------------------------+
//| Check risk limits                                                |
//+------------------------------------------------------------------+
bool CheckRiskLimits()
{
   if(!accountInfo.Update()) return true;

   double equity = accountInfo.Equity();
   double balance = accountInfo.Balance();

   // Daily loss check
   double dailyLoss = (g_dailyStartEquity - equity) / g_dailyStartEquity;
   if(dailyLoss > MaxDailyLoss) {
      Print("RISK LIMIT: Daily loss exceeded: ", DoubleToString(dailyLoss * 100, 2), "% > ", DoubleToString(MaxDailyLoss * 100, 2), "%");
      return false;
   }

   // Drawdown check
   if(g_peakEquity > 0) {
      double drawdown = (g_peakEquity - equity) / g_peakEquity;
      if(drawdown > MaxDrawdown) {
         Print("RISK LIMIT: Max drawdown exceeded: ", DoubleToString(drawdown * 100, 2), "% > ", DoubleToString(MaxDrawdown * 100, 2), "%");
         return false;
      }
   }

   // Max positions check
   if(PositionsTotal() >= MaxOpenPositions) {
      Print("RISK LIMIT: Max open positions reached: ", PositionsTotal());
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Update trading sessions                                          |
//+------------------------------------------------------------------+
void UpdateSessions()
{
   int currentHour = TimeHour(TimeCurrent());

   // Update forex sessions
   for(int i = 0; i < g_forexSessionCount; i++) {
      bool wasActive = g_forexSessions[i].active;

      // Handle overnight sessions (Sydney: 22-7)
      if(g_forexSessions[i].startHour > g_forexSessions[i].endHour) {
         g_forexSessions[i].active = (currentHour >= g_forexSessions[i].startHour || currentHour < g_forexSessions[i].endHour);
      } else {
         g_forexSessions[i].active = (currentHour >= g_forexSessions[i].startHour && currentHour < g_forexSessions[i].endHour);
      }

      if(wasActive != g_forexSessions[i].active) {
         Print("Session ", g_forexSessions[i].name, " ", g_forexSessions[i].active ? "STARTED" : "ENDED");
      }
   }

   // Crypto always active
   for(int i = 0; i < g_cryptoSessionCount; i++) {
      g_cryptoSessions[i].active = true;
   }
}

//+------------------------------------------------------------------+
//| Send market data (tick) to Python                               |
//+------------------------------------------------------------------+
void SendMarketData(const string &symbol)
{
   if(!SymbolSelect(symbol, true)) return;

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick)) return;

   // Check spread
   double spread = (tick.ask - tick.bid) / SymbolInfoDouble(symbol, SYMBOL_POINT);
   double avgSpread = SymbolInfoDouble(symbol, SYMBOL_SPREAD);
   if(spread > avgSpread * MaxSpreadMultiplier) {
      return; // Spread too wide
   }

   // Get symbol info for trade style hints
   string tradeStyle = GetTradeStyleForSymbol(symbol);

   string json = JsonObjectStart();
   json += JsonEncode("type", "market_data") + ",";
   json += JsonEncode("symbol", symbol) + ",";
   json += JsonEncode("bid", tick.bid) + ",";
   json += JsonEncode("ask", tick.ask) + ",";
   json += JsonEncode("last", tick.last) + ",";
   json += JsonEncode("volume", tick.volume) + ",";
   json += JsonEncode("time", tick.time) + ",";
   json += JsonEncode("time_msc", tick.time_msc) + ",";
   json += JsonEncode("flags", tick.flags) + ",";
   json += JsonEncode("volume_real", tick.volume_real) + ",";
   json += JsonEncode("spread_pips", spread) + ",";
   json += JsonEncode("trade_style", tradeStyle);
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Determine trade style for symbol                                 |
//+------------------------------------------------------------------+
string GetTradeStyleForSymbol(const string &symbol)
{
   // Simple heuristic based on symbol
   if(StringFind(symbol, "XAU") != -1 || StringFind(symbol, "XAG") != -1) {
      return "swing_trading"; // Metals tend to trend
   }
   if(StringFind(symbol, "JPY") != -1) {
      return "scalping"; // JPY pairs good for scalping
   }
   if(StringFind(symbol, "BTC") != -1 || StringFind(symbol, "ETH") != -1) {
      return "day_trading"; // Crypto volatile
   }
   return "day_trading"; // Default
}

//+------------------------------------------------------------------+
//| Send Level 2 (Depth of Market) data                             |
//+------------------------------------------------------------------+
void SendLevel2Data(const string &symbol)
{
   // Get DOM data
   MqlBookInfo bookArray[];
   if(!MarketBookGet(symbol, bookArray)) return;

   string json = JsonObjectStart();
   json += JsonEncode("type", "level2_data") + ",";
   json += JsonEncode("symbol", symbol) + ",";
   json += JsonEncode("timestamp", TimeCurrent()) + ",";

   // Build bids array
   json += "\"bids\":[";
   bool firstBid = true;
   for(int i = 0; i < ArraySize(bookArray); i++) {
      if(bookArray[i].type == BOOK_TYPE_BUY) { // Bid
         if(!firstBid) json += ",";
         firstBid = false;
         json += JsonObjectStart();
         json += JsonEncode("price", bookArray[i].price) + ",";
         json += JsonEncode("volume", bookArray[i].volume);
         json += JsonObjectEnd();
      }
   }
   json += "],";

   // Build asks array
   json += "\"asks\":[";
   bool firstAsk = true;
   for(int i = 0; i < ArraySize(bookArray); i++) {
      if(bookArray[i].type == BOOK_TYPE_SELL) { // Ask
         if(!firstAsk) json += ",";
         firstAsk = false;
         json += JsonObjectStart();
         json += JsonEncode("price", bookArray[i].price) + ",";
         json += JsonEncode("volume", bookArray[i].volume);
         json += JsonObjectEnd();
      }
   }
   json += "]}";

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Send account information                                        |
//+------------------------------------------------------------------+
void SendAccountInfo()
{
   if(!accountInfo.Update()) return;

   double equity = accountInfo.Equity();
   double dailyPnL = equity - g_dailyStartEquity;
   double drawdown = g_peakEquity > 0 ? (g_peakEquity - equity) / g_peakEquity : 0;

   string json = JsonObjectStart();
   json += JsonEncode("type", "account_info") + ",";
   json += JsonEncode("login", accountInfo.Login()) + ",";
   json += JsonEncode("balance", accountInfo.Balance()) + ",";
   json += JsonEncode("equity", equity) + ",";
   json += JsonEncode("profit", accountInfo.Profit()) + ",";
   json += JsonEncode("margin", accountInfo.Margin()) + ",";
   json += JsonEncode("free_margin", accountInfo.MarginFree()) + ",";
   json += JsonEncode("margin_level", accountInfo.MarginLevel()) + ",";
   json += JsonEncode("leverage", accountInfo.Leverage()) + ",";
   json += JsonEncode("currency", accountInfo.Currency()) + ",";
   json += JsonEncode("name", accountInfo.Name()) + ",";
   json += JsonEncode("server", accountInfo.Server()) + ",";
   json += JsonEncode("trade_allowed", accountInfo.TradeAllowed()) + ",";
   json += JsonEncode("trade_expert", accountInfo.TradeExpert()) + ",";
   json += JsonEncode("daily_pnl", dailyPnL) + ",";
   json += JsonEncode("drawdown_pct", drawdown) + ",";
   json += JsonEncode("daily_loss_pct", g_dailyStartEquity > 0 ? -dailyPnL / g_dailyStartEquity : 0) + ",";
   json += JsonEncode("peak_equity", g_peakEquity);
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Send open positions                                             |
//+------------------------------------------------------------------+
void SendPositions()
{
   string json = JsonObjectStart();
   json += JsonEncode("type", "positions") + ",";
   json += JsonEncode("count", (double)PositionsTotal()) + ",";
   json += JsonArrayStart() + "\"positions\":[";

   bool first = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      if(!positionInfo.SelectByTicket(ticket)) continue;

      if(!first) json += ",";
      first = false;

      // Calculate hold time
      datetime timeOpen = positionInfo.TimeOpen();
      int holdSeconds = (int)(TimeCurrent() - timeOpen);

      // Current risk/reward
      double sl = positionInfo.StopLoss();
      double tp = positionInfo.TakeProfit();
      double currentPrice = positionInfo.PriceCurrent();
      double entryPrice = positionInfo.PriceOpen();
      double currentRR = 0;
      if(sl > 0 && tp > 0 && entryPrice > 0) {
         double risk = MathAbs(entryPrice - sl);
         double reward = MathAbs(currentPrice - entryPrice);
         if(risk > 0) currentRR = reward / risk;
      }

      json += JsonObjectStart();
      json += JsonEncode("ticket", (double)positionInfo.Ticket()) + ",";
      json += JsonEncode("symbol", positionInfo.Symbol()) + ",";
      json += JsonEncode("type", positionInfo.PositionType() == POSITION_TYPE_BUY ? "buy" : "sell") + ",";
      json += JsonEncode("volume", positionInfo.Volume()) + ",";
      json += JsonEncode("price_open", entryPrice) + ",";
      json += JsonEncode("price_current", currentPrice) + ",";
      json += JsonEncode("sl", sl) + ",";
      json += JsonEncode("tp", tp) + ",";
      json += JsonEncode("profit", positionInfo.Profit()) + ",";
      json += JsonEncode("swap", positionInfo.Swap()) + ",";
      json += JsonEncode("commission", positionInfo.Commission()) + ",";
      json += JsonEncode("magic", (double)positionInfo.Magic()) + ",";
      json += JsonEncode("comment", positionInfo.Comment()) + ",";
      json += JsonEncode("time_open", timeOpen) + ",";
      json += JsonEncode("time_update", positionInfo.TimeUpdate()) + ",";
      json += JsonEncode("hold_time_sec", holdSeconds) + ",";
      json += JsonEncode("current_rr", currentRR) + ",";
      json += JsonEncode("trade_style", GetTradeStyleForSymbol(positionInfo.Symbol()));
      json += JsonObjectEnd();
   }

   json += JsonArrayEnd();
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Send trade event                                                |
//+------------------------------------------------------------------+
void SendTradeEvent(const MqlTradeTransaction &trans,
                    const MqlTradeRequest &request,
                    const MqlTradeResult &result)
{
   string json = JsonObjectStart();
   json += JsonEncode("type", "trade_event") + ",";
   json += JsonEncode("trans_type", (double)trans.type) + ",";
   json += JsonEncode("order_type", (double)request.type) + ",";
   json += JsonEncode("symbol", request.symbol) + ",";
   json += JsonEncode("volume", request.volume) + ",";
   json += JsonEncode("price", request.price) + ",";
   json += JsonEncode("sl", request.sl) + ",";
   json += JsonEncode("tp", request.tp) + ",";
   json += JsonEncode("magic", (double)request.magic) + ",";
   json += JsonEncode("comment", request.comment) + ",";
   json += JsonEncode("result_retcode", (double)result.retcode) + ",";
   json += JsonEncode("result_deal", (double)result.deal) + ",";
   json += JsonEncode("result_order", (double)result.order) + ",";
   json += JsonEncode("result_volume", request.volume) + ",";
   json += JsonEncode("result_price", result.price) + ",";
   json += JsonEncode("result_comment", result.comment);
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Send heartbeat                                                  |
//+------------------------------------------------------------------+
void SendHeartbeat()
{
   string json = JsonObjectStart();
   json += JsonEncode("type", "heartbeat") + ",";
   json += JsonEncode("timestamp", TimeCurrent()) + ",";
   json += JsonEncode("ea_version", "2.0.0") + ",";
   json += JsonEncode("connected", g_connected) + ",";
   json += JsonEncode("account", accountInfo.Login()) + ",";
   json += JsonEncode("tick_count", g_tickCounter) + ",";
   json += JsonEncode("risk_limit_hit", g_riskLimitHit);
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Send risk alert                                                 |
//+------------------------------------------------------------------+
void SendRiskAlert(const string &alertType, const string &message)
{
   string json = JsonObjectStart();
   json += JsonEncode("type", "risk_alert") + ",";
   json += JsonEncode("alert_type", alertType) + ",";
   json += JsonEncode("message", message) + ",";
   json += JsonEncode("timestamp", TimeCurrent()) + ",";
   json += JsonEncode("account", accountInfo.Login());
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Send data to Python (ZeroMQ or HTTP)                            |
//+------------------------------------------------------------------+
void SendToPython(const string &json)
{
   if(UseZeroMQ) {
      SendZeroMQ(json);
   } else {
      SendHTTP(json);
   }
}

//+------------------------------------------------------------------+
//| ZeroMQ connection                                               |
//+------------------------------------------------------------------+
bool ConnectZeroMQ()
{
   // This requires ZeroMQ DLL - placeholder implementation
   // In production, you would load libzmq.dll and use its functions
   Print("ZeroMQ connection not implemented - using HTTP fallback");
   return false;
}

void SendZeroMQ(const string &json)
{
   // Placeholder for ZeroMQ send
}

void CheckZeroMQCommands()
{
   // Placeholder for ZeroMQ receive
}

void DisconnectZeroMQ()
{
   // Placeholder
}

//+------------------------------------------------------------------+
//| HTTP connection (fallback)                                      |
//+------------------------------------------------------------------+
bool ConnectHTTP()
{
   // Test connection
   string url = "http://" + PythonHost + ":" + IntegerToString(HttpPort) + "/health";
   char response[];
   uint res = WebRequest("GET", url, NULL, 0, NULL, 5000, response, NULL);
   if(res > 0) {
      g_connected = true;
      g_reconnectCount = 0;
      Print("HTTP connection to Python system established");
      return true;
   }
   Print("HTTP connection failed: ", GetLastError());
   return false;
}

void SendHTTP(const string &json)
{
   string url = "http://" + PythonHost + ":" + IntegerToString(HttpPort) + "/api/v1/ea/data";
   char postData[];
   StringToCharArray(json, postData);
   char headers[] = "Content-Type: application/json\r\n";
   char response[];
   uint res = WebRequest("POST", url, headers, postData, ArraySize(postData), 5000, response, NULL);
   if(res == 0) {
      Print("HTTP send failed: ", GetLastError());
      g_connected = false;
      // Try reconnect
      if(g_reconnectCount < ReconnectAttempts) {
         Sleep(ReconnectDelay);
         g_reconnectCount++;
         ConnectHTTP();
      }
   } else {
      g_reconnectCount = 0;
   }
}

void CheckHTTPCommands()
{
   string url = "http://" + PythonHost + ":" + IntegerToString(HttpPort) + "/api/v1/ea/commands";
   char response[];
   uint res = WebRequest("GET", url, NULL, 0, NULL, 5000, response, NULL);
   if(res > 0) {
      string respStr;
      CharArrayToString(response, respStr);
      ProcessCommands(respStr);
   }
}

//+------------------------------------------------------------------+
//| Process commands from Python (simplified JSON parsing)          |
//+------------------------------------------------------------------+
void ProcessCommands(const string &jsonCommands)
{
   // This is a simplified parser - in production use a proper JSON library
   // Expected format: [{"type":"order","symbol":"EURUSD","action":"buy","volume":0.1,"price":0,"sl":1.1000,"tp":1.1100,"comment":"Brain decision"}]

   if(StringFind(jsonCommands, "order") == -1) return;

   // Extract individual commands from array
   string remaining = jsonCommands;
   int startPos = 0;

   while(true) {
      int objStart = StringFind(remaining, "{", startPos);
      if(objStart == -1) break;
      int objEnd = StringFind(remaining, "}", objStart);
      if(objEnd == -1) break;

      string cmd = StringSubstr(remaining, objStart, objEnd - objStart + 1);
      ExecuteCommand(cmd);

      startPos = objEnd + 1;
      if(startPos >= StringLen(remaining)) break;
   }
}

//+------------------------------------------------------------------+
//| Execute a single command                                         |
//+------------------------------------------------------------------+
void ExecuteCommand(const string &cmd)
{
   // Parse command fields using simple string extraction
   string type = ExtractJsonField(cmd, "type");
   if(type != "order") return;

   string symbol = ExtractJsonField(cmd, "symbol");
   string action = ExtractJsonField(cmd, "action");
   double volume = StringToDouble(ExtractJsonField(cmd, "volume"));
   double price = StringToDouble(ExtractJsonField(cmd, "price"));
   double sl = StringToDouble(ExtractJsonField(cmd, "sl"));
   double tp = StringToDouble(ExtractJsonField(cmd, "tp"));
   string comment = ExtractJsonField(cmd, "comment");
   int magic = (int)StringToDouble(ExtractJsonField(cmd, "magic"));

   // Validate
   if(symbol == "" || action == "" || volume <= 0) {
      Print("Invalid command: ", cmd);
      return;
   }

   // Check if symbol is allowed
   bool allowed = false;
   for(int i = 0; i < g_symbolsCount; i++) {
      if(g_allowedSymbols[i] == symbol) {
         allowed = true;
         break;
      }
   }
   if(!allowed) {
      Print("Symbol not allowed: ", symbol);
      return;
   }

   // Check risk limits before executing
   if(g_riskLimitHit && (action == "buy" || action == "sell")) {
      Print("Order rejected: Risk limit hit");
      return;
   }

   // Convert action to order type
   ENUM_ORDER_TYPE orderType;
   if(action == "buy") orderType = ORDER_TYPE_BUY;
   else if(action == "sell") orderType = ORDER_TYPE_SELL;
   else if(action == "buy_limit") orderType = ORDER_TYPE_BUY_LIMIT;
   else if(action == "sell_limit") orderType = ORDER_TYPE_SELL_LIMIT;
   else if(action == "buy_stop") orderType = ORDER_TYPE_BUY_STOP;
   else if(action == "sell_stop") orderType = ORDER_TYPE_SELL_STOP;
   else if(action == "close") {
      ClosePositionBySymbol(symbol);
      return;
   } else if(action == "close_all") {
      CloseAllPositions();
      return;
   } else {
      Print("Unknown action: ", action);
      return;
   }

   // Execute order
   ExecuteOrder(symbol, orderType, volume, price, sl, tp, comment, magic);
}

//+------------------------------------------------------------------+
//| Extract JSON field value (simplified)                           |
//+------------------------------------------------------------------+
string ExtractJsonField(const string &json, const string &field)
{
   string search = "\"" + field + "\":";
   int pos = StringFind(json, search);
   if(pos == -1) return "";

   int start = pos + StringLen(search);
   // Skip whitespace
   while(start < StringLen(json) && (json[start] == ' ' || json[start] == '\t')) start++;

   bool isString = false;
   if(start < StringLen(json) && json[start] == '"') {
      isString = true;
      start++;
   }

   int end = start;
   if(isString) {
      while(end < StringLen(json) && json[end] != '"') end++;
   } else {
      while(end < StringLen(json) && json[end] != ',' && json[end] != '}') end++;
   }

   if(end > start) {
      return StringSubstr(json, start, end - start);
   }
   return "";
}

//+------------------------------------------------------------------+
//| Execute order from Python                                       |
//+------------------------------------------------------------------+
bool ExecuteOrder(const string &symbol, ENUM_ORDER_TYPE type, double volume,
                  double price, double sl, double tp, const string &comment, int magic)
{
   if(!AutoTradingEnabled) {
      Print("Auto trading disabled");
      return false;
   }

   if(volume > MaxLotSize) {
      Print("Volume exceeds maximum: ", volume, " > ", MaxLotSize);
      return false;
   }

   // Normalize volume
   double minLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   if(volume < minLot) volume = minLot;
   if(volume > maxLot) volume = maxLot;
   volume = MathRound(volume / stepLot) * stepLot;

   // Normalize prices
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(price > 0) price = NormalizeDouble(price, digits);
   if(sl > 0) sl = NormalizeDouble(sl, digits);
   if(tp > 0) tp = NormalizeDouble(tp, digits);

   // Set magic number
   if(magic > 0) trade.SetExpertMagicNumber(magic);

   bool result = false;
   switch(type) {
      case ORDER_TYPE_BUY:
         result = trade.Buy(volume, symbol, price, sl, tp, comment);
         break;
      case ORDER_TYPE_SELL:
         result = trade.Sell(volume, symbol, price, sl, tp, comment);
         break;
      case ORDER_TYPE_BUY_LIMIT:
         result = trade.BuyLimit(volume, symbol, price, sl, tp, comment);
         break;
      case ORDER_TYPE_SELL_LIMIT:
         result = trade.SellLimit(volume, symbol, price, sl, tp, comment);
         break;
      case ORDER_TYPE_BUY_STOP:
         result = trade.BuyStop(volume, symbol, price, sl, tp, comment);
         break;
      case ORDER_TYPE_SELL_STOP:
         result = trade.SellStop(volume, symbol, price, sl, tp, comment);
         break;
      default:
         Print("Unsupported order type: ", type);
         return false;
   }

   if(!result) {
      Print("Order failed: ", trade.ResultRetcode(), " - ", trade.ResultComment());
      // Send error back to Python
      SendOrderError(symbol, type, trade.ResultRetcode(), trade.ResultComment());
   }

   return result;
}

//+------------------------------------------------------------------+
//| Send order error back to Python                                 |
//+------------------------------------------------------------------+
void SendOrderError(const string &symbol, ENUM_ORDER_TYPE type, int retcode, const string &comment)
{
   string json = JsonObjectStart();
   json += JsonEncode("type", "order_error") + ",";
   json += JsonEncode("symbol", symbol) + ",";
   json += JsonEncode("order_type", (double)type) + ",";
   json += JsonEncode("retcode", retcode) + ",";
   json += JsonEncode("comment", comment) + ",";
   json += JsonEncode("timestamp", TimeCurrent());
   json += JsonObjectEnd();

   SendToPython(json);
}

//+------------------------------------------------------------------+
//| Close position by symbol                                        |
//+------------------------------------------------------------------+
void ClosePositionBySymbol(const string &symbol)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      if(positionInfo.SelectByTicket(ticket)) {
         if(positionInfo.Symbol() == symbol) {
            trade.PositionClose(ticket);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Close all positions                                             |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0) {
         trade.PositionClose(ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| Disconnect                                                      |
//+------------------------------------------------------------------+
void Disconnect()
{
   if(UseZeroMQ) {
      DisconnectZeroMQ();
   }
   g_connected = false;
}

//+------------------------------------------------------------------+
//| JSON helper functions                                           |
//+------------------------------------------------------------------+
string JsonEncode(const string &key, const string &value)
{
   return "\"" + key + "\":\"" + value + "\"";
}

string JsonEncode(const string &key, double value)
{
   return "\"" + key + "\":" + DoubleToString(value, 8);
}

string JsonEncode(const string &key, long value)
{
   return "\"" + key + "\":" + LongToString(value);
}

string JsonEncode(const string &key, int value)
{
   return "\"" + key + "\":" + IntegerToString(value);
}

string JsonEncode(const string &key, bool value)
{
   return "\"" + key + "\":" + (value ? "true" : "false");
}

string JsonObjectStart() { return "{"; }
string JsonObjectEnd() { return "}"; }
string JsonArrayStart() { return "["; }
string JsonArrayEnd() { return "]"; }
//+------------------------------------------------------------------+