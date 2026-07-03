"""
ai_analysis/analyzer.py
將蒐集到的市場數據送給 AI，產出結構化開盤預測
支援 Claude / OpenAI / Gemini（由 settings.py 切換）
"""

import json
import logging
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import AI_PROVIDER, ANTHROPIC_KEY, OPENAI_KEY, GEMINI_KEY

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Prompt 建構
# ─────────────────────────────────────────────────────────
def build_prompt(data: dict) -> str:
    """把 collector 輸出轉成 AI 可讀的分析請求"""

    def fmt(d, key, unit="", pct_key="chg_pct", abs_key="chg_abs"):
        if d is None:
            return "N/A"
        v = d.get(key) or d.get("price") or d.get("value")
        c = d.get(pct_key) or d.get(abs_key)
        if v is None:
            return "N/A"
        chg = f" ({c:+.2f}{'%' if pct_key in d else ''})" if c is not None else ""
        return f"{v:,.4g}{unit}{chg}"

    taiex   = data.get("taiex") or {}
    oi      = data.get("taifex_oi") or {}
    adr     = data.get("tsm_adr") or {}
    sox     = data.get("sox") or {}
    nq      = data.get("nq_futures") or {}
    vix     = data.get("vix") or {}
    usdtwd  = data.get("usdtwd") or {}
    tnx     = data.get("tnx") or {}
    fred    = data.get("fred") or {}
    news    = data.get("news") or []

    news_block = "\n".join(
        f"  [{n.get('source','')}] {n.get('title','')}"
        for n in news[:8]
    ) or "  （無新聞數據）"

    prompt = f"""你是台灣股市量化分析師，請根據以下最新市場數據，預測下一個台灣加權指數開盤方向。

━━ 台灣市場 ━━
• 加權指數（TAIEX）：{taiex.get('taiex_close', 'N/A')}
• 外資台指期淨口數：{oi.get('foreign_net_oi', 'N/A')} 口
• 自營商台指期淨口數：{oi.get('dealer_net_oi', 'N/A')} 口
• 投信台指期淨口數：{oi.get('trust_net_oi', 'N/A')} 口
• 三大法人合計淨口數：{oi.get('total_inst_oi', 'N/A')} 口

━━ 美股 / 科技 ━━
• 台積電 ADR (TSM)：{fmt(adr, 'price', ' USD')}
• 費城半導體 (SOX)：{fmt(sox, 'price')}
• NASDAQ 指數：{fmt(nq, 'price')}
• VIX 恐慌指數：{fmt(vix, 'price')}

━━ 總體 / 匯率 ━━
• USD/TWD：{fmt(usdtwd, 'price')}
• 美 10 年期殖利率（TNX）：{fmt(tnx, 'price', '%')}
• 聯邦基金利率（FRED）：{(fred.get('fed_rate') or {}).get('value', 'N/A')}%
• 美元指數（DXY）：{(fred.get('dxy') or {}).get('value', 'N/A')}

━━ 近期重要新聞 ━━
{news_block}

━━ 分析要求 ━━
請綜合以上數據，輸出「純 JSON 格式」（不含任何 markdown backtick 或前置文字）：

{{
  "open_direction"    : "高開 / 平開 / 低開",
  "direction_code"    : "high / flat / low",
  "point_range_low"   : <整數，預估開盤漲跌點下限，負數代表跌>,
  "point_range_high"  : <整數，預估開盤漲跌點上限>,
  "confidence"        : <0~100 整數>,
  "scenario_probs"    : {{
    "開高走高": <0~100 整數>,
    "開高走低": <0~100 整數>,
    "開低走高": <0~100 整數>,
    "開低走低": <0~100 整數>
  }},
  "key_drivers"       : ["最重要因子1", "最重要因子2", "最重要因子3"],
  "risk_factors"      : ["主要風險1", "主要風險2"],
  "summary_zh"        : "150字以內繁體中文分析摘要",
  "sentiment"         : "偏多 / 中性 / 偏空"
}}

注意：scenario_probs 四項加總必須等於 100。"""
    return prompt


# ─────────────────────────────────────────────────────────
# AI 後端（可互換）
# ─────────────────────────────────────────────────────────
def call_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg = client.messages.create(
        model      = "claude-opus-4-6",
        max_tokens = 1500,
        messages   = [{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model    = "gpt-4o",
        messages = [
            {"role": "system", "content": "你是台灣股市量化分析師，只輸出 JSON。"},
            {"role": "user",   "content": prompt},
        ],
        max_tokens      = 1500,
        response_format = {"type": "json_object"},
    )
    return resp.choices[0].message.content


def call_gemini(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-1.5-pro")
    resp  = model.generate_content(prompt)
    return resp.text


AI_BACKENDS = {
    "claude" : call_claude,
    "openai" : call_openai,
    "gemini" : call_gemini,
}


# ─────────────────────────────────────────────────────────
# 解析 JSON
# ─────────────────────────────────────────────────────────
def parse_ai_response(raw: str) -> dict:
    """從 AI 輸出萃取 JSON（容錯處理）"""
    text = raw.strip()
    # 去掉 markdown fence
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break
    # 找第一個 { 到最後一個 }
    s = text.find("{")
    e = text.rfind("}")
    if s >= 0 and e > s:
        text = text[s:e+1]
    return json.loads(text)


# ─────────────────────────────────────────────────────────
# 主函式
# ─────────────────────────────────────────────────────────
def analyze(market_data: dict) -> dict:
    """送出分析請求，回傳結構化預測結果"""
    provider = AI_PROVIDER.lower()
    backend  = AI_BACKENDS.get(provider)
    if not backend:
        raise ValueError(f"未知 AI_PROVIDER：{provider}（可選 claude/openai/gemini）")

    log.info(f"═══ 呼叫 AI 分析 [{provider}] ═══")
    
    # 檢查對應的金鑰是否填寫，若無則主動退回 Mock 分析
    key_map = {
        "claude": ANTHROPIC_KEY,
        "openai": OPENAI_KEY,
        "gemini": GEMINI_KEY
    }
    current_key = key_map.get(provider, "")
    
    try:
        if not current_key or "xxxxxxxx" in current_key:
            raise ValueError("AI API 金鑰未設定或為預設值")
            
        prompt   = build_prompt(market_data)
        raw      = backend(prompt)
        log.debug(f"AI 原始回應：\n{raw}")
        result   = parse_ai_response(raw)
    except Exception as e:
        log.warning(f"AI 分析未啟動 ({e})，啟動本機動態量化規則分析引擎。")
        
        # 1. 取得真實數據
        taiex = market_data.get("taiex") or {}
        taiex_close = taiex.get("taiex_close") or 22000.0
        
        oi = market_data.get("taifex_oi") or {}
        foreign_oi = oi.get("foreign_net_oi") or 0
        
        txf_pm = market_data.get("txf_pm") or {}
        txf_pm_price = txf_pm.get("price")
        
        twse_inst = market_data.get("twse_inst") or {}
        foreign_net = twse_inst.get("foreign") or 0.0
        trust_net = twse_inst.get("trust") or 0.0
        
        twse_margin = market_data.get("twse_margin") or {}
        margin_diff = twse_margin.get("diff") or 0
        
        adr = market_data.get("tsm_adr") or {}
        sox = market_data.get("sox") or {}
        nq = market_data.get("nq_futures") or {}
        vix = market_data.get("vix") or {}
        usd = market_data.get("usdtwd") or {}
        tnx = market_data.get("tnx") or {}
        gold = market_data.get("gold") or {}
        crude = market_data.get("crude") or {}
        
        adr_chg = adr.get("chg_pct") or 0.0
        sox_chg = sox.get("chg_pct") or 0.0
        nq_chg = nq.get("chg_pct") or 0.0
        vix_price = vix.get("price") or 20.0
        usd_price = usd.get("price")
        usd_ma20 = usd.get("ma20")
        tnx_chg = tnx.get("chg_pct") or 0.0
        gold_chg = gold.get("chg_pct") or 0.0
        crude_chg = crude.get("chg_pct") or 0.0
        
        # 2. 計算各層多空分數與動態權重
        
        # VIX 避險計分 (第三層之一，但影響動態權重)
        vix_score = 0
        if vix_price < 15.0:
            vix_score = 10
        elif 15.0 <= vix_price < 18.0:
            vix_score = 5
        elif 18.0 <= vix_price < 22.0:
            vix_score = 0
        elif 22.0 <= vix_price < 28.0:
            vix_score = -10
        else:
            vix_score = -20
            
        # VIX 動態調節閥
        is_vix_high = (vix_price > 25.0)
        
        # ── 第一層：全球與隔夜市場 (40%) ──
        # 台指期夜盤 (合併富台指)
        txf_pm_score = 0.0
        if txf_pm_price is not None:
            # 夜盤點數相對於日盤大盤收盤價的漲跌幅
            txf_pm_chg = (txf_pm_price - taiex_close) / taiex_close * 100
            # 權重 30%，滿分 30
            txf_pm_score = max(min(txf_pm_chg * 15, 30), -30)
        else:
            txf_pm_chg = 0.0
            
        # 科技群 (Tech Group) 權重 10% (若 VIX 高則調降為 5%)
        # 成交量確認機制
        tech_items = [
            ("TSM", adr_chg, adr.get("volume", 0), adr.get("vol_ma20", 0)),
            ("SOX", sox_chg, sox.get("volume", 0), sox.get("vol_ma20", 0)),
            ("NQ", nq_chg, nq.get("volume", 0), nq.get("vol_ma20", 0))
        ]
        # 找出絕對值最大者 (代表當天最強的科技群驅動力)
        best_name, best_chg, best_vol, best_vma20 = max(tech_items, key=lambda x: abs(x[1]))
        
        vol_factor = 1.0
        if best_vol > 0 and best_vma20 > 0:
            if best_vol > best_vma20 * 1.2:
                vol_factor = 1.2
            elif best_vol < best_vma20 * 0.8:
                vol_factor = 0.8
                
        # 基礎科技分數 10 分
        tech_score = max(min(best_chg * 5 * vol_factor, 10), -10)
        if is_vix_high:
            tech_score *= 0.5 # 避險情緒高，科技股重要性調降 50%
            
        # ── 第二層：資金面與避險指標 (30%) ──
        # 外資期指 (10%)
        oi_score = 0.0
        if foreign_oi > 0:
            oi_score = 5.0
            if foreign_oi > 10000: oi_score = 10.0
        elif foreign_oi < 0:
            oi_score = -5.0
            if foreign_oi < -10000: oi_score = -10.0
            
        # 三大法人現貨 (10%)
        inst_score = 0.0
        if foreign_net > 0:
            inst_score = 5.0
            if foreign_net > 5e9: inst_score = 10.0
        elif foreign_net < 0:
            inst_score = -5.0
            if foreign_net < -5e9: inst_score = -10.0
            
        # 美元 MA 趨勢 (5% 或動態升至 7.5%)
        usd_weight = 7.5 if is_vix_high else 5.0
        usd_score = 0.0
        if usd_price is not None and usd_ma20 is not None:
            if usd_price > usd_ma20:
                usd_score = -usd_weight # 站上20MA，外資撤資
            else:
                usd_score = usd_weight
                
        # 美債殖利率 (5% 或動態升至 7.5%)
        tnx_weight = 7.5 if is_vix_high else 5.0
        tnx_score = max(min(-tnx_chg * 10, tnx_weight), -tnx_weight)
        
        # ── 第三層：全球風險情緒 (20%) ──
        # VIX 避險計分 (已算得 vix_score，滿分對應為 10%)
        vix_score_capped = max(min(vix_score, 10), -20)
        
        # 避險商品：黃金 & 原油 (10%)
        commodity_score = max(min(-(gold_chg + crude_chg) * 3.5, 10), -10)
        
        # ── 第四層：台股本土籌碼 (10%) ──
        # 投信現貨 (5%)
        trust_score = 0.0
        if trust_net > 0:
            trust_score = 3.0
            if trust_net > 2e9: trust_score = 5.0
        elif trust_net < 0:
            trust_score = -3.0
            if trust_net < -2e9: trust_score = -5.0
            
        # 融資張數增減 (5%)
        margin_score = max(min(-margin_diff / 1500.0, 5), -5) # 融資大增扣分，大減加分
        
        # ── 加總多空總分數 ──
        score = txf_pm_score + tech_score + oi_score + inst_score + usd_score + tnx_score + vix_score_capped + commodity_score + trust_score + margin_score
        
        # 3. 信心度的一致性修正
        # 定義 6 個核心多空指標的實時多空方向 (True 代表正向，False 代表負向)
        core_signals = [
            (txf_pm_chg > 0),
            (best_chg > 0),
            (foreign_oi > 0),
            (foreign_net > 0),
            (usd_price < usd_ma20 if usd_price and usd_ma20 else True),
            (vix_price < 22.0)
        ]
        
        is_trend_up = (score > 0)
        matching_signals = sum(1 for sig in core_signals if sig == is_trend_up)
        
        # 一致性係數
        if matching_signals == 6:
            consistency_factor = 1.0
        elif matching_signals == 5:
            consistency_factor = 0.9
        elif matching_signals == 4:
            consistency_factor = 0.8
        else:
            consistency_factor = 0.6
            
        confidence = min(max(int(abs(score) * 1.5 * consistency_factor + 45), 30), 98)
        
        # 動態打包信心分數計算細節，供 UI 卡片點擊 Modal 渲染使用
        confidence_details = {
            "formula": "min(max(int(abs(total_score) * 1.5 * consistency_factor + 45), 30), 98)",
            "total_score": round(score, 2),
            "consistency_factor": consistency_factor,
            "matching_signals": matching_signals,
            "total_signals": 6,
            "components": {
                "txf_pm_score": round(txf_pm_score, 2),     # 台指期夜盤
                "tech_score": round(tech_score, 2),         # 美股 ADR & 費半
                "oi_score": round(oi_score, 2),             # 外資期貨部位
                "inst_score": round(inst_score, 2),         # 外資現貨買賣超
                "usd_score": round(usd_score, 2),           # 美元趨勢
                "tnx_score": round(tnx_score, 2),           # 美債殖利率
                "vix_score": round(vix_score_capped, 2),    # VIX 恐慌指標
                "commodity_score": round(commodity_score, 2),# 避險商品 (黃金原油)
                "trust_score": round(trust_score, 2),       # 本土投信現貨
                "margin_score": round(margin_score, 2)      # 融資浮額增減
            }
        }
        
        # 4. 判定方向、延續率與策略
        if score >= 12.0:
            direction = "看多"
            code = "high"
            sentiment = "偏多"
            pt_low = max(20, int(score * 2.5))
            pt_high = min(280, int(score * 5.0))
            open_pred = "開高"
            
            # 延續率判定
            if foreign_net > 0 and foreign_oi > -5000 and trust_net > 0:
                continuation = "開高走高"
            elif margin_diff > 3000 or foreign_net < -2e9:
                continuation = "開高走低"
            else:
                continuation = "開高震盪"
                
            if score >= 25.0:
                strategy = "積極做多"
            else:
                strategy = "偏多操作"
                
            summary = f"全球科技權值股強彈（{best_name} {best_chg:+.2f}%），台指期夜盤同步上揚 {txf_pm_chg:+.2f}%，多頭共識一致性達 {matching_signals}/6。籌碼與資金面有利於多方，預估今日加權指數將「{open_pred}」，且盤中高機率呈現「{continuation}」走勢。AI金鑰未設定，此為本機四層量化規則引擎之決策結果。"
            
        elif score <= -12.0:
            direction = "看空"
            code = "low"
            sentiment = "偏空"
            pt_low = max(-280, int(score * 5.0))
            pt_high = min(-20, int(score * 2.5))
            open_pred = "開低"
            
            # 延續率判定
            if foreign_net < -5e9 and foreign_oi < -10000:
                continuation = "開低走低"
            elif trust_net > 2e9 and margin_diff < -2000:
                continuation = "開低走高"
            else:
                continuation = "開低震盪"
                
            if score <= -25.0:
                strategy = "積極放空"
            else:
                strategy = "偏空操作"
                
            summary = f"受國際半導體走弱及資金流出影響（{best_name} {best_chg:+.2f}%），外資籌碼持續站於空方，多空一致性比率為 {matching_signals}/6。預估今日加權指數將「{open_pred}」，盤中需慎防「{continuation}」走勢。AI金鑰未設定，此為本機四層量化規則引擎之決策結果。"
            
        else:
            direction = "中性"
            code = "flat"
            sentiment = "中性"
            pt_low = -35
            pt_high = 35
            open_pred = "平盤"
            continuation = "區間震盪"
            strategy = "觀望 / 區間操作"
            summary = f"美股主要指數呈窄幅震盪（NQ {nq_chg:+.2f}%），國際避險情緒指標平穩，台股本土多空資金力道互咬，一致性信號僅 {matching_signals}/6 呈現分裂。預計今日開盤變動幅度有限，大盤傾向「{open_pred}」開出，盤中呈「{continuation}」走勢。"

        # 四大情境機率之量化科學推算
        p_up_up = 25.0
        p_up_down = 25.0
        p_down_up = 25.0
        p_down_down = 25.0
        
        # 根據 score (大盤多空分數) 調整開高/開低權重，score 正值偏向開高
        open_bias = score * 0.8 # 最大調整約 ±40%
        
        # 根據籌碼與風險指標計算盤中走勢延續強度
        trend_score = 0.0
        try:
            foi_val = float(foreign_oi) if foreign_oi is not None else 0.0
            trend_score += (foi_val / 10000.0) * 2.0 # 外資期指部位 (最大約 ±4%)
        except Exception: pass
        
        try:
            adr_chg_val = float(best_chg) if best_chg is not None else 0.0
            trend_score += adr_chg_val * 1.0 # 科技股 ADR 變動強度 (最大約 ±8%)
        except Exception: pass
        
        try:
            margin_diff_val = float(margin_diff) if margin_diff is not None else 0.0
            trend_score += (-margin_diff_val / 2000.0) * 1.5 # 融資增減反向計分 (最大約 ±3%)
        except Exception: pass
        
        try:
            vix_val = float(vix_price) if vix_price is not None else 18.0
            trend_score += (18.0 - vix_val) * 0.8 # VIX 恐慌情緒 (最大約 ±4%)
        except Exception: pass

        try:
            txf_val = float(txf_pm_chg) if txf_pm_chg is not None else 0.0
            trend_score += txf_val * 1.5 # 夜盤漲跌幅強度 (最大約 ±6%)
        except Exception: pass
        
        try:
            usd_chg_val = float(usd_chg) if usd_chg is not None else 0.0
            trend_score += (-usd_chg_val * 10.0) # 匯率升貶強度 (台幣貶值扣分，最大約 ±5%)
        except Exception: pass
        
        try:
            tnx_chg_val = float(tnx_chg) if tnx_chg is not None else 0.0
            trend_score += (-tnx_chg_val * 8.0) # 美債殖利率變動 (殖利率跳升扣分，最大約 ±4%)
        except Exception: pass
        
        try:
            trust_val = float(trust_net) if trust_net is not None else 0.0
            trend_score += (trust_val / 1e9) * 1.0 # 投信現貨買賣超 (投信買超加分，最大約 ±3%)
        except Exception: pass
        
        close_bias = trend_score
        
        p_up_up = max(5.0, 25.0 + open_bias + close_bias)
        p_up_down = max(5.0, 25.0 + open_bias - close_bias)
        p_down_up = max(5.0, 25.0 - open_bias + close_bias)
        p_down_down = max(5.0, 25.0 - open_bias - close_bias)
        
        # 歸一化
        total_p = p_up_up + p_up_down + p_down_up + p_down_down
        p_up_up = int(round((p_up_up / total_p) * 100))
        p_up_down = int(round((p_up_down / total_p) * 100))
        p_down_up = int(round((p_down_up / total_p) * 100))
        p_down_down = 100 - (p_up_up + p_up_down + p_down_up)
        
        probs = {
            "開高走高": p_up_up,
            "開高走低": p_up_down,
            "開低走高": p_down_up,
            "開低走低": p_down_down
        }

        key_drivers = []
        risk_factors = []
        if best_chg > 0: key_drivers.append(f"{best_name} 走強 ({best_chg:+.2f}%)")
        else: risk_factors.append(f"{best_name} 走弱 ({best_chg:+.2f}%)")
        
        if txf_pm_chg > 0: key_drivers.append(f"台指期夜盤溢價 ({txf_pm_chg:+.2f}%)")
        else: risk_factors.append(f"台指期夜盤折價 ({txf_pm_chg:+.2f}%)")
        
        if foreign_oi is not None:
            if foreign_oi > -5000: key_drivers.append(f"外資期貨部位偏多 ({foreign_oi:+,d} 口)")
            else: risk_factors.append(f"外資期指空單高企 ({foreign_oi:+,d} 口)")
        
        if foreign_net is not None:
            if foreign_net > 0: key_drivers.append(f"外資現貨買超 ({foreign_net/1e8:,.1f} 億)")
            else: risk_factors.append(f"外資現貨賣超 ({foreign_net/1e8:,.1f} 億)")
        
        result = {
            "open_direction" : direction,
            "direction_code" : code,
            "point_range_low": pt_low,
            "point_range_high": pt_high,
            "confidence"     : confidence,
            "confidence_details": confidence_details,
            "scenario_probs" : probs,
            "key_drivers"    : key_drivers[:3],
            "risk_factors"   : risk_factors[:2],
            "summary_zh"     : summary,
            "sentiment"      : sentiment,
            "continuation"   : continuation,
            "strategy"       : strategy,
            "open_pred"      : open_pred,
            "raw_response"   : "Fallback mock response",
        }

    result["ai_provider"] = provider if "raw_response" not in result or result["raw_response"] != "Fallback mock response" else "Wayne (未配置金鑰)"
    result["prompt_len"]  = len(build_prompt(market_data))
    log.info(f"AI 預測：{result.get('open_direction')} | 信心：{result.get('confidence')}")
    return result
