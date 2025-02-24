import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import warnings
import numpy as np

warnings.filterwarnings("ignore", category=pd.errors.ChainedAssignmentError)

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

# Detect support and resistance levels
def detect_support_resistance(df, window=50, touch_threshold=2):
    df = df.copy()
    df['resistance'] = None
    df['support'] = None

    for i in range(window, len(df)):
        lookback_start = i - window
        current_window = df.iloc[lookback_start:i]

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

        if resistance_touches >= touch_threshold:
            df.loc[i, 'resistance'] = current_high
        if support_touches >= touch_threshold:
            df.loc[i, 'support'] = current_low

    return df

# Calculate ATR for dynamic SL and TP
def calculate_atr(df, period=14):
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df['atr'].iloc[-1]

# Calculate SMA
def calculate_sma(df, period):
    return df['close'].rolling(window=period).mean()

# Calculate ADX
def calculate_adx(df, period=14):
    df['plus_dm'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                             (df['high'] - df['high'].shift(1)).clip(lower=0), 0)
    df['minus_dm'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                              (df['low'].shift(1) - df['low']).clip(lower=0), 0)

    df['plus_di'] = 100 * (df['plus_dm'].rolling(window=period).mean() / df['tr'].rolling(window=period).mean())
    df['minus_di'] = 100 * (df['minus_dm'].rolling(window=period).mean() / df['tr'].rolling(window=period).mean())
    df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['adx'] = df['dx'].rolling(window=period).mean()
    return df['adx'].iloc[-1]
# Generate signal with new strategy
def generate_signal(df):
    if len(df) < 50:  # Need enough data for SMA and ADX
        return 'HOLD'

    # Calculate SMAs
    sma_short = calculate_sma(df, period=20).iloc[-1]
    sma_long = calculate_sma(df, period=50).iloc[-1]
    sma_short_prev = calculate_sma(df, period=20).iloc[-2]
    sma_long_prev = calculate_sma(df, period=50).iloc[-2]

    # Calculate ADX
    adx = calculate_adx(df)

    # Price and levels
    previous_close = df['close'].iloc[-2]
    current_price = df['close'].iloc[-1]
    previous_resistance = df['resistance'].iloc[-2]
    previous_support = df['support'].iloc[-2]

    # Buy condition: SMA crossover up, ADX > 25, breakout above resistance
    if (sma_short_prev <= sma_long_prev and sma_short > sma_long and
        adx > 25 and not pd.isna(previous_resistance) and
        previous_close < previous_resistance and current_price > previous_resistance):
        return 'BUY'

    # Sell condition: SMA crossover down, ADX > 25, breakout below support
    if (sma_short_prev >= sma_long_prev and sma_short < sma_long and
        adx > 25 and not pd.isna(previous_support) and
        previous_close > previous_support and current_price < previous_support):
        return 'SELL'

    return 'HOLD'

# Calculate dynamic lot size
def calculate_lot_size(balance, risk_percentage, stop_loss_pips, symbol):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Failed to get info for {symbol}")
        return 0.01
    tick_value = symbol_info.trade_tick_value
    risk_amount = balance * (risk_percentage / 100)
    lot_size = risk_amount / (stop_loss_pips * tick_value)
    lot_size = round(lot_size, 2)
    return max(lot_size, 0.01)

# Execute trade
def execute_trade(symbol, signal, df, risk_percentage=1.0):
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        print(f"Position already open for {symbol}, skipping trade.")
        return

    account_info = mt5.account_info()
    if account_info is None:
        print("Failed to get account info")
        return

    balance = account_info.balance
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Failed to get info for {symbol}")
        return

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print("Symbol select failed")
            return

    point = symbol_info.point
    price = mt5.symbol_info_tick(symbol).ask if signal == 'BUY' else mt5.symbol_info_tick(symbol).bid
    deviation = 20
    ask_price = mt5.symbol_info_tick(symbol).ask
    bid_price = mt5.symbol_info_tick(symbol).bid
    spread = ask_price - bid_price
    atr = calculate_atr(df)
    sl_pips = atr * 2.0
    tp_pips = atr * 4.0

    if signal == 'BUY':
        sl = price - sl_pips + spread
        tp = price + tp_pips
    elif signal == 'SELL':
        sl = price + sl_pips - spread
        tp = price - tp_pips
    else:
        return

    stop_loss_pips = abs(price - sl) / point
    lot_size = calculate_lot_size(balance, risk_percentage, stop_loss_pips, symbol)

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
        "comment": "Swing Trade Strategy V2",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {result.comment}")
    else:
        print(f"Executed {lot_size} lots at {price} | SL: {sl:.2f} | TP: {tp:.2f}")
        with open('trades_swing_v2.csv', 'a') as f:
            f.write(f"{datetime.now()},{symbol},{signal},price:{price},sl:{sl},tp:{tp},lot_size:{lot_size}\n")

# Illustrate price levels
def illustrate_levels(current_price, resistance, support):
    if pd.isna(resistance):
        resistance = current_price + 1000
    if pd.isna(support):
        support = current_price - 1000

    price_range = resistance - support
    if price_range == 0:
        price_range = 1

    scale_length = 20
    support_pos = 0
    resistance_pos = scale_length
    current_pos = int(((current_price - support) / price_range) * scale_length)
    current_pos = max(0, min(current_pos, scale_length))

    scale = ['-'] * (scale_length + 1)
    scale[support_pos] = 'S'
    scale[resistance_pos] = 'R'
    scale[current_pos] = 'C'

    scale_str = ''.join(scale)
    print(f"Support: {support:.2f} | Current: {current_price:.2f} | Resistance: {resistance:.2f}")
    print(scale_str)

# Main function
def main():
    symbol = "BTCUSD"
    timeframe = mt5.TIMEFRAME_H4
    num_bars = 500
    window = 50
    check_interval = 60

    if not initialize_mt5():
        return

    if not login_mt5(239634700, password="B6D4YAMdemo_", server="Exness-MT5Trial6"):
        return

    last_bar_time = None
    while True:
        try:
            print(f"\nChecking market at {datetime.now()}")
            latest_bar = mt5.copy_rates_from_pos(symbol, timeframe, 0, 1)[0]
            current_bar_time = latest_bar['time']

            if last_bar_time is None or current_bar_time > last_bar_time:
                last_bar_time = current_bar_time
                df = get_historical_data(symbol, timeframe, num_bars)
                df = detect_support_resistance(df, window=window)
                calculate_atr(df)  # Ensure necessary columns are present
                signal = generate_signal(df)

                current_price = df['close'].iloc[-1]
                resistance = df['resistance'].iloc[-1]
                support = df['support'].iloc[-1]

                print(f"Current Price: {current_price:.2f}")
                print(f"Latest Resistance: {resistance}" if not pd.isna(resistance) else "No resistance")
                print(f"Latest Support: {support}" if not pd.isna(support) else "No support")
                print(f"Signal: {signal}")

                illustrate_levels(current_price, resistance, support)

                if signal in ['BUY', 'SELL']:
                    execute_trade(symbol, signal, df, risk_percentage=1.0)
            else:
                print("No new bar, waiting...")

            time.sleep(check_interval)

        except Exception as e:
            print(f"Error occurred: {str(e)}")
            time.sleep(60)
    

if __name__ == "__main__":
    main()
    mt5.shutdown()