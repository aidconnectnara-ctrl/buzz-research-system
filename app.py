import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import requests
import google.generativeai as genai

# ページ基本設定
st.set_page_config(
    page_title="SNSバズリサーチ ＆ 分析ダッシュボード",
    page_icon="🚀",
    layout="wide"
)

# 1. Streamlit Secretsからの認証情報読み込み
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    THREADS_ACCESS_TOKEN = st.secrets["THREADS_ACCESS_TOKEN"]
    SPREADSHEET_KEY = st.secrets["SPREADSHEET_KEY"]
    DISCORD_WEBHOOK_URL = st.secrets["DISCORD_WEBHOOK_URL"]
    
    # dict() を外してそのまま取得する
    GCP_SA_KEY_JSON = st.secrets["GCP_SA_KEY_JSON"]
    
    # Gemini APIの初期設定
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Secretsの読み込みに失敗しました。StreamlitのSecrets設定を確認してください: {e}")
    st.stop()

# メインタイトル
st.title("🚀 Threads & TikTok バズリサーチダッシュボード")
st.write("ハッシュタグごとのアクセス数ランキング、条件絞り込み、およびGeminiによるバズ要因の自動分析を行います。")

# 2. サイドバーでの条件設定
st.sidebar.header("🔍 リサーチ条件設定")

platform = st.sidebar.selectbox(
    "対象プラットフォーム",
    ["Threads", "TikTok"]
)

hashtag = st.sidebar.text_input("ハッシュタグ（例: #ガソリン代 または ガソリン）", value="#ガソリン代")

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ 抽出フィルター制限")
min_views = st.sidebar.number_input("最小アクセス数（ビュー数など）", min_value=0, value=1000, step=100)
min_followers = st.sidebar.number_input("最小フォロワー数", min_value=0, value=500, step=50)

st.sidebar.markdown("---")
research_button = st.sidebar.button("リサーチ実行 🚀", type="primary")

# 3. リサーチ実行時のメイン処理
if research_button:
    with st.spinner(f"【{platform}】の「{hashtag}」データをリサーチ・分析中..."):
        
        # --- [データ取得ロジックのプレースホルダー / サンプルデータ] ---
        # ※実際のAPIやスクレイピング結果をここに組み込むことで、完全自動化が可能です。
        raw_data = [
            {"post_id": 1, "author": "user_alpha", "content": f"{hashtag}の高騰が家計を直撃。今すぐできる節約術3選！", "views": 15000, "followers": 3200, "likes": 1200},
            {"post_id": 2, "author": "user_beta", "content": f"{hashtag}対策としてガソリンスタンドのアプリ割を徹底解説", "views": 8500, "followers": 800, "likes": 450},
            {"post_id": 3, "author": "user_gamma", "content": f"{hashtag}に関する政府の補助金最新情報まとめ。知らないと損", "views": 32000, "followers": 15000, "likes": 4100},
            {"post_id": 4, "author": "user_delta", "content": f"{hashtag}って最近よく聞くけどみんなどうしてる？", "views": 400, "followers": 150, "likes": 10},
            {"post_id": 5, "author": "user_epsilon", "content": f"{hashtag}の裏技テクニック。この方法で月数千円浮きます", "views": 2100, "followers": 400, "likes": 120},
        ]
        df = pd.DataFrame(raw_data)
        
        # 4. フィルター制限の適用（最小アクセス数 ＆ 最小フォロワー数）
        filtered_df = df[(df["views"] >= min_views) & (df["followers"] >= min_followers)]
        filtered_df = filtered_df.sort_values(by="views", ascending=False).reset_index(drop=True)

    st.success(f"リサーチ完了！条件に一致する投稿が {len(filtered_df)} 件見つしました。")

    if len(filtered_df) > 0:
        # 5. ランキング形式でテーブル表示
        st.subheader("📊 アクセス数ランキング（上位）")
        st.dataframe(filtered_df, use_container_width=True)

        # 6. Geminiによるバズ要因の自動分析
        st.subheader("🤖 Geminiによるインサイト分析")
        top_contents = "\n".join([f"- 投稿者: {row['author']} (フォロワー: {row['followers']}人), 閲覧数: {row['views']}回\n  内容: {row['content']}" for _, row in filtered_df.iterrows()])
        
        prompt = f"""
        あなたは優秀なSNSマーケターです。以下の{platform}のハッシュタグ「{hashtag}」に関する上位の投稿データを分析し、
        どのような内容や切り口がユーザーの共感を呼び、アクセスを集めているか（バズの要因）を日本語でわかりやすく3点にまとめて分析してください。
        
        【データ】
        {top_contents}
        """
        
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            st.info(response.text)
        except Exception as e:
            st.error(f"Gemini分析の生成に失敗しました: {e}")

        # 7. アクションボタン（スプレッドシート保存 ＆ Discord通知）
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 Googleスプレッドシートに保存"):
                try:
                    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                    creds = Credentials.from_service_account_info(GCP_SA_KEY_JSON, scopes=scope)
                    client = gspread.authorize(creds)
                    sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
                    
                    # データをスプレッドシートに追記
                    for _, row in filtered_df.iterrows():
                        sheet.append_row([platform, hashtag, str(row['author']), str(row['content']), row['views'], row['followers'], row['likes']])
                    st.success("Googleスプレッドシートへの保存が完了しました！")
                except Exception as e:
                    st.error(f"スプレッドシート保存エラー: {e}")

        with col2:
            if st.button("🔔 Discordに通知を送信"):
                try:
                    message = f"🚀 【{platform}】ハッシュタグ「{hashtag}」のリサーチ結果上位を通知します！\nヒット件数: {len(filtered_df)}件"
                    payload = {"content": message}
                    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
                    if res.status_code in [200, 204]:
                        st.success("Discordへの通知が送信されました！")
                    else:
                        st.error(f"Discord通知に失敗しました (ステータスコード: {res.status_code})")
                except Exception as e:
                    st.error(f"Discord通知エラー: {e}")
    else:
        st.warning("指定された条件（最小アクセス数・最小フォロワー数）に一致するデータが見つかりませんでした。条件を緩めて再度お試しください。")
else:
    st.info("左側のサイドバーで条件を設定し、「リサーチ実行」ボタンを押してください。")
