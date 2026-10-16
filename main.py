# ---------------------------------------------------------
# 4. TikTok データ取得（検索キーワード一致・柔軟なフィルタリング版）
# ---------------------------------------------------------
def fetch_tiktok_data(hashtag="AI"):
    print(f"--- TikTokデータ取得開始 (#{hashtag}) ---")
    posts = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
            print(f"[DEBUG TikTok] 検出された動画カード数: {len(video_cards)}")
            
            for card in video_cards:
                if len(posts) >= 5:
                    break
                
                link_elem = card.query_selector('a')
                desc_elem = card.query_selector('div[data-e2e="challenge-item-desc"]')
                
                href = link_elem.get_attribute('href') if link_elem else ""
                desc = desc_elem.inner_text() if desc_elem else ""
                
                # デバッグ用ログ
                print(f"[DEBUG TikTok] 取得説明文: {desc[:30]}...")
                
                # 本文が空の場合はスキップ
                if not desc:
                    continue
                
                # ハッシュタグ名（hashtag）が説明文に含まれているか、または日本語が含まれていればOKとする
                # （「AI」などの英字ワードでもヒットするように条件を緩和）
                has_keyword = hashtag.lower() in desc.lower()
                has_japanese = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', desc))
                
                if not (has_keyword or has_japanese):
                    continue
                
                if href and not href.startswith("http"):
                    href = f"https://www.tiktok.com{href}"
                
                posts.append({
                    "platform": "TikTok",
                    "title_text": desc[:50].replace('\n', ' '),
                    "url": href if href else "https://www.tiktok.com",
                    "likes": 100,  # 仮置きのエンゲージメントスコア
                    "comments": 10,
                    "shares": 5,
                    "score": 150
                })
        except Exception as e:
            print(f"TikTok取得エラー: {e}")
        finally:
            browser.close()
            
    print(f"--- TikTokスクレイピング終了 (取得数: {len(posts)}件) ---")
    return posts
