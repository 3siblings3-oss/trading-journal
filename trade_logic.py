
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False

import streamlit as st
import json
import os
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime

TRADES_FILE = "trades.csv"
ACCOUNTS_FILE = "accounts.csv"

class TradeManager:
    def __init__(self):
        self.stock_listing = None
        self.use_gsheets = False
        self.gc = None
        self.sh = None
        
        # Try connecting to Google Sheets
        self.connect_gsheets()
        
        # Init data
        self.init_files()

    def connect_gsheets(self):
        if not HAS_GSHEETS:
            # print("GSheets libraries not found. Using CSV mode.")
            self.use_gsheets = False
            return

        try:
            if "gcp_service_account" in st.secrets:
                # Create a dict from the secrets object
                creds_dict = dict(st.secrets["gcp_service_account"])
                
                # Scope
                scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
                
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                self.gc = gspread.authorize(creds)
                
                # Open or Create Sheet
                try:
                    self.sh = self.gc.open("TradingJournal_DB")
                except gspread.SpreadsheetNotFound:
                    self.sh = self.gc.create("TradingJournal_DB")
                    # Share with user email if needed, or they can find it in Service Account Drive
                    # For now, just create
                    
                self.use_gsheets = True
                print("Connected to Google Sheets!")
        except Exception as e:
            print(f"GSheets Connection Failed (using CSV): {e}")
            self.use_gsheets = False

    def _get_worksheet(self, name):
        if not self.use_gsheets: return None
        try:
            return self.sh.worksheet(name)
        except:
            return self.sh.add_worksheet(title=name, rows=100, cols=20)

    def _load_df(self, filename):
        if self.use_gsheets:
            ws_name = "Accounts" if filename == ACCOUNTS_FILE else "Trades"
            ws = self._get_worksheet(ws_name)
            data = ws.get_all_records()
            if not data:
                return pd.DataFrame() # Return empty if no records
            return pd.DataFrame(data)
        else:
            if os.path.exists(filename):
                return pd.read_csv(filename)
            return pd.DataFrame()

    def _save_df(self, df, filename):
        if self.use_gsheets:
            ws_name = "Accounts" if filename == ACCOUNTS_FILE else "Trades"
            ws = self._get_worksheet(ws_name)
            ws.clear()
            # Update with header and data
            ws.update([df.columns.values.tolist()] + df.values.tolist())
        else:
            df.to_csv(filename, index=False)

    def init_files(self):
        if self.use_gsheets:
            # Check if worksheets exist, init headers if empty
            for name, cols in [("Accounts", ["AccountID", "Broker", "Currency", "InitialBalance", "CurrentBalance"]),
                               ("Trades", ["TradeID", "AccountID", "Symbol", "EntryDate", "Strategy", "TrendScore", 
                                           "EntryPrice", "StopLoss", "Quantity", "UnitQuantity", "RiskAmount", 
                                           "Status", "ExitDate", "ExitPrice", "PnL", "R_Multiple"])]:
                ws = self._get_worksheet(name)
                if not ws.get_all_values():
                    ws.append_row(cols)
        else:
            if not os.path.exists(ACCOUNTS_FILE):
                df = pd.DataFrame(columns=["AccountID", "Broker", "Currency", "InitialBalance", "CurrentBalance"])
                df.to_csv(ACCOUNTS_FILE, index=False)
            
            if not os.path.exists(TRADES_FILE):
                cols = ["TradeID", "AccountID", "Symbol", "EntryDate", "Strategy", 
                        "TrendScore", "EntryPrice", "StopLoss", "Quantity", "UnitQuantity", 
                        "RiskAmount", "Status", "ExitDate", "ExitPrice", "PnL", "R_Multiple"]
                df = pd.DataFrame(columns=cols)
                df.to_csv(TRADES_FILE, index=False)

    # --- Account Management ---
    def get_accounts(self):
        return self._load_df(ACCOUNTS_FILE)

    def add_account(self, name, broker, balance):
        df = self.get_accounts()
        if not df.empty and name in df['AccountID'].values:
            return False, "Account ID already exists"
        
        new_row = {
            "AccountID": name,
            "Broker": broker,
            "Currency": "KRW",
            "InitialBalance": balance,
            "CurrentBalance": balance
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        self._save_df(df, ACCOUNTS_FILE)
        return True, "Account added"

    def delete_account(self, account_id):
        df = self.get_accounts()
        df = df[df['AccountID'] != account_id]
        self._save_df(df, ACCOUNTS_FILE)
        return True

    def update_account(self, old_id, new_id, new_balance):
        df = self.get_accounts()
        idx = df[df['AccountID'] == old_id].index
        if len(idx) > 0:
            # Name Validation
            if old_id != new_id and new_id in df['AccountID'].values:
                return False, "이미 존재하는 계좌명입니다."
            
            # Update Trades first if ID changed
            if old_id != new_id:
                self._update_trades_account_id(old_id, new_id)
            
            current_idx = idx[0]
            df.at[current_idx, 'AccountID'] = new_id
            df.at[current_idx, 'CurrentBalance'] = new_balance
            self._save_df(df, ACCOUNTS_FILE)
            return True, "수정 완료"
        return False, "계좌 찾기 실패"

    def _update_trades_account_id(self, old_id, new_id):
        df = self.get_trades()
        if not df.empty:
            df.loc[df['AccountID'] == str(old_id), 'AccountID'] = str(new_id)
            self._save_df(df, TRADES_FILE)

    # --- Trade Management ---
    def get_trades(self, account_id=None, status=None):
        df = self._load_df(TRADES_FILE)
        if df.empty: return df
        
        # Ensure correct types
        num_cols = ["TradeID", "EntryPrice", "StopLoss", "Quantity", "RiskAmount", "ExitPrice", "PnL", "R_Multiple"]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        if account_id:
            df = df[df['AccountID'] == str(account_id)] # Ensure str comparison
        if status:
            df = df[df['Status'] == status]
        return df

    def add_trade(self, account_id, symbol, strategy, trend_score, entry, sl, qty, unit_qty, risk, entry_date=None):
        df = self._load_df(TRADES_FILE)
        new_id = len(df) + 1
        
        e_date = entry_date if entry_date else datetime.now().strftime("%Y-%m-%d")
        
        new_row = {
            "TradeID": new_id,
            "AccountID": account_id,
            "Symbol": str(symbol), # Force str
            "EntryDate": str(e_date),
            "Strategy": strategy,
            "TrendScore": trend_score,
            "EntryPrice": float(entry),
            "StopLoss": float(sl),
            "Quantity": int(qty),
            "UnitQuantity": int(unit_qty),
            "RiskAmount": int(risk),
            "Status": "Open",
            "ExitDate": "",
            "ExitPrice": 0.0,
            "PnL": 0.0,
            "R_Multiple": 0.0
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        self._save_df(df, TRADES_FILE)
        return True

    def close_trade(self, trade_id, exit_price):
        df = self._load_df(TRADES_FILE)
        idx = df[df['TradeID'] == trade_id].index
        if len(idx) == 0:
            return False
        
        idx = idx[0]
        entry = float(df.at[idx, 'EntryPrice'])
        qty = int(df.at[idx, 'Quantity'])
        sl = float(df.at[idx, 'StopLoss'])
        
        pnl = (exit_price - entry) * qty
        risk_dist = abs(entry - sl)
        r_mult = (exit_price - entry) / risk_dist if risk_dist != 0 else 0

        df.at[idx, 'Status'] = "Closed"
        df.at[idx, 'ExitPrice'] = exit_price
        df.at[idx, 'ExitDate'] = datetime.now().strftime("%Y-%m-%d")
        df.at[idx, 'PnL'] = pnl
        df.at[idx, 'R_Multiple'] = round(r_mult, 2)
        
        self._save_df(df, TRADES_FILE)
        
        acc_id = df.at[idx, 'AccountID']
        self.update_account_balance(acc_id, pnl)
        
        return True

    def update_account_balance(self, account_id, pnl):
        df = self.get_accounts()
        if not df.empty and account_id in df['AccountID'].values:
            df.loc[df['AccountID'] == account_id, 'CurrentBalance'] = pd.to_numeric(df.loc[df['AccountID'] == account_id, 'CurrentBalance']) + pnl
            self._save_df(df, ACCOUNTS_FILE)
            
    def delete_trade(self, trade_id):
        df = self._load_df(TRADES_FILE)
        
        # Check for balance reversal
        trade_rows = df[df['TradeID'] == trade_id]
        if not trade_rows.empty:
            row = trade_rows.iloc[0]
            if row['Status'] == 'Closed':
                pnl = float(row['PnL']) if pd.notnull(row['PnL']) else 0.0
                if pnl != 0:
                    self.update_account_balance(row['AccountID'], -pnl)
                    
        df = df[df['TradeID'] != trade_id]
        self._save_df(df, TRADES_FILE)
        return True

    def update_trade(self, trade_id, updates):
        df = self._load_df(TRADES_FILE)
        idx = df[df['TradeID'] == trade_id].index
        if len(idx) > 0:
            current_idx = idx[0]
            
            # Check if PnL is being changed -> Update Balance
            if 'PnL' in updates:
                old_pnl = float(df.at[current_idx, 'PnL']) if pd.notnull(df.at[current_idx, 'PnL']) else 0.0
                new_pnl = float(updates['PnL'])
                diff = new_pnl - old_pnl
                
                if diff != 0:
                    acc_id = df.at[current_idx, 'AccountID']
                    self.update_account_balance(acc_id, diff)
            
            for key, val in updates.items():
                df.at[current_idx, key] = val
            self._save_df(df, TRADES_FILE)
            return True
        return False

    # --- Logic & Data ---
    def calculate_position(self, capital, risk_pct, entry, sl, trend_score):
        """
        Calculates position size based on:
        1. Trend Score (3=100%, 2=66%, 1=33% of Capital)
        2. Risk Percent
        3. SL Distance
        """
        # 1. Adjust Capital based on Trend
        trend_factor = {3: 1.0, 2: 0.6666, 1: 0.3333}.get(trend_score, 1.0)
        adjusted_capital = capital * trend_factor
        
        # 2. Calculate Risk Amount
        risk_amount = adjusted_capital * (risk_pct / 100.0)
        
        # 3. Calculate Quantity
        # Risk Amount = Qty * |Entry - SL|
        sl_dist = abs(entry - sl)
        if sl_dist == 0:
            return None
        
        total_qty = int(risk_amount / sl_dist)
        
        # 4. Unit Split
        unit_qty = int(total_qty / 3)
        
        return {
            "trend_factor": trend_factor,
            "adjusted_capital": int(adjusted_capital),
            "risk_amount": int(risk_amount),
            "sl_dist": sl_dist,
            "total_qty": total_qty,
            "unit_qty": unit_qty
        }

    def fetch_current_price(self, symbol):
        try:
            # KRX fallback and zero-padding logic
            target_symbol = str(symbol)
            if target_symbol.isdigit() and len(target_symbol) < 6:
                target_symbol = target_symbol.zfill(6)
            
            # Fetch last 10 days
            from datetime import timedelta
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            
            df = fdr.DataReader(target_symbol, start=start_date)
            if not df.empty:
                return float(df['Close'].iloc[-1])
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return None
        return None

    def get_stock_name(self, symbol):
        try:
            target_symbol = str(symbol)
            if target_symbol.isdigit() and len(target_symbol) < 6:
                target_symbol = target_symbol.zfill(6)
                
            if self.stock_listing is None:
                # Cache KRX listing (covers KOSPI, KOSDAQ)
                df_krx = fdr.StockListing('KRX')
                self.stock_listing = df_krx[['Code', 'Name']].set_index('Code')['Name'].to_dict()
            
            return self.stock_listing.get(target_symbol, None)
        except Exception:
            return None
