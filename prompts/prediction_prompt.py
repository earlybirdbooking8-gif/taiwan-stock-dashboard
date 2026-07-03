"""
prompts/prediction_prompt.py
為 LLM 開盤分析生成結構化的 Prompt 模板
"""

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
請綜合以上數據，輸出「純 JSON 格式」（不含 any markdown backtick or 前置文字）：

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
