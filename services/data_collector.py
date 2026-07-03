"""
services/data_collector.py
從 TWSE、TAIFEX、Yahoo Finance、FRED、新聞 API 一次抓齊所有指標
"""

import logging
import requests
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import *

log = logging.getLogger(__name__)
TW = ZoneInfo(TIMEZONE)


# ─────────────────────────────────────────────────────────
# 1. Yahoo Finance — ADR / 美股指數 / VIX / 匯率
# ─────────────────────────────────────────────────────────
def fetch_yahoo() -> dict:
    """回傳各 symbol 的最新收盤價、漲跌幅、MA5、MA20 與成交量資料"""
    result = {}
    for name, symbol in YAHOO_SYMBOLS.items():
        try:
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period="30d") # 抓取 30 天以計算均線均量
            if len(hist) < 1:
                raise ValueError("No data returned")
            
            latest  = hist["Close"].iloc[-1]
            prev    = hist["Close"].iloc[-2] if len(hist) >= 2 else latest
            chg_pct = (latest - prev) / prev * 100
            
            # 計算 5MA 與 20MA
            ma5 = hist["Close"].rolling(5).mean().iloc[-1] if len(hist) >= 5 else latest
            ma20 = hist["Close"].rolling(20).mean().iloc[-1] if len(hist) >= 20 else latest
            
            # 成交量
            vol_latest = hist["Volume"].iloc[-1] if "Volume" in hist.columns else 0.0
            vol_ma20 = hist["Volume"].rolling(20).mean().iloc[-1] if "Volume" in hist.columns and len(hist) >= 20 else vol_latest
            
            result[name] = {
                "price"   : round(latest, 4),
                "prev"    : round(prev, 4),
                "chg_pct" : round(chg_pct, 2),
                "chg_abs" : round(latest - prev, 4),
                "ma5"     : round(ma5, 4) if ma5 is not None else None,
                "ma20"    : round(ma20, 4) if ma20 is not None else None,
                "volume"  : float(vol_latest),
                "vol_ma20": float(vol_ma20)
            }
            log.info(f"  Yahoo {symbol}: {latest:.2f} ({chg_pct:+.2f}%) | 5MA: {ma5:.2f} | 20MA: {ma20:.2f}")
        except Exception as e:
            log.warning(f"  Yahoo {symbol} 失敗：{e}")
            result[name] = None
    return result


# ─────────────────────────────────────────────────────────
# 2. TWSE OpenAPI — 大盤加權指數
# ─────────────────────────────────────────────────────────
def fetch_taiex() -> dict | None:
    """從 TWSE OpenAPI 取得最新大盤指數（台幣收盤）"""
    try:
        resp = requests.get(TWSE_TAIEX, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # 取最新一筆
        row  = data[-1] if data else {}
        idx  = float(row.get("TAIEX", 0))
        prev_close = float(row.get("ClosePrice", idx))
        result = {
            "taiex_close": idx,
            "date"       : row.get("Date", ""),
        }
        log.info(f"  TAIEX 收盤：{idx}")
        return result
    except Exception as e:
        log.warning(f"  TWSE API 失敗：{e}")
        return None


# ─────────────────────────────────────────────────────────
# 3. TAIFEX — 三大法人台指期淨部位（外資未平倉）
# ─────────────────────────────────────────────────────────
def fetch_taifex_oi() -> dict | None:
    """
    抓取 TAIFEX 三大法人台指期未平倉淨口數
    使用 CSV 下載端點（最穩定）
    若當日資料尚未公布（通常在 15:00 前），會自動往前推算，直到抓到最近一交易日的數據
    """
    import time
    for i in range(7):
        try:
            target_date = datetime.now(TW) - timedelta(days=i)
            # 避開週末
            if target_date.weekday() >= 5:
                continue
            
            date_str = target_date.strftime("%Y/%m/%d")
            url = (
                "https://www.taifex.com.tw/cht/3/futContractsDateDown"
                f"?queryStartDate={date_str}&queryEndDate={date_str}"
                "&commodityId=TXF"
            )
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

            lines = resp.text.strip().splitlines()
            if len(lines) <= 1: # 只有標題或為空，表示尚未公布或未開市
                continue
                
            foreign = None
            dealer  = None
            trust   = None

            for line in lines:
                cols = [c.strip().replace(",", "") for c in line.split(",")]
                if "自營商" in line:
                    dealer = _parse_net(cols)
                elif "投信" in line:
                    trust  = _parse_net(cols)
                elif "外資" in line and "外資自行" not in line:
                    foreign = _parse_net(cols)

            if foreign is not None or dealer is not None:
                result = {
                    "foreign_net_oi" : foreign,
                    "dealer_net_oi"  : dealer,
                    "trust_net_oi"   : trust,
                    "total_inst_oi"  : (foreign or 0) + (dealer or 0) + (trust or 0),
                }
                log.info(f"  成功取得 {date_str} TAIFEX 外資淨口數：{foreign}")
                return result
        except Exception as e:
            log.warning(f"  抓取 {date_str} TAIFEX 失敗：{e}")
            
    return None


def _parse_net(cols: list) -> int | None:
    """從欄位清單找「多空未平倉淨口數」"""
    try:
        return int(cols[-2]) if len(cols) > 3 else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
# 4. FRED API — 美元指數 / 利率
# ─────────────────────────────────────────────────────────
def fetch_fred() -> dict:
    """從 FRED 取最新宏觀指標（需 FRED_API_KEY）"""
    if not FRED_KEY:
        log.warning("  FRED_API_KEY 未設定，跳過")
        return {}
    result = {}
    for name, series_id in FRED_SERIES.items():
        try:
            params = {
                "series_id"       : series_id,
                "api_key"         : FRED_KEY,
                "file_type"       : "json",
                "sort_order"      : "desc",
                "limit"           : 2,
                "observation_start": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            }
            resp = requests.get(FRED_BASE, params=params, timeout=10)
            resp.raise_for_status()
            obs  = resp.json().get("observations", [])
            if len(obs) >= 1:
                latest = float(obs[0]["value"]) if obs[0]["value"] != "." else None
                prev   = float(obs[1]["value"]) if len(obs) > 1 and obs[1]["value"] != "." else latest
                result[name] = {
                    "value"   : latest,
                    "prev"    : prev,
                    "chg_abs" : round((latest or 0) - (prev or 0), 4),
                }
                log.info(f"  FRED {series_id}: {latest}")
        except Exception as e:
            log.warning(f"  FRED {series_id} 失敗：{e}")
            result[name] = None
    return result


# ─────────────────────────────────────────────────────────
# 5. 新聞 API — NewsAPI.org
# ─────────────────────────────────────────────────────────
def fetch_news() -> list[dict]:
    """抓取新聞標題"""
    if not NEWSAPI_KEY:
        log.warning("  NEWSAPI_KEY 未設定，跳過")
        return []
    since = (datetime.utcnow() - timedelta(hours=NEWS_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headlines = []
    for query in NEWS_QUERIES[:3]:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q"          : query,
                    "from"       : since,
                    "sortBy"     : "publishedAt",
                    "pageSize"   : 5,
                    "language"   : "en",
                    "apiKey"     : NEWSAPI_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            for a in articles:
                headlines.append({
                    "title"      : a.get("title", ""),
                    "source"     : a.get("source", {}).get("name", ""),
                    "publishedAt": a.get("publishedAt", ""),
                })
        except Exception as e:
            log.warning(f"  NewsAPI [{query}] 失敗：{e}")
    seen  = set()
    dedup = []
    for h in headlines:
        if h["title"] not in seen:
            seen.add(h["title"])
            dedup.append(h)
    log.info(f"  新聞抓取：共 {len(dedup)} 則")
    return dedup[:10]


# ─────────────────────────────────────────────────────────
# 5.1 證交所 BFI82U — 三大法人現貨買賣超金額
# ─────────────────────────────────────────────────────────
def fetch_twse_institutions() -> dict | None:
    """從證交所 BFI82U API 取得三大法人現貨買賣超數據"""
    try:
        for i in range(5):
            target_date = (datetime.now(TW) - timedelta(days=i)).strftime("%Y%m%d")
            url = f"https://www.twse.com.tw/fund/BFI82U?response=json&dayDate={target_date}&type=day"
            resp = requests.get(url, timeout=10)
            resp.encoding = "utf-8"
            resp.raise_for_status()
            data = resp.json()
            if data.get("stat") == "OK" and data.get("data"):
                log.info(f"  [TWSE BFI82U] 成功獲取 {target_date} 三大法人現貨買賣超數據")
                
                rows = data.get("data", [])
                dealer_self = 0.0
                dealer_hedge = 0.0
                trust = 0.0
                foreign = 0.0
                
                for r in rows:
                    name = r[0].strip()
                    diff = float(r[3].replace(",", "")) if len(r) > 3 else 0.0
                    if "自營商" in name and "自行買賣" in name:
                        dealer_self = diff
                    elif "自營商" in name and "避險" in name:
                        dealer_hedge = diff
                    elif "投信" in name:
                        trust = diff
                    elif "外資及" in name:
                        foreign = diff
                        
                return {
                    "date": target_date,
                    "foreign": foreign,
                    "trust": trust,
                    "dealer": dealer_self + dealer_hedge,
                    "total": foreign + trust + dealer_self + dealer_hedge
                }
        return None
    except Exception as e:
        log.warning(f"  [TWSE BFI82U] 取得三大法人買賣超失敗：{e}")
        return None


# ─────────────────────────────────────────────────────────
# 5.2 證交所 MI_MARGN — 全市場大盤融資融券餘額張數增減
# ─────────────────────────────────────────────────────────
def fetch_twse_margin() -> dict | None:
    """從證交所 OpenAPI (MI_MARGN) 獲取融資變動"""
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        rows = resp.json()
        
        if isinstance(rows, list) and len(rows) > 0:
            total_today = 0
            total_prev = 0
            
            for r in rows:
                today = 0
                prev = 0
                for k, v in r.items():
                    cleaned_val = 0
                    if v is not None:
                        val_str = str(v).replace(",", "").strip()
                        if val_str and val_str.isdigit():
                            cleaned_val = int(val_str)
                            
                    if "今日餘額" in k or "今日" in k or k == "融資今日餘額" or "ĸꤵ" in k:
                        today = cleaned_val
                    elif "前日餘額" in k or "前日" in k or k == "融資前日餘額" or "ĸe" in k:
                        prev = cleaned_val
                            
                total_today += today
                total_prev += prev
                    
            diff = total_today - total_prev
            log.info(f"  [TWSE MI_MARGN] 全市場融資餘額：今日 {total_today:,} 張，前日 {total_prev:,} 張，變動 {diff:+,} 張")
            return {
                "today": total_today,
                "prev": total_prev,
                "diff": diff
            }
        return None
    except Exception as e:
        log.warning(f"  [TWSE MI_MARGN] 取得融資餘額失敗：{e}")
        return None


# ─────────────────────────────────────────────────────────
# 5.5 元大 API — 加權指數昨收價
# ─────────────────────────────────────────────────────────
def fetch_taiex_yuanta(client) -> dict | None:
    """透過元大 API 取得最新大盤加權指數的昨收價"""
    try:
        today_str = datetime.now(TW).strftime("%Y/%m/%d")
        start_str = (datetime.now(TW) - timedelta(days=5)).strftime("%Y/%m/%d")
        bars = client.get_kline(YUANTA_ACCOUNT, "0000", start_str, today_str)
        if len(bars) >= 1:
            latest_bar = bars[-1]
            log.info(f"  [元大 API] TAIEX 收盤：{latest_bar.close} (日期：{latest_bar.date})")
            return {
                "taiex_close": latest_bar.close,
                "date": latest_bar.date,
            }
        return None
    except Exception as e:
        log.warning(f"  [元大 API] 取得 TAIEX 失敗：{e}")
        return None


# ─────────────────────────────────────────────────────────
# 5.6 元大 API — 台指期夜盤昨收 (TXFPM1)
# ─────────────────────────────────────────────────────────
def fetch_txf_night_yuanta(client) -> dict | None:
    """透過元大 API 行情訂閱取得台指PM近 (TXFPM1) 價格"""
    try:
        from services.yuanta_service import _get_mod
        import time
        taifex_market = _get_mod("enumMarketType").TAIFEX
        
        client.subscribe_quote(YUANTA_ACCOUNT, YUANTA_TXF_PM, market=taifex_market)
        
        timeout = 10
        quote_data = None
        for _ in range(timeout * 10):
            client._pump_messages()
            q = client.get_latest_quote(YUANTA_TXF_PM)
            if q:
                deal_price = q.get("deal_price", 0.0)
                if deal_price == 0.0:
                    bid = q.get("bid_price", 0.0)
                    ask = q.get("ask_price", 0.0)
                    deal_price = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0.0
                
                if deal_price > 0.0:
                    quote_data = q
                    quote_data["price"] = deal_price
                    break
            time.sleep(0.1)
            
        if quote_data:
            log.info(f"  [元大 API] 訂閱 TXFPM1 (台指PM近) 成功，即時價格：{quote_data['price']}")
            return {
                "price": round(quote_data["price"], 2),
                "prev": round(quote_data.get("bid_price", quote_data["price"]), 2),
                "chg_pct": 0.0,
                "chg_abs": 0.0,
                "date": datetime.now(TW).strftime("%Y/%m/%d %H:%M")
            }
        return None
    except Exception as e:
        log.warning(f"  [元大 API] 訂閱獲取 TXFPM1 失敗：{e}")
        return None


def fetch_txf_night_finmind() -> dict | None:
    """透過 FinMind API 取得台指期夜盤昨收價格"""
    try:
        # 抓取最近 5 天的資料，確保在連假或週末後也能拿到資料
        today = datetime.now(TW)
        start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanFuturesDaily",
            "data_id": "TX",
            "start_date": start_date
        }
        
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            res = r.json()
            if res.get("status") == 200 and res.get("data"):
                data = res["data"]
                # 1. 篩選夜盤 (after_market)
                night_data = [x for x in data if x.get("trading_session") == "after_market"]
                if not night_data:
                    log.warning("  [FinMind API] 找不到夜盤 (after_market) 資料，嘗試使用常規盤 fallback")
                    # Fallback: 如果沒有夜盤資料，就用 position (日盤)
                    night_data = [x for x in data if x.get("trading_session") == "position"]
                    
                if night_data:
                    # 2. 找到最新的一天
                    latest_date = max(x["date"] for x in night_data)
                    latest_day_data = [x for x in night_data if x["date"] == latest_date]
                    
                    # 3. 找到近月主力合約（成交量最大者）
                    best_contract = max(latest_day_data, key=lambda x: x.get("volume", 0))
                    
                    price = best_contract.get("close", 0.0)
                    open_p = best_contract.get("open", 0.0)
                    
                    # 尋找同一交易日、同一合約的日盤 (position) 收盤價作為參考昨收
                    regular_contract = None
                    target_contract_date = best_contract.get("contract_date")
                    
                    # 篩選出跟主力合約同日期、同月份但為日盤的資料
                    regular_matches = [
                        x for x in data 
                        if x.get("date") == latest_date 
                        and x.get("contract_date") == target_contract_date 
                        and x.get("trading_session") == "position"
                    ]
                    
                    # 如果同日期找不到，找最接近的日盤
                    if not regular_matches:
                        all_regular_for_contract = [
                            x for x in data 
                            if x.get("contract_date") == target_contract_date 
                            and x.get("trading_session") == "position"
                        ]
                        if all_regular_for_contract:
                            regular_matches = [max(all_regular_for_contract, key=lambda x: x["date"])]
                    
                    if regular_matches:
                        regular_close = regular_matches[0].get("close", 0.0)
                        if regular_close > 0:
                            chg_abs = price - regular_close
                            chg_pct = (chg_abs / regular_close) * 100
                            prev_price = regular_close
                        else:
                            chg_abs = price - open_p
                            chg_pct = (chg_abs / open_p) * 100 if open_p > 0 else 0.0
                            prev_price = open_p
                    else:
                        chg_abs = price - open_p
                        chg_pct = (chg_abs / open_p) * 100 if open_p > 0 else 0.0
                        prev_price = open_p
                    
                    log.info(f"  [FinMind API] 成功取得台指夜盤，日期：{latest_date}，合約：{best_contract.get('contract_date')}，收盤價：{price}，昨收參考(日盤)：{prev_price}")
                    
                    return {
                        "price": round(price, 2),
                        "prev": round(prev_price, 2),
                        "chg_pct": round(chg_pct, 2),
                        "chg_abs": round(chg_abs, 2),
                        "date": latest_date.replace("-", "/")
                    }
        log.warning(f"  [FinMind API] 讀取台指夜盤失敗，HTTP Code: {r.status_code}")
        return None
    except Exception as e:
        log.warning(f"  [FinMind API] 獲取台指夜盤失敗：{e}")
        return None


# ─────────────────────────────────────────────────────────
# 整合入口
# ─────────────────────────────────────────────────────────
def collect_all() -> dict:
    """一次執行所有資料蒐集，回傳統一格式"""
    log.info("═══ 開始蒐集市場數據 ═══")
    ts = datetime.now(TW).isoformat()

    yuanta_active = False
    yuanta_taiex = None
    yuanta_txf_pm = None
    if USE_YUANTA:
        log.info("正在嘗試初始化元大 API...")
        try:
            from services.yuanta_service import get_client
            client = get_client()
            init_res = client.init()
            if init_res == "OK":
                open_res = client.open()
                if open_res == "OK":
                    login_res = client.login(
                        YUANTA_ACCOUNT,
                        YUANTA_PASSWORD,
                        YUANTA_PFX_PATH,
                        YUANTA_PFX_PASSWORD
                    )
                    log.info(f"元大 API 登入結果: {login_res}")
                    if client.state.logged_in:
                        yuanta_active = True
                        yuanta_taiex = fetch_taiex_yuanta(client)
                        yuanta_txf_pm = fetch_txf_night_yuanta(client)
                else:
                    log.warning(f"元大 API 開啟連線失敗: {open_res}")
            else:
                log.warning(f"元大 API 初始化失敗: {init_res}")
        except Exception as e:
            log.warning(f"載入或執行元大 API 失敗: {e}")

    yahoo   = fetch_yahoo()
    
    if yuanta_active and yuanta_taiex:
        taiex = yuanta_taiex
        log.info("已成功由 [元大 API] 取得大盤數據")
    else:
        taiex = fetch_taiex()
        if yuanta_active:
            log.info("元大 API 大盤數據獲取失敗，已 [Fallback] 至 TWSE OpenAPI")

    txf_pm = fetch_txf_night_finmind()
    if txf_pm:
        log.info("已成功由 [FinMind API] 取得夜盤台指數據")
    else:
        log.info("[FinMind API] 取得夜盤台指數據失敗")

    taifex  = fetch_taifex_oi()
    fred    = fetch_fred()
    news    = fetch_news()
    twse_inst = fetch_twse_institutions()
    twse_margin = fetch_twse_margin()

    if yuanta_active:
        try:
            client.close()
            log.info("元大 API 連線已關閉")
        except Exception:
            pass

    payload = {
        "collected_at" : ts,
        # ── 台灣市場 ──
        "taiex"        : taiex,
        "taifex_oi"    : taifex,
        "txf_pm"       : txf_pm,
        "twse_inst"    : twse_inst,
        "twse_margin"  : twse_margin,
        # ── 美股 / ADR ──
        "tsm_adr"      : yahoo.get("tsm_adr"),
        "sox"          : yahoo.get("sox"),
        "nq_futures"   : yahoo.get("nq_futures"),
        "vix"          : yahoo.get("vix"),
        "gold"         : yahoo.get("gold"),
        "crude"        : yahoo.get("crude"),
        # ── 總體 ──
        "usdtwd"       : yahoo.get("usdtwd"),
        "tnx"          : yahoo.get("tnx"),
        "fred"         : fred,
        # ── 新聞 ──
        "news"         : news,
    }
    log.info("═══ 數據蒐集完成 ═══")
    return payload
