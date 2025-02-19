import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import warnings
warnings.filterwarnings("ignore", category=pd.errors.ChainedAssignmentError)

TARGET_PROFIT_PCT = 1.0  # Close position at 1% profit

# Initialize MT5 connection
def initialize_mt5():
    if not mt5.initialize():
        print("MT5 initialization failed")
        mt5.shutdown()
        return False
    return True

# Login to MT5 account (modify with your credentials)
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

# Detect support and resistance levels
def detect_support_resistance(df, window=20, touch_threshold=2):
    df = df.copy()
    df['resistance'] = None
    df['support'] = None

    # Analyze all candles in the window
    for i in range(window, len(df)):
        lookback_start = i - window
        current_window = df.iloc[lookback_start:i]  # Look back window candles
        
        current_high = current_window['high'].max()
        current_low = current_window['low'].min()
        
        resistance_touches = sum(
            (current_window['high'] >= current_high * 0.999) &
            (current_window['high'] <= current_high * 1.001)
        )
        
        support_touches = sum(
            (current_window['low'] >= current_low * 0.999) &
            (current_window['low'] <= current_low * 1.001)
        )

        # Set levels for current candle based on previous window
        if resistance_touches >= touch_threshold:
            df.loc[i, 'resistance'] = current_high
        if support_touches >= touch_threshold:
            df.loc[i, 'support'] = current_low

    return df

def generate_signal(df):
    if len(df) < 2:
        return 'HOLD'
    
    # Get previous candle's data
    previous_close = df['close'].iloc[-2]
    previous_resistance = df['resistance'].iloc[-2]
    previous_support = df['support'].iloc[-2]
    
    # Get current price
    current_price = df['close'].iloc[-1]
    
    # Buy condition: Previous close above resistance AND price maintains above
    if not pd.isna(previous_resistance) and previous_close > previous_resistance and current_price > previous_resistance:
        return 'BUY'
    
    # Sell condition: Previous close below support AND price maintains below
    if not pd.isna(previous_support) and previous_close < previous_support and current_price < previous_support:
        return 'SELL'
    
    return 'HOLD'


# Execute trade
def execute_trade(symbol, signal, df):
    print("StartExecutingTrade")
    account_info = mt5.account_info()
    if account_info is None:
        print("Failed to get account info")
        return

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Failed to get info for {symbol}")
        return

    if not symbol_info.visible:
        print(f"{symbol} is not visible, trying to switch on")
        if not mt5.symbol_select(symbol, True):
            print("Symbol select failed")
            return

    point = symbol_info.point
    price = mt5.symbol_info_tick(symbol).ask if signal == 'BUY' else mt5.symbol_info_tick(symbol).bid
    deviation = 20

    if signal == 'BUY':
        sl = price - 10 * point*100
        tp = price + (price - sl) * 2
    elif signal == 'SELL':
        sl = price + 10 * point*100
        tp = price - (sl - price) * 2
    else:
        return


    lot_size = 0.05  # Adjust based on your risk management

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY if signal == 'BUY' else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": 234000,
        "comment": "S/R Breakout Strategy",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    print("Before Order")

    result = mt5.order_send(request)
    print(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {result.comment}")
    else:
        print(f"Executed {lot_size} lots at {price} | SL: {sl:.2f} | TP: {tp:.2f}")


def main():
    symbol = "XAUUSD"
    timeframe = mt5.TIMEFRAME_M1
    num_bars = 500
    executed = 0
    window = 20
    check_interval = 5  # 30 seconds

    if not initialize_mt5():
        return

    if not login_mt5(239634700, password="B6D4YAMdemo_",server="Exness-MT5Trial6"):
        return

    while True:
        try:
            print(f"\nChecking market at {datetime.now()}")
            df = get_historical_data(symbol, timeframe, num_bars)
            df = detect_support_resistance(df, window=window)
            signal = generate_signal(df)
            
            print(f"Current Price: {df['close'].iloc[-1]:.2f}")
            print(f"Latest Resistance: {df['resistance'].iloc[-1]}" if not df['resistance'].dropna().empty else "No resistance")
            print(f"Latest Support: {df['support'].iloc[-1]}" if not df['support'].dropna().empty else "No support")
            print(f"Signal: {signal}")
            print(f"Executed: {executed}")
            if signal in ['BUY', 'SELL']:
                execute_trade(symbol, signal, df)
                executed += 1

            time.sleep(check_interval)

        except Exception as e:
            print(f"Error occurred: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()