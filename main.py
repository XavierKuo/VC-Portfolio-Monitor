# ==========================================================
# main.py (Ver 5.7 - 完整整合版)
# 邏輯更新: 支援英文標籤、gpt-4o-mini、優化無消息判斷
# 環境適配: GitHub Actions Secrets
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
# 1. 環境變數與全域設定 (保留 GitHub Actions 設定)
# ===========================

# 從 GitHub Secrets 讀取 Keys (如果讀不到則為 None)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 檔案名稱 (必須與 Google Sheet 一致)
SHEET_NAME = "VC_Portfolio_Config"

# 處理 Google JSON
# GitHub Secret 存的是字串，這裡必須轉回 Python 字典
google_json_str = os.environ.get("GOOGLE_JSON", "{}")
try:
    GOOGLE_CREDS_JSON = json.loads(google_json_str)
except json.JSONDecodeError:
    print("❌ 錯誤: GOOGLE_JSON 格式不正確，請確保貼上的是純 JSON 內容。")
    GOOGLE_CREDS_JSON = {}

# 全域變數容器
PORTFOLIO_CONFIG = {}
MEDIA_SOURCES = {}
GLOBAL_SOCIAL_SITES = []
REGIONS = {
    "TW": {"hl": "zh-TW", "gl": "tw", "name": "台灣"},
    "JP": {"hl": "ja", "gl": "jp", "name": "日本"},
    "US": {"hl": "en", "gl": "us", "name": "美國"},
}

# ===========================
# 2. 核心功能函式區 (更新至 Ver 5.5 Custom)
# ===========================

# --- 1. Telegram 發送函式 ---
def send_telegram_message(message):
    """發送 Telegram 訊息"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram Token 未設定，跳過發送。")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # 訊息分段處理 (Telegram 限制 4096 字元)
    max_length = 4000
    parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
    
    for part in parts:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": part,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            requests.post(url, json=payload)
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
            error_msg = "❌ 錯誤: GOOGLE_CREDS_JSON 是空的，無法連線。"
            print(error_msg)
            return False

        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS_JSON, scope)
        
        print(f"ℹ️ 正在嘗試連線 Google Sheet...")
        print(f"ℹ️ 您的 Service Account Email 是: 【 {creds.service_account_email} 】")
        
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        
        # 1. 讀取 Portfolio
        portfolio_sheet = spreadsheet.worksheet("Portfolio")
        portfolio_records = portfolio_sheet.get_all_records()
        
        PORTFOLIO_CONFIG = {}
        for row in portfolio_records:
            company = row.get('Company')
            if not company: continue
            
            regions_str = row.get('Regions', 'TW')
            # 過濾有效地區
            regions = [r.strip() for r in regions_str.split(',') if r.strip() in REGIONS]
            
            keywords_str = row.get('Keywords', company)
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            
            PORTFOLIO_CONFIG[company] = {"regions": regions, "keywords": keywords}
        print(f"✅ 成功載入 {len(PORTFOLIO_CONFIG)} 間 Portfolio 設定。")

        # 2. 讀取 Media Sources
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
            print(f"✅ 成功載入 {len(MEDIA_SOURCES)} 個地區媒體配置。")
        except gspread.WorksheetNotFound:
             print("⚠️ 警告: 找不到 'Media_Sources' 分頁，將使用預設值。")

        # 3. 讀取 Global Settings
        try:
            global_sheet = spreadsheet.worksheet("Global_Settings")
            global_records = global_sheet.get_all_records()
            global_settings = {}
            for row in global_records:
                global_settings[row.get('Setting_Name')] = row.get('Value')
            
            social_sites_str = global_settings.get('GLOBAL_SOCIAL_SITES', 'site:linkedin.com')
            GLOBAL_SOCIAL_SITES = [s.strip() for s in social_sites_str.split(',') if s.strip()]
            print(f"✅ 成功載入全域社群管道。")
        except gspread.WorksheetNotFound:
             print("⚠️ 警告: 找不到 'Global_Settings' 分頁，將使用預設值。")
             GLOBAL_SOCIAL_SITES = ["site:linkedin.com"]
        
        return True
    
    except Exception as e:
        print(f"❌ Google Sheet 讀取發生錯誤: {e}")
        return False

# --- 3. 搜尋函式 ---
def search_google_news(query, hl="zh-TW", gl="tw"):
    """
    使用 Serper API 搜尋 Google News
    [重要附註]：
    本函式支援全球搜尋，透過參數控制：
    - hl (Host Language): 控制介面語言 (如 'zh-TW', 'ja', 'en')
    - gl (Geo Location): 控制搜尋地區 (如 'tw', 'jp', 'us')
    這些參數是由 Google Sheet 設定檔中的 'Regions' 欄位動態傳入的，
    因此可以完美支援日本 (JP) 與美國 (US) 的在地化搜尋。
    """
    url = "https://google.serper.dev/search"
    payload = json.dumps({
        "q": query,
        "tbs": "qdr:w", # 限制過去一週
        "num": 20,      # 增加搜尋數量以提高命中率
        "hl": hl,
        "gl": gl
    })
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# --- 4. AI 分析函式 ---
def analyze_with_gpt(company_name, all_search_results_list):
    # [設定] OpenAI 模型選擇
    OPENAI_MODEL_NAME = "gpt-4o" 

    all_organic_results = []
    seen_links = set()
    
    # 資料清洗與去重
    for result_dict in all_search_results_list:
        if 'organic' in result_dict:
            for item in result_dict['organic']:
                link = item.get('link')
                if link and link not in seen_links:
                    all_organic_results.append(item)
                    seen_links.add(link)
    
    if not all_organic_results: return None

    # 時間設定
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    today_str = today.strftime("%Y-%m-%d")
    seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d")

    # 建構 Context
    news_text = ""
    for item in all_organic_results[:20]:
        title = item.get('title', 'No Title')
        snippet = item.get('snippet', 'No Snippet')
        link = item.get('link', '')
        date = item.get('date', 'Unknown Date')
        news_text += f"- [Date: {date}] {title} ({link}): {snippet}\n"

    # [設定] 優化後的 System Prompt (全繁體中文輸出版)
    prompt = f"""
    You are a strict VC investment analyst. Today is: {today_str}.
    Task: Review the global search results for portfolio company "{company_name}".

    【Time Filter】
    - Focus on news between **{seven_days_ago_str} and {today_str}**.
    - **Important Exception**: If a news item has NO date or an ambiguous date (e.g., "Recent"), but the content seems highly relevant and new, **INCLUDE IT**. Do not miss major events due to missing date tags.
    - Only exclude news clearly marked as "1 year ago", "2023", etc.
    - If no relevant news at all, reply exactly: "No huge updates".

    【Consolidation & Deduplication】
    - **CRITICAL**: If multiple sources report the same event, consolidate them into ONE summary.
    
    【High Value Signals & Categorization】
    Classify news into these **English Tags** ONLY:
    1. [🚨 CRISIS] (PR crisis, viral controversy, lawsuits)
    2. [💰 FUNDING] (Fundraising, M&A, IPO)
    3. [🚀 PRODUCT] (New product launch, New markets expansion)
    4. [📢 EVENT] (Major brand events, exhibitions)
    5. [🤝 PARTNERSHIP] (Strategic alliances)
    6. [👤 PEOPLE] (C-Level changes)

    【Output Language Rules】
    - **Global Translation**: Regardless of the source language (English, Japanese, etc.), ALL outputs (Titles and Summaries) must be in **Traditional Chinese (繁體中文)**.
    - **Tag Retention**: Keep the Categorization Tags in **English** (e.g., [💰 FUNDING]).
    - Summary Length: Concise, approximately **50-100 characters**.

    【Database】
    {news_text}

    【Output Format】
    If news exists, output in this exact format:

    **Tag | Title (in Traditional Chinese)**
    - (Summary in Traditional Chinese)
    🔍 Source: [Link Title](Link) (Provide only 1 best source link)
    """

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {"model": OPENAI_MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        if 'error' in result: return f"API Error: {result['error']['message']}"
        content = result['choices'][0]['message']['content']
        
        # 偵測無消息的關鍵字
        if "No huge updates" in content or "無重大消息" in content:
            return None
            
        return content
    except Exception as e:
        return f"程式執行錯誤: {str(e)}"

# ===========================
# 3. 主程式執行邏輯區 (Ver 5.3 完整修復版)
# ===========================
if __name__ == "__main__":
    print("🚀 開始執行 VC Portfolio Tracker (GitHub Actions Mode)...\n")

    # 1. 載入配置 (包含錯誤檢查)
    if not load_all_config_from_sheets():
        error_msg = f"❌ 嚴重錯誤: 無法從 Google Sheet 載入配置。檢查 GitHub Secrets 和 Sheet 共用權限。"
        print(error_msg)
        send_telegram_message(error_msg)
        sys.exit(1) # 終止程式

    final_report_sections = []
    stats = {
        "total_tracked": len(PORTFOLIO_CONFIG),
        "news_found": 0,
        "regions_scanned": set(),
        "time_start": datetime.now(),
    }
    successful_scans = 0 # 成功搜尋次數計數器

    # 2. 執行掃描
    for company_name, config in PORTFOLIO_CONFIG.items():
        keywords = config["keywords"]
        target_regions = config["regions"]

        print(f"\n--- 分析: {company_name} ---")

        all_search_results = []
        # 組合全域社群關鍵字
        all_search_terms = keywords + GLOBAL_SOCIAL_SITES

        for region_code in target_regions:
            if region_code not in REGIONS: continue

            # 統計掃描地區
            stats["regions_scanned"].add(region_code)

            region_info = REGIONS[region_code]
            # 取得地區媒體設定
            regional_media = MEDIA_SOURCES.get(region_code, [])

            # 組合查詢
            combined_query = " OR ".join(all_search_terms + regional_media)

            # 執行搜尋
            search_res = search_google_news(combined_query, hl=region_info["hl"], gl=region_info["gl"])

            if "error" in search_res:
                print(f"   ❌ {region_info['name']} 搜尋錯誤: {search_res['error']}")
            else:
                all_search_results.append(search_res)
                successful_scans += 1

        # AI 分析 (如果有搜尋結果)
        if all_search_results:
            print("   🤖 正在進行 AI 綜合分析...")
            analysis = analyze_with_gpt(company_name, all_search_results)

            if analysis and "No huge updates" not in analysis and "API Error" not in analysis:
                print(f"   ✅ {company_name} Something happened!")
                stats["news_found"] += 1
                final_report_sections.append(f"*{company_name}*\n{analysis}\n")
            else:
                print(f"   💤 {company_name} No huge updates~")

        time.sleep(1) # 避免 API 速率限制

    # 3. 生成報告
    time_taken = datetime.now() - stats["time_start"]

    # 計算成功率
    total_expected = stats['total_tracked'] * len(stats['regions_scanned']) if stats['regions_scanned'] else 1
    success_rate = f"{successful_scans / total_expected * 100:.0f}%" if total_expected > 0 else "0%"

    header = f"🤖 *Daily Portfolio Monitor*\n📅 Date: {datetime.now().strftime('%Y-%m-%d')}\n"
    stats_block = (
        "\n📊 *Summary Statistics:*\n"
        f"• Companies: {stats['total_tracked']}\n"
        f"• Updates: {stats['news_found']}\n"
        f"• Success Rate: {success_rate}\n"
        f"• Time: {str(time_taken).split('.')[0]}\n\n"
        "📝 *Highlights:*\n" + "-"*15 + "\n"
    )

    if final_report_sections:
        body = "\n".join(final_report_sections)
        full_report = header + stats_block + body
    else:
        full_report = header + stats_block + "本週 Portfolio 平靜無波。"

    # 4. 發送 Telegram
    print("\n正在發送 Telegram 報告...")
    send_telegram_message(full_report)
    print("✅ 完成！")
