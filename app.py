# app.py
# 这是一个完整的 Streamlit 应用程序，用于创建一个在线的估值定投信号仪表盘。
# (最终版：支持用户在网页上选择不同的指数进行分析)

import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime
import re

# -----------------------------------------------------------------------------
# 0. 指数定义
# -----------------------------------------------------------------------------
# 创建一个字典，用于映射用户友好的指数名称和akshare所需的代码
INDEX_MAP = {
    "沪深300": {"valuation_code": "沪深300", "spot_code": "sh000300"},
    "中证500": {"valuation_code": "中证500", "spot_code": "sh000905"},
    "创业板指": {"valuation_code": "创业板指", "spot_code": "sz399006"},
    "上证50": {"valuation_code": "上证50", "spot_code": "sh000016"},
    "科创50": {"valuation_code": "科创50", "spot_code": "sh000688"},
}

# -----------------------------------------------------------------------------
# 1. 核心函数 (数据获取和信号计算)
# -----------------------------------------------------------------------------

@st.cache_data(ttl="1h") # 缓存1小时
def get_latest_data(valuation_code, spot_code, entry_percentile=0.5, exit_percentile=0.85, history_years=10):
    """
    获取最新的估值、价格数据，并基于指定历史年份生成交易信号。
    """
    # --- 核心修正：移除了 st.toast() 调用 ---
    
    # --- 数据获取逻辑 ---
    try:
        # 1. 获取历史估值数据
        pe_df_raw = ak.stock_index_pe_lg(symbol=valuation_code)
        valuation_df_full = pe_df_raw[['日期', '滚动市盈率']].copy()
        valuation_df_full.rename(columns={'日期': 'date', '滚动市盈率': 'pe'}, inplace=True)
        valuation_df_full['date'] = pd.to_datetime(valuation_df_full['date'])
        valuation_df_full.set_index('date', inplace=True)
        
        # 筛选最近N年的数据作为历史区间
        ten_years_ago = pd.Timestamp.now() - pd.DateOffset(years=history_years)
        valuation_df = valuation_df_full[valuation_df_full.index >= ten_years_ago]

        # 2. 获取实时价格数据
        spot_df = ak.stock_zh_index_spot()
        current_price = spot_df[spot_df['代码'] ==  re.sub(r'\D', '', spot_code）]['最新价'].iloc[0]

    except Exception as e:
        print(f"获取数据时出错: {e}")
        return None, None
    
    if valuation_df.empty:
        return None, None

    # --- 信号计算逻辑 (基于10年数据) ---
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

# --- 让用户选择指数 ---
selected_index_name = st.selectbox(
    "请选择要分析的指数:",
    options=list(INDEX_MAP.keys())
)

# 根据用户的选择获取对应的代码
selected_index_info = INDEX_MAP[selected_index_name]
valuation_code = selected_index_info["valuation_code"]
spot_code = selected_index_info["spot_code"]

# 动态更新标题
st.title(f"📈 {selected_index_name} | 4%定投法决策辅助")

# --- 核心修正：在调用缓存函数之前显示 toast ---
st.toast(f"正在获取 {selected_index_name} 的最新数据...")
# --- 修改结束 ---

# 调用核心函数获取信号和当前价格
signal_data, current_price = get_latest_data(valuation_code=valuation_code, spot_code=spot_code)

if signal_data and current_price is not None:
    signal = signal_data.get('signal', '未知')
    pe_percentile = signal_data.get('pe_percentile', 'N/A')
    date = signal_data.get('date', 'N/A')

    # --- 第一部分：估值信号展示 ---
    st.markdown(f"#### 一、估值区间判断 (基于近10年历史数据)")
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

    # --- 第二部分：4%定投法交互式判断 ---
    if "买入" in signal:
        st.markdown("---")
        st.markdown("#### 二、4%买点精确判断")
        
        last_buy_price = st.number_input(
            label="请输入您的上一次买入价格（如无，则输入0）:",
            min_value=0.0,
            step=10.0,
            format="%.2f"
        )
        
        st.metric(label="当前指数价格", value=f"{current_price:.2f}")

        if last_buy_price > 0:
            trigger_price = last_buy_price * (1 - 0.04)
            st.info(f"下一个4%买点的触发价格为: **{trigger_price:.2f}**")
            
            if current_price <= trigger_price:
                st.success("✅ **行动建议：** 当前价格已低于触发点，**符合4%定投条件！**")
            else:
                st.warning("⏳ **行动建议：** 当前价格尚未达到下一个4%买入点，请**继续等待**。")
        else:
            st.success("✅ **行动建议：** 当前处于估值低位，且您尚未有持仓，**符合首次买入条件！**")

else:
    st.error("无法加载信号数据，请稍后刷新页面重试。")

st.markdown("---")
st.markdown("##### 工作原理")
st.write(
    f"1. **估值判断**：首先判断当前 **{selected_index_name}** 的估值是否进入**最近十年的历史低位**（低于50%分位），这是可以开始定投的大前提。"
    "2. **4%买点判断**：在满足条件1后，本工具会引导您输入上一次的买入价格，并结合当前最新价格，精确判断是否触发了“比上一个买点再跌4%”的买入信号。"
)
st.info("ℹ️ **数据每小时自动更新一次。**")
