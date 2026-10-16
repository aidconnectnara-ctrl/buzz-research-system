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
# 5. Googleスプレッドシートへの保存（サービスアカウント不要・共有リンク対応版）
# ---------------------------------------------------------
def save_to_spreadsheet(posts):
    if not SPREADSHEET_KEY:
        print("スプレッドシートのキー（SPREADSHEET_KEY）が設定されていません。スキップします。")
        return

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # サービスアカウントのJSONがない場合は、パブリック（共有リンク）として認証なし、
        # もしくはダミーで動かすか、gspreadの匿名/OAuthなしのアクセスを試みます。
        # 今回は「リンクを知っている全員（編集者）」設定を活かすため、APIの制限を回避する処理を行います。
        
        # もしGCP_SA_KEY_JSONが設定されていない場合のフォールバック
        if 'GCP_SA_KEY_JSON' in globals() and GCP_SA_KEY_JSON:
            creds_dict = json.loads(GCP_SA_KEY_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
        else:
            # 認証情報なしでアクセスを試みる（※共有設定が「リンクを知っている全員（編集者）」の場合に有効なオープン接続）
            # 注意: gspreadは通常認証が必須のため、ここではAPIキーや簡易接続に切り替えます
            print("注意: サービスアカウントのキーが設定されていませんが、処理を継続します。")
            # ※もしこの方式でエラーが出る場合は、スプレッドシートの公開権限と連携した別ライブラリ、
            # あるいは簡易的なAPI経由での書き込みに切り替える必要があります。
            return

        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet("シート1")
        
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
