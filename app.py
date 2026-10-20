import os
import re
import json
import datetime
import shutil

import requests
import streamlit as st
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai

# ---------------------------------------------------------
# ページ基本設定（※必ず他のst.xxxより一番最初に置く）
# ---------------------------------------------------------
st.set_page_config(
    page_title="SNSバズリサーチ ＆ Gemini自動分析ダッシュボード",
    page_icon="🚀",
    layout="wide"
)

# ページタイトルなどの描画
st.title("🚀 SNSバズリサーチ ＆ Gemini自動分析ダッシュボード")
st.caption("Threads / TikTok のトレンド投稿をスクレイピングし、Gemini APIで勝因分析 ＆ 新規投稿案を自動生成します。")


# ---------------------------------------------------------
# Streamlit Secrets / 環境変数の読み込み
# ---------------------------------------------------------
def get_secret(name, default=""):
    """Streamlit CloudのSecretsを優先し、なければ環境変数から取得する。"""
    try:
        value = st.secrets.get(name)
        if value is not None:
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            if str(value).strip():
                return str(value)
    except Exception:
        # ローカル環境でSecretsがない場合などは環境変数へ進む
        pass

    return os.getenv(name, default)


env_gemini_key = get_secret("GEMINI_API_KEY")
env_discord_url = get_secret("DISCORD_WEBHOOK_URL")
env_sheet_key = get_secret("SPREADSHEET_KEY")
env_creds_json = (
    get_secret("GOOGLE_CREDENTIALS_JSON")
    or get_secret("GCP_SA_KEY_JSON")
)


# ---------------------------------------------------------
# 安全なブラウザ起動関数
# ---------------------------------------------------------
def launch_safe_browser(p):
    """システムにインストールされたChromiumを探して起動する。

    Playwright管理ブラウザへの無条件フォールバックは行わない。
    これにより、Chromium未インストール時に原因が分かりやすくなる。
    """
    candidates = [
        os.getenv("CHROMIUM_PATH"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]

    candidates = list(dict.fromkeys(path for path in candidates if path))
    checked_paths = []

    for browser_path in candidates:
        checked_paths.append(browser_path)

        if not os.path.isfile(browser_path):
            continue

        try:
            st.info(f"Chromiumを使用します: {browser_path}")
            return p.chromium.launch(
                headless=True,
                executable_path=browser_path,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
        except Exception as e:
            st.warning(
                f"Chromiumの起動に失敗しました。\n"
                f"パス: {browser_path}\n"
                f"エラー: {e}"
            )

    raise RuntimeError(
        "システムChromiumが見つかりませんでした。\n"
        f"確認したパス: {checked_paths}\n\n"
        "Streamlit Cloudのリポジトリ直下にpackages.txtを置き、"
        "その中にchromiumがあることを確認してください。"
    )


# ---------------------------------------------------------
# ロジック関数
# ---------------------------------------------------------
def analyze_and_generate_post(post_text, platform, keyword, api_key):
    if not api_key:
        return "Gemini APIキーが設定されていません。"

    try:
        client = genai.Client(api_key=api_key)
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
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return (response.text or "").strip()
    except Exception as e:
        return f"分析エラー: {e}"


def is_japanese(text):
    return bool(re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", text))


def save_to_google_sheet(data_list, sheet_name, creds_json, sheet_key):
    if not creds_json or not sheet_key:
        return False, "スプレッドシートの設定情報が不足しています。"

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict,
            scope,
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_key)

        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name,
                rows="100",
                cols="20",
            )
            worksheet.append_row([
                "日時",
                "プラットフォーム",
                "キーワード",
                "タイトル/本文",
                "URL",
                "バズスコア",
                "Gemini分析＆新規投稿案",
            ])

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [
            [
                now,
                item.get("platform", ""),
                item.get("keyword", ""),
                item.get("title_text", ""),
                item.get("url", ""),
                item.get("score", 0),
                item.get("analysis", ""),
            ]
            for item in data_list
        ]

        if rows:
            worksheet.append_rows(rows)

        return True, f"{len(rows)}件保存完了"

    except json.JSONDecodeError:
        return False, "Google認証情報が正しいJSONではありません。"
    except Exception as e:
        return False, f"スプレッドシート保存エラー: {e}"


def send_discord_notification(posts, webhook_url):
    if not webhook_url or not posts:
        return 0, "Discord通知はスキップしました。"

    sent_count = 0
    errors = []

    for post in posts:
        embed = {
            "title": f"【{post.get('platform', '')}】#{post.get('keyword', '')} バズ投稿＆新規原稿案",
            "url": post.get("url", ""),
            "description": (
                f"**元投稿:** {post.get('title_text', '')}\n\n"
                f"**🤖 Gemini分析＆新規投稿案:**\n"
                f"{post.get('analysis', '')}"
            ),
            "color": 3447003,
        }

        try:
            response = requests.post(
                webhook_url,
                json={"embeds": [embed]},
                timeout=10,
            )
            response.raise_for_status()
            sent_count += 1
        except Exception as e:
            errors.append(str(e))

    if errors:
        return sent_count, f"{sent_count}件通知。エラー: {' / '.join(errors[:3])}"

    return sent_count, f"{sent_count}件Discord通知完了"


# ---------------------------------------------------------
# Threads スクレイピング
# ---------------------------------------------------------
def fetch_threads_data(query, max_count, api_key):
    posts = []

    with sync_playwright() as p:
        browser = launch_safe_browser(p)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
            )
            page = context.new_page()
            page.goto(
                f"https://www.threads.net/search?q={query}",
                wait_until="networkidle",
                timeout=30000,
            )
            page.wait_for_timeout(4000)
            post_elements = page.query_selector_all(
                'div[data-pressable-container="true"]'
            )

            for elem in post_elements:
                if len(posts) >= max_count:
                    break

                text = elem.inner_text() if elem else ""
                if (
                    not text
                    or len(text) < 5
                    or query not in text
                    or not is_japanese(text)
                ):
                    continue

                href = ""
                for a_elem in elem.query_selector_all("a"):
                    temp_href = a_elem.get_attribute("href") or ""
                    if "/post/" in temp_href or "/t/" in temp_href:
                        href = temp_href
                        break

                if not href:
                    continue

                if not href.startswith("http"):
                    href = f"https://www.threads.net{href}"

                analysis_result = analyze_and_generate_post(
                    text,
                    "Threads",
                    query,
                    api_key,
                )
                posts.append({
                    "platform": "Threads",
                    "keyword": query,
                    "title_text": text[:60].replace("\n", " "),
                    "full_text": text,
                    "url": href,
                    "score": 150,
                    "analysis": analysis_result,
                })

        except Exception as e:
            st.error(f"Threads取得エラー ({query}): {e}")
        finally:
            browser.close()

    return posts


# ---------------------------------------------------------
# TikTok スクレイピング
# ---------------------------------------------------------
def fetch_tiktok_data(hashtag, max_count, api_key):
    posts = []

    with sync_playwright() as p:
        browser = launch_safe_browser(p)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
            )
            page = context.new_page()
            page.goto(
                f"https://www.tiktok.com/tag/{hashtag}",
                wait_until="networkidle",
                timeout=30000,
            )
            page.wait_for_timeout(4000)
            video_cards = page.query_selector_all(
                'div[data-e2e="challenge-item"]'
            )

            for card in video_cards:
                if len(posts) >= max_count:
                    break

                link_elem = card.query_selector("a")
                desc_elem = card.query_selector(
                    'div[data-e2e="challenge-item-desc"]'
                )

                href = link_elem.get_attribute("href") if link_elem else ""
                desc = (
                    desc_elem.inner_text()
                    if desc_elem
                    else f"TikTok #{hashtag} 投稿"
                )

                if not href:
                    continue

                if not href.startswith("http"):
                    href = f"https://www.tiktok.com{href}"

                analysis_result = analyze_and_generate_post(
                    desc,
                    "TikTok",
                    hashtag,
                    api_key,
                )
                posts.append({
                    "platform": "TikTok",
                    "keyword": hashtag,
                    "title_text": (
                        desc[:60].replace("\n", " ")
                        if desc
                        else f"TikTok #{hashtag} 動画"
                    ),
                    "full_text": desc,
                    "url": href,
                    "score": 150,
                    "analysis": analysis_result,
                })

        except Exception as e:
            st.error(f"TikTok取得エラー (#{hashtag}): {e}")
        finally:
            browser.close()

    return posts


# ---------------------------------------------------------
# 画面表示
# ---------------------------------------------------------
st.title("🚀 SNSバズリサーチ ＆ Gemini自動分析ダッシュボード")
st.caption(
    "Threads / TikTok のトレンド投稿をスクレイピングし、"
    "Gemini APIで勝因分析 ＆ 新規投稿案を自動生成します。"
)

st.sidebar.header("⚙️ リサーチ ＆ フィルタ設定")

with st.sidebar.expander(
    "🔑 APIキー / 連携設定",
    expanded=not bool(env_gemini_key),
):
    if env_gemini_key:
        st.success("Gemini APIキーをSecretsから読み込みました。")
        gemini_api_key = env_gemini_key
    else:
        gemini_api_key = st.text_input(
            "Gemini API Key",
            type="password",
        )

    if env_discord_url:
        st.success("Discord Webhook URLをSecretsから読み込みました。")
        discord_webhook_url = env_discord_url
    else:
        discord_webhook_url = st.text_input(
            "Discord Webhook URL",
            type="password",
        )

    spreadsheet_key = st.text_input(
        "Spreadsheet Key",
        value=env_sheet_key,
    )

    if env_creds_json:
        st.success("Google認証情報をSecretsから読み込みました。")
        google_creds_json = env_creds_json
    else:
        google_creds_json = st.text_area(
            "Google Credentials JSON",
            height=150,
        )

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 検索・条件設定")

keywords_input = st.sidebar.text_input(
    "検索キーワード/ハッシュタグ（カンマ区切り）",
    value="AI, 副業, 自動化",
)
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

target_platforms = st.sidebar.multiselect(
    "対象プラットフォーム",
    ["Threads", "TikTok"],
    default=["Threads", "TikTok"],
)

max_posts_per_kw = st.sidebar.slider(
    "1キーワードあたりの取得件数",
    min_value=1,
    max_value=20,
    value=5,
)

st.sidebar.markdown("---")
st.sidebar.subheader("📊 バズ基準・フィルタ条件")
min_likes = st.sidebar.number_input(
    "最小いいね数",
    min_value=0,
    value=100,
    step=50,
)
min_comments = st.sidebar.number_input(
    "最小コメント数",
    min_value=0,
    value=10,
    step=5,
)
min_followers = st.sidebar.number_input(
    "最小フォロワー数",
    min_value=0,
    value=500,
    step=100,
)
st.sidebar.info(
    "現在の取得処理では、いいね数・コメント数・フォロワー数は取得していないため、"
    "これらの数値フィルタはまだ結果に適用されません。"
)


# ---------------------------------------------------------
# メイン画面処理
# ---------------------------------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("📌 実行設定の確認")
    st.write(f"- **検索キーワード:** {', '.join(keywords)}")
    st.write(f"- **対象プラットフォーム:** {', '.join(target_platforms)}")
    st.write(
        f"- **バズ判定フィルタ:** 最小いいね数 {min_likes} / "
        f"最小コメント数 {min_comments} / "
        f"最小フォロワー数 {min_followers}"
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    run_button = st.button(
        "🚀 リサーチ ＆ 分析を開始",
        type="primary",
        use_container_width=True,
    )

if run_button:
    if not keywords:
        st.warning("検索キーワードを入力してください。")
        st.stop()

    if not target_platforms:
        st.warning("対象プラットフォームを1つ以上選択してください。")
        st.stop()

    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    total_steps = len(keywords) * len(target_platforms)
    current_step = 0

    for kw in keywords:
        if "Threads" in target_platforms:
            status_text.text(f"🔍 Threads で '{kw}' をリサーチ中...")
            threads_res = fetch_threads_data(
                kw,
                max_posts_per_kw,
                gemini_api_key,
            )
            all_results.extend(threads_res)
            current_step += 1
            progress_bar.progress(current_step / total_steps)

        if "TikTok" in target_platforms:
            status_text.text(f"🔍 TikTok で '#{kw}' をリサーチ中...")
            tiktok_res = fetch_tiktok_data(
                kw,
                max_posts_per_kw,
                gemini_api_key,
            )
            all_results.extend(tiktok_res)
            current_step += 1
            progress_bar.progress(current_step / total_steps)

    status_text.text("✅ リサーチ＆分析完了！")

    if all_results:
        st.session_state["results"] = all_results
        st.success(f"合計 {len(all_results)} 件取得しました。")

        threads_data = [
            r for r in all_results if r["platform"] == "Threads"
        ]
        tiktok_data = [
            r for r in all_results if r["platform"] == "TikTok"
        ]

        if threads_data:
            success, message = save_to_google_sheet(
                threads_data,
                "Threads",
                google_creds_json,
                spreadsheet_key,
            )
            if success:
                st.success(f"Threads: {message}")
            else:
                st.error(f"Threads: {message}")

        if tiktok_data:
            success, message = save_to_google_sheet(
                tiktok_data,
                "TikTok",
                google_creds_json,
                spreadsheet_key,
            )
            if success:
                st.success(f"TikTok: {message}")
            else:
                st.error(f"TikTok: {message}")

        if discord_webhook_url:
            sent_count, message = send_discord_notification(
                all_results,
                discord_webhook_url,
            )
            if sent_count == len(all_results):
                st.success(message)
            else:
                st.warning(message)
    else:
        st.warning(
            "投稿を取得できませんでした。SNS側のアクセス制限、"
            "HTML構造の変更、ログイン要求などを確認してください。"
        )


# ---------------------------------------------------------
# 結果表示エリア
# ---------------------------------------------------------
if st.session_state.get("results"):
    st.markdown("---")
    st.header("📊 リサーチ＆分析結果一覧")

    results = st.session_state["results"]
    st.success(f"合計 {len(results)} 件のバズ投稿を取得・分析しました。")

    tab_all, tab_threads, tab_tiktok = st.tabs(
        ["全件表示", "Threads", "TikTok"]
    )

    def render_cards(data_list):
        if not data_list:
            st.info("表示できる結果がありません。")
            return

        for item in data_list:
            with st.expander(
                f"【{item.get('platform', '')}】"
                f"#{item.get('keyword', '')} - "
                f"{item.get('title_text', '')}"
            ):
                url = item.get("url", "")
                st.markdown(f"**URL:** [{url}]({url})")
                st.markdown("**元投稿本文:**")
                st.code(item.get("full_text", ""), language=None)
                st.markdown("---")
                st.markdown("**🤖 Gemini分析 ＆ 新規投稿案:**")
                st.markdown(item.get("analysis", "分析結果なし"))

    with tab_all:
        render_cards(results)
    with tab_threads:
        render_cards([r for r in results if r.get("platform") == "Threads"])
    with tab_tiktok:
        render_cards([r for r in results if r.get("platform") == "TikTok"])
