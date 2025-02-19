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

# Calculate Average True Range (ATR)
def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr = np.maximum(high - low, 
                   np.maximum(abs(high - close.shift()), 
                            abs(low - close.shift())))
    df['ATR'] = tr.rolling(period).mean()
    return df

# Calculate Simple Moving Average
def calculate_sma(df, period=200):
    df['SMA'] = df['close'].rolling(period).mean()
    return df

# Detect support and resistance levels
def detect_support_resistance(df, window=20, touch_threshold=2):
    df = df.copy()
    df['resistance'] = None
    df['support'] = None

    for i in range(window, len(df)):
        current_high = df['high'].iloc[i-window:i].max()
        current_low = df['low'].iloc[i-window:i].min()


        resistance_touches = sum((df['high'].iloc[i-window:i] >= current_high * 0.999) & 
                                (df['high'].iloc[i-window:i] <= current_high * 1.001))
        support_touches = sum((df['low'].iloc[i-window:i] >= current_low * 0.999) & 
                             (df['low'].iloc[i-window:i] <= current_low * 1.001))

        if resistance_touches >= touch_threshold:
            df.loc[i, 'resistance'] = current_high
        if support_touches >= touch_threshold:
            df.loc[i, 'support'] = current_low

    return df

# Generate trading signals with confirmation and trend filter
def generate_signal(df):
    current_close = df['close'].iloc[-1]
    previous_close = df['close'].iloc[-2]
    resistance = df['resistance'].dropna().iloc[-1] if not df['resistance'].dropna().empty else None
    support = df['support'].dropna().iloc[-1] if not df['support'].dropna().empty else None
    sma_value = df['SMA'].iloc[-1]
    
    # Breakout confirmation (two consecutive closes beyond S/R)
    buy_condition = (resistance and 
                    current_close > resistance and 
                    previous_close > resistance and 
                    current_close > sma_value)



    print("\nBuy Condition",resistance,current_close > resistance,previous_close > resistance,current_close > sma_value)
    
    sell_condition = (support and 
                     current_close < support and 
                     previous_close < support and 
                     current_close < sma_value)

    print("Sell Condition",support,current_close < support,previous_close < support,current_close < sma_value)
    
    if buy_condition:
        return 'BUY'
    elif sell_condition:
        return 'SELL'
    else:
        return 'HOLD'

# Dynamic position sizing based on volatility
def calculate_position_size(df, risk_percent=0.02):
    return 0.01
    account_info = mt5.account_info()
    if not account_info:
        return 0.01  # Default lot size
    
    balance = account_info.balance
    atr = df['ATR'].iloc[-1]
    price = df['close'].iloc[-1]
    
    if atr <= 0 or price <= 0:
        return 0.01  # Fallback
    
    # Calculate risk amount in dollars
    risk_amount = balance * risk_percent
    
    # Calculate position size (1 pip = $1 per 0.01 movement for XAUUSD)
    lot_size = (risk_amount / atr) / 100  # Adjusted for XAUUSD pricing
    
    # Apply broker constraints
    lot_size = max(0.01, min(lot_size, 50))  # Min 0.01, max 50 lots
    return round(lot_size, 2)

# Execute trade with enhanced features
def execute_trade(symbol, signal, df):
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
    lot_size = calculate_position_size(df)
    
    # Calculate stop loss and take profit
    atr = df['ATR'].iloc[-1]
    if signal == 'BUY':
        sl = price - 2 * atr
        tp = price + 3 * atr  # 1.5:1 risk-reward ratio
    else:
        sl = price + 2 * atr
        tp = price - 3 * atr

    print("SL",sl,"TP",tp)
    
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

# Main trading loop
def main():
    symbol = "XAUUSD"
    timeframe = mt5.TIMEFRAME_M1
    num_bars = 500
    executed = 0
    window = 20
    check_interval = 3  # 15 minutes

    if not initialize_mt5():
        return

    # Replace with your credentials
    if not login_mt5(account=239634700, password="B6D4YAMdemo_", server="Exness-MT5Trial6"):
        return

    while True:
        try:
            print(f"\n{datetime.now()} - Analyzing market...")
            df = get_historical_data(symbol, timeframe, num_bars)
            df = calculate_sma(df, 200)
            df = calculate_atr(df, 14)
            df = detect_support_resistance(df, window)
            
            signal = generate_signal(df)
            
            print(f"Price: {df['close'].iloc[-1]:.2f}")
            print(f"SMA(200): {df['SMA'].iloc[-1]:.2f}")
            print(f"ATR(14): {df['ATR'].iloc[-1]:.2f}")
            if(df['resistance'].dropna().empty):
                print("No resistance")
            else:
                print(f"Resistance: {df['resistance'].iloc[-1]}")
            if(df['support'].dropna().empty):
                print("No support")
            else:
                print(f"Support: {df['support'].iloc[-1]}")
            print(f"Signal: {signal}")
            print(f"Executed: {executed}")

            # execute_trade(symbol, signal, df)
            if signal in ['BUY', 'SELL']:
                execute_trade(symbol, signal, df)
                executed += 1

            time.sleep(check_interval)

        except Exception as e:
            print(f"Error: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()