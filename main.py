import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import warnings
import ta  # technical analysis library
import numpy as np

warnings.filterwarnings("ignore", category=pd.errors.ChainedAssignmentError)

TARGET_PROFIT_PCT = 1.0  # Close position at 1% profit
RISK_PERCENT = 0.2       # Risk 0.2% of account balance per trade
MAX_ALLOWED_SPREAD = 5   # Max spread in pips

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
    # Calculate ATR using the ta library over a 14–bar window
    df['ATR'] = ta.volatility.average_true_range(high=df['high'], low=df['low'], close=df['close'], window=14)
    # Add an ATR_count column:
    # This counts how many consecutive bars have an ATR above its own 14–bar rolling average.
    df['ATR_count'] = count_consecutive_high_atr(df['ATR'], window=14, factor=1.0)
    # For additional filtering, we also calculate a 50–period SMA of the closing prices
    df['SMA50'] = ta.trend.sma_indicator(close=df['close'], window=50)
    return df


# Detect support and resistance levels using fractals
def detect_support_resistance(df, window=20):
    df = df.copy()
    # Simple fractal detection: a candle is a fractal high if its high is greater than the 2 candles before and after.
    df['fractal_high'] = (df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(2)) & \
                         (df['high'] > df['high'].shift(-1)) & (df['high'] > df['high'].shift(-2))
    df['fractal_low'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(2)) & \
                        (df['low'] < df['low'].shift(-1)) & (df['low'] < df['low'].shift(-2))
    
    # Collect fractal levels into lists
    fractal_resistances = df.loc[df['fractal_high'], 'high'].tolist()
    fractal_supports = df.loc[df['fractal_low'], 'low'].tolist()
    
    # Aggregate nearby fractal levels into key levels
    key_resistances = aggregate_levels(fractal_resistances, tolerance=0.3)  # adjust tolerance as needed
    key_supports = aggregate_levels(fractal_supports, tolerance=0.3)
    
    # Save aggregated levels in the dataframe (for plotting later, for example)
    df['key_resistance'] = None
    df['key_support'] = None
    # For simplicity, assign the most recent aggregated level (if exists) to the current row
    if key_resistances:
        df.loc[:, 'key_resistance'] = key_resistances[-1]
    if key_supports:
        df.loc[:, 'key_support'] = key_supports[-1]
    
    # Also return the aggregated levels for signal generation
    return df, key_supports, key_resistances

# Function to aggregate levels based on a given tolerance.
def aggregate_levels(levels, tolerance=0.3):
    if not levels:
        return []
    levels.sort()
    aggregated = []
    current_group = [levels[0]]
    for level in levels[1:]:
        if abs(level - current_group[-1]) <= tolerance:
            current_group.append(level)
        else:
            aggregated.append(np.median(current_group))
            current_group = [level]
    aggregated.append(np.median(current_group))
    return aggregated

# Generate trading signal using key levels and additional filters (SMA filter)
def generate_signal(df, key_supports, key_resistances):
    if df.empty:
        return 'HOLD'
    
    # Latest candle data
    previous_close = df['close'].iloc[-2]
    current_close = df['close'].iloc[-1]
    current_price = current_close  # for clarity
    
    current_sma = df['SMA50'].iloc[-1]
    
    # Use the most recent key levels
    key_resistance = key_resistances[-1] if key_resistances else None
    key_support = key_supports[-1] if key_supports else None

    signal = 'HOLD'
    
    # For a BUY: price breaks above key resistance and is above SMA filter.
    if key_resistance is not None and previous_close <= key_resistance < current_price and current_price > current_sma:
        signal = 'BUY'
    # For a SELL: price breaks below key support and is below SMA filter.
    elif key_support is not None and previous_close >= key_support > current_price and current_price < current_sma:
        signal = 'SELL'
    
    return signal
def count_consecutive_high_atr(atr_series, window=14, factor=1.0):
    """
    Count consecutive bars where the ATR is above its rolling mean multiplied by factor.
    
    Parameters:
      atr_series: pd.Series containing ATR values.
      window: The lookback period for calculating the rolling average.
      factor: Multiplier for the rolling average (default 1.0 means count if ATR > rolling average).
      
    Returns:
      A pd.Series with the count of consecutive bars meeting the condition.
    """
    # Calculate the rolling average of ATR (with at least one period)
    atr_avg = atr_series.rolling(window=window, min_periods=1).mean()
    counts = []
    count = 0
    for atr, avg in zip(atr_series, atr_avg):
        if atr > factor * avg:
            count += 1
        else:
            count = 0
        counts.append(count)
    return pd.Series(counts, index=atr_series.index)


# Calculate lot size based on ATR-based stop loss
def calculate_lot_size(symbol, atr_value):
    account_info = mt5.account_info()
    if account_info is None:
        print("Account info not available")
        return 0
    account_balance = account_info.balance
    risk_amount = account_balance * (RISK_PERCENT / 100)
    pip_value = 10  # For XAUUSD, 1 pip = $10 per 1 lot (adjust if needed)
    # Convert ATR (price units) to pip count; for XAUUSD pip size is 0.1
    sl_pips = atr_value / 0.1  
    lot_size = round(risk_amount / (sl_pips * pip_value), 2)
    return lot_size

# Execute trade with dynamic SL/TP using ATR for stop loss and RR of 1:2
def execute_trade(symbol, signal, df):
    print("Start Executing Trade")
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

    # Check spread
    tick = mt5.symbol_info_tick(symbol)
    current_spread = tick.ask - tick.bid
    if current_spread > MAX_ALLOWED_SPREAD * 0.1:  # 0.1 is pip size for XAUUSD
        print(f"Spread too wide: {current_spread/0.1:.1f} pips")
        return

    # Calculate SL and TP using ATR value from latest candle
    atr_value = df['ATR'].iloc[-1]
    if pd.isna(atr_value) or atr_value <= 0:
        print("Invalid ATR value")
        return

    lot_size = calculate_lot_size(symbol, atr_value)
    point = symbol_info.point
    # For BUY, use ask price; for SELL, use bid price.
    price = tick.ask if signal == 'BUY' else tick.bid
    
    # Dynamic SL using ATR; here we use ATR value * factor (e.g., 1.0)
    # factor = df['ATR_count'].iloc[-1]
    factor = 1.5
    if signal == 'BUY':
        sl = price - atr_value * factor
        tp = price + (price - sl) * 2  # RR 1:2
    elif signal == 'SELL':
        sl = price + atr_value * factor
        tp = price - (sl - price) * 2
    else:
        return

    print(f"Signal: {signal} | Price: {price:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | Lot Size: {lot_size}")

    # Prepare trade request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": mt5.ORDER_TYPE_BUY if signal == 'BUY' else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": 234000,
        "comment": "S/R Breakout Strategy with ATR SL and SMA Filter",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    print(request)

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {result.comment}")
    else:
        print(f"Executed {lot_size} lots at {price} | SL: {sl:.2f} | TP: {tp:.2f}")

# Main function
def main():
    symbol = "XAUUSD"
    timeframe = mt5.TIMEFRAME_M1
    num_bars = 500
    executed = 0
    check_interval = 5  # seconds

    if not initialize_mt5():
        return

    if not login_mt5(239634700, password="B6D4YAMdemo_", server="Exness-MT5Trial6"):
        return

    while True:
        try:
            print(f"\nChecking market at {datetime.now()}")
            df = get_historical_data(symbol, timeframe, num_bars)
            # Detect fractal support/resistance and get aggregated key levels
            df, key_supports, key_resistances = detect_support_resistance(df, window=20)
            signal = generate_signal(df, key_supports, key_resistances)
            
            # Print latest key levels if available
            if key_resistances:
                print(f"Key Resistance Level: {key_resistances[-1]:.2f}")
            print(f"Current Price: {df['close'].iloc[-1]:.2f}")
            if key_supports:
                print(f"Key Support Level: {key_supports[-1]:.2f}")
            print(f"Signal: {signal}")
            print(f"Executed Trades: {executed}")
            
            execute_trade(symbol, 'BUY', df)
            # if signal in ['BUY', 'SELL']:
            #     execute_trade(symbol, signal, df)
            #     executed += 1

            time.sleep(check_interval)

        except Exception as e:
            print(f"Error occurred: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()
