/**
 * INTOO V4-Quantamental Terminal 后端中枢 
 * (已更新：支持战役追踪器 TRACKER_ALL 分流版 + V4物理宏观矩阵)
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization", 
};

const FETCH_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  "Accept": "application/json"
};

function createJsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS }
  });
}

export default {
  async scheduled(event, env, ctx) {
    console.log("[SYSTEM] 触发定时宏观引力场扫描...");
    ctx.waitUntil(this.executeMacroScan(env));
  },

  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    try {
      // 路由 A: 宏观扫描数据 (从 RADAR_KV 读取)
      if (request.method === "GET" && url.pathname === "/api/macro") {
        const cachedData = await env.RADAR_KV.get("LATEST_MACRO", "json");
        return cachedData 
          ? createJsonResponse(cachedData) 
          : createJsonResponse({ status: "no_data" });
      }

      // 路由 B: 强制刷新宏观
      if (request.method === "POST" && url.pathname === "/api/scan") {
        const cachedData = await env.RADAR_KV.get("LATEST_MACRO", "json");
        if (cachedData && cachedData.timestamp) {
          const timeSinceLastScan = Date.now() - cachedData.timestamp;
          if (timeSinceLastScan < 10000) {
            return createJsonResponse({ ...cachedData, _notice: "[防御] 冷却期内" });
          }
        }
        const scanResult = await this.executeMacroScan(env);
        return createJsonResponse(scanResult);
      }

      // 路由 C: 获取 V4 股票池 (从 ITOST_KV 读取)
      if (request.method === "GET" && url.pathname === "/api/pool") {
        const poolData = await env.ITOST_KV.get("V4_STOCK_POOL"); 
        if (!poolData) {
            return createJsonResponse({ error: { message: "股票池暂无数据" } }, 404);
        }
        return new Response(poolData, { status: 200, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
      }

      // 路由 D: 接收 Python 推送雷达数据 (支持 TRACKER 双轨同步)
      if (request.method === "POST" && url.pathname === "/api/update_radar") {
        const authHeader = request.headers.get("Authorization");
        const EXPECTED_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"; 
        
        if (authHeader !== `Bearer ${EXPECTED_TOKEN}`) {
            return createJsonResponse({ error: { message: "Unauthorized" } }, 401);
        }

        const payload = await request.json();
        if (!payload || !payload.radar_data) {
             return createJsonResponse({ error: { message: "Bad Request" } }, 400);
        }

        const dateObj = payload.timestamp ? new Date(payload.timestamp) : new Date();
        const hkTime = new Date(dateObj.getTime() + 8 * 60 * 60 * 1000);
        const dateString = hkTime.toISOString().split('T')[0];
        const archiveKey = `RADAR_${dateString}`;

        // 1. 存储今日雷达快照
        await env.RADAR_KV.put(archiveKey, JSON.stringify(payload));
        await env.RADAR_KV.put("RADAR_LATEST", JSON.stringify(payload));

        // 2. 存储全量战役追踪账本 (新逻辑：如果 Payload 包含追踪数据则写入)
        if (payload.tracker_data) {
          const trackerData = {
            timestamp: payload.timestamp,
            tracker_data: payload.tracker_data
          };
          await env.RADAR_KV.put("TRACKER_ALL", JSON.stringify(trackerData));
        }

        return createJsonResponse({ 
            success: true, 
            message: `数据已双轨同步 (${archiveKey} & TRACKER_ALL)`,
            timestamp: payload.timestamp
        });
      }

      // 路由 E: 前端拉取战术雷达数据 (支持 ?type=tracker 分流)
      if (request.method === "GET" && url.pathname === "/api/radar") {
        const type = url.searchParams.get("type");
        const targetDate = url.searchParams.get("date");
        
        let targetKey = "RADAR_LATEST"; // 默认 Key
        
        if (type === "tracker") {
          targetKey = "TRACKER_ALL";    // 获取追踪账本
        } else if (targetDate) {
          targetKey = `RADAR_${targetDate}`; // 获取历史某日雷达
        }

        const radarData = await env.RADAR_KV.get(targetKey); 
        
        if (!radarData) {
            return createJsonResponse({ 
              error: { message: `未找到 ${targetKey} 的存档数据` },
              radar_data: [],
              tracker_data: [] 
            }, 404);
        }
        return new Response(radarData, { status: 200, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
      }

      // 路由 F: 接收 Python 推送财报日历 (存入 CALENDAR_KV)
      if (request.method === "POST" && url.pathname === "/api/update_calendar") {
        const authHeader = request.headers.get("Authorization");
        const EXPECTED_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"; 
        
        if (authHeader !== `Bearer ${EXPECTED_TOKEN}`) {
            return createJsonResponse({ error: { message: "Unauthorized" } }, 401);
        }

        const payload = await request.json();
        if (!payload) return createJsonResponse({ error: { message: "Bad Request" } }, 400);

        await env.CALENDAR_KV.put("LATEST_CALENDAR", JSON.stringify(payload));
        return createJsonResponse({ success: true, message: "日历更新成功" });
      }

      // 路由 G: 前端拉取事件日历 (从 CALENDAR_KV 读取)
      if (request.method === "GET" && url.pathname === "/api/calendar") {
        const calendarData = await env.CALENDAR_KV.get("LATEST_CALENDAR"); 
        if (!calendarData) {
            return createJsonResponse({ status: "no_data", message: "日历暂无数据" });
        }
        return new Response(calendarData, { status: 200, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
      }

      // =====================================================================
      // 🚀 新增模块：强弱相关数据库 (使用 env.RS_KV 变量) 的存取接口
      // =====================================================================
      
      // 路由 H: 接收 Python 推送的最新动能矩阵
      if (request.method === "POST" && url.pathname === "/api/update_rs") {
        const authHeader = request.headers.get("Authorization");
        const EXPECTED_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"; 
        if (authHeader !== `Bearer ${EXPECTED_TOKEN}`) return createJsonResponse({ error: { message: "Unauthorized" } }, 401);
        
        const payload = await request.json();
        await env.RS_KV.put("LATEST_RS_MATRIX", JSON.stringify(payload));
        return createJsonResponse({ success: true, message: "RS矩阵数据已成功写入 RS_KV" });
      }

      // 路由 I: 前端拉取动能矩阵
      if (request.method === "GET" && url.pathname === "/api/rs_matrix") {
        const rsData = await env.RS_KV.get("LATEST_RS_MATRIX");
        if (!rsData) return createJsonResponse({ status: "no_data", message: "RS矩阵暂无数据" });
        return new Response(rsData, { status: 200, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
      }
      // =====================================================================

      // =====================================================================
      // 🚀 新增模块：V4 物理宏观量化矩阵 (M模块 8宫格)
      // =====================================================================
      
      // 路由 K: 接收 GitHub Python 推送的最新物理宏观矩阵
      if (request.method === "POST" && url.pathname === "/api/update_macro_matrix") {
        const authHeader = request.headers.get("Authorization");
        const EXPECTED_TOKEN = "INTOO_V4_SECURE_TOKEN_19881992"; 
        if (authHeader !== `Bearer ${EXPECTED_TOKEN}`) return createJsonResponse({ error: { message: "Unauthorized" } }, 401);
        
        const payload = await request.json();
        await env.RADAR_KV.put("V4_MACRO_MATRIX", JSON.stringify(payload));
        return createJsonResponse({ success: true, message: "物理宏观矩阵已成功写入 RADAR_KV" });
      }

      // 路由 L: 前端 8宫格面板 拉取物理宏观矩阵
      if (request.method === "GET" && url.pathname === "/api/macro_matrix") {
        const matrixData = await env.RADAR_KV.get("V4_MACRO_MATRIX");
        if (!matrixData) return createJsonResponse({ status: "no_data", message: "物理矩阵暂无数据" });
        return new Response(matrixData, { status: 200, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
      }
      // =====================================================================

      // 路由 J: Gemini AI 审计
      if (request.method === "POST" && (url.pathname === "/" || url.pathname === "")) {
        const MODEL = env.GEMINI_MODEL_VERSION || "gemini-2.5-flash";
        const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${env.GEMINI_API_KEY}`;
        
        const requestBody = await request.text();
        const geminiResponse = await fetch(GEMINI_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: requestBody });
        
        const data = await geminiResponse.text();
        return new Response(data, { headers: { "Content-Type": "application/json", ...CORS_HEADERS }});
      }

      return createJsonResponse({ error: { message: "越权访问被拒绝" } }, 404);

    } catch (error) {
      return createJsonResponse({ error: { message: error.message } }, 500);
    }
  },

  async executeMacroScan(env) {
    const MODEL = env.GEMINI_MODEL_VERSION || "gemini-2.5-flash";
    const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${env.GEMINI_API_KEY}`;
    const currentTimestamp = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Hong_Kong', hour12: false });

    let hardDataStr = "[数据暂缺]";
    try {
      const [vixRes, tnxRes, dxyRes, hsiRes] = await Promise.all([
        fetch('https://query1.finance.yahoo.com/v8/finance/chart/^VIX?range=1d&interval=1m', { headers: FETCH_HEADERS }),
        fetch('https://query1.finance.yahoo.com/v8/finance/chart/^TNX?range=1d&interval=1m', { headers: FETCH_HEADERS }),
        fetch('https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=1d&interval=1m', { headers: FETCH_HEADERS }),
        fetch('https://query1.finance.yahoo.com/v8/finance/chart/^HSI?range=1d&interval=1m', { headers: FETCH_HEADERS })
      ]);
      const vixData = await vixRes.json(); const tnxData = await tnxRes.json(); const dxyData = await dxyRes.json(); const hsiData = await hsiRes.json();
      const vixVal = vixData?.chart?.result?.[0]?.meta?.regularMarketPrice || "数据暂缺";
      const tnxVal = tnxData?.chart?.result?.[0]?.meta?.regularMarketPrice || "数据暂缺";
      const dxyVal = dxyData?.chart?.result?.[0]?.meta?.regularMarketPrice || "数据暂缺";
      const hsiVal = hsiData?.chart?.result?.[0]?.meta?.regularMarketPrice || "数据暂缺";
      hardDataStr = `- 实时 VIX: ${vixVal}\n- 美债: ${tnxVal}\n- 美元: ${dxyVal}\n- 恒指: ${hsiVal}`;
    } catch (e) {}

    const payload = {
      contents: [{ parts: [{ text: `【V4_MACRO_SCAN】\n时间: ${currentTimestamp}\n${hardDataStr}\n执行 M 模块盘前扫描...` }] }],
      systemInstruction: { parts: [{ text: `你是 INTOO RESEARCH 的交易预审批助手。基于【V4-Quantamental 体系】对昨日今日的中日美港四大市场的宏观情况进行联网实时查询和归纳总结，输出当日的市场宏观研判和建议，包括流动性与基本面穿透、核心状态、T模块多周期结构、V4体系执行定调。格式要求：
1. 必须在开头显式注明输出时间，严格等同于物理授时。
2. 必须使用标准且紧凑的 Markdown 表格呈现四大市场状态及建议。
3. 【强约束】表格的表头与内容之间、各数据行之间，绝对禁止包含任何空行或冗余换行符（不可出现连续的 \n\n），确保前端渲染紧凑对齐。
4. 语气专业，客观冷静，直接给出核心内容。数据引用必须绝对精确。` }] },
      generationConfig: { temperature: 0.05, topP: 0.8 },
      tools: [{ googleSearch: {} }] 
    };

    const response = await fetch(GEMINI_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (data.error) throw new Error(data.error.message);
    const resultText = data.candidates[0].content.parts[0].text;
    
    const kvData = { timestamp: Date.now(), content: resultText, status: "success" };
    await env.RADAR_KV.put("LATEST_MACRO", JSON.stringify(kvData));
    return kvData;
  }
};
