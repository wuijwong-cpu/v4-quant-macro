import json
import requests
import yfinance as yf
import pandas as pd
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
API_URL = "https://api.intootech.com/api/update_macro_matrix"
SECRET_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"

def generate_macro_data():
    result = []
    
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

    # 构建并发送请求
    output_data = {"status": "success", "data": result}
    headers = {
        "Authorization": f"Bearer {SECRET_TOKEN}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(API_URL, headers=headers, json=output_data)
    
    if response.status_code == 200:
        print("V4_MACRO_MATRIX 同步成功")
    else:
        print(f"数据穿透失败: {response.text}")

if __name__ == "__main__":
    generate_macro_data()
