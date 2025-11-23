# 這是您必須貼入 main.py 檔案頂部「核心功能函式區」的內容

def load_all_config_from_sheets():
    """連線 Google Sheet 並載入所有配置"""
    global PORTFOLIO_CONFIG, MEDIA_SOURCES, GLOBAL_SOCIAL_SITES
    
    try:
        # 授權與連線
        gc = gspread.service_account_from_dict(GOOGLE_CREDS_JSON)
        # 開啟試算表
        sh = gc.open(SHEET_NAME)
        print(f"✅ 成功連線 Google Sheet...")

        # --- 1. 載入 Portfolio_Config (公司清單) ---
        ws_config = sh.worksheet('Portfolio_Config')
        records = ws_config.get_all_records()
        
        # ... (此處省略中間邏輯，請貼上您完整的函式內容)
        
        # ... (此處省略中間邏輯，請貼上您完整的函式內容)
        
        # ... (此處省略中間邏輯，請貼上您完整的函式內容)
        
        # --- 3. 載入 Global_Social_Sites (全球社群媒體) ---
        ws_social = sh.worksheet('Global_Social_Sites')
        social_records = ws_social.get_all_records()
        for record in social_records:
            if record.get('Source') and record.get('Enable', 'Y').upper() == 'Y':
                GLOBAL_SOCIAL_SITES.append(record['Source'])
        print(f"✅ 成功載入 {len(GLOBAL_SOCIAL_SITES)} 個全球社群管道。")
        
        return True
    
    except Exception as e:
        print(f"❌ Google Sheet 讀取發生未知錯誤: <Response [200]>")
        print(f"❌ Configuration Error: 無法從 Google Sheet ({SHEET_NAME}) 載入所有配置。請檢查憑證或 Sheet 權限。")
        return False

# ==========================================================
# main.py (Ver 5.4 - GitHub Actions 專用版)
# 程式碼將從 GitHub Secrets 讀取所有設定
# ==========================================================
import requests
import json
import gspread
import time
import sys
import os # <--- 新增: 用來讀取環境變數
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- 1. 設定與憑證區 (從環境變數讀取) ---
# ⚠️ 注意: 這裡不能填入實際的 Key，程式執行時會自動從 GitHub Secrets 讀取
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SHEET_NAME = "VC_Portfolio_Config" # 檔案名稱維持不變
# 將 GitHub Secret (字串) 轉換回 Python 字典
GOOGLE_CREDS_JSON = json.loads(os.environ.get("GOOGLE_JSON", "{}"))

# --- 靜態與全域變數 (來自 Sheet 或硬編碼) ---
PORTFOLIO_CONFIG = {}
MEDIA_SOURCES = {}
GLOBAL_SOCIAL_SITES = []
REGIONS = {
    "TW": {"hl": "zh-TW", "gl": "tw", "name": "台灣"},
    "JP": {"hl": "ja", "gl": "jp", "name": "日本"},
    "US": {"hl": "en", "gl": "us", "name": "美國"},
}

# ----------------------------------------------------
# 區塊二：功能函式區 (所有函式定義)
# ----------------------------------------------------

# (請將您的 Ver 5.3 中所有函式：load_all_config_from_sheets, 
#  send_telegram_message, search_google_news, analyze_with_gpt 完整貼到這裡)
# (為避免篇幅過長，這裡省略函式內容，請務必貼上您最新的函式內容)
# [INSERT ALL FUNCTIONS HERE]
# ----------------------------------------------------
def send_telegram_message(message):
    """發送 Telegram 訊息"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ 錯誤: Telegram Token 未設定，跳過發送。")
        return
    # ... (function body as defined in Ver 5.4)
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
            print(f"❌ Telegram 發送失敗 (連線錯誤): {e}")

# (請確保 load_all_config_from_sheets 函式內容在 main.py 中)
# (請確保 search_google_news 函式內容在 main.py 中)
# (請確保 analyze_with_gpt 函式內容在 main.py 中)

# ----------------------------------------------------
# 區塊三：主程式執行區 (維持不變的邏輯)
# ----------------------------------------------------
if __name__ == "__main__":
    print("🚀 開始執行 VC Portfolio Tracker (GitHub Actions Mode)...\n")

    # 1. 載入配置 (調用 load_all_config_from_sheets)
    # ... (程式碼邏輯與 Ver 5.3 區塊三相同，省略，確保正確呼叫 load_all_config_from_sheets)
    
    # 呼叫 load_all_config_from_sheets()，並在失敗時退出
    if not load_all_config_from_sheets():
        error_msg = f"❌ 嚴重錯誤: 無法從 Google Sheet 載入配置。檢查 GitHub Secrets 和 Sheet 共用權限。"
        print(error_msg)
        send_telegram_message(error_msg) # 嘗試發送錯誤訊息
        sys.exit(1)

    final_report_sections = []
    # (其餘所有主程式邏輯與 Ver 5.3 區塊三相同，包含 stats 初始化、for 迴圈、分析、報告生成、Telegram 發送)
    # [INSERT ALL MAIN EXECUTION LOGIC HERE]
    # ...
