"""
agents/news_agent.py
新聞輿情 Agent — 對新聞事件進行情緒計分
"""

import logging

log = logging.getLogger(__name__)

class NewsAgent:
    """新聞與輿情分析"""
    def __init__(self):
        pass

    def analyze_news(self, news_list: list) -> float:
        """對新聞列表進行簡要情緒打分（預設 0.0，後續可擴展 NLP 情感分析）"""
        if not news_list:
            return 0.0
        
        log.info(f"[NewsAgent] 分析 {len(news_list)} 則新聞情緒...")
        # 這裡僅進行示意性分析，保持目前商業邏輯不變
        return 0.0
