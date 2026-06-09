import json
import requests
import yfinance as yf
import pandas as pd
import time  # 👈 新增：引入时间模块，用于生成物理时间戳
from ta.trend import ADXIndicator

# V4 宏观重力场 8 大指数映射
INDEX_MAP = {
    "NDX": "^NDX", 
    "SPX": "^GSPC", 
    "DJI": "^DJI",
    "HSI": "^HSI", 
    "HSTECH": "3067.HK", 
    "N225": "^N225", 
    "SHCOMP": "000001.SS", 
    "SZCOMP": "399001.SZ"
}

# 中央数据网关配置
# 注意：GET 接口用于读取现有数据，POST 接口用于覆写
READ_API_URL = "https://api.intootech.com/api/macro_matrix"
WRITE_API_URL = "https://api.intootech.com/api/update_macro_matrix"
SECRET_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"

def generate_macro_data():
    result = []
    
    # -------------------------------------------------------------
    # 1. 运算层：通过 Yahoo Finance 测算 ADX 与均线状态
    # -------------------------------------------------------------
    for v4_id, yf_symbol in INDEX_MAP.items():
        try:
            df = yf.download(yf_symbol, period="6mo", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.droplevel(1)
            
            # 计算 MA 阵列与 ADX 动能
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA50'] = df['Close'].rolling(50).mean()
            df['ADX_14'] = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
            
            # 提取 T-1 物理快照
            latest = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
            
            # 状态判定逻辑
            if latest['Close'] > latest['MA20'] > latest['MA50']:
                regime = "BULL"
            elif latest['Close'] < latest['MA20'] < latest['MA50']:
                regime = "BEAR"
            else:
                regime = "CHOPPY"
            
            result.append({
                "id": v4_id, 
                "adxVal": round(latest['ADX_14'], 1) if not pd.isna(latest['ADX_14']) else 0.0, 
                "regime": regime
            })
        except Exception as e:
            pass

    # -------------------------------------------------------------
    # 2. 融合层 (核心修复)：先读取云端现有的彭博物理广度数据
    # -------------------------------------------------------------
    existing_breadth = {}
    existing_macro_base = {}
    existing_ts_breadth = None  # 👈 新增：初始化本地广度时间戳变量，防止报错
    
    try:
        print("⏳ 正在拉取云端 KV 快照，防止彭博数据被覆盖...")
        resp = requests.get(READ_API_URL, timeout=10)
        if resp.status_code == 200:
            current_kv = resp.json()
            # 安全提取现有的彭博广度和宏观天色数据
            existing_breadth = current_kv.get("breadth", {})
            existing_macro_base = current_kv.get("macro_base", {})
            existing_ts_breadth = current_kv.get("ts_breadth", None)  # 👈 新增：安全提取云端现有的本地彭博时间戳
            print("✅ 云端历史数据提取成功，准备融合拼装。")
    except Exception as e:
        print(f"⚠️ 云端快照拉取失败，将使用空字典兜底: {e}")

    # -------------------------------------------------------------
    # 3. 穿透层：将 GitHub 计算的 ADX 与云端现有的彭博数据合并上传
    # -------------------------------------------------------------
    current_ts = int(time.time() * 1000)  # 👈 新增：生成本次 GitHub 运行的 13 位毫秒级时间戳

    output_data = {
        "status": "success", 
        "ts_regime": current_ts,          # 👈 新增：注入本次 GitHub 更新的动能(ADX)时间
        "ts_breadth": existing_ts_breadth,# 👈 新增：原封不动地继承保护本地彭博的广度时间
        "data": result,                   # GitHub 算出来的新 ADX
        "breadth": existing_breadth,      # 继承原本由本地电脑上传的彭博广度
        "macro_base": existing_macro_base # 继承原有的基础天色
    }
    
    headers = {
        "Authorization": f"Bearer {SECRET_TOKEN}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(WRITE_API_URL, headers=headers, json=output_data)
    
    if response.status_code == 200:
        print("🚀 V4_MACRO_MATRIX 同步成功 (已完美保留彭博广度数据)")
    else:
        print(f"🔴 数据穿透失败: {response.text}")

if __name__ == "__main__":
    generate_macro_data()
