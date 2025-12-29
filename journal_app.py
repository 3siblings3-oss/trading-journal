
import streamlit as st
import pandas as pd
import plotly.express as px
from trade_logic import TradeManager
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="추세 추종 매매일지",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CUSTOM CSS (Premium UI) ---
st.markdown("""
<style>
    .big-font { font-size: 24px !important; font-weight: bold; }
    .metric-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #4CAF50;
        margin-bottom: 10px;
    }
    .loss-card { border-left: 5px solid #FF5252; }
    .neutral-card { border-left: 5px solid #FFC107; }
</style>
""", unsafe_allow_html=True)

# --- INITIALIZE ---
if 'tm' not in st.session_state:
    st.session_state.tm = TradeManager()

tm = st.session_state.tm

# --- SIDEBAR: ACCOUNT MANAGMENT ---
st.sidebar.title("💼 계좌 관리 (Account)")

accounts = tm.get_accounts()
account_names = accounts['AccountID'].tolist() if not accounts.empty else []

selected_account = st.sidebar.selectbox("계좌 선택", account_names)

with st.sidebar.expander("➕ 새 계좌 추가"):
    new_acc_name = st.text_input("계좌명 (예: 키움증권)")
    new_acc_broker = st.text_input("증권사")
    new_acc_balance = st.number_input("초기 자본금", value=10000000, step=1000000)
    if st.button("계좌 생성"):
        success, msg = tm.add_account(new_acc_name, new_acc_broker, new_acc_balance)
        if success:
            st.success("계좌가 생성되었습니다.")
            st.rerun()
        else:
            st.error(msg)
    
    if len(account_names) == 0:
        st.sidebar.warning("⚠️ 먼저 계좌를 생성해주세요!")

    # Account Management (Edit/Delete)
    with st.sidebar.expander("⚙️ 계좌 관리 (Edit/Del)"):
        if len(account_names) > 0:
            target_acc = st.selectbox("관리할 계좌", account_names, key='manage_acc')
            
            # Get current info
            curr_man_row = accounts[accounts['AccountID'] == target_acc].iloc[0]
            
            man_tab1, man_tab2 = st.tabs(["수정", "삭제"])
            
            with man_tab1:
                with st.form("edit_acc_form"):
                    edit_name = st.text_input("계좌명 수정", value=curr_man_row['AccountID'])
                    edit_bal = st.number_input("잔고 수정", value=float(curr_man_row['CurrentBalance']))
                    if st.form_submit_button("수정 저장"):
                        succ, msg = tm.update_account(target_acc, edit_name, edit_bal)
                        if succ:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
            
            with man_tab2:
                st.warning("계좌를 삭제하면? (주의)")
                if st.button("🗑️ 계좌 삭제 확인"):
                    tm.delete_account(target_acc)
                    st.success(f"{target_acc} 삭제됨")
                    st.rerun()
        else:
            st.info("관리할 계좌가 없습니다.")

acc_row = None
if selected_account:
    acc_row = accounts[accounts['AccountID'] == selected_account].iloc[0]
    current_balance = float(acc_row['CurrentBalance'])
    
    # Calculate Invested Amount (Active Trades)
    active_trades = tm.get_trades(selected_account, "Open")
    invested_amt = 0.0
    if not active_trades.empty:
        invested_amt = (active_trades['EntryPrice'] * active_trades['Quantity']).sum()
    
    # Deposit (Available Cash) = Total Balance - Invested Amount
    deposit = current_balance - invested_amt
    
    st.sidebar.markdown("---")
    st.sidebar.metric("예수금 (Deposit)", f"₩{int(deposit):,}")
    st.sidebar.metric("계좌 총 잔고 (Total)", f"₩{int(current_balance):,}")
    st.sidebar.caption(f"증권사: {acc_row['Broker']}")

# --- MAIN CONTENT ---
st.title("📈 추세 추종 매매일지")

tab1, tab2, tab3 = st.tabs(["🧮 리스크 계산기 & 기록", "🏁 진행 중인 매매", "📊 매매 통계"])

# === TAB 1: CALCULATOR ===
with tab1:
    col1, col2 = st.columns([1, 2])
    
    # --- INPUT SECTION ---
    with col1:
        st.subheader("1. 매매 설정 (Setup)")
        raw_symbol = st.text_input("종목 코드", value="005930", help="한국 주식은 종목코드 6자리, 미국은 티커 입력")
        # Auto-pad for KRX (if digit and < 6)
        symbol = raw_symbol.zfill(6) if raw_symbol.isdigit() and len(raw_symbol) < 6 else raw_symbol
        
        # Stock Name Display
        if len(symbol) >= 6:
            stock_name = tm.get_stock_name(symbol)
            if stock_name:
                st.caption(f"🏷️ 종목명: **{stock_name}**")
            else:
                st.caption("⚠️ 종목명을 찾을 수 없습니다.")

        # Trend Selection
        trend_option = st.radio("시장 추세 판단", 
            [3, 2, 1], 
            format_func=lambda x: {3: "🚀 상승장 (100% 비중)", 2: "🦀 횡보장 (66% 비중)", 1: "🐻 하락장 (33% 비중)"}[x]
        )
        
        st.write("---")
        entry_price = st.number_input("진입 가격 (매수가)", value=0)
        
        # SL Mode: Only Percent now
        sl_pct = st.number_input("손절 비율 (-%)", value=8.0, step=0.5, help="기본값 -8%")
        # Auto calculate SL Price
        stop_loss = entry_price * (1 - sl_pct / 100.0)
        if entry_price > 0:
            st.caption(f"📉 계산된 손절가: **{int(stop_loss):,}원** (-{sl_pct}%)")

        risk_pct = st.slider("감수할 리스크 비율 (%)", 1.0, 5.0, 2.0, 0.5)

    # --- RESULT SECTION ---
    with col2:
        st.subheader("2. 포지션 사이징 결과")
        
        calc_res = None
        
        if not selected_account:
            st.warning("👈 왼쪽 사이드바에서 먼저 계좌를 선택해주세요.")
        # Fix condition: stop_loss just needs to be valid (positive)
        elif entry_price <= 0 or stop_loss <= 0:
            st.info("💡 진입 가격과 손절 가격(또는 %)을 입력하면 계산 결과가 표시됩니다.")
        else:
            # Calculate
            # Ensure proper float conversion
            current_cap = float(acc_row['CurrentBalance'])
            calc_res = tm.calculate_position(current_cap, risk_pct, entry_price, stop_loss, trend_option)
            
            if calc_res:
                # Display Result Cards
                c1, c2, c3 = st.columns(3)
                c1.metric("💰 보정 투입자산", f"₩{calc_res['adjusted_capital']:,}")
                c2.metric("⚠️ 총 리스크 금액", f"₩{calc_res['risk_amount']:,}")
                c3.metric("📉 손절폭 (1주당)", f"{float(calc_res['sl_dist']):,.0f}")
                
                # Big Numbers
                bc1, bc2 = st.columns(2)
                bc1.markdown(f"""
                <div class="metric-card">
                    <div style="font-size:14px; color:#888;">추천 매수 수량 (Total)</div>
                    <div class="big-font">{calc_res['total_qty']:,} 주</div>
                    <div style="font-size:12px; color:#aaa;">예상 매수금액: ₩{int(calc_res['total_qty']*entry_price):,}</div>
                </div>
                """, unsafe_allow_html=True)
                
                bc2.markdown(f"""
                <div class="metric-card neutral-card">
                    <div style="font-size:14px; color:#888;">1 유닛 수량 (3분할)</div>
                    <div class="big-font">{calc_res['unit_qty']:,} 주</div>
                    <div style="font-size:12px; color:#aaa;">유닛당 금액: ₩{int(calc_res['unit_qty']*entry_price):,}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("⚠️ 진입가와 손절가가 같을 수 없습니다.")
        
        st.write("---")
        st.subheader("3. 매매 기록 확정 (Confirm)")
        
        # User Manual Input for Recording
        with st.form("trade_record_form"):
            rc1, rc2 = st.columns(2)
            
            with rc1:
                # Default date is today
                record_date = st.date_input("매수 날짜 (Purchase Date)", datetime.now())
                
            with rc2:
                # Default qty is calculated total qty if available, else 0
                default_qty = calc_res['total_qty'] if calc_res else 0
                record_qty = st.number_input("실제 매수 수량 (Purchase Qty)", value=default_qty, step=1)
            
            submit_btn = st.form_submit_button("💾 매매 일지에 저장", use_container_width=True)
            
            if submit_btn:
                if selected_account and record_qty > 0 and entry_price > 0:
                    # Recalculate Risk based on ACTUAL quantity
                    actual_risk = record_qty * abs(entry_price - stop_loss)
                    unit_q = int(record_qty / 3)
                    
                    tm.add_trade(
                        selected_account, symbol, "TrendBreakout", trend_option,
                        entry_price, stop_loss, record_qty, unit_q, actual_risk,
                        entry_date=record_date.strftime("%Y-%m-%d")
                    )
                    st.success(f"매매가 기록되었습니다! ({record_date.strftime('%Y-%m-%d')}, {symbol}, {record_qty}주)")
                else:
                    st.error("계좌 선택, 가격 입력, 매수 수량 > 0 이어야 합니다.")

# === TAB 2: ACTIVE TRADES ===
# === TAB 2: ACTIVE TRADES ===
with tab2:
    col_header, col_btn = st.columns([4, 1])
    col_header.subheader("보유 중인 포지션")
    if col_btn.button("🔄 시세 갱신"):
        st.cache_data.clear()
        st.rerun()

    if selected_account:
        open_trades = tm.get_trades(selected_account, "Open")
        
        if not open_trades.empty:
            # --- 1. TOTAL SUMMARY (Active) ---
            total_eval_amt = 0
            total_net_pnl = 0
            total_fee = 0
            
            # Pre-calculate totals
            # Note: We need to fetch prices for all to get accurate total
            # For performance, we might want to optimize this, but loop is fine for small N
            
            summary_data = []
            
            for idx, row in open_trades.iterrows():
                curr_price = tm.fetch_current_price(row['Symbol'])
                curr_price = float(curr_price) if curr_price else float(row['EntryPrice'])
                
                qty = int(row['Quantity'])
                entry_price = float(row['EntryPrice'])
                eval_amt = curr_price * qty
                
                # Fee: 0.23% of Eval Amount
                fee = eval_amt * 0.0023
                
                gross_pnl = (curr_price * qty) - (entry_price * qty)
                net_pnl = gross_pnl - fee
                
                total_eval_amt += eval_amt
                total_net_pnl += net_pnl
                total_fee += fee
                
                summary_data.append({
                    "TradeID": row['TradeID'],
                    "CurrentPrice": curr_price,
                    "NetPnL": net_pnl,
                    "Fee": fee
                })
            
            # Display Total Summary
            s1, s2, s3 = st.columns(3)
            s1.metric("총 평가 금액", f"₩{int(total_eval_amt):,}")
            s2.metric("예상 수수료 (0.23%)", f"₩{int(total_fee):,}")
            s3.metric("총 평가 손익 (Net)", f"₩{int(total_net_pnl):,}", 
                      delta_color="normal" if total_net_pnl == 0 else "inverse")
            
            st.divider()

            # --- 2. TRADE LIST ---
            # Re-iterate or use summary_data
            for i, row in open_trades.iterrows():
                # Match pre-calculated data
                data = next((item for item in summary_data if item["TradeID"] == row['TradeID']), None)
                curr_price = data['CurrentPrice']
                net_pnl = data['NetPnL']
                fee = data['Fee']
                
                stock_name = tm.get_stock_name(row['Symbol'])
                title_label = f"{stock_name} ({row['Symbol']})" if stock_name else row['Symbol']
                
                with st.expander(f"{title_label} - {row['EntryDate']} (PnL: ₩{int(net_pnl):,})", expanded=True):
                    
                    tc1, tc2, tc3, tc4 = st.columns([1.5, 1.2, 1.5, 1.2]) 
                    
                    entry_price = float(row['EntryPrice'])
                    sl = float(row['StopLoss'])
                    
                    pnl_pct = (net_pnl / (entry_price * int(row['Quantity']))) * 100
                    
                    risk_range = abs(entry_price - sl)
                    r_multiple = (curr_price - entry_price) / risk_range if risk_range else 0
                    
                    tc1.metric("현재가", f"{curr_price:,.0f}", f"{pnl_pct:.2f}% (Net)")
                    tc2.metric("R-배수", f"{r_multiple:.2f}R", delta_color="off")
                    tc3.metric("평가 손익 (수수료후)", f"₩{int(net_pnl):,}")
                    
                    # --- ACTION BUTTONS (Col 4) ---
                    with tc4:
                        ac1, ac2 = st.columns(2)
                        # Toggle Edit State logic using session state
                        edit_key = f"edit_mode_{row['TradeID']}"
                        if ac1.button("✏️", key=f"btn_edit_{row['TradeID']}", help="수정 모드"):
                            st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                            st.rerun()
                            
                        # Close Trade
                        if ac2.button("⚡", key=f"btn_close_{row['TradeID']}", help="포지션 청산"):
                            tm.close_trade(row['TradeID'], curr_price)
                            st.success("청산 완료!")
                            st.rerun()
                            
                    # --- EDIT FORM (Conditional) ---
                    if st.session_state.get(f"edit_mode_{row['TradeID']}", False):
                        st.info("✏️ 포지션 수정 모드")
                        with st.form(key=f"edit_form_{row['TradeID']}"):
                            ec1, ec2, ec3, ec4 = st.columns(4)
                            new_entry = ec1.number_input("매수가 수정", value=entry_price)
                            new_qty = ec2.number_input("수량 수정", value=int(row['Quantity']), step=1)
                            new_sl = ec3.number_input("손절가 수정", value=sl)
                            new_note = ec4.text_input("메모", value=row['Strategy'])
                            
                            c_btn1, c_btn2 = st.columns([1, 1])
                            if c_btn1.form_submit_button("💾 저장"):
                                tm.update_trade(row['TradeID'], {
                                    "EntryPrice": new_entry,
                                    "Quantity": new_qty, 
                                    "StopLoss": new_sl,
                                    "Strategy": new_note
                                })
                                st.session_state[f"edit_mode_{row['TradeID']}"] = False
                                st.success("수정되었습니다.")
                                st.rerun()
                                
                            if c_btn2.form_submit_button("🗑️ 삭제 (주의)"):
                                tm.delete_trade(row['TradeID'])
                                st.success("삭제되었습니다.")
                                st.rerun()

                    # Progress Bar
                    progress_val = min(max((r_multiple + 1.0) / 4.0, 0.0), 1.0)
                    st.progress(progress_val)
                    
                    st.caption(f"진입: {entry_price:,.0f} | 손절: {sl:,.0f} | 리스크: ₩{row['RiskAmount']:,} | 예상 수수료: ₩{int(fee):,}")
                    
                    if not curr_price:
                        st.caption("⚠️ 현재가를 불러올 수 없습니다.")

        else:
            st.info("현재 보유 중인 주식이 없습니다.")
    else:
        st.warning("계좌를 먼저 선택해주세요.")

# === TAB 3: STATS ===
with tab3:
    st.subheader("매매 성과 분석")
    
    # Sub-tabs for Stats
    stat_type = st.radio("보기 모드", ["📊 진행 중 (Active)", "📜 매매 기록 (Closed)"], horizontal=True)
    
    if stat_type == "📊 진행 중 (Active)":
        # Filter Logic: All Accounts or Specific
        filter_opts = ["전체 (All Accounts)"] + account_names
        target_account_filter = st.selectbox("계좌 필터", filter_opts, index=0)
        
        # Determine query param
        q_acc = None if target_account_filter == "전체 (All Accounts)" else target_account_filter
        
        active_df = tm.get_trades(q_acc, "Open")
        
        if not active_df.empty:
            # Calculate summary
            st.caption("현재 보유 중인 종목들의 현황입니다.")
            
            summary_list = []
            total_buy_amt = 0.0
            total_net_pnl = 0.0
            
            for idx, row in active_df.iterrows():
                curr = tm.fetch_current_price(row['Symbol'])
                curr = float(curr) if curr else float(row['EntryPrice'])
                entry = float(row['EntryPrice'])
                qty = int(row['Quantity'])
                
                # 0.23% Fee logic
                fee = (curr * qty) * 0.0023
                net_pnl = ((curr - entry) * qty) - fee
                
                # Accumulate Totals
                total_buy_amt += (entry * qty)
                total_net_pnl += net_pnl
                
                stock_name = tm.get_stock_name(row['Symbol'])
                
                summary_list.append({
                    "Account": row['AccountID'],
                    "종목명": stock_name,
                    "Symbol": row['Symbol'],
                    "매수가": f"{entry:,.0f}",
                    "현재가": f"{curr:,.0f}",
                    "수량": qty,
                    "평가손익(Net)": int(net_pnl),
                    "수익률": f"{(net_pnl/(entry*qty)*100):.2f}%"
                })
            
            # Display Total Metrics
            total_roi = (total_net_pnl / total_buy_amt * 100) if total_buy_amt > 0 else 0.0
            
            m1, m2, m3 = st.columns(3)
            m1.metric("총 매수 금액", f"₩{int(total_buy_amt):,}")
            m2.metric("총 평가 손익 (Net)", f"₩{int(total_net_pnl):,}", delta=f"{int(total_net_pnl):,}")
            m3.metric("총 수익률", f"{total_roi:.2f}%", delta=f"{total_roi:.2f}%")
            
            st.divider()
            
            st.dataframe(pd.DataFrame(summary_list))
        else:
            st.info("진행 중인 매매가 없습니다.")
            
    else:
        if selected_account:
            history = tm.get_trades(selected_account, "Closed")
            
            if not history.empty:
                # Sort by Exit Date (descending)
                if 'ExitDate' in history.columns:
                    history['ExitDate'] = pd.to_datetime(history['ExitDate'], errors='coerce')
                    history = history.sort_values("ExitDate", ascending=False)
                
                # --- KPIs ---
                total_pnl = history['PnL'].sum()
                winning_trades = len(history[history['PnL'] > 0])
                total_trades_count = len(history)
                win_rate = (winning_trades / total_trades_count) * 100 if total_trades_count > 0 else 0
                avg_r = history['R_Multiple'].mean()
                
                k1, k2, k3 = st.columns(3)
                k1.metric("총 실현 손익", f"₩{int(total_pnl):,}")
                k2.metric("승률 (Win Rate)", f"{win_rate:.1f}%")
                k3.metric("평균 R-배수", f"{avg_r:.2f}R")
                
                # --- EQUITY CURVE ---
                history_chart = history.sort_values("ExitDate")
                history_chart['CumulativePnL'] = history_chart['PnL'].cumsum() + float(acc_row['InitialBalance'])
                fig = px.line(history_chart, x='ExitDate', y='CumulativePnL', title="자산 증감 (Equity Curve)", markers=True)
                st.plotly_chart(fig, use_container_width=True)
                
                st.divider()
                
                # --- HISTORY LIST (CARD VIEW) ---
                for idx, row in history.iterrows():
                    stock_name = tm.get_stock_name(row['Symbol'])
                    title_label = f"{stock_name} ({row['Symbol']})" if stock_name else row['Symbol']
                    border_color = "🟢" if row['PnL'] > 0 else "🔴" if row['PnL'] < 0 else "⚪"
                    
                    with st.expander(f"{border_color} {title_label} - {row['ExitDate'].strftime('%Y-%m-%d') if pd.notnull(row['ExitDate']) else '-'} (PnL: ₩{int(row['PnL']):,})"):
                        
                        hc1, hc2, hc3, hc4 = st.columns(4)
                        hc1.metric("진입가", f"{float(row['EntryPrice']):,.0f}")
                        hc2.metric("청산가", f"{float(row['ExitPrice']):,.0f}")
                        hc3.metric("R-배수", f"{float(row['R_Multiple']):.2f}R", 
                                   delta="WIN" if row['PnL'] > 0 else "LOSS", delta_color="normal")
                        hc4.metric("실현 손익", f"₩{int(row['PnL']):,}")
                        
                        # Manage Menu
                        st.markdown("---")
                        h_m_col1, h_m_col2 = st.columns([1, 4])
                        h_action = h_m_col1.selectbox("기록 관리", ["메뉴 선택", "수정", "삭제"], key=f"h_act_{row['TradeID']}", label_visibility="collapsed")
                        
                        if h_action == "수정":
                            with h_m_col2:
                                with st.form(key=f"h_edit_{row['TradeID']}"):
                                    h_new_exit = st.number_input("청산가", value=float(row['ExitPrice']))
                                    h_new_pnl = st.number_input("손익", value=float(row['PnL']))
                                    h_new_note = st.text_input("메모", value=row['Strategy'])
                                    if st.form_submit_button("수정 저장"):
                                        tm.update_trade(row['TradeID'], {"ExitPrice": h_new_exit, "PnL": h_new_pnl, "Strategy": h_new_note})
                                        st.success("수정됨")
                                        st.rerun()
                                        
                        elif h_action == "삭제":
                            with h_m_col2:
                                if st.button("🗑️ 기록 삭제", key=f"h_del_{row['TradeID']}"):
                                    tm.delete_trade(row['TradeID'])
                                    st.success("삭제됨")
                                    st.rerun()

            else:
                st.info("아직 완료된 매매 기록이 없습니다.")
        else:
            st.warning("계좌를 먼저 선택해주세요.")
