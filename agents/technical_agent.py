"""
agents/technical_agent.py
技術分析 Agent — 對美股及台積電 ADR 行情均線與成交量放量進行評估
"""

import logging

log = logging.getLogger(__name__)

class TechnicalAgent:
    """美股與台股技術指標分析"""
    def __init__(self):
        pass

    def evaluate_vol_confirmation(self, current_vol: float, vol_ma20: float) -> float:
        """計算成交量加成係數 (商業邏輯保持不變)"""
        vol_factor = 1.0
        if current_vol > 0 and vol_ma20 > 0:
            if current_vol > vol_ma20 * 1.2:
                vol_factor = 1.2
            elif current_vol < vol_ma20 * 0.8:
                vol_factor = 0.8
        log.info(f"[TechnicalAgent] 成交量確認加成係數：{vol_factor}")
        return vol_factor
