import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import time
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


def getIndicator(df):
    # Calculate indicators
    bbands = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bbands], axis=1)

    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)

    # Generate signals
    df['signal'] = "HOLD"

    for i in range(1, len(df)):
        # LONG ENTRY CONDITIONS
        if (df['close'].iloc[i] <= df['BBL_20_2.0'].iloc[i] and
            df['RSI'].iloc[i] < 30 and
            df['MACDh_12_26_9'].iloc[i] > 0 and
            df['MACDh_12_26_9'].iloc[i-1] <= 0):
            df['signal'].iloc[i] = "BUY"

            with open("signal.txt", "a") as file:
                file.write(f"BUY: {df['close'].iloc[-1]}\n")
        
        # SHORT ENTRY CONDITIONS
        elif (df['close'].iloc[i] >= df['BBU_20_2.0'].iloc[i] and
            df['RSI'].iloc[i] > 70 and
            df['MACDh_12_26_9'].iloc[i] < 0 and
            df['MACDh_12_26_9'].iloc[i-1] >= 0):
            df['signal'].iloc[i] = "SELL"

            with open("signal.txt", "a") as file:
                file.write(f"SELL: {df['close'].iloc[-1]}\n")

    return df

# Fetch historical data
def get_historical_data(symbol, timeframe, num_bars):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df
def main():

    if not initialize_mt5():
        return

    if not login_mt5(account=239634700, password="B6D4YAMdemo_", server="Exness-MT5Trial6"):
        return
    while True:
        df = get_historical_data(symbol="XAUUSD", timeframe=mt5.TIMEFRAME_M1, num_bars=500)
        df = getIndicator(df)

        print(f"Signal: {df['signal'].iloc[-1]}")
        print(f"RSI: {df['RSI'].iloc[-1]}")
        print(f"MACD: {df['MACDh_12_26_9'].iloc[-1]}")
        print(f"BB Upper: {df['BBU_20_2.0'].iloc[-1]}")
        print(f"Price: {df['close'].iloc[-1]}")
        print(f"BB Lower: {df['BBL_20_2.0'].iloc[-1]}\n")
        time.sleep(5)
    

if __name__ == "__main__":
    main()
    mt5.shutdown()