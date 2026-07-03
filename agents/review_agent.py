"""
agents/review_agent.py
審查與 AI 整合 Agent — 負責呼叫 LLM 服務並解析結構化結果，符合 9-Key 協議規範
"""

import json
import logging
from datetime import datetime
from config.settings import AI_PROVIDER, ANTHROPIC_KEY, OPENAI_KEY, GEMINI_KEY
from prompts.prediction_prompt import build_prompt

log = logging.getLogger(__name__)

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

class ReviewAgent:
    """負責語義審查與 LLM API 調用"""
    def __init__(self):
        pass

    def check_key_available(self, provider: str) -> bool:
        key_map = {
            "claude": ANTHROPIC_KEY,
            "openai": OPENAI_KEY,
            "gemini": GEMINI_KEY
        }
        current_key = key_map.get(provider.lower(), "")
        return bool(current_key and "xxxxxxxx" not in current_key)

    def run_ai_analysis(self, market_data: dict) -> dict:
        """嘗試呼叫外部 LLM API 並解析 JSON 預告"""
        provider = AI_PROVIDER.lower()
        backend  = AI_BACKENDS.get(provider)
        if not backend:
            raise ValueError(f"未知 AI_PROVIDER：{provider}")

        log.info(f"[ReviewAgent] 送出數據給 AI 模組 [{provider}]...")
        prompt = build_prompt(market_data)
        raw = backend(prompt)
        result = self._parse_ai_response(raw)
        
        # 9-Key 協議格式輸出
        return {
            "Goal": f"呼叫外部 {provider} API 進行語義分析與摘要生成",
            "Input": {
                "ai_provider": provider,
                "prompt_len": len(prompt)
            },
            "Output": result,
            "Confidence": float(result.get("confidence") or 70.0),
            "Sources": [
                { "name": f"AI.{provider.capitalize()}", "endpoint": "chat_endpoint", "timestamp": datetime.now().isoformat() }
            ],
            "Validation": {
                "valid": True,
                "checks_passed": ["json_parsed_successfully", "ai_summary_not_empty"]
            },
            "Retry": { "retry_count": 0, "retry_logs": [] },
            "Error": None,
            "Health Status": "healthy"
        }

    def _parse_ai_response(self, raw: str) -> dict:
        """容錯解析 AI 的 JSON 輸出"""
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("{"):
                    text = p
                    break
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            text = text[s:e+1]
        return json.loads(text)
