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
# 3. Threads データ取得（Meta公式 Threads API キーワード検索版）
# ---------------------------------------------------------
def fetch_threads_data(query="副業"):
    print(f"--- Threads公式API キーワード検索開始 (Query: {query}) ---")
    posts = []
    
    if not THREADS_ACCESS_TOKEN:
        print("Threads Access Tokenが設定されていないためスキップします。")
        return posts

    try:
        # Threads全体のキーワード検索用エンドポイント
        # ※APIの仕様やMeta側のアプリ権限（threads_keyword_search等）により、
        #   ユーザーIDを挟む形式やエンドポイントのパスが異なる場合があります。
        api_url = "https://graph.threads.net/v1.0/keyword_search"
        
        params = {
            "q": query,
            "access_token": THREADS_ACCESS_TOKEN,
            "fields": "id,text,permalink,timestamp,like_count,reply_count"
        }
        
        response = requests.get(api_url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("data", [])
            
            # 上位5件を取得
            for item in items[:5]:
                text = item.get("text", "タイトルなし")
                permalink = item.get("permalink", "")
                likes = item.get("like_count", 0)
                comments = item.get("reply_count", 0)
                shares = 0 
                
                # バズ度の計算
                score = calculate_buzz_score(likes, comments, shares)
                
                posts.append({
                    "platform": "Threads",
                    "title_text": text[:50].replace('\n', ' '),
                    "url": permalink,
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "score": score
                })
        else:
            print(f"Threads API エラー: ステータスコード {response.status_code}, 応答: {response.text}")
            
    except Exception as e:
        print(f"Threadsデータ取得エラー: {e}")
        
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
# 5. Googleスプレッドシートへの保存（プラットフォーム別対応）
# ---------------------------------------------------------
def save_to_spreadsheet(posts, platform_type="TikTok"):
    if not SPREADSHEET_KEY:
        print("スプレッドシートのキー（SPREADSHEET_KEY）が設定されていません。スキップします。")
        return

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        if 'GCP_SA_KEY_JSON' in globals() and GCP_SA_KEY_JSON:
            creds_dict = json.loads(GCP_SA_KEY_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
        else:
            print("注意: サービスアカウントのキーが設定されていませんが、処理を継続します。")
            return

        # プラットフォームに応じて書き込み先のタブを切り替え（Threadsタブに対応）
        sheet_name = "シート1" if platform_type == "TikTok" else "Threads"
        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(sheet_name)
        
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
        print(f"Googleスプレッドシート ({sheet_name}) への保存完了")
    except Exception as e:
        print(f"スプレッドシート保存エラー ({platform_type}): {e}")

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
    # 1. TikTokデータ収集・保存・通知（必要に応じてハッシュタグを変更）
    tiktok_posts = fetch_tiktok_data(hashtag="便利グッズ")
    if tiktok_posts:
        save_to_spreadsheet(tiktok_posts, platform_type="TikTok")
        send_discord_notification(tiktok_posts)
        
    # 2. Threadsデータ収集・保存・通知（複数のキーワードを順番に検索）
    threads_queries = ["副業", "自動化", "AI"]
    
    for query in threads_queries:
        threads_posts = fetch_threads_data(query=query)
        if threads_posts:
            save_to_spreadsheet(threads_posts, platform_type="Threads")
            send_discord_notification(threads_posts)
        time.sleep(2) # 連続リクエスト対策
