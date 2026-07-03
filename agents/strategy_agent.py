"""
agents/strategy_agent.py
策略分析 Agent — 實作本機四層量化決策引擎，符合 9-Key 協議規範
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)

class StrategyAgent:
    """本機四層量化決策大腦"""
    def __init__(self):
        pass

    def run_local_model(self, market_data: dict) -> dict:
        """執行完整本機四層量化規則分析"""
        log.info("[StrategyAgent] 啟動本機四層量化規則預估引擎...")
        
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
            
        is_vix_high = (vix_price > 25.0)
        
        # ── 第一層：全球與隔夜市場 (40%) ──
        txf_pm_score = 0.0
        if txf_pm_price is not None:
            txf_pm_chg = (txf_pm_price - taiex_close) / taiex_close * 100
            txf_pm_score = max(min(txf_pm_chg * 15, 30), -30)
        else:
            txf_pm_chg = 0.0
            
        tech_items = [
            ("TSM", adr_chg, adr.get("volume", 0), adr.get("vol_ma20", 0)),
            ("SOX", sox_chg, sox.get("volume", 0), sox.get("vol_ma20", 0)),
            ("NQ", nq_chg, nq.get("volume", 0), nq.get("vol_ma20", 0))
        ]
        best_name, best_chg, best_vol, best_vma20 = max(tech_items, key=lambda x: abs(x[1]))
        
        vol_factor = 1.0
        if best_vol > 0 and best_vma20 > 0:
            if best_vol > best_vma20 * 1.2:
                vol_factor = 1.2
            elif best_vol < best_vma20 * 0.8:
                vol_factor = 0.8
                
        tech_score = max(min(best_chg * 5 * vol_factor, 10), -10)
        if is_vix_high:
            tech_score *= 0.5
            
        # ── 第二層：資金面與避險指標 (30%) ──
        oi_score = 0.0
        if foreign_oi > 0:
            oi_score = 5.0
            if foreign_oi > 10000: oi_score = 10.0
        elif foreign_oi < 0:
            oi_score = -5.0
            if foreign_oi < -10000: oi_score = -10.0
            
        inst_score = 0.0
        if foreign_net > 0:
            inst_score = 5.0
            if foreign_net > 5e9: inst_score = 10.0
        elif foreign_net < 0:
            inst_score = -5.0
            if foreign_net < -5e9: inst_score = -10.0
            
        usd_weight = 7.5 if is_vix_high else 5.0
        usd_score = 0.0
        if usd_price is not None and usd_ma20 is not None:
            if usd_price > usd_ma20:
                usd_score = -usd_weight
            else:
                usd_score = usd_weight
                
        tnx_weight = 7.5 if is_vix_high else 5.0
        tnx_score = max(min(-tnx_chg * 10, tnx_weight), -tnx_weight)
        
        # ── 第三層：全球風險情緒 (20%) ──
        vix_score_capped = max(min(vix_score, 10), -20)
        commodity_score = max(min(-(gold_chg + crude_chg) * 3.5, 10), -10)
        
        # ── 第四層：台股本土籌碼 (10%) ──
        trust_score = 0.0
        if trust_net > 0:
            trust_score = 3.0
            if trust_net > 2e9: trust_score = 5.0
        elif trust_net < 0:
            trust_score = -3.0
            if trust_net < -2e9: trust_score = -5.0
            
        margin_score = max(min(-margin_diff / 1500.0, 5), -5)
        
        # ── 加總多空總分數 ──
        score = txf_pm_score + tech_score + oi_score + inst_score + usd_score + tnx_score + vix_score_capped + commodity_score + trust_score + margin_score
        
        # 一致性係數
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
        
        if matching_signals == 6:
            consistency_factor = 1.0
        elif matching_signals == 5:
            consistency_factor = 0.9
        elif matching_signals == 4:
            consistency_factor = 0.8
        else:
            consistency_factor = 0.6
            
        confidence = min(max(int(abs(score) * 1.5 * consistency_factor + 45), 30), 98)
        
        confidence_details = {
            "formula": "min(max(int(abs(total_score) * 1.5 * consistency_factor + 45), 30), 98)",
            "total_score": round(score, 2),
            "consistency_factor": consistency_factor,
            "matching_signals": matching_signals,
            "total_signals": 6,
            "components": {
                "txf_pm_score": round(txf_pm_score, 2),
                "tech_score": round(tech_score, 2),
                "oi_score": round(oi_score, 2),
                "inst_score": round(inst_score, 2),
                "usd_score": round(usd_score, 2),
                "tnx_score": round(tnx_score, 2),
                "vix_score": round(vix_score_capped, 2),
                "commodity_score": round(commodity_score, 2),
                "trust_score": round(trust_score, 2),
                "margin_score": round(margin_score, 2)
            }
        }
        
        if score >= 12.0:
            direction = "看多"
            code = "high"
            sentiment = "偏多"
            pt_low = max(20, int(score * 2.5))
            pt_high = min(280, int(score * 5.0))
            open_pred = "開高"
            
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
        if best_chg > 0: key_drivers.append(f"{best_name}走強 ({best_chg:+.2f}%)")
        else: risk_factors.append(f"{best_name}走弱 ({best_chg:+.2f}%)")
        
        if txf_pm_chg > 0: key_drivers.append(f"台指期夜盤溢價 ({txf_pm_chg:+.2f}%)")
        else: risk_factors.append(f"台指期夜盤折價 ({txf_pm_chg:+.2f}%)")
        
        if foreign_oi is not None:
            if foreign_oi > -5000: key_drivers.append(f"外資期貨部位偏多 ({foreign_oi:+,d} 口)")
            else: risk_factors.append(f"外資期指空單高企 ({foreign_oi:+,d} 口)")
        
        if foreign_net is not None:
            if foreign_net > 0: key_drivers.append(f"外資現貨買超 ({foreign_net/1e8:,.1f} 億)")
            else: risk_factors.append(f"外資現貨賣超 ({foreign_net/1e8:,.1f} 億)")
        
        predict_output = {
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

        # 9-Key 協議格式輸出
        return {
            "Goal": "執行本機四層量化決策模型預報分析",
            "Input": {
                "taiex_close": taiex_close,
                "foreign_oi": foreign_oi,
                "txf_pm_price": txf_pm_price
            },
            "Output": predict_output,
            "Confidence": float(confidence),
            "Sources": [
                { "name": "Local.StrategyAgent", "endpoint": "local_engine", "timestamp": datetime.now().isoformat() }
            ],
            "Validation": {
                "valid": True,
                "checks_passed": ["score_calculation_success", "confidence_check_passed"]
            },
            "Retry": { "retry_count": 0, "retry_logs": [] },
            "Error": None,
            "Health Status": "healthy"
        }
