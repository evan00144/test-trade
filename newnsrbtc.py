import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import warnings
import numpy as np

warnings.filterwarnings("ignore", category=pd.errors.ChainedAssignmentError)

def initialize_mt5():
    if not mt5.initialize():
        print("MT5 initialization failed")
        mt5.shutdown()
        return False
    return True

def login_mt5(account, password, server):
    authorized = mt5.login(login=account, password=password, server=server)
    if not authorized:
        print("Login failed")
        return False
    print(f"Connected to account #{account}")
    return True

def get_historical_data(symbol, timeframe, num_bars):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def detect_support_resistance(df, window=20, touch_threshold=2):
    df = df.copy()
    df['resistance'] = None
    df['support'] = None

    for i in range(window, len(df)):
        current_window = df.iloc[i-window:i]
        current_high = current_window['high'].max()
        current_low = current_window['low'].min()

        resistance_touches = sum((current_window['high'] >= current_high * 0.999) & 
                               (current_window['high'] <= current_high * 1.001))
        support_touches = sum((current_window['low'] >= current_low * 0.999) & 
                            (current_window['low'] <= current_low * 1.001))

        if resistance_touches >= touch_threshold:
            df.loc[i, 'resistance'] = current_high
        if support_touches >= touch_threshold:
            df.loc[i, 'support'] = current_low
    return df

def calculate_atr(df, period=14):
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr'] = df['tr'].rolling(period).mean()
    return df['atr'].iloc[-1]

def calculate_adx(df, period=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    plus_dm = high[1:] - high[:-1]
    minus_dm = low[:-1] - low[1:]
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)

    tr = np.maximum(high[1:] - low[1:], 
                   np.abs(high[1:] - close[:-1]), 
                   np.abs(low[1:] - close[:-1]))
    
    atr = np.zeros(len(tr))
    for i in range(len(tr)):
        if i < period:
            atr[i] = tr[:i+1].mean()
        else:
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period

    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period).mean() / atr)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period).mean()
    
    return adx.iloc[-1], plus_di.iloc[-1], minus_di.iloc[-1]

def determine_trend(adx, plus_di, minus_di):
    if adx > 25:
        return "UP" if plus_di > minus_di else "DOWN"
    return "SIDEWAYS"

def generate_signal(df, trend):
    if len(df) < 3:
        return 'HOLD'

    current_close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    resistance = df['resistance'].iloc[-2]
    support = df['support'].iloc[-2]

    valid_buy = trend == "UP" and not pd.isna(resistance) and \
                prev_close > resistance and current_close > resistance
    valid_sell = trend == "DOWN" and not pd.isna(support) and \
                 prev_close < support and current_close < support
    
    print(f"Valid Buy: {trend == 'UP' and not pd.isna(resistance)}, {prev_close > resistance}, {current_close > resistance}")
    print(f"Valid Sell: {trend == 'DOWN' and not pd.isna(support)}, {prev_close < support}, {current_close < support}")


    return 'BUY' if valid_buy else 'SELL' if valid_sell else 'HOLD'

def calculate_lot_size(balance, risk_percent, sl_pips, symbol):
    tick_value = mt5.symbol_info(symbol).trade_tick_value
    risk_amount = balance * (risk_percent / 100)
    return round(risk_amount / (sl_pips * tick_value), 2)

def execute_trade(symbol, signal, df, risk=1.0):
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if signal == 'BUY' else tick.bid
    atr = calculate_atr(df)
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": calculate_lot_size(mt5.account_info().balance, risk, atr*1.5, symbol),
        "type": mt5.ORDER_TYPE_BUY if signal == 'BUY' else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": price - (atr * 1.5 if signal == 'BUY' else -atr * 1.5),
        "tp": price + (atr * 3 if signal == 'BUY' else -atr * 3),
        "deviation": 20,
        "magic": 234000,
        "comment": "Trend Following Strategy",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Trade failed: {result.comment}")
    else:
        print(f"Executed {request['volume']} lots at {price}")
        with open('trades_log.csv', 'a') as f:
            f.write(f"{datetime.now()},{symbol},{signal},{price},{request['sl']},{request['tp']},{request['volume']}\n")

def main():
    symbol = "BTCUSD"
    timeframe = mt5.TIMEFRAME_M15
    num_bars = 200
    
    if not initialize_mt5() or not login_mt5(239634700, "B6D4YAMdemo_", "Exness-MT5Trial6"):
        return

    while True:
        try:
            df = get_historical_data(symbol, timeframe, num_bars)
            df = detect_support_resistance(df)
            adx, plus_di, minus_di = calculate_adx(df)
            trend = determine_trend(adx, plus_di, minus_di)
            signal = generate_signal(df, trend)
            
            print(f"\n{datetime.now()} | Price: {df['close'].iloc[-1]:.2f}")
            print(f"ADX: {adx:.1f} | +DI: {plus_di:.1f} | -DI: {minus_di:.1f}")
            print(f"Trend: {trend} | Signal: {signal}")

            if signal != 'HOLD':
                execute_trade(symbol, signal, df)
            
            time.sleep(5)
            
        except Exception as e:
            print(f"Error: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()