import sys
import os
import json
import requests
from datetime import datetime, timedelta

def get_txf_night_session_finmind():
    """使用 FinMind API 免費獲取最新的台指期夜盤 (after_market) 價格"""
    url = "https://api.finmindtrade.com/api/v4/data"
    # 往前查詢 15 天，確保跨假日、連假時也能抓到最新資料
    start_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    
    parameter = {
        "dataset": "TaiwanFuturesDaily",
        "data_id": "TX",
        "start_date": start_date
    }
    
    try:
        resp = requests.get(url, params=parameter, timeout=10)
        if resp.status_code == 200:
            res_data = resp.json()
            records = res_data.get("data", [])
            if records:
                # 篩選夜盤數據 (after_market)
                night_records = [r for r in records if r.get("trading_session") == "after_market"]
                if night_records:
                    # 找出最新的交易日期
                    latest_date = night_records[-1].get("date")
                    latest_day_records = [r for r in night_records if r.get("date") == latest_date]
                    
                    # 找出最接近的到期月份 (contract_date 最小的，通常為當月近月合約)
                    latest_day_records.sort(key=lambda x: x.get("contract_date", ""))
                    target_record = latest_day_records[0]
                    
                    return {
                        "price": float(target_record["close"]),
                        "date": target_record["date"],
                        "contract_date": target_record["contract_date"],
                        "source": "FinMind"
                    }
    except Exception:
        pass
    return None

def get_txf_fallback_yahoo():
    """如果 FinMind 失敗，使用 yfinance 抓取加權指數做為備用降級參考"""
    import yfinance as yf
    try:
        ticker = yf.Ticker("^TWII")
        df = ticker.history(period="1d")
        if not df.empty:
            return {
                "price": float(df["Close"].iloc[-1]),
                "date": df.index[-1].strftime("%Y-%m-%d"),
                "contract_date": "N/A",
                "source": "Yahoo (^TWII)"
            }
    except Exception:
        pass
    return None

def main():
    try:
        # 1. 優先使用 FinMind 獲取夜盤數據
        result = get_txf_night_session_finmind()
        
        # 2. 若失敗，降級到 Yahoo Finance
        if not result:
            result = get_txf_fallback_yahoo()
            
        if result:
            # 包裝為元大 API 同等報價格式，供 Pipeline 讀取
            quote_data = {
                "CommodityNo": "TXFPM1",
                "MatchPrice": result["price"],
                "MatchTime": result["date"],
                "Source": result["source"]
            }
            print(json.dumps({"success": True, "data": quote_data}, ensure_ascii=False))
        else:
            print(json.dumps({"error": "無法從任何管道獲取夜盤數據"}))
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.stdout.flush()
    finally:
        os._exit(0)

if __name__ == "__main__":
    main()
