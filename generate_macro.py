import json
import os
import requests
import yfinance as yf
import pandas as pd
from ta.trend import ADXIndicator

# 定义 8 大宏观重力场指数
INDEX_MAP = {
    "NDX": "^NDX", 
    "SPX": "^GSPC", 
    "DJI": "^DJI",
    "HSI": "^HSI", 
    "HSTECH": "3067.HK", # 恒生科技 ETF，数据源更稳定
    "N225": "^N225", 
    "SHCOMP": "000001.SS", 
    "SZCOMP": "399001.SZ"
}

def generate_macro_data():
    result = []
    print(">>> 启动 V4 宏观重力场计算引擎 (Cloudflare KV 直连版)...")
    
    for v4_id, yf_symbol in INDEX_MAP.items():
        try:
            # 1. 抓取过去 6 个月的日线数据
            df = yf.download(yf_symbol, period="6mo", progress=False)
            if df.empty: 
                print(f"[{v4_id}] 警告：未抓取到数据")
                continue
                
            # 清洗雅虎金融最新版的多层表头
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.droplevel(1)
            
            # 2. 注入量化计算公式 (MA 阵列与 ADX)
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA50'] = df['Close'].rolling(50).mean()
            df['ADX_14'] = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
            
            # 3. 严格执行 V4 纪律：只提取昨天 (T-1) 的快照定格数据
            latest = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
            
            adx_val = latest['ADX_14']
            close_price = latest['Close']
            ma20 = latest['MA20']
            ma50 = latest['MA50']
            
            # 4. 物理状态判定逻辑
            if close_price > ma20 and ma20 > ma50: 
                regime = "BULL"
            elif close_price < ma20 and ma20 < ma50: 
                regime = "BEAR"
            else: 
                regime = "CHOPPY"
                
            result.append({
                "id": v4_id, 
                "adxVal": round(adx_val, 1) if not pd.isna(adx_val) else 0.0, 
                "regime": regime
            })
            print(f"[{v4_id}] 计算成功: 状态={regime}, ADX={round(adx_val, 1)}")
            
        except Exception as e:
            print(f"[{v4_id}] 引擎计算失败: {e}")

    # 5. 组装最终的 JSON 数据弹药
    output_data = {"status": "success", "data": result}
    json_str = json.dumps(output_data, ensure_ascii=False)
    
    # ================= KV 发射中心 =================
    # 从 GitHub 的安全保险箱 (Secrets) 中读取 Cloudflare 密钥
    account_id = os.environ.get("CF_ACCOUNT_ID")
    namespace_id = os.environ.get("CF_NAMESPACE_ID")
    api_token = os.environ.get("CF_API_TOKEN")
    
    # 安全拦截：如果没有配置密钥，直接阻断并报警
    if not all([account_id, namespace_id, api_token]):
        print("🚨 致命错误：系统未能读取到 Cloudflare API 密钥！")
        print("请确保已在 GitHub 仓库的 Settings -> Secrets and variables 中配置了 CF_ACCOUNT_ID, CF_NAMESPACE_ID, CF_API_TOKEN。")
        return

    # 构建 Cloudflare KV 的写入接口 URL (写入键值为 'v4_macro_daily')
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/v4_macro_daily"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    # 发射 PUT 请求，用最新数据覆盖旧数据
    print(">>> 正在向 Cloudflare KV 数据库发射数据...")
    response = requests.put(url, headers=headers, data=json_str.encode('utf-8'))
    
    if response.status_code == 200:
        print("🚀 弹药入库完毕！成功将宏观数据写入边缘节点。")
    else:
        print(f"🚨 写入 KV 失败，请检查密钥权限。错误信息: {response.text}")

if __name__ == "__main__":
    generate_macro_data()
