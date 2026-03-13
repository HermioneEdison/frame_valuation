# valuation_app.py
# 用于判断估值是高估还是低估

# -----------------------------------
# 导入需要使用的包
# -----------------------------------

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

st.set_page_config(page_title="PVC期现结构分析", layout="wide")
st.title("PVC期现结构可视化分析工具")
st.caption("输入现货价格和12个合约价格，分析期现结构及价差关系")

# 交易日工具函数
def nth_trading_day_of_month(y: int, m: int, n: int) -> pd.Timestamp:
    """用工作日(周一~周五)近似交易日：返回当月第 n 个交易日（n从1开始）。"""
    import pandas as pd
    import pandas.tseries.offsets as pd_offsets
    first = pd.Timestamp(y, m, 1)
    first_td = first if first.weekday() < 5 else first + pd_offsets.BDay(1)
    return first_td + pd_offsets.BDay(n - 1)

def add_trading_days(ts: pd.Timestamp, k: int) -> pd.Timestamp:
    """加 k 个交易日（工作日近似）。"""
    import pandas.tseries.offsets as pd_offsets
    return ts + pd_offsets.BDay(k)

def build_front_12_contracts(today: date) -> list:
    t = pd.Timestamp(today)
    front_y, front_m = None, None
    for i in range(0, 24):
        y = t.year + (t.month - 1 + i) // 12
        m = (t.month - 1 + i) % 12 + 1
        last_trade = nth_trading_day_of_month(y, m, 10)
        delivery_done = add_trading_days(last_trade, 3)
        if delivery_done > t:
            front_y, front_m = y, m
            break
    if front_y is None:
        raise RuntimeError("无法定位最近交割合约（检查日期/逻辑）。")

    out = []
    for j in range(12):
        y = front_y + (front_m - 1 + j) // 12
        m = (front_m - 1 + j) % 12 + 1
        last_trade = nth_trading_day_of_month(y, m, 10)
        delivery_done = add_trading_days(last_trade, 3)
        out.append({
            '合约': f"v{m:02d}",
            '交割年': y,
            '交割月': m,
            '最后交易日': last_trade,
            '交割完成日': delivery_done
        })
    return out

# 输入区域
col1, col2 = st.columns([1, 2])

with col1:
    今天 = st.date_input("今天日期", value=date.today())
    现货价 = st.number_input("现货价格（元/吨）", min_value=0.0, value=4600.0, step=10.0)
    
    # 获取合约列表
    contracts = build_front_12_contracts(今天)
    contract_names = [c['合约'] for c in contracts]
    
    # 选择主力合约和次主力合约
    主力合约 = st.selectbox("选择主力合约", contract_names, index=0)
    次主力合约 = st.selectbox("选择次主力合约", [c for c in contract_names if c != 主力合约], index=min(1, len(contract_names)-1))

with col2:
    st.subheader("12个合约价格输入")
    
    # 创建两行六列的布局来放置合约价格输入框
    cols = st.columns(6)
    
    # 初始化session state
    for contract in contract_names:
        if f"price_{contract}" not in st.session_state:
            st.session_state[f"price_{contract}"] = 0.0
    
    # 在两行中放置合约价格输入框
    for i, contract in enumerate(contract_names):
        with cols[i % 6]:
            st.session_state[f"price_{contract}"] = st.number_input(
                label=f"{contract}",
                value=float(st.session_state[f"price_{contract}"]),
                step=1.0,
                format="%.2f",
                key=f"inp_price_{contract}"
            )

# 显示合约信息
st.divider()
st.subheader("合约信息")
st.write(f"最近交割合约：**{contracts[0]['合约']}**（{contracts[0]['交割年']}-{contracts[0]['交割月']:02d}）")
st.write(f"主力合约：**{主力合约}** | 次主力合约：**{次主力合约}**")

# 计算价差
主力合约价格 = st.session_state[f"price_{主力合约}"]
次主力合约价格 = st.session_state[f"price_{次主力合约}"]

现货主力价差 = 现货价 - 主力合约价格
主力次主力价差 = 主力合约价格 - 次主力合约价格

st.write(f"现货-主力合约价差：**{现货主力价差:.2f}** 元/吨")
st.write(f"主力-次主力合约价差：**{主力次主力价差:.2f}** 元/吨")

# 数据准备
all_prices = [现货价] + [st.session_state[f"price_{contract}"] for contract in contract_names]
labels = ['现货'] + contract_names

# 可视化选项
st.divider()
st.subheader("可视化设置")
show_values = st.checkbox("在图上显示价格数值", value=True)

# 创建图表
fig = go.Figure()

# 绘制现货到各合约的连线
x_positions = list(range(len(labels)))
fig.add_trace(go.Scatter(
    x=x_positions,
    y=all_prices,
    mode='lines+markers',
    name='期现结构',
    line=dict(color='blue', width=2),
    marker=dict(size=8)
))

# 添加主力合约到后续合约的延长线
主力合约_index = labels.index(主力合约)  # 获取主力合约在labels中的索引
主力合约_price = all_prices[主力合约_index]
次主力合约_price = all_prices[labels.index(次主力合约)]  # 获取次主力合约价格

# 计算现货到主力合约的价差
base_spread = 现货价 - 主力合约_price

# 创建延长线：从主力合约位置开始，所有后续合约都加上相同的价差(base_spread)
extended_x = []
extended_y = []

# 从主力合约开始到所有后续合约
for i in range(len(labels)):
    extended_x.append(i)
    if i == 0:  # 现货点
        extended_y.append(现货价)
    else:  # 合约点：主力合约的实际价格 + 现货-主力的价差
        extended_y.append(主力合约_price + base_spread)

# 添加延长线（虚线）
fig.add_trace(go.Scatter(
    x=extended_x,
    y=extended_y,
    mode='lines',
    name='现货-主力价差平行线',
    line=dict(color='red', width=2, dash='dash'),
    visible='legendonly'  # 默认隐藏，可通过图例控制
))

# 如果需要显示数值
if show_values:
    fig.add_trace(go.Scatter(
        x=x_positions,
        y=all_prices,
        mode='text',
        text=[f'{price:.0f}' for price in all_prices],
        textposition='top center',
        name='价格标注',
        showlegend=False
    ))

# 设置图表属性
fig.update_layout(
    title='PVC期现结构分析',
    xaxis=dict(
        tickmode='array',
        tickvals=list(range(len(labels))),
        ticktext=labels,
        title='合约'
    ),
    yaxis=dict(
        title='价格（元/吨）'
    ),
    hovermode='x unified',
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    )
)

st.plotly_chart(fig, use_container_width=True)

# 详细数据分析表格
st.divider()
st.subheader("详细数据表格")

# 准备数据表格
table_data = []
for i, (label, price) in enumerate(zip(labels, all_prices)):
    if i == 0:  # 现货
        table_data.append({
            '合约': label,
            '价格': price,
            '现货-当前': 0,
            '主力-当前': 主力合约_price - price if label != 主力合约 else 0,
            '次主力-当前': 次主力合约_price - price if label != 次主力合约 else 0
        })
    else:
        contract_name = label
        table_data.append({
            '合约': contract_name,
            '价格': price,
            '现货-当前': 现货价 - price,
            '主力-当前': 主力合约_price - price,
            '次主力-当前': 次主力合约_price - price
        })

df_table = pd.DataFrame(table_data)
st.dataframe(df_table.round(2), use_container_width=True)

# 导出功能
st.divider()
st.subheader("数据导出")
csv = df_table.to_csv(index=False, encoding='utf-8-sig')
st.download_button(
    label="下载数据CSV",
    data=csv,
    file_name="PVC期现结构分析数据.csv",
    mime="text/csv"
)

# 补充说明
st.divider()
st.markdown("""
### 说明
- **现货-主力合约价差**：反映现货与期货市场的相对强弱
- **主力-次主力合约价差**：反映近远月合约间的价差关系
- **延长线**：基于现货-主力价差，延伸至后续合约的参考线
- 价格显示选项可在图表上直接显示具体数值
""")