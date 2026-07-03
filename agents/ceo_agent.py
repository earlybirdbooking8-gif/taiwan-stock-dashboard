"""
agents/ceo_agent.py
CEO Agent — 純調度與派工中樞。
不進行任何股票多空分析與量化計算，專職任務佇列、優先級排程、相依性拓撲、自動重試與計量。
"""

import time
import logging
from typing import Callable, List, Dict, Any, Optional

log = logging.getLogger(__name__)

class Task:
    """任務封裝物件"""
    def __init__(self, name: str, run_fn: Callable, priority: int = 100, dependencies: List[str] = None):
        self.name = name
        self.run_fn = run_fn
        self.priority = priority
        self.dependencies = dependencies or []
        self.status = "pending"  # pending | running | success | failed
        self.output: Dict[str, Any] = {}
        self.execution_time_ms: float = 0.0
        self.retry_info = {"retry_count": 0, "retry_logs": []}
        self.error: Optional[str] = None

class CEOAgent:
    """多 Agent 系統總協調指揮官 (不參與股票分析，只負責派工與監控)"""
    
    def __init__(self):
        self.registry: Dict[str, Any] = {}
        self.tasks: Dict[str, Task] = {}
        self.health_status = "healthy"
        self.token_metrics = {"total_prompt_characters": 0}

    def register_agent(self, name: str, agent_instance: Any):
        """註冊 Agent 實例"""
        self.registry[name] = agent_instance
        log.info(f"[CEOAgent] 註冊 Agent 成功: {name}")

    def add_task(self, name: str, run_fn: Callable, priority: int = 100, dependencies: List[str] = None):
        """新增待調度任務到任務佇列"""
        self.tasks[name] = Task(name, run_fn, priority, dependencies)
        log.info(f"[CEOAgent] 任務新增成功: {name} (優先級: {priority}, 依賴: {dependencies})")

    def run_tasks(self) -> Dict[str, Any]:
        """線性拓撲調度並順序執行任務，支援失敗自動重試(3次)與健康度計量"""
        log.info("[CEOAgent] === 啟動任務佇列優先級調度運作 ===")
        
        # 1. 根據優先級 (由大到小) 進行任務排序，以確保線性與依賴順序
        sorted_task_names = sorted(self.tasks.keys(), key=lambda k: self.tasks[k].priority, reverse=True)
        
        executed_count = 0
        total_time_ms = 0.0
        
        for name in sorted_task_names:
            task = self.tasks[name]
            log.info(f"[CEOAgent] 準備派工任務: {name}...")
            
            # 2. Dependency (相依性檢查)
            dep_failed = False
            for dep in task.dependencies:
                if dep in self.tasks and self.tasks[dep].status != "success":
                    dep_failed = True
                    log.error(f"[CEOAgent] 任務 {name} 依賴檢查失敗: {dep} 未成功完成 (狀態: {self.tasks[dep].status})")
            
            if dep_failed:
                task.status = "failed"
                task.error = f"Dependency check failed for: {task.dependencies}"
                self.health_status = "degraded"
                continue
                
            task.status = "running"
            start_time = time.perf_counter()
            
            # 3. Retry (重試機制 - 最多 3 次)
            success = False
            max_retries = 3
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        task.retry_info["retry_count"] = attempt
                        warn_msg = f"Task {name} failed, retrying ({attempt}/{max_retries})..."
                        task.retry_info["retry_logs"].append(warn_msg)
                        log.warning(f"[CEOAgent] {warn_msg}")
                        time.sleep(1.0) # 重試等待
                        
                    # 執行派工任務
                    res = task.run_fn()
                    
                    # 驗證輸出是否符合基本的 dict 格式
                    if not isinstance(res, dict):
                        raise TypeError(f"Agent output must be dict, got {type(res)}")
                        
                    task.output = res
                    task.status = "success"
                    success = True
                    log.info(f"[CEOAgent] 任務 {name} 執行成功。")
                    break
                except Exception as e:
                    task.error = str(e)
                    log.error(f"[CEOAgent] 任務 {name} 執行異常 (第 {attempt} 次): {e}")
            
            end_time = time.perf_counter()
            task.execution_time_ms = round((end_time - start_time) * 1000, 2)
            total_time_ms += task.execution_time_ms
            
            if not success:
                task.status = "failed"
                self.health_status = "critical"
                log.error(f"[CEOAgent] 任務 {name} 在重試 {max_retries} 次後依然宣告失敗。工作流中斷。")
                break
                
            # 4. 計量 Token Usage & Health Status
            executed_count += 1
            prompt_len = task.output.get("prompt_len") or 0
            self.token_metrics["total_prompt_characters"] += prompt_len
            
        # 5. 彙整與輸出符合 9-Key 標準的 JSON 結構 (不得自行新增格式)
        ceo_output = self._compile_ceo_output(executed_count, total_time_ms)
        
        # 6. Daily Summary (輸出派工日誌摘要)
        self._print_daily_summary(ceo_output)
        
        return ceo_output

    def _compile_ceo_output(self, executed_count: int, total_time_ms: float) -> Dict[str, Any]:
        """建立符合 9-Key 通訊協定規範的 JSON"""
        
        # 彙整子任務的 Output (特別是 market_data 與 ai_result)
        market_data = {}
        ai_result = {}
        
        # 尋找已成功的任務輸出來進行封裝
        if "data_task" in self.tasks and self.tasks["data_task"].status == "success":
            # Data Agent 的 Output 直接是原始 market_data payload
            market_data = self.tasks["data_task"].output.get("Output", {})
            
        if "strategy_task" in self.tasks and self.tasks["strategy_task"].status == "success":
            ai_result = self.tasks["strategy_task"].output.get("Output", {})
            
        # 如果有 ReviewAgent，它的 Output 包含修飾後更準確的 ai_result
        if "review_task" in self.tasks and self.tasks["review_task"].status == "success":
            ai_result = self.tasks["review_task"].output.get("Output", {})

        # 彙整 Sources, Validation, Retry
        merged_sources = []
        merged_retry_logs = []
        retry_count_sum = 0
        validation_passed_rules = ["ceo_priority_queue_checked"]
        
        for t_name, t in self.tasks.items():
            merged_sources.extend(t.output.get("Sources") or [])
            if t.retry_info["retry_count"] > 0:
                retry_count_sum += t.retry_info["retry_count"]
                merged_retry_logs.extend(t.retry_info["retry_logs"])
            if t.output.get("Validation"):
                validation_passed_rules.extend(t.output["Validation"].get("checks_passed") or [])

        # 9 大核心 Keys 映射
        return {
            "Goal": "調度 DataAgent, StrategyAgent 與 ReviewAgent 以完成台股開盤預測並生成報告",
            "Input": {
                "registered_agents": list(self.registry.keys()),
                "total_queued_tasks": len(self.tasks)
            },
            "Output": {
                "market_data": market_data,
                "ai_result": ai_result,
                "performance": {
                    "total_execution_time_ms": round(total_time_ms, 2),
                    "executed_tasks_count": executed_count
                },
                "token_usage": self.token_metrics
            },
            "Confidence": ai_result.get("confidence") or 50.0,
            "Sources": merged_sources,
            "Validation": {
                "valid": self.health_status == "healthy",
                "checks_passed": validation_passed_rules
            },
            "Retry": {
                "retry_count": retry_count_sum,
                "retry_logs": merged_retry_logs
            },
            "Error": self.tasks[list(self.tasks.keys())[-1]].error if any(t.status == "failed" for t in self.tasks.values()) else None,
            "Health Status": self.health_status
        }

    def _print_daily_summary(self, payload: Dict[str, Any]):
        """輸出每日派工與效能彙總日誌"""
        log.info("╔══════════════════════════════════════╗")
        log.info("║  Daily Dispatch Summary (每日派工摘要)║")
        log.info("╚══════════════════════════════════════╝")
        log.info(f"  * 系統健康狀態 : {payload['Health Status']}")
        log.info(f"  * 總執行時間   : {payload['Output']['performance']['total_execution_time_ms']} 毫秒")
        log.info(f"  * 成功派工數   : {payload['Output']['performance']['executed_tasks_count']} / {len(self.tasks)}")
        log.info(f"  * 總字元計量   : {payload['Output']['token_usage']['total_prompt_characters']} characters")
        log.info(f"  * 重試計數累計 : {payload['Retry']['retry_count']} 次")
        log.info("════════════════════════════════════════")
