"""
ui/dashboard_renderer.py
根據最新報告 JSON，生成靜態 HTML 儀表板
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import OUTPUT_DIR, TIMEZONE

log = logging.getLogger(__name__)


def build_html(market_data: dict, ai_result: dict, notion_url: str | None = None) -> str:
    """生成完整 HTML 字串"""
    TW    = ZoneInfo(TIMEZONE)
    ts    = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
    today = datetime.now(TW).strftime("%Y/%m/%d")

    dir_code   = ai_result.get("direction_code", "flat")
    open_pred  = ai_result.get("open_direction", "—")
    pt_low     = ai_result.get("point_range_low", 0)
    pt_high    = ai_result.get("point_range_high", 0)
    confidence = ai_result.get("confidence", 0)
    sentiment  = ai_result.get("sentiment", "中性")
    strategy   = ai_result.get("strategy", "觀望")
    continuation = ai_result.get("continuation", "震盪")
    summary    = ai_result.get("summary_zh", "")
    drivers    = ai_result.get("key_drivers", [])
    risks      = ai_result.get("risk_factors", [])
    probs      = ai_result.get("scenario_probs", {})
    provider   = ai_result.get("ai_provider", "—")
    
    conf_details = ai_result.get("confidence_details") or {}
    total_score = conf_details.get("total_score", 0)
    
    vix_val = (market_data.get("vix") or {}).get("price", 0)
    if vix_val < 15:
        vol_text = "中低"
    elif vix_val < 22:
        vol_text = "中"
    else:
        vol_text = "高"
        
    conf_details_json = json.dumps(conf_details, ensure_ascii=False)

    # 三大法人未平倉數據
    oi = market_data.get("taifex_oi") or {}

    # 取得商品與指數數據
    adr        = market_data.get("tsm_adr")
    sox        = market_data.get("sox")
    nq         = market_data.get("nq_futures")
    usd        = market_data.get("usdtwd") or {}
    tnx        = market_data.get("tnx")
    gold       = market_data.get("gold")
    crude      = market_data.get("crude")
    vix        = market_data.get("vix")
    twse_inst  = market_data.get("twse_inst") or {}
    twse_margin= market_data.get("twse_margin") or {}
    txf_pm     = market_data.get("txf_pm")

    # 定義指標格式化與 Tooltip 生成引擎
    def get_metric_html(d, name, source, api_name, alt_source, key="price", decimals=2, is_currency=False, has_sign=False, is_money=False):
        val = (d or {}).get(key)
        status = "已同步" if val is not None else "同步失敗"
        update_time = ts
        
        if val is not None:
            if is_money:
                val_str = f"{(val / 100000000):+.2f} 億"
            elif has_sign:
                try:
                    val_str = f"{int(val):+,d}"
                except (ValueError, TypeError):
                    val_str = f"{val}"
            else:
                formatted_val = f"{val:,.{decimals}f}"
                if is_currency:
                    val_str = f"${formatted_val} USD" if "ADR" in name or "原油" in name or "黃金" in name else f"{formatted_val}"
                else:
                    val_str = f"{formatted_val}"
            
            sub_str = f"<div class='c-date'>最後更新: {today} | {status}</div>"
        else:
            val_str = "<span class='c-error'>目前無法取得資料</span>"
            sub_str = f"<div class='c-date c-error-text'>原因: API 連線限制或請求超時<br>最後嘗試: {today} | {status}</div>"
            
        tooltip = f"指標名稱：{name}&#10;資料來源：{source}&#10;"
        if api_name:
            tooltip += f"API 名稱：{api_name}&#10;"
        tooltip += f"更新時間：{update_time}&#10;同步狀態：{status}"
        if val is None:
            tooltip += f"&#10;失敗原因：伺服器未回應或超時&#10;替代來源：{alt_source}"
            
        return val_str, sub_str, tooltip

    txf_val, txf_sub, txf_tip = get_metric_html(txf_pm, "台指期盤後收盤 (TXFPM1)", "元大 API / 玩股網", "Yuanta/WantGoo", "三竹股市 / 台灣期交所官網", decimals=0)
    adr_val, adr_sub, adr_tip = get_metric_html(adr, "台積電 ADR (TSM)", "Yahoo Finance 國際市場", "yfinance (TSM)", "富途牛牛 / 紐約證交所官網", decimals=2, is_currency=True)
    sox_val, sox_sub, sox_tip = get_metric_html(sox, "SOX 費城半導體", "Yahoo Finance 國際市場", "yfinance (^SOX)", "英為財情 Investing.com", decimals=0)
    nq_val, nq_sub, nq_tip = get_metric_html(nq, "NASDAQ 指數", "Yahoo Finance 國際市場", "yfinance (^IXIC)", "Bloomberg 國際版", decimals=0)
    foreign_val, foreign_sub, foreign_tip = get_metric_html(twse_inst, "外資現貨買賣超", "台灣證券交易所 (TWSE) 官方", "OpenAPI (BFI82U)", "證交所三大法人買賣日報表", key="foreign", is_money=True)
    trust_val, trust_sub, trust_tip = get_metric_html(twse_inst, "投信現貨買賣超", "台灣證券交易所 (TWSE) 官方", "OpenAPI (BFI82U)", "證交所三大法人買賣日報表", key="trust", is_money=True)
    dealer_val, dealer_sub, dealer_tip = get_metric_html(twse_inst, "自營商買賣超", "玩股網", "爬蟲 (WantGoo)", "證交所三大法人買賣日報表", key="dealer", is_money=True)
    margin_val, margin_sub, margin_tip = get_metric_html(twse_margin, "融資餘額增減", "台灣證券交易所 (TWSE) 官方", "OpenAPI (MI_MARGN)", "證交所信用交易餘額彙總表", key="diff", has_sign=True)
    gold_val, gold_sub, gold_tip = get_metric_html(gold, "黃金期貨 (GC=F)", "Yahoo Finance 國際市場", "yfinance (GC=F)", "芝加哥商品交易所 CME Group", decimals=1, is_currency=True)
    crude_val, crude_sub, crude_tip = get_metric_html(crude, "美原油期貨 (CL=F)", "Yahoo Finance 國際市場", "yfinance (CL=F)", "紐約商業交易所 NYMEX", decimals=2, is_currency=True)
    vix_val, vix_sub, vix_tip = get_metric_html(vix, "VIX 恐慌指數", "Yahoo Finance 國際市場", "yfinance (^VIX)", "芝加哥期權交易所 CBOE")
    usd_val, usd_sub, usd_tip = get_metric_html(usd, "USD/TWD 匯率", "Yahoo Finance 國際市場", "yfinance (TWD=X)", "台北外匯交易中心 / 央行官網", decimals=3)
    tnx_val, tnx_sub, tnx_tip = get_metric_html(tnx, "美 10Y 債殖利率", "Yahoo Finance 國際市場", "yfinance (^TNX)", "美國財政部官方資料庫")

    usd_trend_val = (usd.get('price') or 0) > (usd.get('ma20') or 0)
    usd_trend_status = "已同步" if usd.get('price') is not None else "同步失敗"
    if usd.get('price') is not None:
        usd_trend_val_str = "站上 20MA (趨勢貶)" if usd_trend_val else "低於 20MA (趨勢升)"
        usd_trend_sub_str = f"<div class='c-date'>最後更新: {today} | 已同步</div>"
    else:
        usd_trend_val_str = "<span class='c-error'>目前無法取得資料</span>"
        usd_trend_sub_str = f"<div class='c-date c-error-text'>原因: API 連線限制或請求超時<br>最後嘗試: {today} | {usd_trend_status}</div>"
        
    usd_trend_tip = f"指標名稱：美元匯率均線趨勢&#10;資料來源：Yahoo Finance 國際市場&#10;API 名稱：yfinance (TWD=X)&#10;更新時間：{ts}&#10;同步狀態：{usd_trend_status}"
    if usd.get('price') is None:
        usd_trend_tip += f"&#10;失敗原因：伺服器未回應或超時&#10;替代來源：台北外匯交易中心"

    oi_foreign_val, oi_foreign_sub, oi_foreign_tip = get_metric_html(oi, "外資台指期未平倉口數", "台灣期貨交易所 (TAIFEX) 官方", "TAIFEX OpenAPI / 網頁爬蟲", "期交所三大法人交易口數彙總", key="foreign_net_oi", has_sign=True)
    oi_total_val, oi_total_sub, oi_total_tip = get_metric_html(twse_inst, "台股期貨未平倉(口)", "玩股網", "爬蟲 (WantGoo)", "證交所三大法人買賣日報表", key="total", is_money=True)

    def chg(d, key="chg_pct"):
        v = (d or {}).get(key)
        if v is None:
            return ""
        sign = "▲" if v >= 0 else "▼"
        cls  = "pos" if v >= 0 else "neg"
        return f'<span class="{cls}">{sign}{abs(v):.2f}%</span>'

    dir_cls   = {"high":"dir-up","low":"dir-down","flat":"dir-flat"}.get(dir_code,"dir-flat")
    dir_arrow = {"high":"↓" if open_pred == "開低" else "↑","low":"↓" if open_pred == "開低" else "↓","flat":"→"}.get(dir_code,"→")
    conf_circ = 2 * 3.14159 * 54
    conf_off  = conf_circ * (1 - confidence / 100)

    # 決策指標動態色彩
    strat_col = "#475569"
    if "做多" in strategy or "偏多" in strategy:
        strat_col = "#ef4444"
    elif "放空" in strategy or "偏空" in strategy or "減碼" in strategy:
        strat_col = "#10b981"
    elif "觀望" in strategy:
        strat_col = "#eab308"

    cont_col = "#475569"
    if "走高" in continuation:
        cont_col = "#ef4444"
    elif "走低" in continuation:
        cont_col = "#10b981"
    elif "震盪" in continuation:
        cont_col = "#3b82f6"

    drivers_html = "".join(f"<li><span class='bullet-icon'>✦</span>{d}</li>" for d in drivers) or "<li>—</li>"
    risks_html   = "".join(f"<li><span class='bullet-icon'>⚠️</span>{r}</li>" for r in risks)   or "<li>—</li>"

    prob_items = ""
    colors = {
        "開高走高": "linear-gradient(90deg, #ef4444, #ef4444)",
        "開高走低": "linear-gradient(90deg, #eab308, #eab308)",
        "開低走高": "linear-gradient(90deg, #10b981, #10b981)",
        "開低走低": "linear-gradient(90deg, #64748b, #64748b)"
    }
    for label, pct in probs.items():
        col = colors.get(label, "linear-gradient(90deg, #888, #999)")
        prob_items += f"""
        <div class="prob-row">
          <span class="prob-label">{label}</span>
          <div class="prob-track"><div class="prob-fill" style="width:{pct}%;background:{col}"></div></div>
          <span class="prob-pct">{pct}%</span>
        </div>"""

    notion_link = ""
    if notion_url:
        notion_link = f'<a href="{notion_url}" target="_blank" class="notion-btn">在 Notion 查看完整報告 →</a>'

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股開盤預測 · {today}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<style>
  * {{box-sizing:border-box;margin:0;padding:0}}
  :root {{
    --bg-dark: #f8fafc;
    --card-bg: #ffffff;
    --border-glow: #e2e8f0;
    --primary-color: #4f46e5;
    --text-primary: #0f172a;
    --text-secondary: #475569;
    --up-color: #ef4444;
    --down-color: #10b981;
    --flat-color: #eab308;
    --icon-bg: #e0e7ff;
    --icon-color: #4f46e5;
    --track-bg: #f1f5f9;
    --fluid-gap: clamp(1rem, 2vw, 1.5rem);
    --card-p: clamp(1.25rem, 2.5vw, 1.75rem);
    --icon-sz: clamp(2.5rem, 4vw, 3.5rem);
  }}
  body[data-theme="dark"] {{
    --bg-dark: #0c101b;
    --card-bg: #161a25;
    --border-glow: #242935;
    --primary-color: #3b82f6;
    --text-primary: #f1f5f9;
    --text-secondary: #7e8494;
    --up-color: #f7525f;
    --down-color: #22ab94;
    --flat-color: #ffb61a;
    --icon-bg: rgba(59, 130, 246, 0.1);
    --icon-color: #3b82f6;
    --track-bg: #1d222f;
  }}
  body[data-theme="purple"] {{
    --bg-dark: #070a13;
    --card-bg: rgba(20, 30, 55, 0.45);
    --border-glow: rgba(99, 102, 241, 0.25);
    --primary-color: #6366f1;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --up-color: #f43f5e;
    --down-color: #10b981;
    --flat-color: #eab308;
    --icon-bg: rgba(129, 140, 248, 0.15);
    --icon-color: #a5b4fc;
    --track-bg: rgba(255, 255, 255, 0.05);
  }}
  body[data-theme="terminal"] {{
    --bg-dark: #000000;
    --card-bg: #000000;
    --border-glow: #333333;
    --primary-color: #00ff00;
    --text-primary: #00ff00;
    --text-secondary: #888888;
    --up-color: #ff3333;
    --down-color: #33ff33;
    --flat-color: #ffff33;
    --icon-bg: #111111;
    --icon-color: #00ff00;
    --track-bg: #222222;
  }}
  body {{
    overflow-x: hidden;
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg-dark);
    color: var(--text-primary);
    min-height: 100vh;
    padding: 40px 20px;
    display: flex;
    justify-content: center;
  }}
  .container {{
    overflow-x: hidden;
    max-width: 1400px;
    width: 100%;
  }}
  header {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin-bottom: 32px;
    gap: 12px;
    border-bottom: 1px solid var(--border-glow);
    padding-bottom: 24px;
    text-align: center;
  }}
  .brand {{
    font-size: 28px;
    font-weight: 800;
    letter-spacing: .02em;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .badge {{
    font-size: 11px;
    background: #4f46e5;
    color: #fff;
    padding: 3px 10px;
    border-radius: 30px;
    margin-left: 10px;
    font-weight: 600;
    letter-spacing: .05em;
  }}
  .ts {{
    font-size: 13px;
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
  }}
  .hero {{
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--fluid-gap);
    margin-bottom: var(--fluid-gap);
  }}
  .hero-card {{
    background: var(--card-bg);
    border: 1px solid var(--border-glow);
    border-radius: clamp(12px, 2vw, 20px);
    padding: var(--card-p);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    height: 100%;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
  }}
  .hc-label {{
    font-size: clamp(0.85rem, 1vw, 1.1rem);
    font-weight: 700;
    color: var(--text-secondary);
    letter-spacing: .08em;
    margin-bottom: clamp(0.5rem, 1vw, 1rem);
  }}
  .hc-val {{
    font-size: clamp(1.8rem, 3vw, 2.8rem);
    font-weight: 800;
  }}
  .dir-up {{ color: var(--up-color) !important; }}
  .dir-down {{ color: var(--down-color) !important; }}
  .dir-flat {{ color: var(--flat-color) !important; }}
  
  .hc-sub {{
    margin-top: auto;
    font-size: clamp(0.75rem, 0.9vw, 1rem);
    color: var(--text-secondary);
    padding-top: clamp(0.5rem, 1vw, 1rem);
    border-top: 1px solid var(--border-glow);
    width: 100%;
  }}
  .conf-wrap {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }}
  @keyframes draw {{
    from {{ stroke-dashoffset: {conf_circ:.1f}; }}
    to {{ stroke-dashoffset: {conf_off:.1f}; }}
  }}
  .conf-circle-fill {{
    animation: draw 1.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }}
  .metrics-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--fluid-gap);
    margin-bottom: var(--fluid-gap);
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border-glow);
    border-radius: clamp(12px, 2vw, 20px);
    padding: clamp(12px, 3vw, 16px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    text-align: center;
    height: 100%;
    min-height: 220px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
    transition: transform 0.2s, box-shadow 0.2s;
    cursor: pointer;
  }}
  .card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.06);
  }}
  .c-icon {{
    width: var(--icon-sz);
    aspect-ratio: 1;
    background: var(--icon-bg);
    color: var(--icon-color);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: clamp(1rem, 1.5vw, 1.25rem);
    flex-shrink: 0;
  }}
  .c-icon svg {{
    width: 50%;
    height: 50%;
  }}
  .c-info {{
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
    flex-grow: 1;
  }}
  .c-label {{
    font-size: clamp(0.85rem, 1vw, 1.1rem);
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
    line-height: 1.3;
  }}
  .c-val {{
    font-size: clamp(1.5rem, 2.5vw, 2.2rem);
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
  }}
  .c-chg {{
    font-size: clamp(0.85rem, 1vw, 1.1rem);
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: clamp(1rem, 1.5vw, 1.5rem);
  }}
  .c-date {{
    margin-top: auto;
    width: 100%;
    font-size: clamp(0.7rem, 0.85vw, 0.9rem);
    color: var(--text-secondary);
    padding-top: clamp(0.5rem, 1vw, 1rem);
    border-top: 1px solid var(--border-glow);
  }}
  .c-error {{
    font-size: clamp(0.85rem, 1vw, 1.1rem);
    color: #ef4444;
    font-weight: 700;
  }}
  .c-error-text {{
    color: #ef4444;
  }}
  .night-banner {{
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(168, 85, 247, 0.08));
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: clamp(12px, 2vw, 20px);
    padding: clamp(12px, 3vw, 16px);
    min-height: 220px;
    margin-bottom: var(--fluid-gap);
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(99, 102, 241, 0.02);
    transition: transform 0.2s;
  }}
  .night-banner:hover {{
    transform: translateY(-2px);
  }}
  @media(max-width: 600px) {{
    .night-banner {{
      flex-direction: column;
      text-align: center;
      gap: 1rem;
    }}
  }}
  .pos {{ color: var(--up-color); }}
  .neg {{ color: var(--down-color); }}
  
  .ai-panel {{
    background: var(--card-bg);
    border: 1px solid var(--border-glow);
    border-radius: 20px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
  }}
  .ai-head {{
    font-size: 13px;
    font-weight: 700;
    color: var(--text-secondary);
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 16px;
  }}
  .prob-row {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 12px;
  }}
  .prob-label {{
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
    width: 85px;
    flex-shrink: 0;
  }}
  .prob-track {{
    flex: 1;
    height: 8px;
    background: var(--track-bg);
    border-radius: 99px;
    overflow: hidden;
  }}
  @keyframes expand {{
    from {{ width: 0%; }}
  }}
  .prob-fill {{
    height: 100%;
    border-radius: 99px;
    animation: expand 1.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }}
  .prob-pct {{
    font-size: 14px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
    width: 45px;
    text-align: right;
  }}
  
  /* AI 分析摘要虛線框 */
  .ai-summary-box {{
    border: 1.5px dashed #818cf8;
    background: rgba(129, 140, 248, 0.02);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 24px;
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }}
  .ai-summary-icon {{
    font-size: 20px;
    color: #4f46e5;
    flex-shrink: 0;
    margin-top: 2px;
  }}
  .ai-summary-text {{
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.7;
  }}
  
  .factors {{
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--fluid-gap);
    margin-bottom: var(--fluid-gap);
  }}
  .factor-box {{
    background: var(--card-bg);
    border: 1px solid var(--border-glow);
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
  }}
  .factor-title {{
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 16px;
    letter-spacing: .08em;
    text-transform: uppercase;
  }}
  .factor-box ul {{
    list-style: none;
    font-size: 14px;
    color: var(--text-primary);
    line-height: 2;
  }}
  .factor-box li {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 8px;
  }}
  .bullet-icon {{
    color: var(--primary-color);
    flex-shrink: 0;
  }}
  
  .notion-btn {{
    display: inline-block;
    width: 100%;
    text-align: center;
    margin-top: 8px;
    padding: 14px;
    background: #4f46e5;
    color: #fff;
    font-size: 14px;
    font-weight: 600;
    border-radius: 12px;
    text-decoration: none;
    box-shadow: 0 4px 15px rgba(79, 70, 229, 0.2);
    transition: all 0.3s;
  }}
  .notion-btn:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.35);
    background: #4338ca;
  }}
  
  @media(max-width:768px){{
    .hero {{ grid-template-columns: 1fr; }}
    .grid3 {{ grid-template-columns: 1fr 1fr; }}
    .factors {{ grid-template-columns: 1fr; }}
    body {{ padding: 20px 10px; }}
  }}
  
  /* --- PDF 下載按鈕樣式 --- */
  .btn-pdf {{
    background: #4f46e5;
    border: none;
    border-radius: 30px;
    color: #fff;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(79, 70, 229, 0.2);
  }}
  .btn-pdf:hover {{
    background: #4338ca;
    box-shadow: 0 6px 16px rgba(79, 70, 229, 0.35);
    transform: translateY(-2px);
  }}
  .btn-pdf:active {{
    transform: translateY(0);
  }}
  
  /* --- 主題選擇器樣式 --- */
  .theme-selector {{
    display: inline-flex;
    background: var(--track-bg);
    border: 1px solid var(--border-glow);
    padding: 3px;
    border-radius: 30px;
    gap: 2px;
  }}
  .theme-btn {{
    background: transparent;
    border: none;
    border-radius: 30px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }}
  .theme-btn:hover {{
    color: var(--text-primary);
  }}
  .theme-btn.active {{
    background: var(--card-bg);
    color: var(--primary-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }}
  
  /* --- Modal 彈窗樣式 --- */
  .modal-overlay {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(5px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
  }}
  .modal-overlay.active {{
    opacity: 1;
    pointer-events: auto;
  }}
  .modal-content {{
    background: #ffffff;
    border: 1px solid var(--border-glow);
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
    border-radius: 24px;
    width: 90%;
    max-width: 580px;
    padding: 28px;
    position: relative;
    transform: scale(0.9);
    transition: transform 0.3s ease;
    max-height: 85vh;
    overflow-y: auto;
  }}
  .modal-overlay.active .modal-content {{
    transform: scale(1);
  }}
  .modal-close {{
    position: absolute;
    top: 20px;
    right: 20px;
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 28px;
    cursor: pointer;
    line-height: 1;
    transition: color 0.2s;
  }}
  .modal-close:hover {{
    color: var(--text-primary);
  }}
  .modal-title {{
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 20px;
    border-bottom: 1px solid var(--border-glow);
    padding-bottom: 12px;
  }}
  .modal-body {{
    font-size: 14px;
    line-height: 1.6;
    color: var(--text-primary);
  }}
  .formula-box {{
    background: #f1f5f9;
    padding: 12px 16px;
    border-radius: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: #4f46e5;
    margin-bottom: 16px;
    border: 1px solid var(--border-glow);
  }}
  .score-item {{
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #f1f5f9;
  }}
  .score-val {{
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
  }}
  .score-val.pos {{ color: var(--up-color); }}
  .score-val.neg {{ color: var(--down-color); }}
  .score-val.neu {{ color: var(--text-secondary); }}
  
  .disclosure-table {{
    background: var(--card-bg);
    border: 1px solid var(--border-glow);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
  }}
  .footer-bar {{
    background: #4f46e5;
    color: #ffffff;
    border-radius: 12px;
    padding: 14px 20px;
    font-size: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 30px;
    flex-wrap: wrap;
    gap: 12px;
  }}

  /* --- Mobile First Media Queries --- */
  @media(min-width: 769px) {{
    .metrics-grid, .factors {{
      grid-template-columns: repeat(2, 1fr);
    }}
    .hero {{
      grid-template-columns: repeat(2, 1fr);
    }}
    .card, .hero-card, .night-banner {{
      min-height: auto;
      padding: var(--card-p);
    }}
  }}

  @media(min-width: 1025px) {{
    .metrics-grid {{
      grid-template-columns: repeat(auto-fit, minmax(clamp(260px, 22vw, 320px), 1fr));
    }}
    .hero {{
      grid-template-columns: 1.4fr 1fr 1.2fr 1.2fr 1fr;
    }}
    .factors {{
      grid-template-columns: repeat(2, 1fr);
    }}
  }}

</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <span class="brand">台股開盤預測儀表板<span class="badge">AI 分析</span></span>
    </div>
    <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
      <div class="theme-selector">
        <button class="theme-btn active" data-t="light" onclick="setTheme('light')">🌞 Light</button>
        <button class="theme-btn" data-t="dark" onclick="setTheme('dark')">🌙 Dark</button>
        <button class="theme-btn" data-t="purple" onclick="setTheme('purple')">🟣 Purple</button>
        <button class="theme-btn" data-t="terminal" onclick="setTheme('terminal')">⚫ Terminal</button>
      </div>
      <span class="ts">更新時間：{ts} (基於 {provider} 分析)</span>
      <button class="btn-pdf" onclick="downloadPDF()">
        <svg style="width: 14px; height: 14px; fill: currentColor;" viewBox="0 0 24 24">
          <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
        </svg>
        下載 PDF
      </button>
    </div>
  </header>

  <!-- Hero Row -->
  <div class="hero">
    <div class="hero-card">
      <div class="hc-label">開盤預測</div>
      <div class="hc-val {dir_cls}">{dir_arrow} {open_pred}</div>
      <div class="hc-sub">預測區間<br>{pt_low:+d} ～ {pt_high:+d} 點區間</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">趨勢結構</div>
      <div class="hc-val" style="color:var(--text-primary);">{sentiment}</div>
      <div class="hc-sub">{today}</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">盤勢強度</div>
      <div class="hc-val" style="color:{strat_col};">{strategy}</div>
      <div class="hc-sub">多空分數<br>{total_score}/100</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">盤中波動率</div>
      <div class="hc-val" style="color:{cont_col};">{continuation}</div>
      <div class="hc-sub">預期波動<br>{vol_text}</div>
    </div>
    <div class="hero-card conf-wrap" style="cursor: pointer;" onclick="openConfidenceModal()">
      <div class="hc-label" style="align-self: flex-start;">分析信心分數</div>
      <svg width="110" height="110" viewBox="0 0 120 120" style="margin:5px auto;display:block">
        <circle cx="60" cy="60" r="54" fill="none" stroke="rgba(79, 70, 229, 0.06)" stroke-width="8"/>
        <circle class="conf-circle-fill" cx="60" cy="60" r="54" fill="none"
          stroke="#4f46e5"
          stroke-width="8" stroke-linecap="round"
          stroke-dasharray="{conf_circ:.1f}"
          stroke-dashoffset="{conf_circ:.1f}"
          transform="rotate(-90 60 60)"/>
        <text x="60" y="58" text-anchor="middle" fill="#4f46e5" font-size="24" font-weight="800" font-family="'Outfit', sans-serif">{confidence}</text>
        <text x="60" y="76" text-anchor="middle" fill="var(--text-secondary)" font-size="11" font-weight="500">/ 100</text>
      </svg>
    </div>
  </div>

  <!-- Night Futures Banner -->
  <div class="night-banner" onclick="window.open('https://www.wantgoo.com/futures/wtxp&', '_blank')" title="{txf_tip}">
    <div>
      <div class="c-label" style="color: #4f46e5; letter-spacing: .08em; text-transform: uppercase;">台指期盤後收盤 (TXFPM1)</div>
      <div class="c-val">{txf_val}</div>
      {txf_sub}
    </div>
    <div style="text-align: right;">
      <div class="c-label" style="letter-spacing: .08em;">漲跌幅度</div>
      <div class="c-chg">{chg(txf_pm)}</div>
    </div>
  </div>

  <!-- Market Data Grid -->
  <div class="metrics-grid">
    <!-- TSM -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/TSM', '_blank')" title="{adr_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          <path d="M2 12h20"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">台積電 ADR (TSM)</div>
        <div class="c-val">{adr_val}</div>
        <div class="c-chg">{chg(adr)}</div>
        {adr_sub}
      </div>
    </div>
    
    <!-- SOX -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/%5ESOX', '_blank')" title="{sox_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="4" width="16" height="16" rx="2"/>
          <path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">SOX 費城半導體</div>
        <div class="c-val">{sox_val}</div>
        <div class="c-chg">{chg(sox)}</div>
        {sox_sub}
      </div>
    </div>
    
    <!-- NQ -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/%5EIXIC', '_blank')" title="{nq_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">NASDAQ 指數</div>
        <div class="c-val">{nq_val}</div>
        <div class="c-chg">{chg(nq)}</div>
        {nq_sub}
      </div>
    </div>
    
    <!-- 外資現貨買賣超 -->
    <div class="card" onclick="window.open('https://www.wantgoo.com/stock/institutional-investors/three-trade-for-trading-amount', '_blank')" title="{foreign_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">外資現貨買賣超</div>
        <div class="c-val" style="color: {'#ef4444' if (twse_inst.get('foreign') or 0)>=0 else '#10b981'}">{foreign_val}</div>
        <div class="c-chg" style="color: var(--text-secondary)">大盤籌碼</div>
        {foreign_sub}
      </div>
    </div>
    
    <!-- 投信現貨買賣超 -->
    <div class="card" onclick="window.open('https://www.wantgoo.com/stock/institutional-investors/three-trade-for-trading-amount', '_blank')" title="{trust_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">投信現貨買賣超</div>
        <div class="c-val" style="color: {'#ef4444' if (twse_inst.get('trust') or 0)>=0 else '#10b981'}">{trust_val}</div>
        <div class="c-chg" style="color: var(--text-secondary)">大盤籌碼</div>
        {trust_sub}
      </div>
    </div>
    
    <!-- 自營商買賣超 -->
    <div class="card" onclick="window.open('https://www.wantgoo.com/stock/institutional-investors/three-trade-for-trading-amount', '_blank')" title="{dealer_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">自營商買賣超</div>
        <div class="c-val" style="color: {'#ef4444' if (twse_inst.get('dealer') or 0)>=0 else '#10b981'}">{dealer_val}</div>
        <div class="c-chg" style="color: var(--text-secondary)">大盤籌碼</div>
        {dealer_sub}
      </div>
    </div>
    
    <!-- 融資餘額增減 -->
    <div class="card" onclick="window.open('https://www.wantgoo.com/stock/margin-trading/market-price/taiex', '_blank')" title="{margin_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">融資餘額增減</div>
        <div class="c-val" style="color: {'#10b981' if (twse_margin.get('diff') or 0)>=0 else '#ef4444'}">{margin_val}</div>
        <div class="c-chg" style="color: var(--text-secondary)">信用浮額變動</div>
        {margin_sub}
      </div>
    </div>
    
    <!-- 黃金期貨 -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/GC=F', '_blank')" title="{gold_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">黃金期貨 (GC=F)</div>
        <div class="c-val">{gold_val}</div>
        <div class="c-chg">{chg(gold)}</div>
        {gold_sub}
      </div>
    </div>
    
    <!-- 美原油期貨 -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/CL=F', '_blank')" title="{crude_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">美原油期貨 (CL=F)</div>
        <div class="c-val">{crude_val}</div>
        <div class="c-chg">{chg(crude)}</div>
        {crude_sub}
      </div>
    </div>
    
    <!-- VIX 恐慌指數 -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/%5EVIX', '_blank')" title="{vix_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">VIX 恐慌指數</div>
        <div class="c-val">{vix_val}</div>
        <div class="c-chg">{chg(vix)}</div>
        {vix_sub}
      </div>
    </div>
    
    <!-- USD/TWD 匯率 -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/TWD=X', '_blank')" title="{usd_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 1l4 4-4 4"/><path d="M3 5h18M7 23l-4-4 4-4"/><path d="M21 19H3"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">USD/TWD 匯率</div>
        <div class="c-val">{usd_val}</div>
        <div class="c-chg">{chg(usd)}</div>
        {usd_sub}
      </div>
    </div>
    
    <!-- 美 10Y 債殖利率 -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/%5ETNX', '_blank')" title="{tnx_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="7.5" cy="7.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/><line x1="21" y1="3" x2="3" y2="21"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">美 10Y 債殖利率</div>
        <div class="c-val">{tnx_val}%</div>
        <div class="c-chg">{chg(tnx)}</div>
        {tnx_sub}
      </div>
    </div>
    
    <!-- 美元匯率均線趨勢 -->
    <div class="card" onclick="window.open('https://finance.yahoo.com/quote/TWD=X', '_blank')" title="{usd_trend_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">美元匯率均線趨勢</div>
        <div class="c-val" style="font-size: 15px; color: {'#10b981' if (usd.get('price') or 0) > (usd.get('ma20') or 0) else '#ef4444'}; font-weight:700;">
          {usd_trend_val_str}
        </div>
        <div class="c-chg" style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-secondary)">
          20MA: {usd.get('ma20') or 0.0:.3f}
        </div>
        {usd_trend_sub_str}
      </div>
    </div>
    
    <!-- 外資台指期未平倉口數 -->
    <div class="card" onclick="window.open('https://www.taifex.com.tw/cht/3/callsAndPutsDate', '_blank')" title="{oi_foreign_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="8" r="4"/><path d="M18 21v-2a4 4 0 0 0-4-4H10a4 4 0 0 0-4 4v2"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">外資台指期未平倉口數</div>
        <div class="c-val" style="color: {'#ef4444' if (oi.get('foreign_net_oi') or 0)>0 else '#10b981'}">{oi_foreign_val}</div>
        {oi_foreign_sub}
      </div>
    </div>
    
    <!-- 台股期貨未平倉(口) -->
    <div class="card" onclick="window.open('https://www.wantgoo.com/stock/institutional-investors/three-trade-for-trading-amount', '_blank')" title="{oi_total_tip}">
      <div class="c-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
      </div>
      <div class="c-info">
        <div class="c-label">台股期貨未平倉(口)</div>
        <div class="c-val" style="color: {'#ef4444' if (twse_inst.get('total') or 0)>=0 else '#10b981'}">{oi_total_val}</div>
        {oi_total_sub}
      </div>
    </div>
  </div>

  <!-- AI Prediction Panel -->
  <div class="ai-panel">
    <div class="ai-head">盤勢機率分布</div>
    {prob_items}
  </div>

  <!-- AI 分析摘要虛線框 -->
  <div class="ai-summary-box">
    <div class="ai-summary-icon">💡</div>
    <div class="ai-summary-text">
      <strong>AI 分析摘要：</strong>{summary}
    </div>
  </div>

  <!-- Drivers & Risks -->
  <div class="factors">
    <div class="factor-box">
      <div class="factor-title">關鍵驅動因子</div>
      <ul>{drivers_html}</ul>
    </div>
    <div class="factor-box">
      <div class="factor-title">主要風險因子</div>
      <ul>{risks_html}</ul>
    </div>
  </div>

  {notion_link}

  <!-- 數據來源明細披露區 -->
  <div class="disclosure-table" style="margin-top: 30px;">
    <div class="c-label" style="color: #4f46e5; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 16px;">🔍 儀表板數據來源與採集清單 (Data Disclosure)</div>
    <div style="overflow-x: auto;">
      <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; color: var(--text-secondary);">
        <thead>
          <tr style="border-bottom: 1px solid #e2e8f0; color: var(--text-primary);">
            <th style="padding: 8px 12px;">指標名稱</th>
            <th style="padding: 8px 12px;">採集來源</th>
            <th style="padding: 8px 12px;">API 代碼 / 採集途徑</th>
            <th style="padding: 8px 12px;">計價單位 / 格式</th>
          </tr>
        </thead>
        <tbody>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">加權指數 (TAIEX)</td>
            <td style="padding: 8px 12px;">台灣證券交易所 (TWSE) 官方</td>
            <td style="padding: 8px 12px;">OpenAPI (FMTQIK)</td>
            <td style="padding: 8px 12px;">新台幣點數</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">台指期夜盤 (TXFPM1)</td>
            <td style="padding: 8px 12px;">FinMind 金融數據 API</td>
            <td style="padding: 8px 12px;">TaiwanFuturesDaily (after_market)</td>
            <td style="padding: 8px 12px;">指數點數</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">台積電 ADR (TSM)</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (TSM)</td>
            <td style="padding: 8px 12px;">美元 (USD)</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">費城半導體 (SOX)</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (^SOX)</td>
            <td style="padding: 8px 12px;">指數點數</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">NASDAQ 指數</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (^IXIC)</td>
            <td style="padding: 8px 12px;">指數點數</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">VIX 恐慌指數</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (^VIX)</td>
            <td style="padding: 8px 12px;">指數點數</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">外資及投信現貨買賣超</td>
            <td style="padding: 8px 12px;">台灣證券交易所 (TWSE) 官方</td>
            <td style="padding: 8px 12px;">OpenAPI (BFI82U)</td>
            <td style="padding: 8px 12px;">新台幣金額 (億元)</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">全市場信用融資餘額</td>
            <td style="padding: 8px 12px;">台灣證券交易所 (TWSE) 官方</td>
            <td style="padding: 8px 12px;">OpenAPI (MI_MARGN) 彙總</td>
            <td style="padding: 8px 12px;">融資張數增減</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">黃金與布蘭特原油期貨</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (GC=F / CL=F)</td>
            <td style="padding: 8px 12px;">美元 (USD) / 漲跌幅</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">USD/TWD 匯率 (及20MA)</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (TWD=X) 30日歷史</td>
            <td style="padding: 8px 12px;">台幣/美元價格 (20MA趨勢)</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">三大法人期指部位</td>
            <td style="padding: 8px 12px;">台灣期貨交易所 (TAIFEX) 官方</td>
            <td style="padding: 8px 12px;">每日結算 CSV (TXF 合約)</td>
            <td style="padding: 8px 12px;">多空未平倉淨口數</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 8px 12px; color: var(--text-primary);">美 10Y 公債殖利率</td>
            <td style="padding: 8px 12px;">Yahoo Finance 國際市場</td>
            <td style="padding: 8px 12px;">yfinance API (^TNX)</td>
            <td style="padding: 8px 12px;">年化百分比 %</td>
          </tr>
          <tr>
            <td style="padding: 8px 12px; color: var(--text-primary);">美元指數 / 利率</td>
            <td style="padding: 8px 12px;">聖路易斯聯邦準備銀行 (FRED)</td>
            <td style="padding: 8px 12px;">FRED API (DTWEXBGS / FEDFUNDS)</td>
            <td style="padding: 8px 12px;">指數點數 / 百分比</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 藍色底部 Footer 條 -->
  <div class="footer-bar">
    <span>本報告由 AI 量化引擎自動生成，僅供參考，投資請審慎評估。</span>
    <span>資料來源：TWSE · TAIFEX · Nasdaq · CBOE · Yahoo Finance · FRED</span>
  </div>
</div>

<!-- 信心分數計算明細 Modal -->
<div id="confidence-modal" class="modal-overlay" onclick="closeConfidenceModal(event)">
  <div class="modal-content" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeConfidenceModal(event)">&times;</button>
    <div class="modal-title">🛡️ 分析信心分數計算明細</div>
    <div class="modal-body">
      <p style="margin-bottom: 12px; color: var(--text-secondary);">信心分數是由本機四層量化決策引擎所計算出來的，其核心公式如下：</p>
      <div class="formula-box" style="text-align: center;">
        Confidence = min(max(int(|Score| * 1.5 * Factor + 45), 30), 98)
      </div>
      
      <div style="margin-bottom: 20px; border-bottom: 1px solid var(--border-glow); padding-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; font-weight: 600; font-size: 15px; margin-bottom: 8px;">
          <span>當前多空總分 (Score)</span>
          <span style="font-family: 'JetBrains Mono', monospace;" id="modal-score">0.0</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-weight: 600; font-size: 15px; margin-bottom: 8px;">
          <span>一致性修正係數 (Factor)</span>
          <span style="font-family: 'JetBrains Mono', monospace;" id="modal-factor">1.0 (6/6 相符)</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 16px; color: #4f46e5; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-glow);">
          <span>最終信心分數</span>
          <span id="modal-confidence">0</span>
        </div>
      </div>

      <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 12px;">📊 10 大分項量化評估得分明細：</div>
      <div id="modal-scores-list" style="margin-bottom: 10px;">
        <!-- JS 動態填入 -->
      </div>
    </div>
  </div>
</div>

<script>
// 儲存 Python 傳入的信心分數計算明細
const confDetails = {conf_details_json};

function openConfidenceModal() {{
  const scoreEl = document.getElementById('modal-score');
  const factorEl = document.getElementById('modal-factor');
  const confidenceEl = document.getElementById('modal-confidence');
  const listEl = document.getElementById('modal-scores-list');
  
  if (!confDetails || !confDetails.components) return;
  
  // 填入核心數據
  scoreEl.textContent = (confDetails.total_score >= 0 ? '+' : '') + confDetails.total_score;
  scoreEl.className = confDetails.total_score >= 0 ? 'score-val pos' : 'score-val neg';
  
  const signals = confDetails.matching_signals || 0;
  const totalSigs = confDetails.total_signals || 6;
  const factor = confDetails.consistency_factor || 1.0;
  factorEl.textContent = factor.toFixed(1) + ' (' + signals + '/' + totalSigs + ' 指標同向修正)';
  
  const confidenceVal = Math.min(Math.max(Math.floor(Math.abs(confDetails.total_score) * 1.5 * factor + 45), 30), 98);
  confidenceEl.textContent = confidenceVal + ' %';
  
  // 渲染分項清單
  const translateMap = {{
    "txf_pm_score": "台指期夜盤昨收趨勢",
    "tech_score": "科技權值 ADR & 費半強度",
    "oi_score": "外資台指期未平倉口數",
    "inst_score": "外資現貨當日買賣超",
    "usd_score": "美元匯率均線趨勢 (20MA)",
    "tnx_score": "美債 10Y 殖利率變動率",
    "vix_score": "VIX 全球恐慌情緒指標",
    "commodity_score": "黃金 & 原油避險商品強度",
    "trust_score": "本土投信現貨買賣超",
    "margin_score": "本土信用融資餘額增減"
  }};
  
  listEl.innerHTML = '';
  for (const [key, val] of Object.entries(confDetails.components)) {{
    const label = translateMap[key] || key;
    const valClass = val > 0 ? 'score-val pos' : (val < 0 ? 'score-val neg' : 'score-val neu');
    const valStr = val > 0 ? '+' + val : val;
    
    const row = document.createElement('div');
    row.className = 'score-item';
    row.innerHTML = `
      <span style="color: var(--text-secondary);">${{label}}</span>
      <span class="${{valClass}}">${{valStr}} 分</span>
    `;
    listEl.appendChild(row);
  }}
  
  document.getElementById('confidence-modal').classList.add('active');
}}

function closeConfidenceModal(e) {{
  document.getElementById('confidence-modal').classList.remove('active');
}}

function setTheme(name) {{
  document.body.setAttribute('data-theme', name);
  localStorage.setItem('df_theme', name);
  document.querySelectorAll('.theme-btn').forEach(btn => {{
    if (btn.getAttribute('data-t') === name) {{
      btn.classList.add('active');
    }} else {{
      btn.classList.remove('active');
    }}
  }});
}}

// 初始化載入偏好主題
(function() {{
  const saved = localStorage.getItem('df_theme') || 'light';
  setTheme(saved);
}})();

function downloadPDF() {{
  const btn = document.querySelector('.btn-pdf');
  if (!btn) return;
  
  btn.disabled = true;
  const originalHTML = btn.innerHTML;
  btn.innerHTML = '⏳ 產生中...';
  
  const theme = document.body.getAttribute('data-theme') || 'light';
  const bgColors = {{
    'light': '#f8fafc',
    'dark': '#0c101b',
    'purple': '#070a13',
    'terminal': '#000000'
  }};
  const bgColor = bgColors[theme] || '#f8fafc';
  
  const element = document.querySelector('.container');
  const opt = {{
    margin:       [10, 10, 10, 10],
    filename:     '台股開盤預測儀表板_' + new Date().toISOString().split('T')[0] + '.pdf',
    image:        {{ type: 'jpeg', quality: 0.98 }},
    html2canvas:  {{ scale: 2, useCORS: true, logging: false, backgroundColor: bgColor }},
    jsPDF:        {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
  }};
  
  html2pdf().set(opt).from(element).output('datauristring').then(function(pdfDataUri) {{
    const base64 = pdfDataUri.split(',')[1];
    window.parent.postMessage({{
      type: 'download_pdf',
      base64: base64,
      filename: opt.filename
    }}, '*');
    btn.innerHTML = originalHTML;
    btn.disabled = false;
  }}).catch(function(err) {{
    console.error("PDF 產生失敗：", err);
    alert("PDF 匯出失敗，請重試。錯誤資訊：" + err.message);
    btn.innerHTML = originalHTML;
    btn.disabled = false;
  }});
}}
</script>
</body>
</html>"""


def save_html(market_data: dict, ai_result: dict, notion_url: str | None = None) -> str:
    """生成並儲存 HTML，回傳檔案路徑"""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    html = build_html(market_data, ai_result, notion_url)
    path = os.path.join(OUTPUT_DIR, "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"Dashboard 已輸出：{path}")
    return path
