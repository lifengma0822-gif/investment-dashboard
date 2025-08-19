# app.py
# 这是一个完整的 Streamlit 应用程序，用于创建一个在线的估值定投信号仪表盘。
# (增强版：已加入完整的4%定投法交互式判断逻辑)

import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. 核心函数 (数据获取和信号计算)
# -----------------------------------------------------------------------------

@st.cache_data(ttl="1h") # 缩短缓存时间为1小时，以便更及时获取价格
def get_latest_data(valuation_code="000300", entry_percentile=0.5, exit_percentile=0.85):
    """
    获取最新的估值、价格数据，并生成交易信号。
    """
    st.toast("正在从网络获取最新数据...")
    
    # --- 数据获取逻辑 ---
    try:
        # 1. 获取历史估值数据
        pe_df_raw = ak.stock_index_pe_lg(symbol=valuation_code)
        valuation_df = pe_df_raw[['日期', '滚动市盈率']]
        valuation_df.rename(columns={'日期': 'date', '滚动市盈率': 'pe'}, inplace=True)
        valuation_df['date'] = pd.to_datetime(valuation_df['date'])
        valuation_df.set_index('date', inplace=True)
        
        # 2. 获取实时价格数据
        spot_df = ak.stock_zh_index_spot()
        current_price = spot_df[spot_df['代码'] == f"sh{valuation_code}"]['最新价'].iloc[0]

    except Exception as e:
        st.error(f"获取数据时出错: {e}")
        return None, None
    
    if valuation_df.empty:
        return None, None

    # --- 信号计算逻辑 ---
    latest_pe_percentile = valuation_df['pe'].rank(pct=True).iloc[-1]
    latest_date = valuation_df.index[-1].strftime('%Y-%m-%d')

    signal = "建议持有"
    if latest_pe_percentile < entry_percentile:
        signal = "进入买入区间"
    elif latest_pe_percentile > exit_percentile:
        signal = "进入卖出区间"
        
    result = {
        "date": latest_date,
        "pe_percentile": f"{latest_pe_percentile:.2%}",
        "signal": signal,
        "entry_threshold": f"<{entry_percentile:.0%}",
        "exit_threshold": f">{exit_percentile:.0%}"
    }
    
    return result, current_price

# -----------------------------------------------------------------------------
# 2. Streamlit 网页界面布局
# -----------------------------------------------------------------------------

st.set_page_config(page_title="估值定投信号", page_icon="📈", layout="centered")
st.title("📈 沪深300 | 4%定投法决策辅助")

# 调用核心函数获取信号和当前价格
signal_data, current_price = get_latest_data(valuation_code="000300")

if signal_data and current_price:
    signal = signal_data.get('signal', '未知')
    pe_percentile = signal_data.get('pe_percentile', 'N/A')
    date = signal_data.get('date', 'N/A')

    # --- 第一部分：估值信号展示 ---
    st.markdown("#### 一、估值区间判断")
    if "买入" in signal:
        st.success(f"**当前信号：{signal}**")
    elif "卖出" in signal:
        st.error(f"**当前信号：{signal}**")
    else:
        st.warning(f"**当前信号：{signal}**")

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="当前估值分位", value=pe_percentile)
    with col2:
        st.metric(label="数据更新日期", value=date)
    st.caption(f"买入阈值: {signal_data.get('entry_threshold')} | 卖出阈值: {signal_data.get('exit_threshold')}")

    # --- 第二部分：4%定投法交互式判断 (核心升级) ---
    if "买入" in signal:
        st.markdown("---")
        st.markdown("#### 二、4%买点精确判断")
        
        # 获取用户输入的上一次买入价
        last_buy_price = st.number_input(
            label="请输入您的上一次买入价格（如无，则输入0）:",
            min_value=0.0,
            step=10.0,
            format="%.2f"
        )
        
        st.metric(label="当前指数价格", value=f"{current_price:.2f}")

        if last_buy_price > 0:
            # 计算下一个4%买点的触发价格
            trigger_price = last_buy_price * (1 - 0.04)
            
            st.info(f"下一个4%买点的触发价格为: **{trigger_price:.2f}**")
            
            # 判断当前价格是否满足条件
            if current_price <= trigger_price:
                st.success("✅ **行动建议：** 当前价格已低于触发点，**符合4%定投条件！**")
            else:
                st.warning("⏳ **行动建议：** 当前价格尚未达到下一个4%买入点，请**继续等待**。")
        else:
            # 如果是第一次买入
            st.success("✅ **行动建议：** 当前处于估值低位，且您尚未有持仓，**符合首次买入条件！**")

else:
    st.error("无法加载信号数据，请稍后刷新页面重试。")

st.markdown("---")
st.markdown("##### 工作原理")
st.write(
    "1. **估值判断**：首先判断当前沪深300的估值是否进入历史低位（低于50%分位），这是可以开始定投的大前提。"
    "2. **4%买点判断**：在满足条件1后，本工具会引导您输入上一次的买入价格，并结合当前最新价格，精确判断是否触发了“比上一个买点再跌4%”的买入信号。"
)
st.info("ℹ️ **数据每小时自动更新一次。**")
