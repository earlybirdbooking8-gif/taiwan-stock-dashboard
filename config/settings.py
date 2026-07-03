"""
台股開盤預測系統 — 設定檔
請將 .env 檔案放在專案根目錄，填入真實金鑰
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── AI 模型 ──────────────────────────────────────────────
AI_PROVIDER   = os.getenv("AI_PROVIDER", "claude")          # claude | openai | gemini
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")

# ── 元大 API ──────────────────────────────────────────────
USE_YUANTA          = os.getenv("USE_YUANTA", "false").lower() == "true"
YUANTA_DLL_DIR      = os.getenv("YUANTA_DLL_DIR", r"D:\元大證券\YuantaSparkAPI_win-x64_Python\YuantaSparkAPI_win-x64_Python")
YUANTA_ACCOUNT      = os.getenv("YUANTA_ACCOUNT", "")
YUANTA_PASSWORD     = os.getenv("YUANTA_PASSWORD", "")
YUANTA_PFX_PATH     = os.getenv("YUANTA_PFX_PATH", "")
YUANTA_PFX_PASSWORD = os.getenv("YUANTA_PFX_PASSWORD", "")
YUANTA_TXF_PM       = "TXFPM1"

# ── Notion ────────────────────────────────────────────────
NOTION_TOKEN      = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")   # 每日報告 DB

# ── Yahoo Finance（免費，不需 key） ───────────────────────
YAHOO_SYMBOLS = {
    "tsm_adr"   : "TSM",        # 台積電 ADR
    "sox"       : "^SOX",       # 費城半導體
    "nq_futures": "^IXIC",      # NASDAQ 指數
    "vix"       : "^VIX",       # 恐慌指數
    "usdtwd"    : "TWD=X",      # USD/TWD
    "tnx"       : "^TNX",       # 美10年期殖利率
    "gold"      : "GC=F",       # 黃金期貨
    "crude"     : "CL=F",       # 原油期貨
}

# ── TWSE OpenAPI（免費，不需 key） ───────────────────────
TWSE_BASE   = "https://openapi.twse.com.tw/v1"
TWSE_TAIEX  = f"{TWSE_BASE}/exchangeReport/FMTQIK"         # 大盤指數
TWSE_MARGIN = f"{TWSE_BASE}/exchangeReport/MI_MARGN"        # 融資融券

# ── TAIFEX（免費） ───────────────────────────────────────
TAIFEX_BASE = "https://www.taifex.com.tw/cht/3"
TAIFEX_OI   = "https://www.taifex.com.tw/cht/3/largeTraderFutQry"  # 三大法人

# ── FRED API（免費，需申請 key） ─────────────────────────
FRED_KEY    = os.getenv("FRED_API_KEY", "")
FRED_BASE   = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = {
    "dxy"        : "DTWEXBGS",  # 美元指數
    "fed_rate"   : "FEDFUNDS",  # 聯邦基金利率
    "us10y"      : "DGS10",     # 10年期公債殖利率
}

# ── 新聞 API ─────────────────────────────────────────────
NEWSAPI_KEY  = os.getenv("NEWSAPI_KEY", "")
NEWS_QUERIES = ["TSMC", "Taiwan semiconductor", "台積電", "台股", "SOX"]
NEWS_LOOKBACK_HOURS = 16                                     # 抓多少小時前的新聞

# ── 執行排程 ─────────────────────────────────────────────
# 建議：每天 07:30 台灣時間（美股收盤後、台股開盤前）
SCHEDULE_TIME = "07:30"
TIMEZONE      = "Asia/Taipei"

# ── 輸出 ─────────────────────────────────────────────────
OUTPUT_DIR  = "outputs"
LOG_DIR     = "logs"
REPORT_JSON = "outputs/latest_report.json"
REPORT_HTML = "outputs/dashboard.html"
