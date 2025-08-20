# app.py
# 这是一个完整的 Streamlit 应用程序，用于创建一个在线的估值定投信号仪表盘。
# (最终版：支持用户在网页上选择不同的指数进行分析)

import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime
import re
import matplotlib.pyplot as plt
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

@st.cache_data(ttl="12h") # 缓存1小时
def get_latest_data(valuation_code, spot_code, entry_percentile=0.5, exit_percentile=0.85, history_years=10):
    """
    获取最新的估值、价格数据，并返回用于分析和绘图的历史数据及实时估值快照。
    """
    try:
        # 1. 获取历史估值数据
        pe_df_raw = ak.stock_index_pe_lg(symbol=valuation_code)
        valuation_df_full = pe_df_raw[['日期', '滚动市盈率']].copy()
        valuation_df_full.rename(columns={'日期': 'date', '滚动市盈率': 'pe'}, inplace=True)
        valuation_df_full['date'] = pd.to_datetime(valuation_df_full['date'])
        valuation_df_full.set_index('date', inplace=True)
        
        # 2. 获取历史价格数据
        price_df_full = ak.stock_zh_index_daily(symbol=spot_code)
        price_df_full['date'] = pd.to_datetime(price_df_full['date'])
        price_df_full.set_index('date', inplace=True)

        # 3. 筛选最近N年的数据作为历史区间
        ten_years_ago = pd.Timestamp.now() - pd.DateOffset(years=history_years)
        valuation_df_10y = valuation_df_full[valuation_df_full.index >= ten_years_ago]
        price_df_10y = price_df_full[price_df_full.index >= ten_years_ago]
        
        if valuation_df_10y.empty or price_df_10y.empty:
            return None, None, None, None, None
        
        # 4. 获取最新收盘价 (与最新估值日期对齐)
        latest_date_dt = valuation_df_10y.index[-1]
        current_price_eod = price_df_10y['close'].asof(latest_date_dt)

        # --- 新增：实时估值计算 ---
        realtime_metrics = None
        try:
            spot_df = ak.stock_zh_index_spot_em()
            realtime_price = spot_df[spot_df['代码'] ==  re.sub(r'\D', '', spot_code)]['最新价'].iloc[0]
            
            last_pe = valuation_df_10y['pe'].iloc[-1]
            last_close = price_df_10y['close'].iloc[-1]
            
            if last_pe > 0 and last_close > 0:
                inferred_eps = last_close / last_pe
                realtime_pe = realtime_price / inferred_eps
                
                combined_pe = pd.concat([valuation_df_10y['pe'], pd.Series([realtime_pe])])
                realtime_pe_percentile = combined_pe.rank(pct=True).iloc[-1]
                
                realtime_metrics = {
                    "realtime_price": realtime_price,
                    "realtime_pe": f"{realtime_pe:.2f}",
                    "realtime_pe_percentile": f"{realtime_pe_percentile:.2%}"
                }
        except Exception as e:
            print(f"无法计算实时估值: {e}")
            realtime_metrics = None # 如果失败，则优雅地跳过
        # --- 新增结束 ---

    except Exception as e:
        print(f"获取数据时出错: {e}")
        return None, None, None, None, None
    
    # --- 信号计算逻辑 (基于日度收盘数据) ---
    latest_pe_percentile = valuation_df_10y['pe'].rank(pct=True).iloc[-1]
    latest_date_str = latest_date_dt.strftime('%Y-%m-%d')

    signal = "建议持有"
    if latest_pe_percentile < entry_percentile:
        signal = "进入买入区间"
    elif latest_pe_percentile > exit_percentile:
        signal = "进入卖出区间"
        
    result = {
        "date": latest_date_str,
        "pe_percentile": f"{latest_pe_percentile:.2%}",
        "signal": signal,
        "entry_threshold": f"<{entry_percentile:.0%}",
        "exit_threshold": f">{exit_percentile:.0%}"
    }
    
    return result, current_price_eod, valuation_df_10y, price_df_10y, realtime_metrics
# -----------------------------------------------------------------------------
# 2. 绘图函数 (不变)
# -----------------------------------------------------------------------------
def plot_pe_history(valuation_df, price_df, stats):
    """绘制历史估值与点位图"""
    
    # --- 设置matplotlib以支持中文显示 ---
    try:
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
    except Exception as e:
        print(f"设置中文字体失败: {e}")
        st.warning("中文字体设置失败，图表中的中文可能无法正常显示。")

    # --- 核心修改点：使用传入的统计值绘制分位线 ---
    danger_value = stats['danger_value']
    median_value = stats['median_value']
    opportunity_value = stats['opportunity_value']
    
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax1 = plt.subplots(figsize=(12, 6))

    # 绘制左轴：市盈率(PE)
    ax1.plot(valuation_df.index, valuation_df['pe'], color='dodgerblue', label='市盈率TTM', zorder=10)
    ax1.axhline(danger_value, color='red', linestyle='--', label=f'危险值 ({danger_value:.2f})')
    ax1.axhline(median_value, color='grey', linestyle='--', label=f'中位值 ({median_value:.2f})')
    ax1.axhline(opportunity_value, color='green', linestyle='--', label=f'机会值 ({opportunity_value:.2f})')
    ax1.set_ylabel('市盈率 (PE-TTM)', color='dodgerblue', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='dodgerblue')
    
    # 绘制右轴：指数点位
    ax2 = ax1.twinx()
    ax2.fill_between(price_df.index, price_df['close'], color='lightgrey', alpha=0.5, label='指数点位')
    ax2.set_ylabel('指数点位', color='grey', fontsize=12)
    ax2.tick_params(axis='y', labelcolor='grey')
    
    # 合并图例
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper left')
    
    fig.tight_layout()
    st.pyplot(fig)

# -----------------------------------------------------------------------------
# 2. Streamlit 网页界面布局
# -----------------------------------------------------------------------------

st.set_page_config(page_title="估值定投信号", page_icon="📈", layout="centered")

selected_index_name = st.selectbox(
    "请选择要分析的指数:",
    options=list(INDEX_MAP.keys())
)

selected_index_info = INDEX_MAP[selected_index_name]
valuation_code = selected_index_info["valuation_code"]
spot_code = selected_index_info["spot_code"]

st.title(f"📈 {selected_index_name} | 4%定投法决策辅助")

st.toast(f"正在获取 {selected_index_name} 的最新数据...")

# 调用核心函数获取所有需要的数据
signal_data, current_price, valuation_history, price_history, realtime_metrics = get_latest_data(
    valuation_code=valuation_code, spot_code=spot_code
)

if signal_data and current_price is not None:
    # --- 第一部分：估值信号展示 ---
    st.markdown(f"#### 一、估值区间判断 (基于近10年收盘数据)")
    signal = signal_data.get('signal', '未知')
    if "买入" in signal: st.success(f"**当前信号：{signal}**")
    elif "卖出" in signal: st.error(f"**当前信号：{signal}**")
    else: st.warning(f"**当前信号：{signal}**")
    col1, col2 = st.columns(2)
    with col1: st.metric(label="当前估值分位", value=signal_data.get('pe_percentile', 'N/A'))
    with col2: st.metric(label="数据更新日期", value=signal_data.get('date', 'N/A'))
    st.caption(f"买入阈值: {signal_data.get('entry_threshold')} | 卖出阈值: {signal_data.get('exit_threshold')}")

    # --- 新增：实时估值快照 ---
    if realtime_metrics:
        st.markdown("---")
        st.markdown("#### 实时估值快照 (仅供参考)")
        col1, col2, col3 = st.columns(3)
        col1.metric("实时价格", f"{realtime_metrics['realtime_price']:.2f}")
        col2.metric("估算实时PE", realtime_metrics['realtime_pe'])
        col3.metric("估算实时分位", realtime_metrics['realtime_pe_percentile'])

    # --- 第二部分：4%定投法交互式判断 ---
    if "买入" in signal:
        st.markdown("---")
        st.markdown("#### 二、4%买点精确判断")
        
        # --- 核心修改点 1: 增加投资金额输入框 ---
        investment_amount = st.number_input(
            label="请输入本次计划投入金额:",
            min_value=0.0,
            step=100.0,
            format="%.2f"
        )
        
        last_buy_price = st.number_input(label="请输入您的上一次买入价格（如无，则输入0）:", min_value=0.0, step=10.0, format="%.2f")
        
        price_for_decision = realtime_metrics['realtime_price'] if realtime_metrics else current_price
        st.metric(label="当前用于判断的价格", value=f"{price_for_decision:.2f}")

        # --- 核心修改点 2: 在行动建议中加入份额估算 ---
        def show_purchase_suggestion(amount, price):
            if amount > 0 and price > 0:
                shares_to_buy = amount / price
                st.info(f"💡 使用 {amount:.2f} 元，大约可买入 **{shares_to_buy:.2f}** 份。")

        if last_buy_price > 0:
            trigger_price = last_buy_price * (1 - 0.04)
            st.info(f"下一个4%买点的触发价格为: **{trigger_price:.2f}**")
            if price_for_decision <= trigger_price:
                st.success("✅ **行动建议：** 当前价格已低于触发点，**符合4%定投条件！**")
                show_purchase_suggestion(investment_amount, price_for_decision)
            else:
                st.warning("⏳ **行动建议：** 当前价格尚未达到下一个4%买入点，请**继续等待**。")
        else:
            st.success("✅ **行动建议：** 当前处于估值低位，且您尚未有持仓，**符合首次买入条件！**")
            show_purchase_suggestion(investment_amount, price_for_decision)
        # --- 修改结束 ---

    # --- 第三部分：显示历史估值图表 ---
    if valuation_history is not None and price_history is not None:
        st.markdown("---")
        plot_pe_history(valuation_history, price_history, selected_index_name)

else:
    st.error("无法加载信号数据，请稍后刷新页面重试。")

st.markdown("---")
st.markdown("##### 工作原理")
st.write(
    f"1. **估值判断**：首先判断当前 **{selected_index_name}** 的估值是否进入**最近十年的历史低位**（低于50%分位），这是可以开始定投的大前提。"
    "2. **4%买点判断**：在满足条件1后，本工具会引导您输入上一次的买入价格，并结合当前最新价格，精确判断是否触发了“比上一个买点再跌4%”的买入信号。"
)
st.info("ℹ️ **数据每小时自动更新一次。**")
