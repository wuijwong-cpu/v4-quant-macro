import json
import requests
import yfinance as yf
import pandas as pd
import time 
import os
import datetime
from ta.trend import ADXIndicator

# =====================================================================
# ⚙️ 核心配置区域
# =====================================================================
INDEX_MAP = {
    "NDX": "^NDX", "SPX": "^GSPC", "DJI": "^DJI",
    "HSI": "^HSI", "HSTECH": "3067.HK", 
    "N225": "^N225", 
    "SHCOMP": "000001.SS", "SZCOMP": "399001.SZ"
}

READ_API_URL = "https://api.intootech.com/api/macro_matrix"
WRITE_API_URL = "https://api.intootech.com/api/update_macro_matrix"
SECRET_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"
GITHUB_HISTORY_FILE = "v4_macro_history_cloud.csv" # 👈 云端持久化文件命名

# =====================================================================
# 💾 新增：云端 GitHub 专用历史数据写入器
# =====================================================================
def save_github_history(adx_data_list, breadth_data, macro_base_data):
    """
    将云端融合后的全量数据写入 GitHub 仓库的 CSV 文件中。
    注意：必须强制使用香港时间 (HKT, UTC+8)，防止 GitHub 服务器时差导致日期记录错误。
    """
    # 强制获取香港时间 (UTC+8) 的当前日期
    hkt_timezone = datetime.timezone(datetime.timedelta(hours=8))
    today_str = datetime.datetime.now(hkt_timezone).strftime("%Y-%m-%d")
    
    row_dict = {"Date": today_str}

    # 1. 扁平化基础宏观数据
    for key, data in macro_base_data.items():
        row_dict[key.upper()] = data.get("val", "")

    # 2. 扁平化广度数据 (云端读取的彭博数据)
    for mkt, data in breadth_data.items():
        row_dict[f"{mkt}_AdvPct"] = data.get("advancePct", "")
        row_dict[f"{mkt}_MA50Pct"] = data.get("ma50Pct", "")

    # 3. 扁平化趋势动能数据 (本次运算的 ADX)
    for item in adx_data_list:
        idx_name = item["id"]
        row_dict[f"{idx_name}_ADX"] = item["adxVal"]
        row_dict[f"{idx_name}_Regime"] = item["regime"]

    df_new = pd.DataFrame([row_dict])

    try:
        # 如果文件存在，则读取并进行防重写处理（Upsert）
        if os.path.exists(GITHUB_HISTORY_FILE):
            df_hist = pd.read_csv(GITHUB_HISTORY_FILE)
            # 删除当天可能已经存在的旧记录
            df_hist = df_hist[df_hist['Date'] != today_str]
            df_combined = pd.concat([df_hist, df_new], ignore_index=True)
        else:
            df_combined = df_new
        
        # 字段名首字母排序，确保列对齐 (Date 固定在首列)
        cols = ['Date'] + sorted([c for c in df_combined.columns if c != 'Date'])
        df_combined = df_combined[cols]
        
        df_combined.to_csv(GITHUB_HISTORY_FILE, index=False, encoding='utf-8-sig')
        print(f"💾 [云端持久化] 成功！历史快照已生成在工作区: {GITHUB_HISTORY_FILE}")
    except Exception as e:
        print(f"⚠️ [云端持久化] 写入 CSV 失败: {e}")

# =====================================================================
# 🚀 主运行程序
# =====================================================================
def generate_macro_data():
    result = []
    
    # 1. 运算层
    for v4_id, yf_symbol in INDEX_MAP.items():
        try:
            df = yf.download(yf_symbol, period="6mo", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.droplevel(1)
            
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA50'] = df['Close'].rolling(50).mean()
            df['ADX_14'] = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
            
            latest = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
            
            if latest['Close'] > latest['MA20'] > latest['MA50']: regime = "BULL"
            elif latest['Close'] < latest['MA20'] < latest['MA50']: regime = "BEAR"
            else: regime = "CHOPPY"
            
            result.append({
                "id": v4_id, 
                "adxVal": round(latest['ADX_14'], 1) if not pd.isna(latest['ADX_14']) else 0.0, 
                "regime": regime
            })
        except Exception:
            pass

    # 2. 融合层 (读取云端彭博数据)
    existing_breadth = {}
    existing_macro_base = {}
    existing_ts_breadth = None 
    
    try:
        print("⏳ 拉取云端 KV 快照...")
        resp = requests.get(READ_API_URL, timeout=10)
        if resp.status_code == 200:
            current_kv = resp.json()
            existing_breadth = current_kv.get("breadth", {})
            existing_macro_base = current_kv.get("macro_base", {})
            existing_ts_breadth = current_kv.get("ts_breadth", None) 
    except Exception as e:
        print(f"⚠️ 云端快照拉取失败: {e}")

    # -------------------------------------------------------------
    # 👈 核心插入：在此处调用 CSV 写入函数
    # 此时 result 包含了最新的美股 ADX，existing_breadth 包含了本地传上去的彭博广度
    # 这是全天最完整、最完美的数据切片！
    # -------------------------------------------------------------
    save_github_history(result, existing_breadth, existing_macro_base)

    # 3. 穿透层
    current_ts = int(time.time() * 1000) 
    output_data = {
        "status": "success", 
        "ts_regime": current_ts,          
        "ts_breadth": existing_ts_breadth,
        "data": result,                   
        "breadth": existing_breadth,      
        "macro_base": existing_macro_base 
    }
    
    headers = {"Authorization": f"Bearer {SECRET_TOKEN}", "Content-Type": "application/json"}
    response = requests.post(WRITE_API_URL, headers=headers, json=output_data)
    
    if response.status_code == 200:
        print("🚀 V4_MACRO_MATRIX 同步成功")
    else:
        print(f"🔴 数据穿透失败: {response.text}")

if __name__ == "__main__":
    generate_macro_data()
