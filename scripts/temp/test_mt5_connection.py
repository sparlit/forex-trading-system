import MetaTrader5 as mt5
print('MT5 version:', mt5.__version__)
if mt5.initialize():
    print('MT5 initialized successfully')
    account = mt5.account_info()
    if account:
        print('Account login:', account.login)
        print('Account balance:', account.balance)
    else:
        print('Failed to get account info')
    mt5.shutdown()
else:
    print('MT5 initialize failed:', mt5.last_error())