# MT5 Expert Advisor - Forex Trading System Bridge

This Expert Advisor (EA) acts as a bridge between MetaTrader 5 and the Python autonomous trading system.

## Features

- **Real-time Market Data Streaming**: Streams tick data for configured symbols to Python
- **Account Information**: Sends balance, equity, margin, and margin level
- **Position Monitoring**: Reports all open positions with P&L
- **Trade Execution**: Executes orders received from Python brain
- **Trade Event Reporting**: Notifies Python of all trade transactions
- **Heartbeat Monitoring**: Ensures connection health
- **Dual Transport**: Supports both ZeroMQ (low latency) and HTTP (fallback)
- **Level 2 Data**: Can stream Depth of Market data (if broker supports)

## Installation

1. Copy `ForexTradingSystemEA.mq5` to your MT5 `MQL5/Experts/` folder
2. Compile in MetaEditor (F7)
3. Attach to any chart (recommended: EURUSD H1)
4. Configure input parameters

## Configuration

### Connection Settings
- `PythonHost`: IP address of Python system (default: 127.0.0.1)
- `PythonPort`: ZeroMQ port (default: 5555)
- `HttpPort`: Python API port (default: 8000)
- `UseZeroMQ`: Use ZeroMQ for lower latency (requires ZeroMQ DLL)
- `HeartbeatInterval`: Heartbeat frequency in seconds
- `ReconnectAttempts`: Number of reconnection attempts
- `ReconnectDelay`: Delay between reconnections (ms)

### Trading Settings
- `AllowedSymbols`: Comma-separated list of symbols to trade
- `MaxSpreadMultiplier`: Maximum spread vs average (prevents trading during wide spreads)
- `AutoTradingEnabled`: Allow EA to execute trades from Python
- `MaxLotSize`: Maximum lot size per trade
- `RiskPerTrade`: Risk percentage per trade

## Python Side Integration

The Python system needs to implement endpoints:

### HTTP Endpoints (if UseZeroMQ=false)

1. **POST /api/v1/ea/data** - Receive market data, account info, positions
   ```json
   {
     "type": "market_data",
     "symbol": "EURUSD",
     "bid": 1.1050,
     "ask": 1.1052,
     "last": 1.1051,
     "volume": 100,
     "time": 1234567890,
     "time_msc": 1234567890123,
     "flags": 0,
     "volume_real": 1.0
   }
   ```

2. **GET /api/v1/ea/commands** - EA polls for commands
   Returns:
   ```json
   [
     {
       "type": "order",
       "symbol": "EURUSD",
       "action": "buy",
       "volume": 0.1,
       "price": 0,
       "sl": 1.1000,
       "tp": 1.1100,
       "comment": "Brain decision"
     }
   ]
   ```

3. **GET /health** - Health check endpoint

### ZeroMQ Protocol (if UseZeroMQ=true)

- **PUB/SUB pattern**: EA publishes market data, subscribes to commands
- **Endpoint**: `tcp://<PythonHost>:<PythonPort>`
- **Message format**: JSON strings

## Data Flow

```
MT5 (EA)                          Python (Brain)
    |                                  |
    |--- Market Data (ticks) --------->|
    |--- Account Info ---------------->|
    |--- Positions ------------------->|
    |                                  |
    |<-- Trading Commands (orders) ----|
    |                                  |
    |--- Trade Events (fills) -------->|
    |                                  |
    |--- Heartbeat ------------------->|
```

## Security

- Run on trusted network only
- Consider VPN for remote connections
- Validate all incoming commands
- Use authentication tokens in production

## Requirements

- MetaTrader 5 (build 3000+)
- MQL5 Standard Library (included)
- ZeroMQ DLL (optional, for ZeroMQ transport)
- Python system running and accessible

## Troubleshooting

1. **Connection failed**: Check firewall, IP, port
2. **No data**: Check symbol names match broker's naming
3. **Orders rejected**: Check AutoTrading enabled, sufficient margin
4. **High latency**: Use ZeroMQ, reduce heartbeat interval

## License

Part of Forex Trading System - Autonomous Trading Platform
