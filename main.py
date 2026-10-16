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
GCP_SA_KEY_JSON = os.getenv("GCP_SA_KEY_JSON", "")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY", "")

# ---------------------------------------------------------
# 2. バズ度計算ロジック
# ---------------------------------------------------------
def calculate_buzz_score(likes, comments, shares_or_reposts):
    total_engagement = likes + (comments * 2.0) + (shares_or_reposts * 3.0)
    return round(total_engagement, 2)

# ---------------------------------------------------------
# 3. Threads データ取得（Playwrightによるキーワード検索スクレイピング）
# ---------------------------------------------------------
def fetch_threads_data(query="AI"):
    print(f"--- Threads検索スクレイピング開始 (Query: {query}) ---")
    posts = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Threadsの検索用URL構造にキーワードを当てはめる
        target_url = f"https://www.threads.net/search?q={query}"
        
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(4000) # 描画待ち
            
            # 投稿カード要素の取得（※ThreadsのUI構造に合わせて柔軟に調整）
            # 投稿のテキストやリンク要素をセレクタで抽出
            post_elements = page.query_selector_all('div[data-pressable-container="true"]')
            
            count = 0
            for elem in post_elements:
                if count >= 5:
                    break
                try:
                    text_elem = elem.query_selector('span')
                    link_elem = elem.query_selector('a')
                    
                    text = text_elem.inner_text() if text_elem else ""
                    href = link_elem.get_attribute('href') if link_elem else ""
                    
                    if not text or len(text) < 5:
                        continue
                        
                    if href and not href.startswith("http"):
                        href = f"https://www.threads.net{href}"
                    
                    likes = 10  # スクレイピングで数値が取れない場合の初期値・仮置き
                    comments = 2
                    shares = 1
                    score = calculate_buzz_score(likes, comments, shares)
                    
                    posts.append({
                        "platform": "Threads",
                        "title_text": text[:50].replace('\n', ' '),
                        "url": href if href else "https://www.threads.net",
                        "likes": likes,
                        "comments": comments,
                        "shares": shares,
                        "score": score
                    })
                    count += 1
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Threadsスクレイピングエラー: {e}")
        finally:
            browser.close()
            
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
def save_to_spreadsheet(posts, platform_type="TikTok"):
    if not SPREADSHEET_KEY:
        print("スプレッドシートのキー（SPREADSHEET_KEY）が設定されていません。スキップします。")
        return

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        if GCP_SA_KEY_JSON:
            creds_dict = json.loads(GCP_SA_KEY_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
        else:
            print("注意: サービスアカウントのキーが設定されていません。")
            return

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
    # 1. TikTokデータ収集・保存・通知
    tiktok_posts = fetch_tiktok_data(hashtag="便利グッズ")
    if tiktok_posts:
        save_to_spreadsheet(tiktok_posts, platform_type="TikTok")
        send_discord_notification(tiktok_posts)
        
    # 2. Threadsデータ収集・保存・通知（「副業」「自動化」「AI」の複数キーワードを順次スクレイピング）
    threads_queries = ["副業", "自動化", "AI"]
    
    for query in threads_queries:
        threads_posts = fetch_threads_data(query=query)
        if threads_posts:
            save_to_spreadsheet(threads_posts, platform_type="Threads")
            send_discord_notification(threads_posts)
        time.sleep(3)
