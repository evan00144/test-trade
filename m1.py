import MetaTrader5 as mt5
import pandas as pd
import time
import numpy as np
from datetime import datetime

# Initialize MT5 connection
def initialize_mt5():
    if not mt5.initialize():
        print("MT5 initialization failed")
        mt5.shutdown()
        return False
    return True

# Login to MT5 account
def login_mt5(account, password, server):
    authorized = mt5.login(login=account, password=password, server=server)
    if not authorized:
        print("Login failed")
        return False
    print(f"Connected to account #{account}")
    return True

# Fetch historical data
def get_historical_data(symbol, timeframe, num_bars):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df


# Generate trading signals with confirmation and trend filter
def generate_signal(df, lowest, highest):
    # Ensure there are enough data points
    if len(df) < 3:
        return 'HOLD'
    
    # Get the necessary data points
    prev_close = df['close'].iloc[-2]
    prev_highs = df['high'].iloc[-4:-2]
    prev_lows = df['low'].iloc[-4:-2]

    # Buy signal: previous close > 2 previous highs
    print(f'prev_close: {prev_close}, prev_highs: {prev_highs.max()}, prev_lows: {prev_lows.min()}')
    if prev_close > prev_highs.max():
        lowest = prev_lows.min()
        with open('signal.txt', 'a') as file:
            file.write(f"BUY: {prev_close}\n")
        return 'BUY', lowest, highest
    
    # Sell signal: previous close < 2 previous lows
    elif prev_close < prev_lows.min():
        highest = prev_highs.max()
        with open('signal.txt', 'a') as file:
            file.write(f"SELL: {prev_close}\n")
        return 'SELL', lowest, highest
    
    # Hold if neither condition is met
    return 'HOLD', lowest, highest

# Dynamic position sizing based on volatility

# Execute trade with enhanced features
def execute_trade(symbol, signal, df, lowest, highest):
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"Failed to get info for {symbol}")
        return

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print("Symbol select failed")
            return

    point = symbol_info.point
    price = mt5.symbol_info_tick(symbol).ask if signal == 'BUY' else mt5.symbol_info_tick(symbol).bid
    
    # Calculate position size
    lot_size = 0.06
    print(f"lowest: {lowest}, highest: {highest}")
    multiplier = 1
    if signal == 'BUY':
        sl = lowest - 0.2
        tp = price + 0.5
    else:
        sl = highest + 0.2
        tp = price - 0.5

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY if signal == 'BUY' else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 234000,
        "comment": "Enhanced S/R Strategy",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {result.comment}")
    else:
        print(f"Executed {lot_size} lots at {price} | SL: {sl:.2f} | TP: {tp:.2f}")

        with open('trades_m1.csv', 'a') as f:
            f.write(f"{datetime.now()},{symbol},{signal},price:{price},sl:{sl},tp:{tp},lot_size:{lot_size}\n")

# Main trading loop
def main():
    symbol = "XAUUSD"
    timeframe = mt5.TIMEFRAME_M1
    num_bars = 500
    executed = 0
    window = 20
    check_interval = 5  # 15 minutes

    if not initialize_mt5():
        return

    # Replace with your credentials
    if not login_mt5(account=239634700, password="B6D4YAMdemo_", server="Exness-MT5Trial6"):
        return

    while True:
        try:
            lowest = 0
            highest = 0
            print(f"\n{datetime.now()} - Analyzing market...")
            df = get_historical_data(symbol, timeframe, num_bars)
            signal, lowest, highest = generate_signal(df, lowest, highest)
            
            print(f"Signal: {signal}")
            print(f"Executed: {executed}")

            if signal in ['BUY', 'SELL']:
                execute_trade(symbol, signal, df, lowest, highest)
                executed += 1
            else:
                print("No signal")

            time.sleep(check_interval)

        except Exception as e:
            print(f"Error: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()