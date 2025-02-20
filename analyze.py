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


def check_current_position():
    # Check if current position is closed
    current_position = mt5.positions_get()
    if current_position:
        # make into dataframe and add header
        df_current_position = pd.DataFrame(current_position)
        df_current_position.columns = current_position[0]._asdict().keys()
        print(df_current_position)
    else:
        print("No current position")

def check_trade_history():
    # Check if trade history is closed
    trade_history = mt5.history_deals_get(datetime.now() - pd.Timedelta(days=1), datetime.now())
    if trade_history:
        df_trade_history = pd.DataFrame(trade_history)
        df_trade_history.columns = trade_history[0]._asdict().keys()
        # show only lot, price tp sl and profit
        unique_volumes = df_trade_history['volume'].unique()
        for volume in unique_volumes:
            df_volume = df_trade_history[df_trade_history['volume'] == volume]
            df_volume.loc[:, 'profit'] = df_volume['profit'].astype(int)
            df_volume_win = df_volume[(df_volume['profit']) > 0]  
            df_volume_loss = df_volume[(df_volume['profit']) <= 0]
            df_percentage_win = len(df_volume_win) / len(df_volume) * 100

            total_profit = df_volume_win['profit'].sum()
            total_loss = df_volume_loss['profit'].sum()
            
            print(f"Volume {volume} win: {len(df_volume_win)}, loss: {len(df_volume_loss)}, "
                  f"win rate: {df_percentage_win:.2f}%, total profit: ${total_profit}, total loss: ${total_loss}, clean profit: ${total_profit + total_loss}")
            
    else:
        print("No trade history")
    

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

    # analyze_trades_by_lotsize()
    check_trade_history()
    

if __name__ == "__main__":
    main()
    mt5.shutdown()