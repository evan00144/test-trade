import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import pytz

# ========================
# Global Configuration
# ========================
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
TIMEFRAME = mt5.TIMEFRAME_M1
RISK_PERCENT = 0.3
MAX_DAILY_LOSS = 2.0  # Percentage of account
TRADE_SESSIONS = {
    "Tokyo": {
        "symbols": ["USDJPY"],
        "time": ("00:00", "06:00"),
        "strategy": "asian_range_breakout"
    },
    "London": {
        "symbols": ["EURUSD", "GBPUSD"],
        "time": ("06:00", "12:00"),
        "strategy": "momentum_scalp"
    },
    "NewYork": {
        "symbols": ["EURUSD", "GBPUSD"],
        "time": ("12:00", "18:00"),
        "strategy": "volatility_arbitrage"
    }
}

# ========================
# Strategy Parameters
# ========================
STRATEGY_PARAMS = {
    "asian_range_breakout": {
        "range_period": 30,  # Minutes
        "atr_period": 14,
        "entry_threshold": 0.7
    },
    "momentum_scalp": {
        "ema_fast": 8,
        "ema_slow": 21,
        "rsi_period": 9,
        "stoch_period": 14
    },
    "volatility_arbitrage": {
        "bollinger_period": 20,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9
    }
}

class ScalpingEngine:
    def __init__(self):
        self.sessions = TRADE_SESSIONS
        self.strategy_params = STRATEGY_PARAMS
        self.trade_history = []
        self.daily_pnl = 0.0
        self.equity = None
        
    def connect_mt5(self):
        if not mt5.initialize():
            raise ConnectionError("MT5 connection failed")
        else: 
            authorized = mt5.login(login=239634700, password="B6D4YAMdemo_", server="Exness-MT5Trial6")
            if not authorized:
                print("Login failed")
                return False
            print(f"Connected to account #{239634700}")
            self.equity = mt5.account_info().equity
            return True
            
    def calculate_position_size(self, symbol):
        tick_value = mt5.symbol_info(symbol).trade_tick_value
        risk_amount = self.equity * RISK_PERCENT / 100
        return round(risk_amount / tick_value, 2)
    
    def get_current_session(self):
        london_tz = pytz.timezone('Europe/London')
        now = datetime.now(london_tz)
        current_time = now.time()
        
        for session, config in self.sessions.items():
            start = datetime.strptime(config["time"][0], "%H:%M").time()
            end = datetime.strptime(config["time"][1], "%H:%M").time()
            
            if start <= current_time < end:
                return session, config
        return None, None
    
    # ========================
    # Session-Specific Strategies
    # ========================
    def asian_range_breakout(self, symbol):
        params = self.strategy_params["asian_range_breakout"]
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, params["range_period"] + 50)
        df = pd.DataFrame(rates)

        # Calculate Asian Range

         # Convert the 'time' column to datetime and set it as the index
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        # Calculate Asian Range
        asian_session = df.between_time("00:00", "06:00")
        high = asian_session['high'].max()
        low = asian_session['low'].min()
        
        # Current Price Action
        current_high = df['high'].iloc[-1]
        current_low = df['low'].iloc[-1]
        
        # ATR Filter
        atr = self.calculate_atr(df, params["atr_period"])

        print(f"High: {high}, Low: {low}, ATR: {atr}, Entry Threshold: {params['entry_threshold']}")
        print(f"Current High: {current_high}, Current Low: {current_low}")
        
        if current_high > high + (atr * params["entry_threshold"]):
            return 'BUY'
        elif current_low < low - (atr * params["entry_threshold"]):
            return 'SELL'
        return None
    
    def momentum_scalp(self, symbol):
        params = self.strategy_params["momentum_scalp"]
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100)
        df = pd.DataFrame(rates)
        
        # EMA Cross
        df['ema_fast'] = df['close'].ewm(span=params["ema_fast"]).mean()
        df['ema_slow'] = df['close'].ewm(span=params["ema_slow"]).mean()
        
        # RSI and Stochastic
        df['rsi'] = self.calculate_rsi(df, params["rsi_period"])
        df['stoch'] = self.calculate_stochastic(df, params["stoch_period"])
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Entry Conditions
        if (current['ema_fast'] > current['ema_slow'] and
            prev['rsi'] < 35 and current['rsi'] > 40 and
            current['stoch'] < 0.2):
            return 'BUY'
        elif (current['ema_fast'] < current['ema_slow'] and
              prev['rsi'] > 65 and current['rsi'] < 60 and
              current['stoch'] > 0.8):
            return 'SELL'
        return None
    
    def volatility_arbitrage(self, symbol):
        params = self.strategy_params["volatility_arbitrage"]
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100)
        df = pd.DataFrame(rates)
        
        # Bollinger Bands
        df['ma'] = df['close'].rolling(params["bollinger_period"]).mean()
        df['std'] = df['close'].rolling(params["bollinger_period"]).std()
        df['upper'] = df['ma'] + (df['std'] * 2)
        df['lower'] = df['ma'] - (df['std'] * 2)
        
        # MACD
        df['macd'] = df['close'].ewm(span=params["macd_fast"]).mean() - \
                     df['close'].ewm(span=params["macd_slow"]).mean()
        df['signal'] = df['macd'].ewm(span=params["macd_signal"]).mean()
        
        current = df.iloc[-1]
        
        if current['close'] < current['lower'] and current['macd'] > current['signal']:
            return 'BUY'
        elif current['close'] > current['upper'] and current['macd'] < current['signal']:
            return 'SELL'
        return None
    
    # ========================
    # Utility Functions
    # ========================
    def calculate_atr(self, df, period):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]
    
    def calculate_rsi(self, df, period):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def calculate_stochastic(self, df, period):
        low_min = df['low'].rolling(period).min()
        high_max = df['high'].rolling(period).max()
        return 100 * (df['close'] - low_min) / (high_max - low_min)
    
    def execute_trade(self, symbol, direction):
        # Risk Management Check
        if self.daily_pnl <= -MAX_DAILY_LOSS:
            return False
            
        lot_size = self.calculate_position_size(symbol)
        price = mt5.symbol_info_tick(symbol).ask if direction == 'BUY' else \
                mt5.symbol_info_tick(symbol).bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": 2,
            "magic": 1001,
            "comment": "Multi-Session Scalp",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            self.trade_history.append(result)
            return True
        return False
    
    def monitor_positions(self):
        positions = mt5.positions_get()
        for pos in positions:
            # Implement trailing stops or profit protection logic
            pass
            
    def run(self):
        self.connect_mt5()
        print("Scalping Engine Started")
        
        while True:
            try:
                current_session, config = self.get_current_session()
                print(f"Current Session: {current_session}")
                print(f"config: {config}")
                if not current_session:
                    time.sleep(60)
                    continue
                
                for symbol in config["symbols"]:
                    strategy = getattr(self, config["strategy"])
                    
                    signal = strategy(symbol)
                    
                    print(f"Symbol: {symbol} | Signal: {signal}")
                    
                    if signal:
                        self.execute_trade(symbol, signal)
                        time.sleep(1)  # Rate limit
                
                self.monitor_positions()
                time.sleep(5)
                
            except KeyboardInterrupt:
                print("Shutting down...")
                break
            except Exception as e:
                print(f"Error: {str(e)}")
                time.sleep(30)

if __name__ == "__main__":
    engine = ScalpingEngine()
    engine.run()
    mt5.shutdown()