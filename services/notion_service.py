"""
services/notion_service.py
將每日預測報告寫入 Notion Database
每次執行新增一筆頁面（每日一筆）
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import NOTION_TOKEN, NOTION_DATABASE_ID, TIMEZONE

log = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization"  : f"Bearer {NOTION_TOKEN}",
        "Notion-Version" : "2022-06-28",
        "Content-Type"   : "application/json",
    }


def _color_for_direction(code: str) -> str:
    return {"high": "red", "low": "green", "flat": "yellow"}.get(code, "gray")


def write_report(market_data: dict, ai_result: dict) -> str | None:
    """
    在 Notion DB 新增一筆每日報告頁面
    回傳新建頁面的 URL（成功）或 None（失敗）
    """
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        log.warning("Notion 未設定（NOTION_TOKEN / NOTION_DATABASE_ID），跳過")
        return None

    import requests

    TW    = ZoneInfo(TIMEZONE)
    today = datetime.now(TW).strftime("%Y-%m-%d")
    ts    = datetime.now(TW).strftime("%Y-%m-%d %H:%M")

    direction    = ai_result.get("direction_code", "flat")
    open_dir     = ai_result.get("open_direction", "—")
    pt_low       = ai_result.get("point_range_low", 0)
    pt_high      = ai_result.get("point_range_high", 0)
    confidence   = ai_result.get("confidence", 0)
    sentiment    = ai_result.get("sentiment", "中性")
    summary      = ai_result.get("summary_zh", "")
    key_drivers  = ai_result.get("key_drivers", [])
    risk_factors = ai_result.get("risk_factors", [])
    probs        = ai_result.get("scenario_probs", {})

    # TAIFEX
    oi      = market_data.get("taifex_oi") or {}
    adr     = market_data.get("tsm_adr") or {}
    sox_d   = market_data.get("sox") or {}
    vix_d   = market_data.get("vix") or {}
    usd_d   = market_data.get("usdtwd") or {}

    page = {
        "parent"    : {"database_id": NOTION_DATABASE_ID},
        "icon"      : {"emoji": "📈" if direction == "high" else "📉" if direction == "low" else "➡️"},
        "properties": {
            "日期"          : {"title": [{"text": {"content": today}}]},
            "開盤方向"      : {"select": {"name": open_dir,  "color": _color_for_direction(direction)}},
            "點數區間"      : {"rich_text": [{"text": {"content": f"{pt_low:+d} ～ {pt_high:+d} 點"}}]},
            "信心分數"      : {"number": confidence},
            "盤勢情緒"      : {"select": {"name": sentiment}},
            "TSM ADR 漲跌"  : {"number": adr.get("chg_pct")},
            "SOX 漲跌"      : {"number": sox_d.get("chg_pct")},
            "VIX"           : {"number": vix_d.get("price")},
            "USD/TWD"       : {"number": usd_d.get("price")},
            "外資淨口數"    : {"number": oi.get("foreign_net_oi")},
            "開高走高機率"  : {"number": probs.get("開高走高")},
            "開低走低機率"  : {"number": probs.get("開低走低")},
            "AI 提供者"     : {"select": {"name": ai_result.get("ai_provider", "—")}},
        },
        "children": _build_blocks(summary, key_drivers, risk_factors, probs, ts),
    }

    try:
        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(),
            json=page,
            timeout=15
        )
        if resp.status_code == 200:
            url = resp.json().get("url", "")
            log.info(f"Notion 報告已寫入：{url}")
            return url
        else:
            log.error(f"Notion 寫入失敗 [{resp.status_code}]：{resp.text}")
            return None
    except Exception as e:
        log.error(f"Notion 寫入異常：{e}")
        return None


def _build_blocks(summary, drivers, risks, probs, ts) -> list:
    """建立 Notion 頁面內容（callout + 段落）"""
    blocks = [
        _callout("🤖 AI 分析摘要", summary, "blue"),
        _heading("📊 盤勢機率分布"),
        _paragraph("\n".join(
            f"{'🟢' if '走高' in k else '🔴'} {k}：{v}%"
            for k, v in probs.items()
        )),
        _heading("🔑 關鍵驅動因子"),
        _bulleted(drivers),
        _heading("⚠️ 主要風險"),
        _bulleted(risks),
        _divider(),
        _paragraph(f"_資料更新時間：{ts}_"),
    ]
    return [b for b in blocks if b]


def _callout(title, text, color="blue") -> dict:
    return {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"{title}\n\n{text}"}}],
            "color"    : f"{color}_background",
        }
    }


def _heading(text) -> dict:
    return {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}
    }


def _paragraph(text) -> dict:
    return {
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}
    }


def _bulleted(items: list) -> dict:
    if not items:
        return _paragraph("（無）")
    children = [
        {"object": "block", "type": "bulleted_list_item",
         "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": str(i)}}]}}
        for i in items
    ]
    # Notion API 不支援 batch bulleted block，只能各別送，這裡回傳第一個並附子項
    return children[0] if len(children) == 1 else {
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": "\n".join(f"• {i}" for i in items)}}]}
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}
