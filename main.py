# ==========================================================
# main.py (Ver 5.6 - 完整整合版)
# 邏輯來源: Colab Ver 5.3
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
# 1. 環境變數與全域設定
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
# 2. 核心功能函式
# ===========================

def send_telegram_message(message):
    """發送 Telegram 訊息 (含錯誤診斷)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram Token 未設定，跳過發送。")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Telegram API 錯誤！狀態碼: {response.status_code}")
                print(f"   原因: {response.text}")
            time.sleep(1)
        except Exception as e:
            print(f"❌ Telegram 發送失敗: {e}")

def load_all_config_from_sheets():
    """從 Google Sheet 讀取所有配置 (完整邏輯)"""
    global PORTFOLIO_CONFIG, MEDIA_SOURCES, GLOBAL_SOCIAL_SITES
    
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        if not GOOGLE_CREDS_JSON:
            print("❌ 錯誤: GOOGLE_JSON 為空，無法連線。")
            return False

        # 使用 oauth2client 進行認證 (與 Colab 邏輯一致)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS_JSON, scope)
        client = gspread.authorize(creds)
        
        # 開啟試算表
        spreadsheet = client.open(SHEET_NAME)
        print(f"✅ 成功連線 Google Sheet: {SHEET_NAME}")
        
        # 1. 讀取 Portfolio
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
    
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ 嚴重錯誤: 找不到名為 '{SHEET_NAME}' 的 Google Sheet。")
        print("💡 請確認：1. GitHub Secret JSON 正確 2. Service Account 已加入編輯者 3. 檔名完全一致")
        return False
    except Exception as e:
        print(f"❌ Google Sheet 讀取發生未知錯誤: {e}")
        return False

def search_google_news(query, hl="zh-TW", gl="tw"):
    """Serper API 搜尋"""
    url = "https://google.serper.dev/search"
    payload = json.dumps({
        "q": query,
        "tbs": "qdr:w",
        "num": 15,
        "hl": hl,
        "gl": gl
    })
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def analyze_with_gpt(company_name, all_search_results_list):
    """OpenAI 分析"""
    all_organic_results = []
    seen_links = set()
    
    for result_dict in all_search_results_list:
        if 'organic' in result_dict:
            for item in result_dict['organic']:
                link = item.get('link')
                if link and link not in seen_links:
                    all_organic_results.append(item)
                    seen_links.add(link)
    
    if not all_organic_results: return None

    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    today_str = today.strftime("%Y-%m-%d")
    seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d")

    news_text = ""
    for item in all_organic_results[:20]:
        title = item.get('title', 'No Title')
        snippet = item.get('snippet', 'No Snippet')
        link = item.get('link', '')
        date = item.get('date', 'Unknown Date')
        news_text += f"- [時間標記: {date}] {title} ({link}): {snippet}\n"

    prompt = f"""
    你是一位嚴謹的 VC 投資分析師。今天是：{today_str}。
    任務：審查「{company_name}」彙整後的全球搜尋結果。

    【嚴格時間過濾】
    僅接受發生在 **{seven_days_ago_str} 至 {today_str}** 之間的新聞。
    若時間標記顯示 "1 year ago", "2023" 等舊聞，**絕對排除**。
    若無新消息，回答「無重大消息」。

    【高價值訊號】
    1. 🚨 公關危機/社群炎上
    2. 💰 募資/併購/IPO
    3. 🚀 產品釋出/重大更新
    4. 📢 重大品牌活動/年度展會
    5. 🤝 關鍵合作
    6. 👤 高層人事異動

    【內容翻譯】
    若為外文，請翻譯為繁體中文。

    【資料庫】
    {news_text}

    【輸出格式】
    若無消息，回答「無重大消息」。
    若有，依序輸出：
    - **【類別 | 跨國統一標籤】標題**
    - **事件摘要** (100字內)
    - **🔍 依據來源** (含連結)
    """

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        if 'error' in result: return f"API Error: {result['error']['message']}"
        content = result['choices'][0]['message']['content']
        if "無重大消息" in content: return None
        return content
    except Exception as e:
        return f"程式執行錯誤: {str(e)}"

# ===========================
# 3. 主程式執行邏輯
# ===========================
if __name__ == "__main__":
    print("🚀 開始執行 VC Portfolio Tracker (GitHub Actions Mode)...\n")

    # 1. 載入配置
    if not load_all_config_from_sheets():
        error_msg = f"❌ 嚴重錯誤: 無法從 Google Sheet 載入配置。檢查 GitHub Secrets 和 Sheet 共用權限。"
        print(error_msg)
        send_telegram_message(error_msg)
        sys.exit(1)

    final_report_sections = []
    stats = {
        "total_tracked": len(PORTFOLIO_CONFIG),
        "news_found": 0,
        "regions_scanned": set(),
        "time_start": datetime.now(),
    }
    successful_scans = 0 

    # 2. 執行掃描
    for company_name, config in PORTFOLIO_CONFIG.items():
        keywords = config["keywords"]
        target_regions = config["regions"]
        
        print(f"\n--- 分析: {company_name} ---")
        
        all_search_results = []
        all_search_terms = keywords + GLOBAL_SOCIAL_SITES
        
        for region_code in target_regions:
            if region_code not in REGIONS: continue
            
            stats["regions_scanned"].add(region_code)
            region_info = REGIONS[region_code]
            regional_media = MEDIA_SOURCES.get(region_code, [])
            
            combined_query = " OR ".join(all_search_terms + regional_media)
            
            search_res = search_google_news(combined_query, hl=region_info["hl"], gl=region_info["gl"])
            
            if "error" in search_res:
                print(f"   ❌ {region_info['name']} 搜尋錯誤: {search_res['error']}")
            else:
                all_search_results.append(search_res)
                successful_scans += 1

        if all_search_results:
            print("   🤖 正在進行 AI 綜合分析...")
            analysis = analyze_with_gpt(company_name, all_search_results)
            
            if analysis and "無重大消息" not in analysis and "API Error" not in analysis:
                print(f"   ✅ {company_name} 發現消息")
                stats["news_found"] += 1
                final_report_sections.append(f"*{company_name}*\n{analysis}\n")
            else:
                print(f"   💤 {company_name} 無重大消息")
        
        time.sleep(1)

    # 3. 生成報告
    time_taken = datetime.now() - stats["time_start"]
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

    print("\n正在發送 Telegram 報告...")
    send_telegram_message(full_report)
    print("✅ 完成！")
