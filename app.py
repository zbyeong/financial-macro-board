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
• **가상자산 시세/지표**: Upbit, Binance, yfinance (가격 겹침 듀얼 차트 적용)
• **미 3대 지수**: Yahoo Finance
• **Shiller CAPE**: multpl.com (차단 우회 적용)
• **증시 공포·탐욕 지수**: CNN Business (실시간 연동)
• **미 국채 금리**: St. Louis 연준 FRED
• **거시 유동성**: WTI, Brent, VIX, DXY, High Yield Spread
• **M7 실적/PER**: Yahoo Finance
• **거시 경제 일정**: ForexFactory
""")

st.title("🌐 글로벌 매크로 & 가상자산 대시보드")
st.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (KST)")

if st.sidebar.button("🔄 데이터 새로고침", use_container_width=True):
    st.rerun()

# ---------------------------------------------------------
# Data Fetching Functions
# ---------------------------------------------------------

@st.cache_data(ttl=1800)
def get_crypto_fear_and_greed():
    """Alternative.me 크립토 공포 탐욕 지수 (무료 API)"""
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        data = res['data'][0]
        score = int(data['value'])
        rating_raw = data['value_classification']
        
        rating_map = {
            'Extreme Fear': '극도의 공포 😱', 'Fear': '공포 😨',
            'Neutral': '중립 😐', 'Greed': '탐욕 😋', 'Extreme Greed': '극도의 탐욕 🤑'
        }
        return score, rating_map.get(rating_raw, rating_raw)
    except Exception:
        return 50, "중립 😐"

@st.cache_data(ttl=60)
def get_crypto_extended_data():
    """업비트, 환율, 바이낸스 시세 수집"""
    result = {
        "btc_krw": 0, "btc_pct": 0.0,
        "eth_krw": 0, "eth_pct": 0.0,
        "kimchi_premium": None,
        "funding_rate": None,
        "binance_btc_usd": None,
        "usdkrw": 1380.0
    }

    try:
        upbit_url = "https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH"
        upbit_res = requests.get(upbit_url, timeout=5).json()
        result["btc_krw"] = upbit_res[0]['trade_price']
        result["btc_pct"] = upbit_res[0]['signed_change_rate'] * 100
        result["eth_krw"] = upbit_res[1]['trade_price']
        result["eth_pct"] = upbit_res[1]['signed_change_rate'] * 100
    except Exception:
        pass

    try:
        forex_url = "https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD"
        forex_res = requests.get(forex_url, timeout=5).json()
        result["usdkrw"] = float(forex_res[0]['basePrice'])
    except Exception:
        try:
            usdkrw_ticker = yf.Ticker("KRW=X")
            hist = usdkrw_ticker.history(period="5d")
            if not hist.empty:
                result["usdkrw"] = float(hist['Close'].iloc[-1])
        except Exception:
            pass

    btc_usd = None
    try:
        binance_url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        binance_res = requests.get(binance_url, timeout=5).json()
        btc_usd = float(binance_res['price'])
    except Exception:
        try:
            btc_yf = yf.Ticker("BTC-USD").history(period="2d")
            if not btc_yf.empty:
                btc_usd = float(btc_yf['Close'].iloc[-1])
        except Exception:
            pass

    result["binance_btc_usd"] = btc_usd

    try:
        funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
        funding_res = requests.get(funding_url, timeout=5).json()
        result["funding_rate"] = float(funding_res['lastFundingRate']) * 100
    except Exception:
        result["funding_rate"] = None

    if result["btc_krw"] > 0 and btc_usd and result["usdkrw"] > 0:
        global_btc_krw = btc_usd * result["usdkrw"]
        result["kimchi_premium"] = ((result["btc_krw"] / global_btc_krw) - 1) * 100

    return result

@st.cache_data(ttl=86400)
def get_btc_all_indicators():
    """yfinance 기반 비트코인 200주 이평선, 주봉 RSI, MVRV, NUPL 및 장기홀더/HODL 고속 모델"""
    try:
        btc = yf.Ticker("BTC-USD")
        df = btc.history(period="max", interval="1wk")
        if df.empty or len(df) < 50:
            df = btc.history(period="max", interval="1d")
            df = df['Close'].resample('W').last().to_frame()
        else:
            df = df[['Close']]
            
        df = df.dropna()
        df['200W_MA'] = df['Close'].rolling(window=200).mean()
        
        # 주봉 RSI (14주)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['Weekly_RSI'] = 100 - (100 / (1 + rs))
        
        # MVRV 및 NUPL 모델
        ma_365 = df['Close'].rolling(window=52).mean()
        df['MVRV_Model'] = (df['Close'] / ma_365) * 1.2
        df['NUPL_Model'] = (df['Close'] - ma_365) / df['Close']
        
        # 장기 보유자 공급량 (LTH Supply) 및 1년 이상 미이동 비중(HODL Wave Proxy) 모델
        z_score = (df['Close'] - df['Close'].rolling(window=150).mean()) / df['Close'].rolling(window=150).std()
        
        base_inactive_supply = 13500000
        df['Inactive_1yr_Supply'] = base_inactive_supply - (z_score * 800000).clip(lower=-4000000, upper=4000000)
        
        base_ratio = 63.0
        df['Inactive_1yr_Ratio'] = base_ratio - (z_score * 12.0).clip(lower=-25, upper=25)
        
        return df.dropna(subset=['Weekly_RSI'])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_us_indices():
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
                    "price": curr, "change": change, "pct": pct,
                    "df_1m": hist, "link": link
                }
        except Exception:
            data[name] = {"price": 0.0, "change": 0.0, "pct": 0.0, "df_1m": pd.DataFrame(), "link": link}
    return data

@st.cache_data(ttl=3600)
def get_shiller_cape():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    try:
        url = "https://www.multpl.com/shiller-pe"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            tables = pd.read_html(res.text)
            cape_val = float(tables[0].iloc[0, 1].split()[0])
            return cape_val
    except Exception:
        pass

    try:
        url_backup = "https://www.multpl.com/shiller-pe/table/by-month"
        res = requests.get(url_backup, headers=headers, timeout=5)
        if res.status_code == 200:
            tables = pd.read_html(res.text)
            cape_val = float(tables[0].iloc[0, 1])
            return cape_val
    except Exception:
        pass

    return 36.5

@st.cache_data(ttl=1800)
def get_fear_and_greed():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://edition.cnn.com/markets/fear-and-greed'
    }
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            score = round(data['fear_and_greed']['score'], 1)
            rating_raw = data['fear_and_greed']['rating'].lower()
            rating_map = {
                'extreme fear': '극도의 공포 😱',
                'fear': '공포 😨',
                'neutral': '중립 😐',
                'greed': '탐욕 😋',
                'extreme greed': '극도의 탐욕 🤑'
            }
            return score, rating_map.get(rating_raw, rating_raw)
    except Exception:
        pass

    return 50.0, "중립 😐"

@st.cache_data(ttl=3600)
def get_fred_treasury_data():
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
            
            data[name] = {"price": curr, "change": change, "pct": pct, "df_1m": df_1m, "link": link}
        except Exception:
            data[name] = {"price": 0.0, "change": 0.0, "pct": 0.0, "df_1m": pd.DataFrame(), "link": link}
    return data

@st.cache_data(ttl=3600)
def get_hy_spread():
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
        return {"price": curr, "change": change, "pct": pct, "df_1m": df_1m, "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"}
    except Exception:
        return {"price": 3.50, "change": 0.0, "pct": 0.0, "df_1m": pd.DataFrame(), "link": ""}

@st.cache_data(ttl=60)
def get_macro_data():
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
        except Exception:
            data[name] = {"price": 0.0, "change": 0.0, "pct": 0.0, "link": link}
    return data

@st.cache_data(ttl=300)
def get_m7_drawdown():
    m7_tickers = {
        'NVIDIA': 'NVDA', 'Apple': 'AAPL', 'Microsoft': 'MSFT',
        'Alphabet': 'GOOGL', 'Amazon': 'AMZN', 'Meta': 'META', 'Tesla': 'TSLA'
    }
    results = []
    for name, symbol in m7_tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            info = ticker.info
            
            if not hist.empty:
                curr_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                day_pct = ((curr_price - prev_price) / prev_price) * 100
                high_52w = hist['High'].max()
                drawdown = ((curr_price - high_52w) / high_52w) * 100
                
                pe_ttm = info.get('trailingPE', None)
                pe_fwd = info.get('forwardPE', None)
                
                results.append({
                    "종목명": name, "티커": symbol,
                    "현재가 ($)": round(curr_price, 2),
                    "일간 변동률 (%)": round(day_pct, 2),
                    "52주 최고가 ($)": round(high_52w, 2),
                    "고점 대비 하락률 (Drawdown)": round(drawdown, 2),
                    "PER (TTM)": pe_ttm,
                    "PER (FWD)": pe_fwd
                })
        except Exception:
            pass
    return pd.DataFrame(results)

@st.cache_data(ttl=3600)
def get_upcoming_market_events():
    today = datetime.now().date()
    end_date = today + timedelta(days=15)
    events = []
    
    m7_symbols = {'NVIDIA': 'NVDA', 'Apple': 'AAPL', 'Microsoft': 'MSFT', 'Alphabet': 'GOOGL', 'Amazon': 'AMZN', 'Meta': 'META', 'Tesla': 'TSLA'}
    for name, symbol in m7_symbols.items():
        try:
            t = yf.Ticker(symbol)
            cal = t.calendar
            earnings_dates = []
            if isinstance(cal, dict) and 'Earnings Date' in cal:
                earnings_dates = cal['Earnings Date']
            elif isinstance(cal, pd.DataFrame) and 'Earnings Date' in cal.index:
                earnings_dates = cal.loc['Earnings Date']
                
            if not isinstance(earnings_dates, list):
                earnings_dates = [earnings_dates]
                
            for ed in earnings_dates:
                if pd.notnull(ed):
                    ed_date = pd.to_datetime(ed).date()
                    if today <= ed_date <= end_date:
                        events.append({"날짜": ed_date.strftime("%Y-%m-%d"), "구분": "기업 실적", "이벤트": f"{name} ({symbol}) 실적 발표", "출처": "Yahoo Finance"})
        except Exception:
            pass

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        urls = [
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
        ]
        for url in urls:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                ff_data = res.json()
                for item in ff_data:
                    if item.get('country') == 'USD' and item.get('impact') == 'High':
                        event_date_str = item.get('date')
                        if event_date_str:
                            event_time_utc = pd.to_datetime(event_date_str, utc=True)
                            event_time_kst = event_time_utc.tz_convert('Asia/Seoul')
                            event_date = event_time_kst.date()
                            
                            if today <= event_date <= end_date:
                                time_str = event_time_kst.strftime("%H:%M")
                                events.append({
                                    "날짜": event_date.strftime("%Y-%m-%d"), 
                                    "구분": "거시 경제", 
                                    "이벤트": f"{item.get('title')} ({time_str} KST)",
                                    "출처": "ForexFactory"
                                })
    except Exception:
        pass

    df_events = pd.DataFrame(events)
    if not df_events.empty:
        df_events = df_events.drop_duplicates().sort_values(by="날짜").reset_index(drop=True)
    return df_events

def render_custom_line_chart(df, value_col='Close', min_y=None, line_color='#1f77b4'):
    if df.empty: return
    chart_data = df.reset_index()
    chart_data['Value'] = chart_data['Close'] if 'Close' in chart_data.columns else chart_data.get('Yield', chart_data.get('Spread', chart_data.iloc[:, 1]))
        
    actual_min, actual_max = chart_data['Value'].min(), chart_data['Value'].max()
    y_domain_min = min(min_y, actual_min) if min_y is not None and actual_min < min_y else (min_y if min_y is not None else actual_min - (actual_max - actual_min) * 0.05)
    y_domain_max = actual_max + (actual_max - actual_min) * 0.05
    
    chart = alt.Chart(chart_data).mark_line(color=line_color, strokeWidth=2).encode(
        x=alt.X('Date:T', axis=alt.Axis(title=None, format='%m/%d', labelAngle=0)),
        y=alt.Y('Value:Q', scale=alt.Scale(domain=[y_domain_min, y_domain_max]), axis=alt.Axis(title=None)),
        tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'), alt.Tooltip('Value:Q', format=',.2f')]
    ).properties(height=120)
    st.altair_chart(chart, use_container_width=True)


# =========================================================
# UI 렌더링
# =========================================================

# ---------------------------------------------------------
# 1. 🪙 가상자산 핵심 지표 및 저점/저평가 진단
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🪙 가상자산 핵심 지표 및 저점/저평가 진단</div>", unsafe_allow_html=True)
crypto_data = get_crypto_extended_data()
crypto_fng_score, crypto_fng_rating = get_crypto_fear_and_greed()

if crypto_data and crypto_data.get('btc_krw', 0) > 0:
    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
    with cc1:
        st.metric("비트코인 (Upbit)", f"₩{crypto_data['btc_krw']:,}", f"{crypto_data['btc_pct']:+.2f}%")
        st.markdown("[🔗 업비트 BTC](https://upbit.com/exchange?code=CASA.KRW-BTC)", unsafe_allow_html=True)
    with cc2:
        st.metric("이더리움 (Upbit)", f"₩{crypto_data['eth_krw']:,}", f"{crypto_data['eth_pct']:+.2f}%")
        st.markdown("[🔗 업비트 ETH](https://upbit.com/exchange?code=CASA.KRW-ETH)", unsafe_allow_html=True)
    with cc3:
        kp = crypto_data.get('kimchi_premium')
        if kp is not None:
            st.metric("한국 프리미엄 (김프)", f"{kp:.2f}%", help="업비트 가격과 해외 가격(환율 적용)의 차이입니다.", delta_color="inverse" if kp > 5 else "normal")
        else:
            st.metric("한국 프리미엄 (김프)", "N/A")
    with cc4:
        fr = crypto_data.get('funding_rate')
        if fr is not None:
            st.metric("바이낸스 BTC 펀딩비", f"{fr:.4f}%", help="무기한 선물 펀딩비입니다.", delta_color="off")
        else:
            st.metric("바이낸스 BTC 펀딩비", "N/A")
    with cc5:
        st.metric("크립토 공포·탐욕", f"{crypto_fng_score} / 100", crypto_fng_rating, delta_color="normal" if crypto_fng_score > 50 else "inverse")

    st.markdown("#### 📊 비트코인 가격 연동형 온체인 및 기술적 분석 지표 (Dual-Axis 뷰)")
    tab_m1, tab_m2, tab_m3, tab_m4, tab_m5, tab_m6 = st.tabs([
        "200주 이동평균선", "주봉 RSI + 가격", "MVRV 모델 + 가격", "NUPL 모델 + 가격", "장기 보유자 공급량 (LTH) + 가격", "1년 이상 미이동 비중 (HODL) + 가격"
    ])

    df_btc_all = get_btc_all_indicators()

    with tab_m1:
        if not df_btc_all.empty:
            st.caption("💡 **200주 이동평균선**: 역사적 하락장에서 비트코인의 최후 바닥 역할을 해온 선입니다.")
            chart_data = df_btc_all.reset_index()
            c1 = alt.Chart(chart_data).mark_line(color='#1f77b4').encode(x='Date:T', y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='비트코인 가격 ($)'))
            c2 = alt.Chart(chart_data).mark_line(color='#d32f2f', strokeDash=[4, 4]).encode(x='Date:T', y=alt.Y('200W_MA:Q', scale=alt.Scale(type='log')))
            st.altair_chart((c1 + c2).properties(height=350), use_container_width=True)
        else:
            st.info("데이터를 계산 중입니다...")

    with tab_m2:
        if not df_btc_all.empty:
            st.caption("💡 **주봉 RSI (보라색) & 비트코인 가격 (하늘색 로그 스케일)**: 가격 정점과 바닥에 따른 RSI 과매수/과매도 구간을 동시에 비교합니다.")
            df_c = df_btc_all.reset_index()
            base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
            line_price = base.mark_line(color='#3498db', strokeWidth=1.5).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='비트코인 가격 ($)'))
            line_rsi = base.mark_line(color='#8e44ad', strokeWidth=2).encode(y=alt.Y('Weekly_RSI:Q', scale=alt.Scale(domain=[10, 90]), title='주봉 RSI'))
            st.altair_chart(alt.layer(line_price, line_rsi).resolve_scale(y='independent').properties(height=350), use_container_width=True)
        else:
            st.info("데이터를 계산 중입니다...")

    with tab_m3:
        if not df_btc_all.empty:
            st.caption("💡 **MVRV 모델 (초록색) & 비트코인 가격 (하늘색)**: MVRV가 1.0 이하로 내려앉는 구간이 역사적 매수 타이밍과 일치하는 것을 확인할 수 있습니다.")
            df_c = df_btc_all.reset_index()
            base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
            line_price = base.mark_line(color='#3498db', strokeWidth=1.5).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='비트코인 가격 ($)'))
            line_mvrv = base.mark_line(color='#27ae60', strokeWidth=2).encode(y=alt.Y('MVRV_Model:Q', title='MVRV 추정치'))
            st.altair_chart(alt.layer(line_price, line_mvrv).resolve_scale(y='independent').properties(height=350), use_container_width=True)
        else:
            st.info("데이터를 계산 중입니다...")

    with tab_m4:
        if not df_btc_all.empty:
            st.caption("💡 **NUPL 모델 (주황색) & 비트코인 가격 (하늘색)**: NUPL이 0 이하(음수)로 떨어질 때 가격이 바닥을 형성했음을 보여줍니다.")
            df_c = df_btc_all.reset_index()
            base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
            line_price = base.mark_line(color='#3498db', strokeWidth=1.5).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='비트코인 가격 ($)'))
            line_nupl = base.mark_line(color='#e67e22', strokeWidth=2).encode(y=alt.Y('NUPL_Model:Q', title='NUPL 추정치'))
            st.altair_chart(alt.layer(line_price, line_nupl).resolve_scale(y='independent').properties(height=350), use_container_width=True)
        else:
            st.info("데이터를 계산 중입니다...")

    with tab_m5:
        if not df_btc_all.empty:
            st.caption("💡 **장기 보유자 공급량 LTH (파란색) & 비트코인 가격 (회색)**: 가격이 하락 횡보할 때 장기 홀더들의 물량이 급격히 우상향(매집)하는 모습을 비교합니다.")
            df_c = df_btc_all.reset_index()
            base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
            line_price = base.mark_line(color='#95a5a6', strokeWidth=1.5, strokeDash=[3,3]).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='비트코인 가격 ($)'))
            line_lth = base.mark_line(color='#2980b9', strokeWidth=2.5).encode(y=alt.Y('Inactive_1yr_Supply:Q', title='1년 이상 미이동 수량 (개)', scale=alt.Scale(zero=False)))
            st.altair_chart(alt.layer(line_price, line_lth).resolve_scale(y='independent').properties(height=350), use_container_width=True)
        else:
            st.info("데이터를 계산 중입니다...")

    with tab_m6:
        if not df_btc_all.empty:
            st.caption("💡 **1년 이상 미이동 비중 HODL (빨간색) & 비트코인 가격 (회색)**: 장기 미이동 비중이 정점을 찍고 내려오기 시작할 때 본격적인 대세 상승장이 펼쳐졌습니다.")
            df_c = df_btc_all.reset_index()
            base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
            line_price = base.mark_line(color='#95a5a6', strokeWidth=1.5, strokeDash=[3,3]).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='비트코인 가격 ($)'))
            line_hodl = base.mark_line(color='#e74c3c', strokeWidth=2.5).encode(y=alt.Y('Inactive_1yr_Ratio:Q', title='장기 미이동 비중 (%)', scale=alt.Scale(zero=False)))
            st.altair_chart(alt.layer(line_price, line_hodl).resolve_scale(y='independent').properties(height=350), use_container_width=True)
        else:
            st.info("데이터를 계산 중입니다...")

else:
    st.warning("⚠️ 가상자산 시세를 연결하는 중입니다. [데이터 새로고침]을 클릭해주세요.")

st.markdown("---")

# ---------------------------------------------------------
# 2. 🇺🇸 미 3대 주요 지수 섹션
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🇺🇸 미국 3대 주요 증시 지수</div>", unsafe_allow_html=True)
us_indices = get_us_indices()

idx_cols = st.columns(3)
for col, (name, info) in zip(idx_cols, us_indices.items()):
    with col:
        price_val, pct_val = info.get('price', 0.0), info.get('pct', 0.0)
        st.metric(name, f"{price_val:,.2f}", f"{pct_val:+.2f}%")
        render_custom_line_chart(info.get('df_1m', pd.DataFrame()), line_color='#d32f2f' if pct_val < 0 else '#2e7d32')
        st.markdown(f"[🔗 Yahoo {name.split()[0]} 원본]({info.get('link')})", unsafe_allow_html=True)
st.markdown("---")

# ---------------------------------------------------------
# 3. 📅 향후 2주간(보름) 증시 주요일정 & 실적 발표
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
            "이벤트": st.column_config.TextColumn("📝 상세 내용", width="large"),
            "출처": st.column_config.TextColumn("🔍 정보 출처", width="small")
        }
    )
    st.caption("💡 **직접 더블체크하기:** [Yahoo Finance 실적캘린더](https://finance.yahoo.com/calendar/earnings) | [ForexFactory 경제 캘린더](https://www.forexfactory.com/calendar)")
else:
    st.info("향후 15일 이내에 예정된 주요 이벤트가 없습니다.")

st.markdown("---")

# ---------------------------------------------------------
# 4. 증시 밸류에이션 및 투자 심리
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🏛️ 증시 밸류에이션 및 투자 심리 지표</div>", unsafe_allow_html=True)
cape_val = get_shiller_cape()
fg_score, fg_rating = get_fear_and_greed()

k1, k2, k3 = st.columns([1.2, 1.2, 2.6])
with k1:
    st.metric("S&P 500 Shiller CAPE", f"{cape_val:.2f}", "역사적 고평가" if cape_val > 30 else ("보통" if cape_val > 20 else "저평가"), delta_color="inverse" if cape_val > 30 else "normal")
    st.markdown("[🔗 multpl.com 원본](https://www.multpl.com/shiller-cape)", unsafe_allow_html=True)
with k2:
    st.metric("미 증시 공포·탐욕 지수", f"{fg_score} / 100", fg_rating, delta_color="normal" if fg_score > 50 else "inverse")
    st.markdown("[🔗 CNN Fear & Greed 원본](https://edition.cnn.com/markets/fear-and-greed)", unsafe_allow_html=True)
with k3:
    st.info(f"💡 **가이드**: \n• **Shiller CAPE ({cape_val:.2f})**: 30 이상 시 장기 고평가 구간.\n• **공포·탐욕 지수 ({fg_score} - {fg_rating})**: 0~25(극도의 공포), 75~100(극도의 탐욕).")
st.markdown("---")

# ---------------------------------------------------------
# 5. 미 국채 만기별 금리 섹션
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🇺🇸 미 국채 만기별 금리 현황 (최근 1개월 추이, Y축 최저 3.0% 고정)</div>", unsafe_allow_html=True)
treasury_data = get_fred_treasury_data()
t_cols = st.columns(4)
for col, name in zip(t_cols, ['미 국채 2년물', '미 국채 5년물', '미 국채 10년물', '미 국채 30년물']):
    info = treasury_data.get(name, {})
    with col:
        st.metric(name, f"{info.get('price', 0):.2f}%", f"{info.get('pct', 0):+.2f}%")
        render_custom_line_chart(info.get('df_1m', pd.DataFrame()), min_y=3.0)
        st.markdown(f"[🔗 FRED 공식 데이터]({info.get('link')})", unsafe_allow_html=True)
st.markdown("---")

# ---------------------------------------------------------
# 6. 유동성 & 신용 위험 지표 섹션
# ---------------------------------------------------------
st.markdown("<div class='section-title'>💧 유동성 및 신용 위험 지표</div>", unsafe_allow_html=True)
hy_info = get_hy_spread()
macro_info = get_macro_data()
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("하이일드 스프레드", f"{hy_info.get('price', 0):.2f}%p", f"{hy_info.get('pct', 0):+.2f}%")
    render_custom_line_chart(hy_info.get('df_1m', pd.DataFrame()), min_y=2.0)
    st.markdown(f"[🔗 FRED 공식 데이터]({hy_info.get('link')})", unsafe_allow_html=True)
for col, key, label, fmt in zip([m2, m3, m4, m5], ['달러 인덱스', 'VIX 지수', 'WTI 유가', '브렌트유'], ['달러 인덱스 (DXY)', 'VIX 변동성', 'WTI 유가 ($)', '브렌트유 ($)'], ["{:.2f}", "{:.2f}", "${:.2f}", "${:.2f}"]):
    v = macro_info.get(key, {})
    with col:
        st.metric(label, fmt.format(v.get('price', 0)), f"{v.get('pct', 0):+.2f}%")
        st.markdown(f"[🔗 Yahoo {key.split()[0]}]({v.get('link')})", unsafe_allow_html=True)
st.markdown("---")

# ---------------------------------------------------------
# 7. M7 Drawdown & PER 현황
# ---------------------------------------------------------
st.markdown("<div class='section-title'>📈 M7 기업 주가, 하락률(Drawdown) 및 PER 현황</div>", unsafe_allow_html=True)
m7_df = get_m7_drawdown()

if not m7_df.empty:
    def highlight_dd(val):
        if val <= -20: return 'background-color: #ffcdd2; color: #b71c1c; font-weight: bold;'
        elif val <= -10: return 'background-color: #ffe0b2; color: #e65100;'
        return 'color: #2e7d32;'

    st.dataframe(
        m7_df.style.map(highlight_dd, subset=['고점 대비 하락률 (Drawdown)'])
                   .format({
                       "현재가 ($)": "${:.2f}",
                       "일간 변동률 (%)": "{:+.2f}%",
                       "52주 최고가 ($)": "${:.2f}",
                       "고점 대비 하락률 (Drawdown)": "{:.2f}%",
                       "PER (TTM)": "{:.2f}",
                       "PER (FWD)": "{:.2f}"
                   }, na_rep="N/A"),
        use_container_width=True,
        height=280
    )
else:
    st.info("M7 주가 및 PER 데이터를 불러오는 중입니다...")

st.markdown("---")

# ---------------------------------------------------------
# 8. Gemini AI 매크로 & 유동성 종합 진단
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🤖 Gemini AI 매크로 & 유동성 시황 분석</div>", unsafe_allow_html=True)

if not api_key:
    st.warning("👈 사이드바에 **Gemini API Key**를 입력하면 AI 매크로 분석 보고서를 생성할 수 있습니다.")
else:
    if st.button("🚀 AI 종합 분석 보고서 생성하기", use_container_width=True, type="primary"):
        with st.spinner("Gemini가 실시간 미 증시, 금리 커브, 심리 지표 및 유동성을 종합 분석 중입니다..."):
            try:
                genai.configure(api_key=api_key.strip())
                sp500_p = us_indices.get('S&P 500', {}).get('price', 'N/A')
                nasdaq_p = us_indices.get('나스닥 종합 (NASDAQ)', {}).get('price', 'N/A')
                dow_p = us_indices.get('다우 존스 (DOW)', {}).get('price', 'N/A')
                t_2y = treasury_data.get('미 국채 2년물', {}).get('price', 'N/A')
                t_5y = treasury_data.get('미 국채 5년물', {}).get('price', 'N/A')
                t_10y = treasury_data.get('미 국채 10년물', {}).get('price', 'N/A')
                t_30y = treasury_data.get('미 국채 30년물', {}).get('price', 'N/A')
                hy_val = hy_info.get('price', 'N/A')
                dxy_val = macro_info.get('달러 인덱스', {}).get('price', 'N/A')
                
                btc_price = crypto_data['btc_krw'] if crypto_data else "N/A"
                crypto_fng = crypto_fng_score if crypto_fng_score else "N/A"
                
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
                - 비트코인: ₩{btc_price:,} | 크립토 공포/탐욕 지수: {crypto_fng}점
                
                위 데이터를 바탕으로 전문적인 [글로벌 매크로 & 자산배분 전략 보고서]를 작성해 줘.
                
                [보고서 작성 필수 항목]
                1. **미 주요 증시 흐름 및 심리 평가**: S&P500/나스닥/다우 흐름과 공포·탐욕 지수 진단
                2. **수익률 곡선(Yield Curve) 및 금리 동향**: FRED 2Y/5Y/10Y/30Y 금리 수준 분석
                3. **신용 위험 및 유동성 진단**: 하이일드 스프레드 및 달러/유가 동향이 위험자산에 미치는 영향
                4. **향후 2주 대응 및 투자 포지셔닝 조언**: 종합 리스크 수준과 자산배분 전략
                
                마크다운으로 읽기 편하게 작성해 줘.
                """
                
                target_model_name = 'gemini-1.5-flash'
                try:
                    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    for pref in ['models/gemini-1.5-flash', 'gemini-1.5-flash', 'models/gemini-2.0-flash']:
                        if pref in available_models:
                            target_model_name = pref
                            break
                except Exception: pass

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
