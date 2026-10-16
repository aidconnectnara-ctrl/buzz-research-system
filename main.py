import os
import json
import time
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# 1. 環境変数の読み込み
# ---------------------------------------------------------
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
GCP_SA_KEY_JSON = os.getenv("GCP_SA_KEY_JSON", "")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY", "")

# ---------------------------------------------------------
# 2. バズ度計算ロジック
# ---------------------------------------------------------
def calculate_buzz_score(likes, comments, shares_or_reposts):
    total_engagement = likes + (comments * 2.0) + (shares_or_reposts * 3.0)
    return round(total_engagement, 2)

# ---------------------------------------------------------
# 3. Threads データ取得（プレースホルダー）
# ---------------------------------------------------------
def fetch_threads_data():
    print("--- Threadsデータ取得開始 ---")
    posts = []
    if not THREADS_ACCESS_TOKEN:
        print("Threads Access Tokenが設定されていないためスキップします。")
        return posts
    return posts

# ---------------------------------------------------------
# 4. TikTok データ取得（Playwrightによるトレンドスクレイピング）
# ---------------------------------------------------------
def fetch_tiktok_data(hashtag="便利グッズ"):
    print(f"--- TikTokデータ取得開始 (#{hashtag}) ---")
    posts = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        target_url = f"https://www.tiktok.com/tag/{hashtag}"
        
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            
            video_cards = page.query_selector_all('div[data-e2e="challenge-item"]')
            for card in video_cards[:5]:
                link_elem = card.query_selector('a')
                desc_elem = card.query_selector('div[data-e2e="challenge-item-desc"]')
                
                href = link_elem.get_attribute('href') if link_elem else ""
                desc = desc_elem.inner_text() if desc_elem else "タイトルなし"
                
                posts.append({
                    "platform": "TikTok",
                    "title_text": desc[:50].replace('\n', ' '),
                    "url": href,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "score": 100
                })
        except Exception as e:
            print(f"TikTok取得エラー: {e}")
        finally:
            browser.close()
            
    return posts

# ---------------------------------------------------------
# 5. Googleスプレッドシートへの保存
# ---------------------------------------------------------
def save_to_spreadsheet(posts):
    if not GCP_SA_KEY_JSON or not SPREADSHEET_KEY:
        print("スプレッドシート設定が不足しています。スキップします。")
        return

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(GCP_SA_KEY_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
        
        for post in posts:
            row = [
                time.strftime("%Y-%m-%d %H:%M:%S"),
                post["platform"],
                post["title_text"],
                post["url"],
                post["likes"],
                post["comments"],
                post["shares"],
                post["score"]
            ]
            sheet.append_row(row)
        print("Googleスプレッドシートへの保存完了")
    except Exception as e:
        print(f"スプレッドシート保存エラー: {e}")

# ---------------------------------------------------------
# 6. Discord 通知
# ---------------------------------------------------------
def send_discord_notification(posts):
    if not DISCORD_WEBHOOK_URL:
        return

    for post in posts:
        content = {
            "embeds": [
                {
                    "title": f"🔥 【バズ検知】{post['platform']} 急上昇！",
                    "description": post["title_text"],
                    "url": post["url"],
                    "color": 15548997,
                    "fields": [
                        {"name": "リンク", "value": f"[投稿を見る]({post['url']})", "inline": False}
                    ],
                    "footer": {"text": "Buzz Research System"}
                }
            ]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=content)
        time.sleep(1)

# ---------------------------------------------------------
# メイン実行
# ---------------------------------------------------------
if __name__ == "__main__":
    all_posts = []
    
    # TikTokデータ収集実行
    tiktok_posts = fetch_tiktok_data(hashtag="便利グッズ")
    all_posts.extend(tiktok_posts)
    
    if all_posts:
        save_to_spreadsheet(all_posts)
        send_discord_notification(all_posts)
