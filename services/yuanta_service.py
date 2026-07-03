"""
元大證券 YuantaSparkAPI 封裝服務層
初始化、登入、回呼管理
"""
from __future__ import annotations
import os, sys, time, json, threading, uuid, platform
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import YUANTA_DLL_DIR

# ---------- 延遲載入：真正使用時才載入 DLL ----------
_YUANTA_LOADED = False
_YUANTA_MODULES = {}

def _load_yuanta_dll():
    """載入元大 SparkAPI .NET DLL（只執行一次）"""
    global _YUANTA_LOADED, _YUANTA_MODULES
    if _YUANTA_LOADED:
        return

    from pythonnet import load
    load("coreclr")

    import clr

    dll_dir = Path(YUANTA_DLL_DIR)
    sys.path.append(str(dll_dir))
    if sys.platform == "win32":
        os.add_dll_directory(str(dll_dir))

    original_cwd = os.getcwd()
    try:
        os.chdir(str(dll_dir))
        clr.AddReference("YuantaSparkAPI")
    finally:
        os.chdir(original_cwd)

    from YuantaOneAPI import (
        YuantaSparkAPITrader, enumLangType, enumEnvironmentMode, enumLogType,
        OnResponseEventHandler,
        LoginResult, Status, LoginData,
        StockOrder, StkOrderResult, OrderStatus, StkOrderData,
        FutureOrder, FutOrderResult, FutOrderData,
        RealReport, RealReportResult, RealReportMerge, RealReportMergeResult,
        OrderTradeReportResult,
        StoreSummaryResult, StkStore,
        FutStoreSummaryResult, FutStore,
        Quote, enumMarketType,
        Watchlist, WatchListResult, WatchlistAll, WatchListAllResult,
        StockTick, StockTickResult,
        FiveTickA, FiveTickAResult,
        MarketInformation, MarketInfoResult,
        StockOtherInformation, StockOtherInfoResult,
        KLineType,
        QueryWatchListResult, QueryWatchList,
        UnGainLossDetailResult,
        RealizedGainLoss,
        StkInfo, StkInformationResult,
        StkClassifyPriceResult,
        StickDetailResult, enumStkTickSelectType,
        SubQuoteListResult,
        enumQuoteIndexType,
        enumLogType,
        enumQuoteIndexType,
    )

    _YUANTA_MODULES["api"] = YuantaSparkAPITrader
    _YUANTA_MODULES["OnResponseEventHandler"] = OnResponseEventHandler
    _YUANTA_MODULES["KLineType"] = KLineType
    _YUANTA_MODULES["enumMarketType"] = enumMarketType
    _YUANTA_MODULES["StockOrder"] = StockOrder
    _YUANTA_MODULES["Watchlist"] = Watchlist
    _YUANTA_MODULES["WatchlistAll"] = WatchlistAll
    _YUANTA_MODULES["StockTick"] = StockTick
    _YUANTA_MODULES["FiveTickA"] = FiveTickA
    _YUANTA_MODULES["RealizedGainLoss"] = RealizedGainLoss
    _YUANTA_MODULES["LogType"] = enumLogType
    _YUANTA_MODULES["QuoteType"] = enumQuoteIndexType
    _YUANTA_MODULES["enumEnvironmentMode"] = enumEnvironmentMode
    _YUANTA_MODULES["LangType"] = enumLangType

    _YUANTA_LOADED = True


def _get_mod(name):
    """取得延遲載入的模組物件"""
    if not _YUANTA_LOADED:
        _load_yuanta_dll()
    return _YUANTA_MODULES[name]


# =====================================================
# 資料模型
# =====================================================

@dataclass
class AccountInfo:
    account: str = ""
    name: str = ""
    investor_id: str = ""
    seller_no: int = 0

@dataclass
class LoginState:
    connected: bool = False
    logged_in: bool = False
    accounts: list[AccountInfo] = field(default_factory=list)
    error: str = ""

@dataclass
class StockPosition:
    security_no: str = ""
    security_name: str = ""
    stock_qty: int = 0
    avg_cost: float = 0.0
    market_price: float = 0.0
    unrealized_pnl: float = 0.0

@dataclass
class OrderRecord:
    order_no: str = ""
    security_no: str = ""
    buy_sell: str = ""
    price: float = 0.0
    qty: int = 0
    trade_qty: int = 0
    status: str = ""
    fare: float = 0.0
    tax: float = 0.0
    trade_date: str = ""

@dataclass
class Position:
    security_no: str = ""
    security_name: str = ""
    stock_qty: int = 0
    avg_cost: float = 0.0

@dataclass
class KBar:
    date: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0


# =====================================================
# Yuanta API 客戶端封裝
# =====================================================

class YuantaClient:
    """封裝 YuantaSparkAPITrader 的同步/非同步操作"""

    def __init__(self):
        self._api = None
        self._lock = threading.Lock()
        self._response_event = threading.Event()
        self._is_ready = threading.Event()
        self._last_response = None
        self._response_data: dict = {}
        self.state = LoginState()
        self._accounts_raw: list = []
        self._quote_callback: Optional[Callable] = None
        self._tick_callback: Optional[Callable] = None
        self._quotes: dict[str, dict] = {}

    def _debug_log(self, msg: str):
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "yuanta_debug.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} - {msg}\n")
        except Exception:
            pass

    # ----- 初始化與連線 -----

    def init(self) -> str:
        """初始化 API 物件"""
        self._debug_log("init: 正在初始化元大 API...")
        try:
            _load_yuanta_dll()
            SparkAPI = _get_mod("api")
            self._api = SparkAPI()
            
            # 必須保留 delegate 參照，否則 Python GC 會回收它，導致 C# 回呼時發生 AccessViolationException 記憶體崩潰
            self._on_response_delegate = _get_mod("OnResponseEventHandler")(self._on_response)
            self._api.OnResponse += self._on_response_delegate
            
            self._api.SetLogType(_get_mod("LogType").COMMON)
            self._debug_log("init: 初始化成功 (OK)")
            return "OK"
        except Exception as e:
            self._debug_log(f"init: 初始化失敗: {e}")
            return f"初始化失敗: {e}"

    def open(self) -> str:
        """開啟 API 連線"""
        self._debug_log("open: 正在開啟 API 連線...")
        try:
            self._is_ready.clear()
            self._api.Open(_get_mod("enumEnvironmentMode").PROD)
            if self._is_ready.wait(timeout=10):
                self.state.connected = True
                self._debug_log("open: 開啟連線成功，且主機已確認 Connected (OK)")
                return "OK"
            else:
                self._debug_log("open: 連線逾時 (10秒內未收到主機 Connected 回應)")
                return "連線逾時"
        except Exception as e:
            self._debug_log(f"open: 開啟連線失敗: {e}")
            return f"開啟連線失敗: {e}"

    def login(self, account: str, password: str,
              pfx_path: str = "", pfx_pass: str = "") -> str:
        """登入元大 API"""
        self._debug_log(f"login: 開始登入, 帳號={account}, 有憑證={bool(pfx_path)}")
        try:
            self._response_event.clear()
            if pfx_path and pfx_pass:
                self._debug_log(f"login: 使用憑證直接登入，憑證路徑: {pfx_path}")
                self._api.Login(pfx_path, pfx_pass, account, password)
            elif platform.system() == "Windows":
                self._debug_log("login: Windows 系統，使用雙參數 Login 登入（自系統憑證區自動讀取）")
                self._api.Login(account, password)
            else:
                self._debug_log("login: 無憑證資訊，使用雙參數 Login 登入")
                self._api.Login(account, password)
            
            for i in range(100):
                if "login" in self._response_data:
                    self._debug_log(f"login: 第 {i} 次輪詢檢測到登入回應事件！")
                    break
                self._pump_messages()
                time.sleep(0.1)

            if "login" in self._response_data:
                result = self._response_data.pop("login")
                status = result.LoginStatus
                self._debug_log(f"login: 登入結果代碼: {status.MsgCode}, 訊息: {status.MsgContent}, 帳號筆數: {status.Count}")
                if status.MsgCode in ("0001", "00001") and status.Count > 0:
                    self.state.logged_in = True
                    datas = result.LoginList
                    for i in range(status.Count):
                        info = AccountInfo(
                            account=datas[i].Account,
                            name=datas[i].Name,
                            investor_id=datas[i].InvestorID,
                            seller_no=datas[i].SellerNo,
                        )
                        self.state.accounts.append(info)
                        self._accounts_raw.append(datas[i])
                    res_msg = f"登入成功 ({status.Count} 個帳號)"
                    self._debug_log(f"login: {res_msg}")
                    return res_msg
                else:
                    res_msg = f"登入失敗: {status.MsgCode} - {status.MsgContent}"
                    self._debug_log(f"login: {res_msg}")
                    return res_msg
            
            self._debug_log("login: 登入逾時，無回應 (10秒內未收到 Login 回標)")
            return "登入逾時，無回應"
        except Exception as e:
            self.state.error = str(e)
            self._debug_log(f"login: 登入異常: {e}")
            return f"登入異常: {e}"

    def logout(self) -> str:
        if self._api:
            self._api.LogOut()
        self.state.logged_in = False
        return "OK"

    def close(self) -> str:
        if self._api:
            self._api.Close()
        self.state.connected = False
        self.state.logged_in = False
        return "OK"

    # ----- 內部回呼 -----

    def _on_response(self, intMark, dwIndex, strIndex, objHandle, objValue):
        type_name = ""
        try:
            type_name = objValue.GetType().Name
        except Exception:
            try:
                type_name = type(objValue).__name__
            except Exception:
                pass
        
        val_str = ""
        try:
            val_str = str(objValue)
        except Exception:
            pass

        self._debug_log(f"OnResponse: 觸發事件, strIndex='{strIndex}', type_name='{type_name}', intMark={intMark}, dwIndex={dwIndex}, objValue={val_str}")
        self._last_response = objValue
        self._response_event.set()
        if "交易主機 Is Connected" in val_str:
            self._debug_log("OnResponse: 檢測到交易主機已連線！設置 self._is_ready")
            self._is_ready.set()
        try:
            if strIndex == "Login" or type_name == "LoginResult":
                self._debug_log("OnResponse: 收到/解析為 Login 回應！寫入 self._response_data['login']")
                self._response_data["login"] = objValue
            elif strIndex == "SendStockOrder" or type_name == "StkOrderResult":
                self._response_data["order"] = objValue
            elif strIndex == "GetStoreSummary" or type_name == "StoreSummaryResult":
                self._response_data["store"] = objValue
            elif strIndex == "GetOrderTradeReport" or type_name == "OrderTradeReportResult":
                self._response_data["trade_report"] = objValue
            elif strIndex == "GetRealReport" or type_name == "RealReportResult":
                self._response_data["real_report"] = objValue
            elif strIndex == "GetRealReportMerge" or type_name == "RealReportMergeResult":
                self._response_data["real_report_merge"] = objValue
            elif strIndex == "SubscribeWatchlistAll" or type_name == "WatchListAllResult":
                try:
                    wResult = objValue
                    symbol = getattr(wResult, "StkCode", None)
                    if symbol:
                        if symbol not in self._quotes:
                            self._quotes[symbol] = {
                                "symbol": symbol,
                                "deal_price": 0.0,
                                "deal_vol": 0,
                                "total_vol": 0,
                                "time": "",
                                "bid_price": 0.0,
                                "ask_price": 0.0,
                                "value": 0.0
                            }
                        
                        flag = getattr(wResult, "IndexFlag", None)
                        flag_str = str(flag) if flag is not None else ""
                        
                        if "IndexFlag22" in flag_str:
                            pass
                        elif "IndexFlag28" in flag_str:
                            flag28 = getattr(wResult, "IndexFlag_28", None)
                            if flag28 is not None:
                                self._quotes[symbol]["bid_price"] = float(getattr(flag28, "BuyPrice", 0.0))
                                self._quotes[symbol]["ask_price"] = float(getattr(flag28, "SellPrice", 0.0))
                        elif "IndexFlag29" in flag_str:
                            flag29 = getattr(wResult, "IndexFlag_29", None)
                            if flag29 is not None:
                                self._quotes[symbol]["deal_price"] = float(getattr(flag29, "Deal", 0.0))
                                self._quotes[symbol]["deal_vol"] = int(getattr(flag29, "Vol", 0))
                                self._quotes[symbol]["total_vol"] = int(getattr(flag29, "TotalVol", 0))
                                
                                t_val = getattr(flag29, "Time", None)
                                if t_val is not None:
                                    try:
                                        time_str = f"{t_val.Hour:02d}:{t_val.Minute:02d}:{t_val.Second:02d}.{t_val.Millisecond:03d}"
                                    except Exception:
                                        try:
                                            time_str = f"{t_val.bytHour:02d}:{t_val.bytMin:02d}:{t_val.bytSec:02d}.{t_val.ushtMSec:03d}"
                                        except Exception:
                                            time_str = str(t_val)
                                    self._quotes[symbol]["time"] = time_str
                        else:
                            val = getattr(wResult, "Value", None)
                            if val is not None:
                                try:
                                    self._quotes[symbol]["value"] = float(val)
                                except Exception:
                                    pass
                except Exception as q_err:
                    self._debug_log(f"OnResponse SubscribeWatchlistAll parsing error: {q_err}")
            elif strIndex == "SubscribeStocktick":
                pass
            elif strIndex == "GetKLine":
                self._response_data["kline"] = objValue
            elif strIndex == "GetUnrealizedGainLossDetail":
                self._response_data["unrealized"] = objValue
            elif strIndex == "GetHisRealizedGainLoss":
                self._response_data["realized"] = objValue
            elif strIndex == "GetStockInformation":
                self._response_data["stock_info"] = objValue
            elif strIndex == "GetQuoteList":
                pass
        except Exception:
            pass

    def _pump_messages(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wait_response(self, key: str, timeout: float = 5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if key in self._response_data:
                return self._response_data.pop(key)
            self._pump_messages()
            time.sleep(0.1)
        return None

    # ----- 行情 -----

    def subscribe_quote(self, account: str, security_no: str,
                        market=None, callback=None):
        if market is None:
            market = _get_mod("enumMarketType").TWSE
        elif isinstance(market, int):
            market = _get_mod("enumMarketType")(market)
        self._quote_callback = callback
        
        wa = _get_mod("WatchlistAll")()
        wa.StockCode = security_no
        wa.MarketType = market
        wa.QuoteType = _get_mod("QuoteType")(255)
        
        from System.Collections.Generic import List
        lst = List[_get_mod("WatchlistAll")]()
        lst.Add(wa)
        
        lang = _get_mod("LangType")(0)
        self._api.SubscribeWatchlistAll(account, lst, lang)

    def get_latest_quote(self, symbol: str) -> Optional[dict]:
        return self._quotes.get(symbol)

    def subscribe_tick(self, account: str, security_no: str,
                       market=None, callback=None):
        if market is None:
            market = _get_mod("enumMarketType").TWSE
        elif isinstance(market, int):
            market = _get_mod("enumMarketType")(market)
        self._tick_callback = callback
        
        st_obj = _get_mod("StockTick")()
        st_obj.SecurityNo = security_no
        st_obj.MarketType = market
        
        from System.Collections.Generic import List
        lst = List[_get_mod("StockTick")]()
        lst.Add(st_obj)
        
        lang = _get_mod("LangType")(0)
        self._api.SubscribeStockTick(account, lst, lang)

    def subscribe_five_tick(self, account: str, security_no: str,
                            market=None):
        if market is None:
            market = _get_mod("enumMarketType").TWSE
        elif isinstance(market, int):
            market = _get_mod("enumMarketType")(market)
            
        ft = _get_mod("FiveTickA")()
        ft.SecurityNo = security_no
        ft.MarketType = market
        
        from System.Collections.Generic import List
        lst = List[_get_mod("FiveTickA")]()
        lst.Add(ft)
        
        lang = _get_mod("LangType")(0)
        self._api.SubscribeFiveTickA(account, lst, lang)

    def unsubscribe_all(self, account: str):
        self._api.UnSubscribeWatchlistAll(account)
        self._api.UnSubscribeStocktick(account)

    # ----- K 線 -----

    def get_kline(self, account: str, security_no: str,
                  start_date: str, end_date: str,
                  kline_type: int = 11,
                  market=None) -> list[KBar]:
        kt = _get_mod("KLineType")(kline_type)
        if market is None:
            market = _get_mod("enumMarketType").TWSE
        elif isinstance(market, int):
            market = _get_mod("enumMarketType")(market)

        self._api.GetKLine(account, kt, market,
                          security_no, start_date, end_date)
        result = self._wait_response("kline", timeout=8)
        if not result:
            return []
        bars = []
        try:
            kline_result = result
            count = kline_result.ResultCount.Count
            datas = kline_result.ResultList
            for i in range(count):
                d = datas[i]
                bars.append(KBar(
                    date=str(d.Date),
                    open=float(d.Open),
                    high=float(d.High),
                    low=float(d.Low),
                    close=float(d.Close),
                    volume=int(d.Volume),
                ))
        except Exception:
            pass
        return bars

    # ----- 庫存 -----

    def get_store_summary(self, account: str) -> list[Position]:
        self._api.GetStoreSummary(account)
        result = self._wait_response("store")
        if not result:
            return []
        positions = []
        try:
            store = result
            datas = store.ResultList
            for i in range(store.ResultCount.Count):
                d = datas[i]
                positions.append(Position(
                    security_no=str(d.SecurityNo),
                    security_name=str(d.SecurityName),
                    stock_qty=int(d.StockQty),
                    avg_cost=float(d.AvgCost),
                ))
        except Exception:
            pass
        return positions

    # ----- 成交 -----

    def get_order_trade_report(self, account: str) -> list[OrderRecord]:
        self._api.GetOrderTradeReport(account)
        result = self._wait_response("trade_report")
        if not result:
            return []
        records = []
        try:
            rpt = result
            datas = rpt.ResultList
            for i in range(rpt.ResultCount.Count):
                d = datas[i]
                records.append(OrderRecord(
                    order_no=str(d.OrderNo),
                    security_no=str(d.SecurityNo),
                    buy_sell=str(d.BuySell),
                    price=float(d.TradePrice),
                    qty=int(d.OrderQty),
                    trade_qty=int(d.TradeQty),
                    status=str(d.OrderStatus),
                    fare=float(getattr(d, 'Fare', 0)),
                    tax=float(getattr(d, 'Tax', 0)),
                    trade_date=str(d.TradeDate),
                ))
        except Exception:
            pass
        return records

    # ----- 損益 -----

    def get_unrealized_pnl(self, account: str) -> list[dict]:
        self._api.GetUnrealizedGainLossDetail(account)
        result = self._wait_response("unrealized")
        if not result:
            return []
        items = []
        try:
            data = result
            datas = data.ResultList
            for i in range(data.ResultCount.Count):
                d = datas[i]
                items.append({
                    "security_no": str(d.SecurityNo),
                    "stock": int(d.Stock),
                    "cost": float(d.Cost),
                    "market_value": float(d.MarketValue),
                    "unrealized_pnl": float(d.UnRealizedGainLoss),
                    "pnl_percent": float(d.GainLossPercent),
                })
        except Exception:
            pass
        return items

    def get_realized_pnl(self, account: str,
                         start_date: str, end_date: str) -> list[dict]:
        gl = _get_mod("RealizedGainLoss")()
        gl.Account = account
        gl.StartDate = start_date
        gl.EndDate = end_date
        self._api.GetHisRealizedGainLoss(gl)
        result = self._wait_response("realized")
        if not result:
            return []
        items = []
        try:
            data = result
            datas = data.ResultList
            for i in range(data.ResultCount.Count):
                d = datas[i]
                items.append({
                    "security_no": str(d.SecurityNo),
                    "buy_sell": str(d.BuySell),
                    "trade_date": str(d.TradeDate),
                    "price": float(d.Price),
                    "qty": int(d.Qty),
                    "pnl": float(d.GainLoss),
                    "fare": float(getattr(d, 'Fare', 0)),
                })
        except Exception:
            pass
        return items

    # ----- 下單 -----

    def place_stock_order(self, account: str, security_no: str,
                          buy_sell: str, price: float, qty: int,
                          price_type: str = "L",
                          order_type: str = "0",
                          trade_type: str = "0",
                          market=None) -> dict:
        if market is None:
            market = _get_mod("enumMarketType").TWSE
        order = _get_mod("StockOrder")()
        order.Account = account
        order.SecurityNo = security_no
        order.SecurityType = "S"
        order.BuySell = buy_sell
        order.Price = price
        order.Qty = qty
        order.PriceType = price_type
        order.OrderType = order_type
        order.TradeType = trade_type
        order.MarketType = market

        self._api.SendStockOrder(order)
        result = self._wait_response("order", timeout=8)
        if not result:
            return {"status": "timeout", "msg": "委託無回應"}

        try:
            stk = result
            status = stk.ResultCount
            datas = stk.ResultList
            orders_list = []
            for i in range(status.Count):
                d = datas[i]
                orders_list.append({
                    "order_no": str(d.OrderNo),
                    "price": float(d.Price),
                    "qty": int(d.Qty),
                    "status": str(d.OrderStatus),
                    "msg": f"{status.MsgCode}: {status.MsgContent}",
                })
            return {
                "status": "ok",
                "msg": f"{status.MsgCode}: {status.MsgContent}",
                "orders": orders_list,
            }
        except Exception as e:
            return {"status": "error", "msg": str(e)}


# 單例
_client: Optional[YuantaClient] = None

def get_client() -> YuantaClient:
    global _client
    if _client is None:
        _client = YuantaClient()
    return _client
