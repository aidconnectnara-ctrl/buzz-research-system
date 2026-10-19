import os
import re
import json
import requests
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai

# ---------------------------------------------------------
# 0. 環境変数・設定
# ---------------------------------------------------------
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GCP_SA_KEY_JSON")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SEARCH_KEYWORDS = ["AI", "副業", "自動化"]

# ---------------------------------------------------------
# 1. Gemini APIによる投稿分析 ＆ 新規投稿案の生成関数
# ---------------------------------------------------------
def analyze_and_generate_post(post_text, platform="Threads", keyword="AI"):
    """
    Gemini APIを使って投稿を分析し、さらにその分析を基にした新しい投稿案を生成する
    """
    if not GEMINI_API_KEY:
        print("[DEBUG Gemini] GEMINI_API_KEY が未設定のため分析をスキップします。")
        return "APIキー未設定", "APIキー未設定"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
以下の{platform}のバズ投稿を分析し、それに基づいた「新しいバズ投稿案」を日本語で作成してください。

【対象の投稿本文】
{post_text}

【出力フォーマット】
--- 【1. 投稿の分析結果】 ---
・1行目のフック特徴: （読者の手を止めた理由や感情トリガー）
・文章構成パターン: （PREP法、ストーリー型、箇条書きなど）
・バズ勝因: （保存・拡散・コメントを促したポイント）

--- 【2. この勝因を活かした新しい投稿案（ジャンル: {keyword}）】 ---
・1行目の強いフック（キャッチコピー）: 
・本文・構成: 
・アクション促進（保存・コメント誘導など）: 
"""
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        result_text = response.text.strip()
        
        # 分析結果と新規投稿案を分割しやすくするための処理（あるいは全体を格納）
        return result_text, result_text
    except Exception as e:
        print(f"[DEBUG Gemini] 分析・生成エラー: {e}")
        return "分析エラー発生", "生成エラー発生"

# 日本語判定ヘルパー
def is_japanese(text):
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text))

# ---------------------------------------------------------
# 2. Googleスプレッドシート連携
# ---------------------------------------------------------
def save_to_google_sheet(data_list, sheet_name="シート1"):
    if not GOOGLE_CREDENTIALS_JSON or not SPREADSHEET_KEY:
        print("Googleスプレッドシートの認証情報またはキーが設定されていません。")
        return

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open_by_key(SPREADSHEET_KEY)
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")
            worksheet.append_row(["日時", "プラットフォーム", "キーワード", "タイトル/本文", "URL", "バズスコア", "Gemini分析＆新規投稿案"])

        rows = []
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for item in data_list:
            rows.append([
                now,
                item.get("platform", ""),
                item.get("keyword", ""),
                item.get("title_text", ""),
                item.get("url", ""),
                item.get("score", 0),
                item.get("analysis", "")  # 分析＆新規投稿案のまとめ
            ])
            
        worksheet.append_rows(rows)
        print(f"Googleスプレッドシート ({sheet_name}) への保存完了: {len(rows)}件")
    except Exception as e:
        print(f"スプレッドシート保存エラー: {e}")

# ---------------------------------------------------------
# 3. Threads データ取得 ＆ 分析・生成
# ---------------------------------------------------------
def fetch_threads_data(query="AI"):
    print(f"--- Threads検索スクレイピング開始 (Query: {query}) ---")
    posts = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium-browser"
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
            extra_http_headers={"Accept-Language": "ja-JP,ja;q=0.9"}
        )
        page = context.new_page()
        target_url = f"https://www.threads.net/search?q={query}"
        
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(5000)
            
            post_elements = page.query_selector_all('div[data-pressable-container="true"]')
            
            for elem in post_elements:
                if len(posts) >= 5:
                    break
                try:
                    text = elem.inner_text() if elem else ""
                    if not text or len(text) < 5:
                        continue
                    
                    if query not in text or not is_japanese(text):
                        continue
                    
                    link_elems = elem.query_selector_all('a')
                    href = ""
                    for a_elem in link_elems:
                        temp_href = a_elem.get_attribute('href') or ""
                        if "/post/" in temp_href or "/t/" in temp_href:
                            href = temp_href
                            break
                    
                    if not href:
                        continue
                        
                    if not href.startswith("http"):
                        href = f"https://www.threads.net{href}"
                    
                    print(f"[Gemini分析・生成中] Threads: {text[:30]}...")
                    analysis_result, _ = analyze_and_generate_post(text, platform="Threads", keyword=query)
                    
                    posts.append({
                        "platform": "Threads",
                        "keyword": query,
                        "title_text": text[:50].replace('\n', ' '),
                        "url": href,
                        "score": 150,
                        "analysis": analysis_result
                    })
                except Exception as inner_e:
                    continue
                    
        except Exception as e:
            print(f"Threadsスクレイピングエラー: {e}")
        finally:
            browser.close()
            
    print(f"--- Threadsスクレイピング終了 (取得数: {len(posts)}件) ---")
    return posts

# ---------------------------------------------------------
# 4. TikTok データ取得 ＆ 分析・生成
# ---------------------------------------------------------
def fetch_tiktok_data(hashtag="AI"):
    print(f"--- TikTokデータ取得開始 (#{hashtag}) ---")
    posts = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium-browser"
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
            extra_http_headers={"Accept-Language": "ja-JP,ja;q=0.9"}
        )
        page = context.new_page()
        target_url = f"https://www.tiktok.com/tag/{hashtag}"
        
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(4000)
            
            video_cards = page.query_selector_all('div[data-e2e="challenge-item"]')
            
            for card in video_cards:
                if len(posts) >= 5:
                    break
                
                try:
                    link_elem = card.query_selector('a')
                    desc_elem = card.query_selector('div[data-e2e="challenge-item-desc"]')
                    
                    href = link_elem.get_attribute('href') if link_elem else ""
                    desc = desc_elem.inner_text() if desc_elem else f"TikTok #{hashtag} 投稿"
                    
                    if not href:
                        continue
                        
                    if not href.startswith("http"):
                        href = f"https://www.tiktok.com{href}"
                    
                    print(f"[Gemini分析・生成中] TikTok: {desc[:30]}...")
                    analysis_result, _ = analyze_and_generate_post(desc, platform="TikTok", keyword=hashtag)
                    
                    posts.append({
                        "platform": "TikTok",
                        "keyword": hashtag,
                        "title_text": desc[:50].replace('\n', ' ') if desc else f"TikTok #{hashtag} トレンド動画",
                        "url": href,
                        "score": 150,
                        "analysis": analysis_result
                    })
                except Exception as inner_e:
                    continue
                    
        except Exception as e:
            print(f"TikTok取得エラー: {e}")
        finally:
            browser.close()
            
    print(f"--- TikTokスクレイピング終了 (取得数: {len(posts)}件) ---")
    return posts

# ---------------------------------------------------------
# 5. Discord Webhook通知
# ---------------------------------------------------------
def send_discord_notification(posts):
    if not DISCORD_WEBHOOK_URL or not posts:
        return
        
    for post in posts:
        embed = {
            "title": f"【{post['platform']}】#{post['keyword']} バズ投稿＆新規原稿案",
            "url": post['url'],
            "description": f"**元投稿:** {post['title_text']}\n\n**🤖 Gemini分析＆新規投稿案:**\n{post['analysis']}",
            "
