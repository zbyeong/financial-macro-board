import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import altair as alt

# Page Configuration
st.set_page_config(
    page_title="글로벌 매크로 & 가상자산 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Mobile & Responsive Optimization
st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .stMetric {
        background-color: #f8f9fa;
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid #e9ecef;
        margin-bottom: 10px;
    }
    .section-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin-top: 1.2rem;
        margin-bottom: 0.6rem;
        color: #0f172a;
    }
    @media (max-width: 768px) {
        .section-title {
            font-size: 1.05rem;
            margin-top: 1rem;
        }
        .stMetric {
            padding: 8px;
        }
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Sidebar: Data sources and refresh controls
# ---------------------------------------------------------
st.sidebar.title("⚙️ 대시보드 설정")
st.sidebar.markdown("### 📌 수집 지표 및 출처")
st.sidebar.caption("""
• **가상자산 시세/기술 지표**: Upbit, Binance, Yahoo Finance
• **크립토 공포·탐욕 지수**: CoinMarketCap API
• **미 3대 지수·대형주 시가총액/PER**: Yahoo Finance
• **Shiller CAPE**: multpl.com
• **미 증시 공포·탐욕 지수**: CNN Business
• **미 국채 금리·장단기 금리차·하이일드 스프레드**: FRED
• **거시 지표**: WTI, Brent, VIX, DXY
""")

st.title("🌐 글로벌 매크로 & 가상자산 대시보드")
st.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (KST)")

if st.sidebar.button("🔄 데이터 새로고침", use_container_width=True):
    st.rerun()

# ---------------------------------------------------------
# Data Fetching Functions
# ---------------------------------------------------------

@st.cache_data(ttl=900)
def get_crypto_fear_and_greed():
    """CoinMarketCap Crypto Fear & Greed Index. 공개 API라 별도 키가 필요하지 않음."""
    url = "https://pro-api.coinmarketcap.com/public-api/v3/fear-and-greed/latest"
    rating_map = {
        "extreme fear": "극도의 공포 😱",
        "fear": "공포 😨",
        "neutral": "중립 😐",
        "greed": "탐욕 😋",
        "extreme greed": "극도의 탐욕 🤑",
    }
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        if isinstance(data, list):
            data = data[0] if data else {}
        score = int(data["value"])
        rating_raw = str(data.get("value_classification", "")).lower()
        update_raw = data.get("update_time") or payload.get("status", {}).get("timestamp")
        update_label = None
        if update_raw:
            try:
                update_label = pd.to_datetime(update_raw, utc=True).tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M KST")
            except Exception:
                update_label = str(update_raw)
        return score, rating_map.get(rating_raw, rating_raw or "분류 정보 없음"), update_label
    except Exception:
        return None, "데이터 연결 실패", None

@st.cache_data(ttl=60)
def get_crypto_extended_data():
    result = {
        "btc_krw": 0, "btc_pct": 0.0,
        "eth_krw": 0, "eth_pct": 0.0,
        "kimchi_premium": None,
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


    if result["btc_krw"] > 0 and btc_usd and result["usdkrw"] > 0:
        global_btc_krw = btc_usd * result["usdkrw"]
        result["kimchi_premium"] = ((result["btc_krw"] / global_btc_krw) - 1) * 100

    return result

@st.cache_data(ttl=86400)
def get_btc_all_indicators():
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
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['Weekly_RSI'] = 100 - (100 / (1 + rs))
        
        ma_365 = df['Close'].rolling(window=52).mean()
        df['MVRV_Model'] = (df['Close'] / ma_365) * 1.2
        df['NUPL_Model'] = (df['Close'] - ma_365) / df['Close']
        
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
            else:
                data[name] = {"price": None, "change": None, "pct": None, "df_1m": pd.DataFrame(), "link": link}
        except Exception:
            data[name] = {"price": None, "change": None, "pct": None, "df_1m": pd.DataFrame(), "link": link}
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
            raw_value = str(tables[0].iloc[0, 1]).replace(",", "").strip()
            return float(raw_value.split()[0])
    except Exception:
        pass
    return None

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
                'extreme fear': '극도의 공포 😱', 'fear': '공포 😨',
                'neutral': '중립 😐', 'greed': '탐욕 😋', 'extreme greed': '극도의 탐욕 🤑'
            }
            return score, rating_map.get(rating_raw, rating_raw)
    except Exception:
        pass
    return None, "데이터 연결 실패"

@st.cache_data(ttl=3600)
def get_fred_treasury_data():
    series_ids = {
        '미 국채 2년물': ('DGS2', 'https://fred.stlouisfed.org/series/DGS2'),
        '미 국채 5년물': ('DGS5', 'https://fred.stlouisfed.org/series/DGS5'),
        '미 국채 10년물': ('DGS10', 'https://fred.stlouisfed.org/series/DGS10'),
        '미 국채 30년물': ('DGS30', 'https://fred.stlouisfed.org/series/DGS30'),
        '미 국채 10년물-2년물 금리차': ('T10Y2Y', 'https://fred.stlouisfed.org/series/T10Y2Y')
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
            if len(df_1m) < 2:
                df_1m = df.tail(30)
            if df_1m.empty:
                raise ValueError("FRED series has no valid observations")
            curr = float(df_1m['Yield'].iloc[-1])
            prev = float(df_1m['Yield'].iloc[-2]) if len(df_1m) >= 2 else curr
            change = curr - prev
            pct = (change / prev) * 100 if prev != 0 else 0
            data[name] = {"price": curr, "change": change, "pct": pct, "df_1m": df_1m, "link": link}
        except Exception:
            data[name] = {"price": None, "change": None, "pct": None, "df_1m": pd.DataFrame(), "link": link}
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
        if len(df_1m) < 2:
            df_1m = df.tail(30)
        if df_1m.empty:
            raise ValueError("FRED series has no valid observations")
        curr = float(df_1m['Spread'].iloc[-1])
        prev = float(df_1m['Spread'].iloc[-2]) if len(df_1m) >= 2 else curr
        change = curr - prev
        pct = (change / prev) * 100 if prev != 0 else 0
        return {"price": curr, "change": change, "pct": pct, "df_1m": df_1m, "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"}
    except Exception:
        return {"price": None, "change": None, "pct": None, "df_1m": pd.DataFrame(), "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"}

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
            else:
                data[name] = {"price": None, "change": None, "pct": None, "link": link}
        except Exception:
            data[name] = {"price": None, "change": None, "pct": None, "link": link}
    return data

@st.cache_data(ttl=900)
def get_top10_market_cap():
    """Yahoo Finance 스크리너의 시총 순위를 우선 사용하고, 실패하면 대형주 후보군으로 보완."""
    screen_quotes = []
    try:
        from yfinance import EquityQuery
        query = EquityQuery("and", [
            EquityQuery("eq", ["region", "us"]),
            EquityQuery("gt", ["intradaymarketcap", 50_000_000_000]),
        ])
        screen_result = yf.screen(
            query,
            size=100,
            sortField="intradaymarketcap",
            sortAsc=False,
        )
        screen_quotes = screen_result.get("quotes", [])
    except Exception:
        screen_quotes = []

    # 스크리너가 반환하지 못하는 경우를 위한 대형주 후보군(미국 상장 ADR 포함)
    fallback_candidates = {
        "NVDA": "NVIDIA", "AAPL": "Apple", "MSFT": "Microsoft",
        "GOOGL": "Alphabet", "GOOG": "Alphabet", "AMZN": "Amazon",
        "TSM": "TSMC (ADR)", "SPCX": "SpaceX", "META": "Meta",
        "TSLA": "Tesla", "AVGO": "Broadcom", "LLY": "Eli Lilly",
        "MU": "Micron", "BRK-B": "Berkshire Hathaway", "WMT": "Walmart",
        "JPM": "JPMorgan Chase", "ORCL": "Oracle", "AMD": "AMD",
        "V": "Visa", "XOM": "Exxon Mobil", "PLTR": "Palantir",
        "COST": "Costco", "NFLX": "Netflix", "MA": "Mastercard",
    }

    candidates = {}
    for quote in screen_quotes:
        symbol = quote.get("symbol")
        market_cap = quote.get("marketCap") or quote.get("intradayMarketCap") or quote.get("intradaymarketcap")
        if symbol and market_cap:
            candidates[symbol] = {
                "name": quote.get("shortName") or quote.get("longName") or symbol,
                "market_cap": float(market_cap),
                "trailing_pe": quote.get("trailingPE"),
                "forward_pe": quote.get("forwardPE"),
            }

    # Yahoo 스크리너 결과에서 동일 회사의 복수 주식 클래스가 포함될 수 있어 고유 기업 수를 계산
    existing_company_keys = {
        "".join(ch for ch in str(item["name"]).lower() if ch.isalnum())
        for item in candidates.values()
    }
    # 상위 10개 기업을 확보하지 못한 경우 대형주 후보군으로 보완
    if len(existing_company_keys) < 10:
        for symbol, fallback_name in fallback_candidates.items():
            if symbol in candidates:
                continue
            try:
                ticker = yf.Ticker(symbol)
                fast = ticker.fast_info
                try:
                    market_cap = fast["market_cap"]
                except Exception:
                    market_cap = None
                if not market_cap:
                    info = ticker.get_info()
                    market_cap = info.get("marketCap")
                    name = info.get("shortName") or info.get("longName") or fallback_name
                    trailing_pe = info.get("trailingPE")
                    forward_pe = info.get("forwardPE")
                else:
                    name = fallback_name
                    trailing_pe = None
                    forward_pe = None
                company_key = "".join(ch for ch in str(name).lower() if ch.isalnum())
                if market_cap and company_key not in existing_company_keys:
                    candidates[symbol] = {
                        "name": name,
                        "market_cap": float(market_cap),
                        "trailing_pe": trailing_pe,
                        "forward_pe": forward_pe,
                    }
                    existing_company_keys.add(company_key)
            except Exception:
                continue

    ranked_all = sorted(candidates.items(), key=lambda item: item[1]["market_cap"], reverse=True)
    ranked = []
    seen_companies = set()
    for symbol, item in ranked_all:
        company_key = "".join(ch for ch in str(item["name"]).lower() if ch.isalnum())
        if company_key in seen_companies:
            continue
        seen_companies.add(company_key)
        ranked.append((symbol, item))
        if len(ranked) == 10:
            break
    rows = []
    for rank, (symbol, item) in enumerate(ranked, start=1):
        try:
            ticker = yf.Ticker(symbol)
            try:
                hist = ticker.history(period="1y", auto_adjust=False)
            except Exception:
                hist = pd.DataFrame()
            if hist.empty:
                current_price = None
                day_pct = None
                high_52w = None
                drawdown = None
            else:
                close = hist["Close"].dropna()
                current_price = float(close.iloc[-1]) if len(close) else None
                day_pct = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(close) >= 2 else None
                high_52w = float(hist["High"].max()) if "High" in hist and not hist["High"].dropna().empty else None
                drawdown = ((current_price / high_52w) - 1) * 100 if current_price and high_52w else None

            # 스크리너에서 PER가 없으면 상세정보에서 보충
            trailing_pe = item.get("trailing_pe")
            forward_pe = item.get("forward_pe")
            if trailing_pe is None or forward_pe is None:
                try:
                    info = ticker.get_info()
                    trailing_pe = trailing_pe if trailing_pe is not None else info.get("trailingPE")
                    forward_pe = forward_pe if forward_pe is not None else info.get("forwardPE")
                except Exception:
                    pass

            cap = item["market_cap"]
            if cap >= 1_000_000_000_000:
                cap_label = f"${cap / 1_000_000_000_000:.2f}T"
            else:
                cap_label = f"${cap / 1_000_000_000:.1f}B"

            rows.append({
                "순위": rank,
                "기업명": item["name"],
                "티커": symbol,
                "시가총액 (USD)": cap_label,
                "시가총액_원값": cap,
                "현재가 ($)": round(current_price, 2) if current_price is not None else None,
                "일간 변동률 (%)": round(day_pct, 2) if day_pct is not None else None,
                "52주 최고가 ($)": round(high_52w, 2) if high_52w is not None else None,
                "고점 대비 하락률 (%)": round(drawdown, 2) if drawdown is not None else None,
                "PER (TTM)": round(safe_number(trailing_pe), 2) if safe_number(trailing_pe) is not None else None,
                "PER (FWD)": round(safe_number(forward_pe), 2) if safe_number(forward_pe) is not None else None,
            })
        except Exception:
            continue

    for final_rank, row in enumerate(rows, start=1):
        row["순위"] = final_rank
    return pd.DataFrame(rows)

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
            earnings_dates = cal.get('Earnings Date', []) if isinstance(cal, dict) else []
            for ed in earnings_dates:
                if pd.notnull(ed):
                    ed_date = pd.to_datetime(ed).date()
                    if today <= ed_date <= end_date:
                        events.append({"날짜": ed_date.strftime("%Y-%m-%d"), "구분": "기업 실적", "이벤트": f"{name} ({symbol}) 실적 발표", "출처": "Yahoo Finance"})
        except Exception:
            pass
    return pd.DataFrame(events)

def render_custom_line_chart(df, value_col='Close', min_y=None, line_color='#1f77b4'):
    if df.empty: return
    chart_data = df.reset_index()
    chart_data['Value'] = chart_data['Close'] if 'Close' in chart_data.columns else chart_data.get('Yield', chart_data.get('Spread', chart_data.iloc[:, 1]))
    actual_min, actual_max = chart_data['Value'].min(), chart_data['Value'].max()
    value_range = actual_max - actual_min
    padding = value_range * 0.05 if value_range > 0 else max(abs(actual_max) * 0.01, 0.01)
    y_domain_min = min(min_y, actual_min) if min_y is not None and actual_min < min_y else (min_y if min_y is not None else actual_min - padding)
    y_domain_max = actual_max + padding
    chart = alt.Chart(chart_data).mark_line(color=line_color, strokeWidth=2).encode(
        x=alt.X('Date:T', axis=alt.Axis(title=None, format='%m/%d', labelAngle=0)),
        y=alt.Y('Value:Q', scale=alt.Scale(domain=[y_domain_min, y_domain_max]), axis=alt.Axis(title=None)),
        tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'), alt.Tooltip('Value:Q', format=',.2f')]
    ).properties(height=120)
    st.altair_chart(chart, use_container_width=True)


def safe_number(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_macro_assessment(us_indices, cape_value, stock_fg_score, treasury_data, hy_info, macro_info, crypto_fg_score):
    """외부 생성형 AI 없이 수집 지표와 공개된 임계값으로 재현 가능한 시황 점검을 생성."""
    score = 0
    evaluated = 0
    positives, cautions, observations = [], [], []

    def assess(name, value, positive_condition, negative_condition, positive_text, negative_text, unit=""):
        nonlocal score, evaluated
        value = safe_number(value)
        if value is None:
            observations.append(f"{name}: 데이터 없음 (종합 점수에서 제외)")
            return

        evaluated += 1
        formatted_value = f"{value:,.2f}{unit}"
        if positive_condition(value):
            score += 1
            positives.append(positive_text)
            observations.append(f"{name} ({formatted_value}) — 우호: {positive_text}")
        elif negative_condition(value):
            score -= 1
            cautions.append(negative_text)
            observations.append(f"{name} ({formatted_value}) — 경계: {negative_text}")
        else:
            observations.append(f"{name} ({formatted_value}) — 중립: 설정된 우호·경계 임계값에 해당하지 않습니다.")

    assess(
        "S&P 500 일간 등락률", us_indices.get("S&P 500", {}).get("pct"),
        lambda v: v >= 0.5, lambda v: v <= -0.5,
        "S&P 500의 당일 흐름이 강세(상승률 +0.5% 이상)입니다.",
        "S&P 500의 당일 흐름이 약세(하락률 -0.5% 이하)입니다.", "%",
    )
    assess(
        "나스닥 일간 등락률", us_indices.get("나스닥 종합 (NASDAQ)", {}).get("pct"),
        lambda v: v >= 0.5, lambda v: v <= -0.5,
        "나스닥의 당일 흐름이 강세(상승률 +0.5% 이상)입니다.",
        "나스닥의 당일 흐름이 약세(하락률 -0.5% 이하)입니다.", "%",
    )
    assess(
        "VIX", macro_info.get("VIX 지수", {}).get("price"),
        lambda v: v < 18, lambda v: v >= 25,
        "VIX가 18 미만으로 변동성 부담이 비교적 낮습니다.",
        "VIX가 25 이상으로 위험회피 심리가 커져 있습니다.",
    )
    assess(
        "하이일드 스프레드", hy_info.get("price"),
        lambda v: v < 3.5, lambda v: v >= 5.0,
        "하이일드 스프레드가 3.5%p 미만으로 신용시장 긴장이 낮은 편입니다.",
        "하이일드 스프레드가 5.0%p 이상으로 신용위험 경계가 필요합니다.", "%p",
    )
    assess(
        "미 국채 10년물-2년물 금리차", treasury_data.get("미 국채 10년물-2년물 금리차", {}).get("price"),
        lambda v: v > 0.25, lambda v: v < -0.25,
        "10년물-2년물 금리차가 +0.25%p를 넘어 장단기 금리곡선이 정상 구간입니다.",
        "10년물-2년물 금리차가 -0.25%p 미만으로 역전 폭이 유의미합니다.", "%p",
    )
    assess(
        "미 증시 공포·탐욕 지수", stock_fg_score,
        lambda v: 45 <= v <= 65, lambda v: v < 20 or v > 80,
        "미 증시 공포·탐욕 지수가 45~65로 중립에 가까운 심리입니다.",
        "미 증시 투자심리가 극단(20 미만 공포 또는 80 초과 탐욕)에 치우쳐 있습니다.", "/100",
    )
    assess(
        "Shiller CAPE", cape_value,
        lambda v: v < 25, lambda v: v >= 35,
        "Shiller CAPE가 25 미만으로 장기 밸류에이션 부담이 상대적으로 낮습니다.",
        "Shiller CAPE가 35 이상으로 장기 밸류에이션 부담이 큰 구간입니다.",
    )
    assess(
        "달러 인덱스 일간 등락률", macro_info.get("달러 인덱스", {}).get("pct"),
        lambda v: v <= -0.5, lambda v: v >= 0.5,
        "달러 인덱스가 하루 0.5% 이상 하락해 달러 강세 압력이 완화됐습니다.",
        "달러 인덱스가 하루 0.5% 이상 상승해 글로벌 금융여건에 부담이 될 수 있습니다.", "%",
    )
    assess(
        "WTI 유가 일간 등락률", macro_info.get("WTI 유가", {}).get("pct"),
        lambda v: v <= -3.0, lambda v: v >= 3.0,
        "WTI가 하루 3% 이상 하락해 에너지발 물가 압력이 완화될 여지가 있습니다.",
        "WTI가 하루 3% 이상 상승해 인플레이션·금리 부담을 점검할 필요가 있습니다.", "%",
    )

    if evaluated == 0:
        regime = "데이터 부족"
        explanation = "분석에 필요한 지표를 충분히 불러오지 못했습니다. 데이터 출처 링크와 연결 상태를 확인하세요."
    elif score >= 3:
        regime = "위험선호 우위 (Risk-on)"
        explanation = "확인 가능한 지표에서 우호 신호가 상대적으로 우세합니다. 다만 단기 가격 추격보다 변동성·신용지표 확인이 우선입니다."
    elif score <= -3:
        regime = "위험회피 우위 (Risk-off)"
        explanation = "확인 가능한 지표에서 경계 신호가 상대적으로 우세합니다. 레버리지와 포지션 크기를 보수적으로 관리할 필요가 있습니다."
    else:
        regime = "혼조·중립 (Mixed)"
        explanation = "긍정과 경계 신호가 혼재하거나 신호 강도가 제한적입니다. 한 방향으로 단정하기보다 지표 간 불일치와 추세 확인이 중요합니다."

    crypto_note = None
    crypto_value = safe_number(crypto_fg_score)
    if crypto_value is not None:
        if crypto_value < 20:
            crypto_note = f"크립토 공포·탐욕 지수 {crypto_value:.0f}: 극단적 공포 구간으로 투매·유동성 위축 여부를 점검해야 합니다."
        elif crypto_value > 80:
            crypto_note = f"크립토 공포·탐욕 지수 {crypto_value:.0f}: 극단적 탐욕 구간으로 과열 및 레버리지 쏠림을 경계해야 합니다."
        else:
            crypto_note = f"크립토 공포·탐욕 지수 {crypto_value:.0f}: 극단 구간은 아니지만 가격 흐름·거래량과 함께 해석해야 합니다."
    else:
        crypto_note = "크립토 공포·탐욕 지수: 데이터 연결 실패로 분석에서 제외했습니다."

    return {
        "score": score,
        "evaluated": evaluated,
        "regime": regime,
        "explanation": explanation,
        "positives": positives,
        "cautions": cautions,
        "observations": observations,
        "crypto_note": crypto_note,
    }


# =========================================================
# UI 렌더링
# =========================================================

# ---------------------------------------------------------
# 1. 🪙 가상자산 핵심 지표
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🪙 가상자산 핵심 지표</div>", unsafe_allow_html=True)
crypto_data = get_crypto_extended_data()
crypto_fng_score, crypto_fng_rating, crypto_fng_updated = get_crypto_fear_and_greed()

if crypto_data and crypto_data.get('btc_krw', 0) > 0:
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        st.metric("비트코인 (Upbit)", f"₩{crypto_data['btc_krw']:,.0f}", f"{crypto_data['btc_pct']:+.2f}%")
        st.markdown("[🔗 업비트 BTC](https://upbit.com/exchange?code=CRIX.UPBIT.KRW-BTC)")
    with cc2:
        st.metric("이더리움 (Upbit)", f"₩{crypto_data['eth_krw']:,.0f}", f"{crypto_data['eth_pct']:+.2f}%")
        st.markdown("[🔗 업비트 ETH](https://upbit.com/exchange?code=CRIX.UPBIT.KRW-ETH)")
    with cc3:
        kp = crypto_data.get('kimchi_premium')
        st.metric("한국 프리미엄", f"{kp:.2f}%" if kp is not None else "N/A", delta_color="inverse" if kp is not None and kp > 5 else "normal")

    st.metric(
        "크립토 공포·탐욕 (CoinMarketCap)",
        f"{crypto_fng_score} / 100" if crypto_fng_score is not None else "N/A",
        crypto_fng_rating,
    )
else:
    st.warning("⚠️ 가상자산 시세를 불러오지 못했습니다. 잠시 후 데이터 새로고침을 시도해주세요.")
    st.metric(
        "크립토 공포·탐욕 (CoinMarketCap)",
        f"{crypto_fng_score} / 100" if crypto_fng_score is not None else "N/A",
        crypto_fng_rating,
    )

st.caption(f"CoinMarketCap 지수 업데이트: {crypto_fng_updated or '확인 불가'}")
st.markdown(
    "[🔗 CoinMarketCap 지수 원본](https://coinmarketcap.com/ko/charts/fear-and-greed-index/) · "
    "[API 원문](https://pro-api.coinmarketcap.com/public-api/v3/fear-and-greed/latest) · "
    "[API 문서](https://coinmarketcap.com/api/documentation/pro-api-reference/keyless-public-api/)")

st.markdown("#### 📊 비트코인 가격 연동형 온체인 및 기술적 분석 지표")
tab_m1, tab_m2, tab_m3, tab_m4, tab_m5, tab_m6 = st.tabs([
    "200주 이평", "주봉 RSI", "MVRV", "NUPL", "LTH (장기홀더)", "HODL (미이동비중)"
])

df_btc_all = get_btc_all_indicators()

with tab_m1:
    if not df_btc_all.empty:
        chart_data = df_btc_all.reset_index()
        c1 = alt.Chart(chart_data).mark_line(color='#1f77b4').encode(x='Date:T', y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='가격 ($)'))
        c2 = alt.Chart(chart_data).mark_line(color='#d32f2f', strokeDash=[4, 4]).encode(x='Date:T', y=alt.Y('200W_MA:Q', scale=alt.Scale(type='log')))
        st.altair_chart((c1 + c2).properties(height=300), use_container_width=True)

with tab_m2:
    if not df_btc_all.empty:
        df_c = df_btc_all.reset_index()
        base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
        line_price = base.mark_line(color='#3498db', strokeWidth=1.5).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='가격 ($)'))
        line_rsi = base.mark_line(color='#8e44ad', strokeWidth=2).encode(y=alt.Y('Weekly_RSI:Q', scale=alt.Scale(domain=[10, 90]), title='RSI'))
        st.altair_chart(alt.layer(line_price, line_rsi).resolve_scale(y='independent').properties(height=300), use_container_width=True)

with tab_m3:
    if not df_btc_all.empty:
        df_c = df_btc_all.reset_index()
        base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
        line_price = base.mark_line(color='#3498db', strokeWidth=1.5).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='가격 ($)'))
        line_mvrv = base.mark_line(color='#27ae60', strokeWidth=2).encode(y=alt.Y('MVRV_Model:Q', title='MVRV'))
        st.altair_chart(alt.layer(line_price, line_mvrv).resolve_scale(y='independent').properties(height=300), use_container_width=True)

with tab_m4:
    if not df_btc_all.empty:
        df_c = df_btc_all.reset_index()
        base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
        line_price = base.mark_line(color='#3498db', strokeWidth=1.5).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='가격 ($)'))
        line_nupl = base.mark_line(color='#e67e22', strokeWidth=2).encode(y=alt.Y('NUPL_Model:Q', title='NUPL'))
        st.altair_chart(alt.layer(line_price, line_nupl).resolve_scale(y='independent').properties(height=300), use_container_width=True)

with tab_m5:
    if not df_btc_all.empty:
        df_c = df_btc_all.reset_index()
        base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
        line_price = base.mark_line(color='#95a5a6', strokeWidth=1.5, strokeDash=[3,3]).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='가격 ($)'))
        line_lth = base.mark_line(color='#2980b9', strokeWidth=2.5).encode(y=alt.Y('Inactive_1yr_Supply:Q', title='장기 미이동 수량 (개)', scale=alt.Scale(zero=False)))
        st.altair_chart(alt.layer(line_price, line_lth).resolve_scale(y='independent').properties(height=300), use_container_width=True)

with tab_m6:
    if not df_btc_all.empty:
        df_c = df_btc_all.reset_index()
        base = alt.Chart(df_c).encode(x=alt.X('Date:T', title='날짜'))
        line_price = base.mark_line(color='#95a5a6', strokeWidth=1.5, strokeDash=[3,3]).encode(y=alt.Y('Close:Q', scale=alt.Scale(type='log'), title='가격 ($)'))
        line_hodl = base.mark_line(color='#e74c3c', strokeWidth=2.5).encode(y=alt.Y('Inactive_1yr_Ratio:Q', title='장기 미이동 비중 (%)', scale=alt.Scale(zero=False)))
        st.altair_chart(alt.layer(line_price, line_hodl).resolve_scale(y='independent').properties(height=300), use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------
# 2. 🇺🇸 미 3대 주요 지수 섹션
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🇺🇸 미국 3대 주요 증시 지수</div>", unsafe_allow_html=True)
us_indices = get_us_indices()
for name, info in us_indices.items():
    price_val = safe_number(info.get('price'))
    pct_val = safe_number(info.get('pct'))
    st.metric(name, f"{price_val:,.2f}" if price_val is not None else "N/A", f"{pct_val:+.2f}%" if pct_val is not None else None)
    render_custom_line_chart(info.get('df_1m', pd.DataFrame()), line_color='#d32f2f' if pct_val is not None and pct_val < 0 else '#2e7d32')
    st.markdown(f"[🔗 Yahoo Finance 원본]({info.get('link')})")
st.markdown("---")

# ---------------------------------------------------------
# 3. 📅 향후 2주간 주요 일정 & 실적 발표
# ---------------------------------------------------------
st.markdown("<div class='section-title'>📅 향후 2주간 주요 일정 & 실적 발표</div>", unsafe_allow_html=True)
events_df = get_upcoming_market_events()
if not events_df.empty:
    st.dataframe(events_df, use_container_width=True, hide_index=True)
else:
    st.info("향후 15일 이내에 예정된 주요 이벤트가 없습니다.")
st.markdown("---")

# ---------------------------------------------------------
# 4. 증시 밸류에이션 및 투자 심리
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🏛️ 증시 밸류에이션 및 투자 심리 지표</div>", unsafe_allow_html=True)
cape_val = get_shiller_cape()
fg_score, fg_rating = get_fear_and_greed()
st.metric(
    "S&P 500 Shiller CAPE",
    f"{cape_val:.2f}" if cape_val is not None else "N/A",
    ("고평가 부담" if cape_val is not None and cape_val > 30 else "보통") if cape_val is not None else "데이터 없음",
)
st.markdown("[🔗 multpl.com 원본](https://www.multpl.com/shiller-pe)")
st.metric("미 증시 공포·탐욕 지수", f"{fg_score:.1f} / 100" if fg_score is not None else "N/A", fg_rating)
st.markdown("[🔗 CNN Fear & Greed 원본](https://edition.cnn.com/markets/fear-and-greed)")
st.markdown("---")

# ---------------------------------------------------------
# 5. 미 국채 만기별 금리 섹션
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🇺🇸 미 국채 만기별 금리 현황 (최근 1개월)</div>", unsafe_allow_html=True)
treasury_data = get_fred_treasury_data()
for name in ['미 국채 2년물', '미 국채 5년물', '미 국채 10년물', '미 국채 30년물']:
    info = treasury_data.get(name, {})
    value = safe_number(info.get('price'))
    delta = safe_number(info.get('change'))
    st.metric(name, f"{value:.2f}%" if value is not None else "N/A", f"{delta:+.2f}%p" if delta is not None else None)
    render_custom_line_chart(info.get('df_1m', pd.DataFrame()), min_y=3.0)
    st.markdown(f"[🔗 FRED 공식 데이터]({info.get('link')})")

spread_info = treasury_data.get('미 국채 10년물-2년물 금리차', {})
spread_value = safe_number(spread_info.get('price'))
spread_change = safe_number(spread_info.get('change'))
st.metric(
    "미 국채 10년물 금리 - 2년물 금리",
    f"{spread_value:+.2f}%p" if spread_value is not None else "N/A",
    f"{spread_change:+.2f}%p" if spread_change is not None else None,
    help="FRED T10Y2Y: 10년 만기 국채금리에서 2년 만기 국채금리를 뺀 값입니다. 0%p 미만이면 장단기 금리 역전입니다.",
)
render_custom_line_chart(spread_info.get('df_1m', pd.DataFrame()))
st.markdown("[🔗 FRED 10Y-2Y 공식 데이터](https://fred.stlouisfed.org/series/T10Y2Y)")
st.markdown("---")

# ---------------------------------------------------------
# 6. 유동성 & 신용 위험 지표 섹션
# ---------------------------------------------------------
st.markdown("<div class='section-title'>💧 유동성 및 신용 위험 지표</div>", unsafe_allow_html=True)
hy_info = get_hy_spread()
macro_info = get_macro_data()
hy_value = safe_number(hy_info.get('price'))
hy_change = safe_number(hy_info.get('change'))
st.metric("하이일드 스프레드", f"{hy_value:.2f}%p" if hy_value is not None else "N/A", f"{hy_change:+.2f}%p" if hy_change is not None else None)
render_custom_line_chart(hy_info.get('df_1m', pd.DataFrame()), min_y=2.0)
st.markdown(f"[🔗 FRED 공식 데이터]({hy_info.get('link')})")

for key, label, fmt in zip(['달러 인덱스', 'VIX 지수', 'WTI 유가', '브렌트유'], ['달러 인덱스 (DXY)', 'VIX 변동성', 'WTI 유가 ($)', '브렌트유 ($)'], ["{:.2f}", "{:.2f}", "${:.2f}", "${:.2f}"]):
    v = macro_info.get(key, {})
    current = safe_number(v.get('price'))
    change_pct = safe_number(v.get('pct'))
    st.metric(label, fmt.format(current) if current is not None else "N/A", f"{change_pct:+.2f}%" if change_pct is not None else None)
    st.markdown(f"[🔗 Yahoo Finance 원본]({v.get('link')})")
st.markdown("---")

# ---------------------------------------------------------
# 7. 미국 상장 시가총액 상위 10개 기업
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🏆 미국 상장 시가총액 상위 10개 기업</div>", unsafe_allow_html=True)
top10_df = get_top10_market_cap()
if not top10_df.empty:
    top10_display = top10_df.drop(columns=["시가총액_원값"], errors="ignore")
    st.dataframe(top10_display, use_container_width=True, height=390, hide_index=True)
    if len(top10_df) >= 2:
        cap1 = safe_number(top10_df.iloc[0]["시가총액_원값"])
        cap2 = safe_number(top10_df.iloc[1]["시가총액_원값"])
        gap_pct = ((cap1 - cap2) / cap2) * 100 if cap1 is not None and cap2 else None
        c1, c2 = st.columns(2)
        with c1:
            st.metric("시가총액 1위", f"{top10_df.iloc[0]['기업명']} ({top10_df.iloc[0]['티커']})")
        with c2:
            st.metric(
                "1위와 2위의 시가총액 격차 (2위 대비)",
                f"{gap_pct:.1f}%" if gap_pct is not None else "N/A",
                help="(1위 시가총액 - 2위 시가총액) ÷ 2위 시가총액 × 100",
            )
else:
    st.info("시가총액 순위 데이터를 불러오지 못했습니다. Yahoo Finance 연결 상태를 확인해주세요.")
st.caption("순위·시가총액: Yahoo Finance 스크리너 우선, 조회 실패 시 대형주 후보군으로 보완. 미국 거래소 상장 종목 기준이며 ADR이 포함될 수 있습니다.")
st.markdown("[🔗 Yahoo Finance 시장 데이터](https://finance.yahoo.com/) · [미국 상장 기업 시가총액 순위 참고](https://stockanalysis.com/list/largest-us-companies/)")
st.markdown("---")

# ---------------------------------------------------------
# 8. 지표 기반 매크로·유동성 종합 진단 (외부 AI API 미사용)
# ---------------------------------------------------------
st.markdown("<div class='section-title'>🧭 지표 기반 매크로·유동성 종합 진단</div>", unsafe_allow_html=True)
assessment = build_macro_assessment(
    us_indices=us_indices,
    cape_value=cape_val,
    stock_fg_score=fg_score,
    treasury_data=treasury_data,
    hy_info=hy_info,
    macro_info=macro_info,
    crypto_fg_score=crypto_fng_score,
)

ac1, ac2 = st.columns([1, 2])
with ac1:
    st.metric("종합 환경 판정", assessment["regime"])
    st.metric("확인 가능한 신호 점수", f"{assessment['score']:+d} / {assessment['evaluated']}")
with ac2:
    st.markdown("**현재 해석**  \n" + assessment["explanation"])
    if assessment["crypto_note"]:
        st.markdown("**가상자산 심리**  \n" + assessment["crypto_note"])

left, right = st.columns(2)
with left:
    st.markdown("#### 우호 신호")
    if assessment["positives"]:
        for item in assessment["positives"]:
            st.markdown(f"- {item}")
    else:
        st.caption("현재 임계값을 충족한 우호 신호가 없습니다.")
with right:
    st.markdown("#### 경계 신호")
    if assessment["cautions"]:
        for item in assessment["cautions"]:
            st.markdown(f"- {item}")
    else:
        st.caption("현재 임계값을 충족한 경계 신호가 없습니다.")

with st.expander("전체 지표별 관찰 결과"):
    for observation in assessment["observations"]:
        st.markdown(f"- {observation}")

with st.expander("분석 기준 및 해석상 유의점"):
    st.markdown("""
    - 본 분석은 **현재 화면에 수집된 수치**를 사전에 정한 기준에 대입하는 규칙 기반 진단입니다. 별도 생성형 AI API 키가 필요하지 않습니다.
    - S&P 500·나스닥 일간 등락률 ±0.5%, VIX 18/25, 하이일드 스프레드 3.5/5.0%p, 10년물-2년물 금리차 ±0.25%p, CNN 심리지수 20/45~65/80, Shiller CAPE 25/35, DXY ±0.5%, WTI ±3%를 참고 임계값으로 사용합니다.
    - 우호·경계 신호를 각각 +1/-1로 단순 합산합니다. +3 이상은 위험선호 우위, -3 이하는 위험회피 우위, 그 사이는 혼조로 표시합니다. 누락 데이터는 점수에 포함하지 않습니다.
    - 이 점수는 경기침체·주가 방향을 예측하거나 매매 신호를 보장하지 않습니다. 특히 장단기 금리차, CAPE 등은 시차가 긴 지표이므로 추세·정책·실적과 함께 해석해야 합니다.
    """)

st.markdown("<br><hr><center><small>Global Macro & Crypto Market Dashboard</small></center>", unsafe_allow_html=True)
