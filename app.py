import streamlit as st

# ページ基本設定（※必ず最初に置く）
st.set_page_config(
    page_title="SNSバズリサーチ ＆ Gemini自動分析ダッシュボード",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 SNSバズリサーチ ＆ Gemini自動分析ダッシュボード（テスト画面）")
st.success("Streamlitサーバーが正常に起動し、描画に成功しています！")

st.markdown("---")
st.info("この画面が問題なく表示されましたら、APIキーの設定や本番用コードへの切り替えを進めていきましょう。")
