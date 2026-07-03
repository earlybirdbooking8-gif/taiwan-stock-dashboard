"""
core/pipeline.py
主執行引擎 — 串接數據、CEO Agent 派工、Notion 與 HTML 渲染，支援排程與手動執行
"""

import json
import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config.settings import OUTPUT_DIR, LOG_DIR, TIMEZONE, REPORT_JSON, SCHEDULE_TIME, AI_PROVIDER
from agents.ceo_agent import CEOAgent
from agents.data_agent import DataAgent
from agents.strategy_agent import StrategyAgent
from agents.review_agent import ReviewAgent
from services.notion_service import write_report
from ui.dashboard_renderer import save_html

log = logging.getLogger("pipeline")


def run_pipeline() -> dict:
    """執行完整流程：CEO Agent 調度任務鏈 (派工) -> Notion -> Dashboard"""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    status_file = os.path.join(ROOT, "outputs", "predict_status.json")
    os.makedirs(os.path.join(ROOT, "outputs"), exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as sf:
        json.dump({"status": "running", "pid": os.getpid(), "start_time": datetime.now().isoformat()}, sf, ensure_ascii=False)

    try:
        log.info("╔══════════════════════════════════════╗")
        log.info("║  台股開盤預測 Multi-Agent Pipeline    ║")
        log.info("╚══════════════════════════════════════╝")

        # 1. 實例化與註冊 Agent
        ceo = CEOAgent()
        data_agent = DataAgent()
        strategy_agent = StrategyAgent()
        review_agent = ReviewAgent()
        
        ceo.register_agent("data_agent", data_agent)
        ceo.register_agent("strategy_agent", strategy_agent)
        ceo.register_agent("review_agent", review_agent)

        # 2. 建立任務佇列並定義依賴
        # [Task 1] Data Agent - 優先級 100
        ceo.add_task(
            "data_task",
            run_fn=data_agent.run,
            priority=100
        )

        # [Task 2] Strategy Agent - 優先級 80 (依賴 data_task)
        ceo.add_task(
            "strategy_task",
            run_fn=lambda: strategy_agent.run_local_model(
                ceo.tasks["data_task"].output.get("Output", {})
            ),
            priority=80,
            dependencies=["data_task"]
        )

        # [Task 3] Review Agent - 優先級 60 (依賴 data_task)
        def run_review_or_fallback():
            market_data = ceo.tasks["data_task"].output.get("Output", {})
            provider = AI_PROVIDER.lower()
            has_key = review_agent.check_key_available(provider)
            
            if has_key:
                try:
                    return review_agent.run_ai_analysis(market_data)
                except Exception as e:
                    log.warning(f"AI review analysis failed ({e}), fallback to local strategy...")
            
            # Fallback 策略：呼叫本機四層量化規則
            local_res = strategy_agent.run_local_model(market_data)
            local_res["Goal"] = "AI審查未啟用，退回本機四層量化預測"
            local_res["Output"]["ai_provider"] = "Wayne Intelligence Engine"
            return local_res

        ceo.add_task(
            "review_task",
            run_fn=run_review_or_fallback,
            priority=60,
            dependencies=["data_task"]
        )

        # 3. 執行 CEO Agent 派工調度
        ceo_report = ceo.run_tasks()
        
        # 4. 提取整合好的數據與決策結果 (來自 CEO Agent 的 Output)
        market_data = ceo_report["Output"]["market_data"]
        ai_result   = ceo_report["Output"]["ai_result"]

        # 5. 合併存 JSON（備份用）
        report = {
            "market_data": market_data,
            "ai_result"  : ai_result,
            "ceo_report" : ceo_report # 備份完整的 CEO 任務調度報告
        }
        with open(REPORT_JSON, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        log.info(f"報告已存：{REPORT_JSON}")

        # 6. 寫入 Notion
        notion_url = write_report(market_data, ai_result)

        # 7. 產生 Dashboard HTML
        html_path = save_html(market_data, ai_result, notion_url)

        log.info("╔══════════════════════════════════════╗")
        log.info(f"║  完成！預測：{ai_result.get('open_direction','—'):<18}     ║")
        log.info(f"║  信心分數：{ai_result.get('confidence', 0):<20}   ║")
        log.info(f"║  Dashboard：{html_path:<19}  ║")
        log.info("╚══════════════════════════════════════╝")

        with open(status_file, "w", encoding="utf-8") as sf:
            json.dump({"status": "success", "pid": os.getpid(), "end_time": datetime.now().isoformat()}, sf, ensure_ascii=False)

        return report
    except Exception as e:
        with open(status_file, "w", encoding="utf-8") as sf:
            json.dump({"status": "failed", "pid": os.getpid(), "error": str(e)}, sf, ensure_ascii=False)
        raise e


def run_scheduler():
    """每天定時自動執行"""
    try:
        import schedule
        import time
    except ImportError:
        log.error("請先安裝 schedule：pip install schedule")
        sys.exit(1)

    TZ = ZoneInfo(TIMEZONE)

    def job():
        now = datetime.now(TZ)
        if now.weekday() < 5:
            log.info(f"排程觸發 [{now.strftime('%Y-%m-%d %H:%M')}]")
            try:
                run_pipeline()
            except Exception as e:
                log.error(f"Pipeline 執行失敗：{e}", exc_info=True)
        else:
            log.info(f"假日 ({now.strftime('%A')})，跳過")

    schedule.every().day.at(SCHEDULE_TIME).do(job)
    log.info(f"排程已啟動，每天 {SCHEDULE_TIME} ({TIMEZONE}) 執行")

    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="台股開盤預測 Multi-Agent Pipeline")
    parser.add_argument("--schedule", action="store_true", help="啟動排程模式")
    parser.add_argument("--dry-run",  action="store_true", help="使用假數據測試")
    args = parser.parse_args()

    if args.dry_run:
        log.info("🔧 Dry-run 模式：載入假數據")
        if os.path.exists(REPORT_JSON):
            with open(REPORT_JSON, encoding="utf-8") as f:
                last = json.load(f)
            market_data = last.get("market_data", {})
            ai_result   = last.get("ai_result", {})
            ai_result["ai_provider"] = "dry-run"
        else:
            market_data = {
                "collected_at": datetime.now().isoformat(),
                "taiex": {"taiex_close": 22890.5, "date": "2026-06-26"},
                "taifex_oi": {
                    "foreign_net_oi": 15420,
                    "dealer_net_oi": -2400,
                    "trust_net_oi": 3100,
                    "total_inst_oi": 16120
                },
                "txf_pm": {"price": 22915.0, "prev": 22850.0, "chg_pct": 0.28, "chg_abs": 65.0, "date": "2026-06-26"},
                "tsm_adr": {"price": 178.50, "prev": 175.20, "chg_pct": 1.88, "chg_abs": 3.3},
                "sox": {"price": 5420.5, "prev": 5350.2, "chg_pct": 1.31, "chg_abs": 70.3},
                "nq_futures": {"price": 19850.0, "prev": 19720.0, "chg_pct": 0.66, "chg_abs": 130.0},
                "vix": {"price": 12.85, "prev": 13.20, "chg_pct": -2.65, "chg_abs": -0.35},
                "usdtwd": {"price": 32.251, "prev": 32.321, "chg_pct": -0.22, "chg_abs": -0.07},
                "tnx": {"price": 4.251, "prev": 4.285, "chg_pct": -0.79, "chg_abs": -0.034},
                "fred": {
                    "dxy": {"value": 104.5, "prev": 104.8, "chg_abs": -0.3},
                    "fed_rate": {"value": 5.25, "prev": 5.25, "chg_abs": 0.0}
                },
                "news": [
                    {"title": "台積電 2 奈米訂單超預期，法人看好明年展望", "source": "經濟日報", "publishedAt": "2026-06-26T10:00:00Z"},
                    {"title": "費半指數強彈，AI 晶片股領漲美股行情", "source": "Yahoo Finance", "publishedAt": "2026-06-26T22:30:00Z"}
                ]
            }
            ai_result   = {
                "open_direction" : "高開（測試）",
                "direction_code" : "high",
                "point_range_low": 80, "point_range_high": 130,
                "confidence"     : 72,
                "scenario_probs" : {"開高走高":45,"開高走低":20,"開低走高":20,"開低走低":15},
                "key_drivers"    : ["台積電 ADR +2.8%","SOX +1.4%","外資期貨多單增加"],
                "risk_factors"   : ["VIX 可能反彈","美元走強壓力"],
                "summary_zh"     : "Dry-run 測試模式。實際執行時將由 AI 提供分析。",
                "sentiment"      : "偏多",
                "ai_provider"    : "dry-run",
            }
        html_path = save_html(market_data, ai_result)
        log.info(f"Dry-run 完成，Dashboard：{html_path}")
    elif args.schedule:
        run_scheduler()
    else:
        run_pipeline()
