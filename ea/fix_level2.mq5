//+------------------------------------------------------------------+
//| Send Level 2 (Depth of Market) data                             |
//+------------------------------------------------------------------+
void SendLevel2Data(const string &symbol) {
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