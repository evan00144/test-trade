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

def analyze_trades_by_lotsize():
    # Fetch trade history
    trades = mt5.history_deals_get(datetime.now() - pd.Timedelta(days=30), datetime.now())
    if trades is None:
        print("No trade history found")
        return

    # Convert to DataFrame
    df_trades = pd.DataFrame(list(trades), columns=trades[0]._asdict().keys())

    # Filter for closed trades
    df_trades = df_trades[df_trades['type'].isin([mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL])]

    # Calculate profit/loss
    df_trades['profit'] = df_trades['profit'] - df_trades['commission'] - df_trades['swap']

    # Group by lot size and calculate win/loss
    grouped = df_trades.groupby('volume')['profit'].agg(['sum', 'count'])

    # Add win/loss count
    grouped['wins'] = df_trades[df_trades['profit'] > 0].groupby('volume')['profit'].count()
    grouped['losses'] = df_trades[df_trades['profit'] <= 0].groupby('volume')['profit'].count()

    grouped['win_rate'] = grouped['wins'] / grouped['count'] * 100
    grouped['profit_rate'] = grouped['sum'] / grouped['count']

    print(grouped)

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

    analyze_trades_by_lotsize()
    

if __name__ == "__main__":
    main()
    mt5.shutdown()