import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import pytz

class ScalpingBot:
    def __init__(self, config):
        self.config = config
        self.initialize_mt5()
        self.session_times = self.get_session_times()
        self.trade_allowed = True
        self.daily_loss = 0.0
        self.last_check = datetime.now()
        self.trade_history = []
        
        print(f"Connected to account #{mt5.account_info().login}")

    def initialize_mt5(self):
        if not mt5.initialize():
            raise RuntimeError("MT5 initialization failed")
            
        if not mt5.login(login=self.config['account'], 
                       password=self.config['password'],
                       server=self.config['server']):
            raise RuntimeError("MT5 login failed")

    def get_session_times(self):
        return {
            'London': {'start': 3, 'end': 12},
            'NewYork': {'start': 8, 'end': 17},
            'Tokyo': {'start': 23, 'end': 8},
            'Sydney': {'start': 17, 'end': 2}
        }

    def check_if_trade_history_closed(self):
        """Check closed trades and update daily loss tracking"""
        if not self.trade_history:
            return
        
        # Get all current positions
        positions = mt5.positions_get()
        current_tickets = [pos.ticket for pos in positions] if positions else []
        
        # Process closed trades
        for trade in self.trade_history[:]:  # Create copy to modify during iteration
            position = mt5.history_deals_get(
                position=trade.get('ticket'),
                date_from=datetime.now() - timedelta(days=1)
            )
            
            if position:  # Trade is closed
                profit = sum(deal.profit for deal in position)
                self.daily_loss += profit
                
                # Log trade result
                result = "WIN" if profit > 0 else "LOSS"
                print(f"Trade closed: {trade['symbol']} {trade['direction']} - {result} (${profit:.2f})")
                
                # Remove from trade history
                self.trade_history.remove(trade)
            
            elif trade.get('ticket') not in current_tickets:
                # Trade not found in history or current positions, remove it
                self.trade_history.remove(trade)
        
        # Print current positions
        if positions:
            print("\nCurrent Positions:")
            for pos in positions:
                profit = pos.profit + pos.swap
                print(f"{pos.symbol} {pos.type} - Profit: ${profit:.2f}")

    def run(self):
        while True:
            try:
                current_time = datetime.now(pytz.timezone('US/Eastern'))
                
                # Check daily loss limit
                # self.check_daily_loss_limit()

                self.check_if_trade_history_closed()
                
                # Main trading logic
                for symbol in self.config['symbols']:
                    # if self.is_trading_time(symbol):
                        # print(f'{symbol} is in session')
                    self.process_symbol(symbol)
                    # else:
                    #     print(f'{symbol} is not in session')
                
                # Sleep for 10 seconds between checks
                time.sleep(10)
                
            except KeyboardInterrupt:
                print("\nShutting down...")
                mt5.shutdown()
                break

    def process_symbol(self, symbol):
        # Get latest market data
        rates = self.get_rates(symbol, self.config['timeframe'], 100)
        if rates is None or len(rates) < 50:
            return
            
        # Calculate indicators
        df = self.calculate_indicators(rates)
        current_price = mt5.symbol_info_tick(symbol).ask
        # Check entry conditions
        print(f'Processing {symbol}')
        if self.check_long_conditions(df, symbol):
            self.execute_trade(symbol, 'buy', current_price)
        elif self.check_short_conditions(df, symbol):
            self.execute_trade(symbol, 'sell', current_price)

    def calculate_indicators(self, rates):
        df = pd.DataFrame(rates)
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['rsi'] = self.calculate_rsi(df['close'])
        df['bb_upper'], df['bb_lower'] = self.calculate_bollinger_bands(df['close'])
        df['vol_sma'] = df['tick_volume'].rolling(20).mean()
        return df.iloc[-1]  # Return latest values

    def check_long_conditions(self, data, symbol):
        cond1 = data['close'] > data['ema9'] and data['close'] > data['ema21']
        cond2 = 50 < data['rsi'] <= 65
        cond3 = data['low'] <= data['bb_lower']
        print(f'{symbol} Buy cond1: {cond1}, cond2: {cond2}, cond3: {cond3}')
        if 'XAU' in symbol:
            cond4 = data['tick_volume'] > data['vol_sma'] * self.config['volatility_threshold']
            return all([cond1, cond2, cond3, cond4])
        return all([cond1, cond2, cond3])

    def check_short_conditions(self, data, symbol):
        cond1 = data['close'] < data['ema9'] and data['close'] < data['ema21']
        cond2 = 35 <= data['rsi'] < 50
        cond3 = data['high'] >= data['bb_upper']
        print(f'{symbol} Sell cond1: {cond1}, cond2: {cond2}, cond3: {cond3}')
        if 'XAU' in symbol:
            cond4 = data['tick_volume'] > data['vol_sma'] * self.config['volatility_threshold']
            return all([cond1, cond2, cond3, cond4])
        return all([cond1, cond2, cond3])

    def execute_trade(self, symbol, direction, entry_price):
        if not self.trade_allowed:
            return
            
        # Calculate position size
        position_size = self.calculate_position_size(symbol, entry_price)
        if position_size <= 0:
            return
            
        # Calculate SL/TP
        sl, tp = self.calculate_risk_levels(symbol, direction, entry_price)
        
        # Create trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": position_size,
            "type": mt5.ORDER_TYPE_BUY if direction == 'buy' else mt5.ORDER_TYPE_SELL,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 202308,
            "comment": "ScalpingBot",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        # Send order
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Trade failed: {result.comment}")
        else:
            print(f"Trade executed: {symbol} {direction} {position_size} lots")
            with open(f'{symbol}.csv', 'a') as f:
                f.write(f"{datetime.now()} | {symbol} | {direction} | {position_size} | Entry: {entry_price} | SL: {sl}, TP: {tp}\n")

    def calculate_position_size(self, symbol, entry_price):
        account_balance = mt5.account_info().balance
        risk_amount = account_balance * self.config['risk_per_trade']
        symbol_info = mt5.symbol_info(symbol)
        
        if 'XAU' in symbol:
            risk_per_unit = (self.config['sl_dollars'] / symbol_info.trade_tick_value)
            position_size = risk_amount / risk_per_unit
        else:
            pip_value = symbol_info.point * 10  # 1 pip in price terms
            risk_pips = self.config['sl_pips'] * pip_value
            position_size = risk_amount / (risk_pips * symbol_info.trade_contract_size)
            
        return round(position_size, 2)

    def calculate_risk_levels(self, symbol, direction, entry_price):
        symbol_info = mt5.symbol_info(symbol)
        if 'XAU' in symbol:
            if direction == 'buy':
                sl = entry_price - self.config['sl_dollars']
                tp = entry_price + self.config['tp_dollars']
            else:
                sl = entry_price + self.config['sl_dollars']
                tp = entry_price - self.config['tp_dollars']
        else:
            pip_size = symbol_info.point * 10
            if direction == 'buy':
                sl = entry_price - self.config['sl_pips'] * pip_size
                tp = entry_price + self.config['tp_pips'] * pip_size
            else:
                sl = entry_price + self.config['sl_pips'] * pip_size
                tp = entry_price - self.config['tp_pips'] * pip_size
                
        return sl, tp

    def get_rates(self, symbol, timeframe, count):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        return rates if rates is not None else None

    def check_daily_loss_limit(self):
        if datetime.now().date() != self.last_check.date():
            self.daily_loss = 0.0
            self.last_check = datetime.now()
            
        if self.daily_loss <= -self.config['daily_loss_limit']:
            print("Daily loss limit reached. Stopping trading.")
            self.trade_allowed = False

    def is_trading_time(self, symbol):
        current_hour = datetime.now(pytz.timezone('US/Eastern')).hour
        session = self.get_symbol_session(symbol)
        if session['start'] < session['end']:
            return session['start'] <= current_hour < session['end']
        else:
            return current_hour >= session['start'] or current_hour < session['end']

    def get_symbol_session(self, symbol):
        if 'JPY' in symbol or 'AUD' in symbol:
            return self.session_times['Tokyo']
        elif 'EUR' in symbol or 'GBP' in symbol:
            return self.session_times['London']
        elif 'XAU' in symbol or 'CAD' in symbol:
            return self.session_times['NewYork']
        else:
            return self.session_times['Sydney']

    @staticmethod
    def calculate_rsi(series, period=7):
        delta = series.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/period).mean()
        avg_loss = loss.ewm(alpha=1/period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_bollinger_bands(series, period=20, dev=2):
        sma = series.rolling(period).mean()
        std = series.rolling(period).std()
        return sma + (std * dev), sma - (std * dev)

if __name__ == "__main__":
    config = {
        'account': 239634700,
        'password': 'B6D4YAMdemo_',
        'server': 'Exness-MT5Trial6',
        'symbols': ['EURUSD', 'GBPUSD', 'XAUUSD'],
        'timeframe': mt5.TIMEFRAME_M1,
        'risk_per_trade': 0.01,
        'daily_loss_limit': 0.03,
        'sl_pips': 5,
        'tp_pips': 10,
        'sl_dollars': 3.0,
        'tp_dollars': 5.0,
        'volatility_threshold': 1.5
    }

    bot = ScalpingBot(config)
    bot.run()