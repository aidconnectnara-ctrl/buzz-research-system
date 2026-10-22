import streamlit as st

# ページ基本設定
st.set_page_config(
    page_title="SNSバズリサーチ ＆ 分析ダッシュボード",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 SNSバズリサーチ ＆ 分析ダッシュボード")
st.success("システムは正常に稼働しています。リサーチ条件を設定してください。")

# サイドバーでの条件設定
st.sidebar.header("🔍 リサーチ条件設定")

platform = st.sidebar.selectbox(
    "対象プラットフォーム",
    ["Threads", "TikTok"]
)

hashtag = st.sidebar.text_input("ハッシュタグ（例: #ガソリン代 または ガソリン）", value="")

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ 抽出フィルター制限")
min_views = st.sidebar.number_input("最小アクセス数（ビュー数など）", min_value=0, value=1000, step=100)
min_followers = st.sidebar.number_input("最小フォロワー数", min_value=0, value=500, step=50)

st.sidebar.markdown("---")
research_button = st.sidebar.button("リサーチ開始 🚀")

# メイン画面の表示
if research_button:
    st.info(f"【{platform}】の「{hashtag}」についてリサーチを実行します...")
    st.write(f"- 条件: アクセス数 {min_views}件以上 / フォロワー数 {min_followers}件以上")
    # ここに今後のスクレイピング・データ処理ロジックを組み込んでいきます
    st.warning("※現在、データ取得ロジックの接続準備中です。")
else:
    st.info("左側のサイドバーで条件を入力し、「リサーチ開始」ボタンを押してください。")
