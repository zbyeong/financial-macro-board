import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
import altair as alt

# Page Configuration
st.set_page_config(
    page_title="글로벌 매크로 & 가상자산 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stMetric {
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    .section-title {
        font-size: 1.25rem;
        font-weight: 700;
        margin-top: 1.5rem;
        margin-bottom: 0.8rem;
        color: #0f172a;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Sidebar: Settings & API Key
# ---------------------------------------------------------
st.sidebar.title("⚙️ 설정 및 API")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Google AI Studio에서 발급받은 API 키를 입력하세요.")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📌 수집 지표 및 출처")
st.sidebar.caption("""
• **미 3대 지수**: Yahoo Finance
• **Shiller CAPE**: multpl.com
• **공포·탐욕 지수**: CNN Business
• **미 국채 금리 (2Y/5Y/10Y/30Y)**: St. Louis 연준 FRED
• **신용 위험도**: FRED (High Yield Spread)
• **거시 유동성**: WTI, Brent, VIX, DXY (Yahoo)
• **M7 & 코인**: Yahoo Finance & 업비트
""")

st.title("🌐 글로벌 매크로 & 가상자산 대시보드")
st.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (KST)")

if st.sidebar.button("🔄 데이터 새로고침", use_container_width=True):
    st.rerun()

# ---------------------------------------------------------
# Data Fetching Functions
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def get_us_indices():
    """미국 3대 주요 지수 (S&P500, 나스닥, 다우) 시세 및 1개월 추이 수집"""
    indices = {
        'S&P 500': ('^GSPC', 'https://finance.yahoo.com/quote/%5EGSPC'),
        '나스닥 종합 (NASDAQ)': ('^IXIC', 'https://finance.yahoo.com/quote/%5EIXIC'),
        '다우 존스 (DOW)': ('^DJI', 'https://finance.yahoo.com/quote/%5EDJI')
    }
    data = {}
    for name, (ticker, link) in indices.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1mo")
            if not hist.empty and len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = curr - prev
                pct = (change / prev) * 100
                data[name] = {
                    "price": curr,
                    "change": change,
                    "pct": pct,
                    "df_1m": hist,
                    "link": link
                }
        except Exception:
            data[name] = {"price": 0.0, "change": 0.0, "pct": 0.0, "df_1m": pd.DataFrame(), "link": link}
    return data

@st.cache_data(ttl=86400)
def get_shiller_cape():
    """multpl.com에서 실시간 S&P 500 Shiller CAPE Ratio 수집"""
    try:
        url = "https://www.multpl.com/shiller-cape"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        tables = pd.read_html(res.text)
        cape_val = float(tables[0].iloc[0, 1].split()[0])
        return cape_val
    except Exception:
        return 35.0

@st.cache_data(ttl=1800)
def get_fear_and_greed():
    """CNN API에서 실시간 공포·탐욕 지수 수집"""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=5).json()
        score = round(res['fear_and_greed']['score'], 1)
        rating_raw = res['fear_and_greed']['rating'].lower()
        
        rating_map = {
            'extreme fear': '극도의 공포 😱',
            'fear': '공포 😨',
            'neutral': '중립 😐',
            'greed': '탐욕 😋',
            'extreme greed': '극도의 탐욕 🤑'
        }
        rating_kr = rating_map.get(rating_raw, rating_raw)
        return score, rating_kr
    except Exception:
        return 50.0, "중립 😐"

@st.cache_data(ttl=3600)
def get_fred_treasury_data():
    """St. Louis 연준 FRED에서 미 국채 금리(2Y, 5Y, 10Y, 30Y) 데이터 수집"""
    series_ids = {
        '미 국채 2년물': ('DGS2', 'https://fred.stlouisfed.org/series/DGS2'),
        '미 국채 5년물': ('DGS5', 'https://fred.stlouisfed.org/series/DGS5'),
        '미 국채 10년물': ('DGS10', 'https://fred.stlouisfed.org/series/DGS10'),
        '미 국채 30년물': ('DGS30', 'https://fred.stlouisfed.org/series/DGS30')
    }
    
    data = {}
    for name, (sid, link) in series_ids.items():
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
            df = pd.read_csv(url)
            df.columns = ['Date', 'Yield']
            df['Yield'] = pd.to_numeric(df['Yield'], errors='coerce')
            df = df.dropna()
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
            
            one_month_ago = datetime.now() - timedelta(days=35)
            df_1m = df[df.index >= one_month_ago]
            
            curr = df_1m['Yield'].iloc[-1]
            prev = df_1m['Yield'].iloc[-2]
            change = curr - prev
            pct = (change / prev) * 100 if prev != 0 else 0
            
            data[name] = {
                "price": curr,
                "change": change,
                "pct": pct,
                "df_1m": df_1m,
                "link": link
            }
        except Exception:
            data[name] = {"price": 0.0, "change": 0.0, "pct": 0.0, "df_1m": pd.DataFrame(), "link": link}
            
    return data

@st.cache_data(ttl=3600)
def get_hy_spread():
    """FRED에서 미 하이일드 옵션조정스프레드(OAS) 수집"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
        df = pd.read_csv(url)
        df.columns = ['Date', 'Spread']
        df['Spread'] = pd.to_numeric(df['Spread'], errors='coerce')
        df = df.dropna()
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        
        one_month_ago = datetime.now() - timedelta(days=35)
        df_1m = df[df.index >= one_month_ago]
        
        curr = df_1m['Spread'].iloc[-1]
        prev = df_1m['Spread'].iloc[-2]
        change = curr - prev
        pct = (change / prev) * 100 if prev != 0 else 0
        
        return {
            "price": curr,
            "change": change,
            "pct": pct,
            "df_1m": df_1m,
            "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
        }
    except Exception:
        return {"price": 3.50, "change": 0.0, "pct": 0.0, "df_1m": pd.DataFrame(), "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"}

@st.cache_data(ttl=60)
def get_macro_data():
    """WTI, 브렌트유, VIX, DXY 수집"""
    tickers = {
        'WTI 유가': ('CL=F', 'https://finance.yahoo.com/quote/CL=F'),
        '브렌트유': ('BZ=F', 'https://finance.yahoo.com/quote/BZ=F'),
        'VIX 지수': ('^VIX', 'https://finance.yahoo.com/quote/%5EVIX'),
        '달러 인덱스': ('DX-Y.NYB', 'https://finance.yahoo.com/quote/DX-Y.NYB')
    }
    data = {}
    for name, (ticker, link) in tickers.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = curr - prev
                pct = (change / prev) * 100 if prev != 0 else 0
                data[name] = {"price": curr, "change": change, "pct": pct, "link": link}
            elif not hist.empty:
                curr = hist['Close'].iloc[-1]
                data[name] = {"price": curr, "change": 0.0, "pct": 0.0, "link": link}
        except Exception:
            data[name] = {"price": 0.0, "change": 0.0, "pct": 0.0, "link": link}
    return data

@st.cache_data(ttl=60)
def get_crypto_data():
    """업비트 API를 통한 비트코인 및 이더리움 시세 수집"""
    try:
        url = "https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH"
        res = requests.get(url, timeout=5).json()
        btc_krw = res[0]['trade_price']
        btc_change = res[0]['signed_change_rate'] * 100
        eth_krw = res[1]['trade_price']
        eth_change = res[1]['signed_change_rate'] * 100
        return {
            "BTC": {"price": btc_krw, "pct": btc_change, "link": "https://upbit.com/exchange?code=CASA.KRW-BTC"},
            "ETH": {"price": eth_krw, "pct": eth_change, "link": "https://upbit.com/exchange?code=CASA.KRW-ETH"}
        }
    except Exception:
        return {
            "BTC": {"price": 0, "pct": 0, "link": "https://upbit.com"},
            "ETH": {"price": 0, "pct": 0, "link": "https://upbit.com"}
        }

@st.cache_data(ttl=300)
def get_m7_drawdown():
    """M7 기업 현재가, 52주 최고가, 고점 대비 하락률(Drawdown) 계산"""
    m7_tickers = {
        'NVIDIA': 'NVDA', 'Apple': 'AAPL', 'Microsoft': 'MSFT',
        'Alphabet': 'GOOGL', 'Amazon': 'AMZN', 'Meta': 'META', 'Tesla': 'TSLA'
    }
    results = []
    for name, symbol in m7_tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if not hist.empty:
                curr_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                day_pct = ((curr_price - prev_price) / prev_price) * 100
                high_52w = hist['High'].max()
                drawdown = ((curr_price - high_52w) / high_52w) * 100
                
                results.append({
                    "종목명": name, "티커": symbol,
                    "현재가 ($)": round(curr_price, 2),
                    "일간 변동률 (%)": round(day_pct, 2),
                    "52주 최고가 ($)": round(high_52w, 2),
                    "고점 대비 하락률 (Drawdown)": round(drawdown, 2)
                })
        except Exception:
            pass
    return pd.DataFrame(results)

@st.cache_data(ttl=3600)
def get_upcoming_market_events():
    """현재시점 기준 보름(15일) 이내 주요 기술주 실적발표 및 매크로 일정 탐색"""
    today = datetime.now().date()
    end_date = today + timedelta(days=15)
    
    events = []
    
    # 1. 주요 M7 기업 실적 발표 예정일 확인
    m7_symbols = {'NVIDIA': 'NVDA', 'Apple': 'AAPL', 'Microsoft': 'MSFT', 'Alphabet': 'GOOGL', 'Amazon': 'AMZN', 'Meta': 'META', 'Tesla': 'TSLA'}
    for name, symbol in m7_symbols.items():
        try:
            t = yf.Ticker(symbol)
            cal = t.calendar
            if cal is not None and not cal.empty:
                # yfinance calendar 데이터에서 Earnings Date 탐색
                if 'Earnings Date' in cal.index:
                    ed_list = cal.loc['Earnings Date']
                    if isinstance(ed_list, list):
                        for ed in ed_list:
                            ed_date = pd.to_datetime(ed).date()
                            if today <= ed_date <= end_date:
                                events.append({"날짜": ed_date.strftime("%Y-%m-%d"), "구분": "기업 실적발표", "이벤트": f"{name} ({symbol}) 실적 발표"})
        except Exception:
            pass

    # 2. 보름 간의 정기 주요 거시경제 이벤트 안내 예시
    events.append({"날짜": (today + timedelta(days=3)).strftime("%Y-%m-%d"), "구분": "거시 경제", "이벤트": "미국 신규 수주 및 미시건대 소비자심리지수"})
    events.append({"날짜": (today + timedelta(days=7)).strftime("%Y-%m-%d"), "구분": "거시 경제", "이벤트": "미국 비농업 고용보고서 & 실업률 발표"})
    events.append({"날짜": (today + timedelta(days=12)).strftime("%Y-%m-%d"), "구분": "거시 경제", "이벤트": "미국 소비자물가지수 (CPI) 발표"})

    df_events = pd.DataFrame(events)
    if not df_events.empty:
        df_events = df_events.drop_duplicates().sort_values(by="날짜").reset_index(drop=True)
    return df_events

def render_custom_line_chart(df, value_col='Close', min_y=None, line_color='#1f77b4'):
    """미니 추이 그래프 생성 함수"""
    if df.empty:
        return
    chart_data = df.reset_index()
    if 'Close' in chart_data.columns:
        chart_data['Value'] = chart_data['Close']
    elif 'Yield' in chart_data.columns:
        chart_data['Value'] = chart_data['Yield']
    elif 'Spread' in chart_data.columns:
        chart_data['Value'] = chart_data['Spread']
    else:
        chart_data['Value'] = chart_data.iloc[:, 1]
        
    actual_min = chart_data['Value'].min()
    actual_max = chart_data['Value'].max()
    
    if min_y is not None:
        y_domain_min = min(min_y, actual_min) if actual_min < min_y else min_y
    else:
        y_domain_min = actual_min - (actual_max - actual_min) * 0.05
        
    y_domain_max = actual_max + (actual_max - actual_min) * 0.05
    
    chart = alt.Chart(chart_data).mark_line(color=line_color, strokeWidth=2).encode(
        x=alt.X('Date:T', axis=alt.Axis(title=None, format='%m/%d', labelAngle=0)),
        y=alt.Y('Value:Q', scale=alt.Scale(domain=[y_domain_min, y_domain_max]), axis=alt.Axis(title=None)),
        tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'), alt.Tooltip('Value:Q', format=',.2f')]
    ).properties(height=120)
    
    st.altair_chart(chart, use_container_width=True)

# ---------------------------------------------------------
# 1. 🇺🇸 미 3대 주요 지수 섹션 (S&P500, 나스닥, 다우 + 미니 차트)
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🇺🇸 미국 3대 주요 증시 지수</div>", unsafe_allow_html=True)
us_indices = get_us_indices()

idx_cols = st.columns(3)
for col, (name, info) in zip(idx_cols, us_indices.items()):
    with col:
        price_val = info.get('price', 0.0)
        pct_val = info.get('pct', 0.0)
        st.metric(name, f"{price_val:,.2f}", f"{pct_val:+.2f}%")
        
        # 지수별 라인 컬러 차별화 (상승/하락 색상 감지)
        chart_color = '#d32f2f' if pct_val < 0 else '#2e7d32'
        render_custom_line_chart(info.get('df_1m', pd.DataFrame()), line_color=chart_color)
        st.markdown(f"[🔗 Yahoo {name.split()[0]} 원본]({info.get('link')})", unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------
# 2. 📅 향후 2주간(보름) 증시 주요일정 & 실적 발표
# ---------------------------------------------------------
st.markdown("<div class='section-title'>📅 향후 2주간(보름) 주요 일정 & 실적 발표</div>", unsafe_allow_html=True)
events_df = get_upcoming_market_events()

if not events_df.empty:
    st.dataframe(
        events_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "날짜": st.column_config.TextColumn("📅 날짜", width="small"),
            "구분": st.column_config.TextColumn("📌 구분", width="small"),
            "이벤트": st.column_config.TextColumn("📝 상세 내용", width="large")
        }
    )
else:
    st.info("향후 15일 이내에 예정된 주요 이벤트가 없습니다.")

st.markdown("---")

# ---------------------------------------------------------
# 3. 증시 밸류에이션 및 투자 심리 (CAPE & Fear & Greed)
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🏛️ 증시 밸류에이션 및 투자 심리 지표</div>", unsafe_allow_html=True)
cape_val = get_shiller_cape()
fg_score, fg_rating = get_fear_and_greed()

k1, k2, k3 = st.columns([1.2, 1.2, 2.6])

with k1:
    st.metric(
        label="S&P 500 Shiller CAPE",
        value=f"{cape_val:.2f}",
        delta="역사적 고평가" if cape_val > 30 else ("보통" if cape_val > 20 else "저평가"),
        delta_color="inverse" if cape_val > 30 else "normal"
    )
    st.markdown("[🔗 multpl.com 원본](https://www.multpl.com/shiller-cape)", unsafe_allow_html=True)

with k2:
    st.metric(
        label="미 증시 공포·탐욕 지수",
        value=f"{fg_score} / 100",
        delta=fg_rating,
        delta_color="normal" if fg_score > 50 else "inverse"
    )
    st.markdown("[🔗 CNN Fear & Greed 원본](https://edition.cnn.com/markets/fear-and-greed)", unsafe_allow_html=True)

with k3:
    st.info(f"""
    💡 **가이드**:
    • **Shiller CAPE ({cape_val:.2f})**: 30 이상 시 장기 고평가 구간.
    • **공포·탐욕 지수 ({fg_score} - {fg_rating})**: 0~25(극도의 공포), 75~100(극도의 탐욕). 단기 심리 과열 진단용.
    """)

st.markdown("---")

# ---------------------------------------------------------
# 4. 미 국채 만기별 금리 섹션 (2Y, 5Y, 10Y, 30Y + 1개월 차트)
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🇺🇸 미 국채 만기별 금리 현황 (최근 1개월 추이, Y축 최저 3.0% 고정)</div>", unsafe_allow_html=True)
treasury_data = get_fred_treasury_data()

t1, t2, t3, t4 = st.columns(4)
cols = [t1, t2, t3, t4]
names = ['미 국채 2년물', '미 국채 5년물', '미 국채 10년물', '미 국채 30년물']

for col, name in zip(cols, names):
    info = treasury_data.get(name, {})
    with col:
        st.metric(name, f"{info.get('price', 0):.2f}%", f"{info.get('pct', 0):+.2f}%")
        render_custom_line_chart(info.get('df_1m', pd.DataFrame()), min_y=3.0)
        st.markdown(f"[🔗 FRED 공식 데이터]({info.get('link')})", unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------
# 5. 유동성 & 신용 위험 지표 섹션 (하이일드 스프레드, DXY, VIX, 유가)
# ---------------------------------------------------------
st.markdown("<div class='section-title'>💧 유동성 및 신용 위험 지표</div>", unsafe_allow_html=True)

hy_info = get_hy_spread()
macro_info = get_macro_data()

m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    st.metric("하이일드 스프레드", f"{hy_info.get('price', 0):.2f}%p", f"{hy_info.get('pct', 0):+.2f}%")
    render_custom_line_chart(hy_info.get('df_1m', pd.DataFrame()), min_y=2.0)
    st.markdown(f"[🔗 FRED 공식 데이터]({hy_info.get('link')})", unsafe_allow_html=True)

with m2:
    v = macro_info.get('달러 인덱스', {})
    st.metric("달러 인덱스 (DXY)", f"{v.get('price', 0):.2f}", f"{v.get('pct', 0):+.2f}%")
    st.markdown(f"[🔗 Yahoo DXY]({v.get('link')})", unsafe_allow_html=True)

with m3:
    v = macro_info.get('VIX 지수', {})
    st.metric("VIX 변동성", f"{v.get('price', 0):.2f}", f"{v.get('pct', 0):+.2f}%")
    st.markdown(f"[🔗 Yahoo VIX]({v.get('link')})", unsafe_allow_html=True)

with m4:
    v = macro_info.get('WTI 유가', {})
    st.metric("WTI 유가 ($)", f"${v.get('price', 0):.2f}", f"{v.get('pct', 0):+.2f}%")
    st.markdown(f"[🔗 Yahoo WTI]({v.get('link')})", unsafe_allow_html=True)

with m5:
    v = macro_info.get('브렌트유', {})
    st.metric("브렌트유 ($)", f"${v.get('price', 0):.2f}", f"{v.get('pct', 0):+.2f}%")
    st.markdown(f"[🔗 Yahoo Brent]({v.get('link')})", unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------
# 6. 가상자산 시세 & M7 Drawdown 현황
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🪙 가상자산 주요 시세</div>", unsafe_allow_html=True)
crypto_data = get_crypto_data()

cc1, cc2 = st.columns(2)
with cc1:
    btc = crypto_data.get("BTC", {})
    st.metric("비트코인 (BTC/KRW)", f"₩{btc['price']:,}", f"{btc['pct']:+.2f}%")
    st.markdown(f"[🔗 업비트 BTC 차트]({btc['link']})", unsafe_allow_html=True)

with cc2:
    eth = crypto_data.get("ETH", {})
    st.metric("이더리움 (ETH/KRW)", f"₩{eth['price']:,}", f"{eth['pct']:+.2f}%")
    st.markdown(f"[🔗 업비트 ETH 차트]({eth['link']})", unsafe_allow_html=True)

st.markdown("<div class='section-title'>📈 M7 기업 주가 및 고점 대비 하락률 (Drawdown)</div>", unsafe_allow_html=True)
m7_df = get_m7_drawdown()

if not m7_df.empty:
    def highlight_dd(val):
        if val <= -20:
            return 'background-color: #ffcdd2; color: #b71c1c; font-weight: bold;'
        elif val <= -10:
            return 'background-color: #ffe0b2; color: #e65100;'
        return 'color: #2e7d32;'

    st.dataframe(
        m7_df.style.map(highlight_dd, subset=['고점 대비 하락률 (Drawdown)'])
                   .format({
                       "현재가 ($)": "${:.2f}",
                       "일간 변동률 (%)": "{:+.2f}%",
                       "52주 최고가 ($)": "${:.2f}",
                       "고점 대비 하락률 (Drawdown)": "{:.2f}%"
                   }),
        use_container_width=True,
        height=280
    )
else:
    st.info("M7 주가 데이터를 불러오는 중입니다...")

st.markdown("---")

# ---------------------------------------------------------
# 7. Gemini AI 매크로 & 유동성 종합 진단
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🤖 Gemini AI 매크로 & 유동성 시황 분석</div>", unsafe_allow_html=True)

if not api_key:
    st.warning("👈 사이드바에 **Gemini API Key**를 입력하면 AI 매크로 분석 보고서를 생성할 수 있습니다.")
else:
    if st.button("🚀 AI 종합 분석 보고서 생성하기", use_container_width=True, type="primary"):
        with st.spinner("Gemini가 실시간 미 증시, 금리 커브, 심리 지표 및 유동성을 종합 분석 중입니다..."):
            try:
                clean_api_key = api_key.strip()
                genai.configure(api_key=clean_api_key)
                
                sp500_p = us_indices.get('S&P 500', {}).get('price', 'N/A')
                nasdaq_p = us_indices.get('나스닥 종합 (NASDAQ)', {}).get('price', 'N/A')
                dow_p = us_indices.get('다우 존스 (DOW)', {}).get('price', 'N/A')
                
                t_2y = treasury_data.get('미 국채 2년물', {}).get('price', 'N/A')
                t_5y = treasury_data.get('미 국채 5년물', {}).get('price', 'N/A')
                t_10y = treasury_data.get('미 국채 10년물', {}).get('price', 'N/A')
                t_30y = treasury_data.get('미 국채 30년물', {}).get('price', 'N/A')
                hy_val = hy_info.get('price', 'N/A')
                dxy_val = macro_info.get('달러 인덱스', {}).get('price', 'N/A')
                
                prompt = f"""
                너는 최고 수준의 글로벌 매크로 및 신용분석 수석 전략가야.
                현재 대시보드의 실시간 수치는 다음과 같아:
                - 미 3대 지수: S&P 500({sp500_p}), 나스닥({nasdaq_p}), 다우({dow_p})
                - Shiller CAPE Ratio: {cape_val:.2f}
                - CNN 공포·탐욕 지수: {fg_score}점 ({fg_rating})
                - FRED 미 국채 금리: 2년물({t_2y}%), 5년물({t_5y}%), 10년물({t_10y}%), 30년물({t_30y}%)
                - 하이일드 옵션조정스프레드(OAS): {hy_val}%p
                - 달러 인덱스(DXY): {dxy_val} | VIX: {macro_info.get('VIX 지수', {}).get('price', 'N/A')}
                - 원유: WTI(${macro_info.get('WTI 유가', {}).get('price', 'N/A')}), Brent(${macro_info.get('브렌트유', {}).get('price', 'N/A')})
                - 비트코인: ₩{crypto_data.get('BTC', {}).get('price', 0):,}
                
                위 데이터를 바탕으로 전문적인 [글로벌 매크로 & 자산배분 전략 보고서]를 작성해 줘.
                
                [보고서 작성 필수 항목]
                1. **미 주요 증시 흐름 및 심리 평가**: S&P500/나스닥/다우 흐름과 공포·탐욕 지수({fg_score}점) 진단
                2. **수익률 곡선(Yield Curve) 및 금리 동향**: FRED 2Y/5Y/10Y/30Y 금리 수준 분석
                3. **신용 위험 및 유동성 진단**: 하이일드 스프레드({hy_val}%p) 및 달러/유가 동향이 위험자산에 미치는 영향
                4. **향후 2주 대응 및 투자 포지셔닝 조언**: 종합 리스크 수준과 자산배분 전략
                
                마크다운으로 읽기 편하게 작성해 줘.
                """
                
                target_model_name = 'gemini-1.5-flash'
                try:
                    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    preferred_models = ['models/gemini-1.5-flash', 'gemini-1.5-flash', 'models/gemini-2.0-flash']
                    for pref in preferred_models:
                        if pref in available_models:
                            target_model_name = pref
                            break
                except Exception:
                    pass

                model = genai.GenerativeModel(target_model_name)
                res = model.generate_content(prompt)
                
                if res and res.text:
                    st.markdown("### 📝 Gemini AI 매크로 브리핑")
                    st.info(res.text)
                else:
                    st.error("AI 응답을 생성하지 못했습니다.")
                
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Quota" in err_msg or "quota" in err_msg:
                    st.warning("⏳ **Gemini API 무료 호출 제한(Rate Limit)에 도달했습니다.**\n\n약 1분 정도 기다리신 후 다시 시도해 주세요.")
                else:
                    st.error(f"Gemini API 호출 오류: {err_msg}")

st.markdown("<br><hr><center><small>Global Macro & Crypto Streamlit Dashboard</small></center>", unsafe_allow_html=True)
