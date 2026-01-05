# ==========================================================
# main.py (Ver 7.2 - GitHub Production)
# 功能：
# 1. 雙重搜尋機制 (Targeted Media -> Fallback Wide Search)
# 2. AI 嚴格事實摘要 + 六大訊號分類
# 3. Vibe VC 風格報告 (移除重複標題，優化排版)
# ==========================================================
import requests
import json
import gspread
import time
import sys
import os
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ===========================
# 1. 環境變數與全域設定
# ===========================

# GitHub Secrets 讀取
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SHEET_NAME = "VC_Portfolio_Config"

# 處理 Google JSON (從 GitHub Secret 字串轉為 JSON 物件)
google_json_str = os.environ.get("GOOGLE_JSON", "{}")
try:
    GOOGLE_CREDS_JSON = json.loads(google_json_str)
except json.JSONDecodeError:
    print("❌ 錯誤: GOOGLE_JSON 格式不正確。")
    GOOGLE_CREDS_JSON = {}

# 全域變數初始化
PORTFOLIO_CONFIG = {}
MEDIA_SOURCES = {}
GLOBAL_SOCIAL_SITES = []
REGIONS = {
    "TW": {"hl": "zh-TW", "gl": "tw", "name": "TW"},
    "JP": {"hl": "ja", "gl": "jp", "name": "JP"},
    "US": {"hl": "en", "gl": "us", "name": "US"},
}

# ===========================
# 2. 核心功能函式區
# ===========================

# --- 1. Telegram 發送函式 ---
def send_telegram_message(message):
    """發送 Telegram 訊息"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram Token 未設定，跳過發送。")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Telegram 訊息長度限制處理 (4096 char limit safeguard)
    max_length = 3800 
    parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
    
    for part in parts:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": part,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Telegram API Error: {response.text}")
            time.sleep(1)
        except Exception as e:
            print(f"❌ Telegram 發送失敗: {e}")

# --- 2. Google Sheet 讀取函式 ---
def load_all_config_from_sheets():
    """從 Google Sheet 讀取所有配置"""
    global PORTFOLIO_CONFIG, MEDIA_SOURCES, GLOBAL_SOCIAL_SITES
    
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        if not GOOGLE_CREDS_JSON:
            print("❌ 錯誤: GOOGLE_CREDS_JSON 為空。")
            return False

        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS_JSON, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        
        # 1. Portfolio
        portfolio_sheet = spreadsheet.worksheet("Portfolio")
        portfolio_records = portfolio_sheet.get_all_records()
        
        PORTFOLIO_CONFIG = {}
        for row in portfolio_records:
            company = row.get('Company')
            if not company: continue
            
            regions_str = row.get('Regions', 'TW')
            regions = [r.strip() for r in regions_str.split(',') if r.strip() in REGIONS]
            
            keywords_str = row.get('Keywords', company)
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            
            PORTFOLIO_CONFIG[company] = {"regions": regions, "keywords": keywords}
        print(f"✅ 成功載入 {len(PORTFOLIO_CONFIG)} 間 Portfolio。")

        # 2. Media Sources
        try:
            media_sheet = spreadsheet.worksheet("Media_Sources")
            media_records = media_sheet.get_all_records()
            MEDIA_SOURCES = {}
            for row in media_records:
                code = row.get('Region', '').upper()
                sites_str = row.get('Sites', '')
                sites = [s.strip() for s in sites_str.split(',') if s.strip()]
                if code and sites:
                    MEDIA_SOURCES[code] = sites
        except gspread.WorksheetNotFound:
             print("⚠️ 無 Media_Sources 分頁，使用預設值。")

        # 3. Global Settings
        try:
            global_sheet = spreadsheet.worksheet("Global_Settings")
            global_records = global_sheet.get_all_records()
            global_settings = {}
            for row in global_records:
                global_settings[row.get('Setting_Name')] = row.get('Value')
            
            social_sites_str = global_settings.get('GLOBAL_SOCIAL_SITES', 'site:linkedin.com')
            GLOBAL_SOCIAL_SITES = [s.strip() for s in social_sites_str.split(',') if s.strip()]
        except gspread.WorksheetNotFound:
             GLOBAL_SOCIAL_SITES = ["site:linkedin.com"]
        
        return True
    except Exception as e:
        print(f"❌ Google Sheet 讀取錯誤: {e}")
        return False

# --- 3. 搜尋函式 ---
def search_google_news(query, hl="zh-TW", gl="tw"):
    """Serper API 搜尋"""
    url = "https://google.serper.dev/search"
    payload = json.dumps({
        "q": query,
        "tbs": "qdr:w", # 限制過去一週
        "num": 25,      # 取前 25 筆確保覆蓋率
        "hl": hl,
        "gl": gl
    })
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# --- 4. AI 分析函式 (Ver 7.1 - 訊號分類與格式美化版) ---
def analyze_with_gpt(company_name, all_search_results_list):
    OPENAI_MODEL_NAME = "gpt-4o" 
    all_items = []
    seen = set()
    for res in all_search_results_list:
        items = res.get('organic', [])
        for item in items:
            if item.get('link') not in seen:
                all_items.append(item)
                seen.add(item.get('link'))
    
    if not all_items: return None

    today_str = datetime.now().strftime("%Y-%m-%d")
    news_context = ""
    # 提供前 20 筆資料給 AI，增加深度
    for i in all_items[:20]:
        news_context += f"- [Source: {i.get('source', 'Unknown')}] [Title: {i.get('title')}] [Date: {i.get('date', 'Recent')}]\n  Snippet: {i.get('snippet')}\n  Link: {i.get('link')}\n"

    prompt = f"""
    Role: You are a Senior Venture Capitalist; 
    Date: Today is {today_str}; 
    Mission：分析「{company_name}」過去 7 天的重要動態，並遵守以下的消息分類與輸出格式。

    【High Value Signals & Categorization】
    請將新聞分類為以下 6 種英文標籤：
    1. [🚨 CRISIS] (公關危機、法律訴訟、負面爭議)
    2. [💰 FUNDING] (募資動態、併購 M&A、上市 IPO)
    3. [🚀 PRODUCT] (新產品發布、重大功能更新)
    4. [📢 EVENT] (品牌重大活動、大型展覽)
    5. [🤝 PARTNERSHIP] (策略聯盟、重大客戶簽約)
    6. [👤 PEOPLE] (核心高層 C-Level 變動)

    【核心指令：翻譯與品質】
    1. **全繁體中文輸出**：無論原始資料是日文或英文，輸出內容（含標題與摘要）必須翻譯為「繁體中文」。
    2. **確保摘要深度**：摘要應包含具體的事實細節，例如「「具體合作對象」或「營運、財務數據」。不應為了簡短而忽略關鍵名詞。
    3. **嚴格事實過濾**：僅描述發生的事件，嚴禁 AI 自行發揮預測或推論意見。

    【輸出格式規範】
    1. **Company Header**：第一行必須是 "🏢 **{company_name}**" 公司名稱需粗體且後方空兩行。
    2. **數量限制**：每家公司最多提供 3 個最重要的更新。
    3. **條目間隔**：不同消息條目之間請空一行。
    4. **標題格式**：**標籤 | 繁體中文標題**。
    5. **內容格式**：摘要後方換行接 "🔍 Ref."。
    6. **連結格式**：使用 Markdown `[網站名稱 | 原始標題](原始連結)`。

    【輸出範例參考】
    🏢 **SpaceX**

    [💰 FUNDING] | SpaceX 成功獲得 NASA 登月計劃新合約
    SpaceX 本週正式取得 NASA 價值 2 億美元的合約，將專用於開發星艦系統的著陸技術。
    🔍 Ref. [Reuters | SpaceX clinches NASA contract](https://reuters.com/...)

    若完全無符合上述類別的新聞，請回覆：No huge updates.
    
    資料庫內容：
    {news_context}
    """
    try:
        data = {"model": OPENAI_MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        res = requests.post("https://api.openai.com/v1/chat/completions", 
                            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, json=data).json()
        
        if 'error' in res:
            print(f"⚠️ OpenAI API Error: {res['error']}")
            return None

        content = res['choices'][0]['message']['content']
        
        if "No huge updates" in content:
            return None
            
        return content
    except Exception as e:
        print(f"AI 分析出錯: {e}")
        return None

# ===========================
# 3. 主程式執行邏輯區 (Ver 7.2 - GitHub Actions Mode)
# ===========================
if __name__ == "__main__":
    print("🚀 Starting VC Portfolio Tracker (GitHub Actions Mode)...")

    # 檢查是否能成功載入配置
    if not load_all_config_from_sheets():
        error_msg = f"❌ 嚴重錯誤: 無法從 Google Sheet 載入配置。"
        print(error_msg)
        send_telegram_message(error_msg)
        sys.exit(1)

    final_report_sections = []
    stats = {
        "total_tracked": len(PORTFOLIO_CONFIG),
        "news_found": 0,
        "regions_scanned": set(), 
        "time_start": datetime.now()
    }

    # 執行掃描
    for company, cfg in PORTFOLIO_CONFIG.items():
        print(f"🔎 Scanning: {company}...")
        
        keywords_query = "(" + " OR ".join(cfg['keywords']) + ")"
        all_res = []
        total_items_found = 0
        
        for r_code in cfg['regions']:
            if r_code not in REGIONS: continue
            stats["regions_scanned"].add(REGIONS[r_code]['name'])
            
            # --- 第一階段：限定媒體搜尋 (Targeted Search) ---
            media_list = MEDIA_SOURCES.get(r_code, []) + GLOBAL_SOCIAL_SITES
            media_list = [m.strip() for m in media_list if m.strip()]
            media_filter = "(" + " OR ".join(media_list[:8]) + ")" if media_list else ""
            
            full_query = f"{keywords_query} {media_filter}".strip()
            res = search_google_news(full_query, hl=REGIONS[r_code]['hl'], gl=REGIONS[r_code]['gl'])
            
            items = res.get('organic', [])
            
            # --- 第二階段：備援機制 (Fallback: Wide Search) ---
            # 若限定媒體無結果，針對該地區補跑一次「全網搜尋」
            if not items:
                print(f"   ⚠️ Fallback to Wide Search for {company} in {r_code}...")
                wide_query = f"{keywords_query} latest news"
                res = search_google_news(wide_query, hl=REGIONS[r_code]['hl'], gl=REGIONS[r_code]['gl'])
                items = res.get('organic', [])
            
            if items:
                total_items_found += len(items)
                all_res.append(res)

        # --- AI 分析階段 ---
        if total_items_found > 0:
            report = analyze_with_gpt(company, all_res)
            if report:
                print(f"   ✅ Update Found!")
                stats["news_found"] += 1
                # 直接加入 AI 產出的格式內容 (內含 Company Header)
                final_report_sections.append(report)
            else:
                print(f"   💤 No significant update judged by AI")
        else:
            print(f"   📭 No results found from any source")
        
        time.sleep(1) # 避免 API Rate Limit

    # --- 生成報告 (Vibe VC Style) ---
    today_str = datetime.now().strftime('%Y-%m-%d')
    header = f"✨ *Weekly Portfolio Update* ({today_str})\n\n"

    display_regions = ", ".join(stats["regions_scanned"]) if stats["regions_scanned"] else "None"
    
    stats_block = (
        "📊 *Summary Statistics*\n"
        f"• Companies Tracked: `{stats['total_tracked']}`\n"
        f"• Important Updates: `{stats['news_found']}`\n"
        f"• Regions Scanned: {display_regions}\n\n"
        "📝 *Key Highlights*\n"
        "━━━━━━━━━━━\n\n"
    )

    if final_report_sections:
        # 使用雙換行分隔不同公司的區塊
        body = "\n\n".join(final_report_sections)
        full_report = header + stats_block + body
    else:
        full_report = header + stats_block + "_No major updates found this week._"

    print("\n📤 Sending Telegram report...")
    send_telegram_message(full_report)
    print("✅ Done!")
