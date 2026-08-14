
import asyncio
import MetaTrader5 as mt5
from src.infra.config.settings import settings
from src.data.models import Timeframe

async def test():
    initialized = mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    print("MT5 initialized:", initialized)
    
    # Test the exact logic from _monitor_bars
    symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    timeframes = ["1m", "5m", "1h"]
    
    for symbol in symbols:
        for tf_str in ["1m", "5m", "1h"]:
            tf = Timeframe(tf_str)
            from src.data.ingest.mt5_connector import MT5_TIMEFRAME_MAP
            mt5_tf = MT5_TIMEFRAME_MAP.get(Timeframe(tf_str))
            print(f"Testing {symbol} {tf_str} -> MT5 TF: {mt5_tf}")
            
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1 if tf_str == "1m" else mt5.TIMEFRAME_M5 if tf_str == "5m" else mt5.TIMEFRAME_H1, 0, 2)
            print(f"  {symbol} {tf_str}: {len(rates) if rates else 0} bars")
            if rates is not None and len(rates) >= 2:
                r = rates[1]
                print(f"  Bar: time={r['time']} O={r['open']} H={r['high']} L={r['low']} C={r['close']}")
    
    mt5.shutdown()

asyncio.run(test())
