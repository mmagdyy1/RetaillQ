import streamlit as st

st.set_page_config(
    page_title="RetailIQ",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }

        /* منع flicker لما بتنتقل بين الصفحات */
        .stSpinner { background: #0f1117; }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🛒 RetailIQ")
    st.markdown("---")
    page = st.radio("", ["📊 Analytics", "⚡ Live Streaming"], label_visibility="collapsed")

# ── Page transition handler ────────────────────────────────────
prev_page = st.session_state.get("current_page", None)

if prev_page != page:
    # لما تنتقل من Streaming → Analytics: وقّف الـ auto-refresh ونظّف الـ consumer
    if prev_page == "⚡ Live Streaming":
        if "kafka_consumer" in st.session_state:
            try:
                st.session_state.kafka_consumer.close()
            except Exception:
                pass
            del st.session_state["kafka_consumer"]
        st.session_state.kafka_connected = None

    # لما تنتقل من Analytics → Streaming: امسح الـ Snowflake cache
    if prev_page == "📊 Analytics":
        st.cache_data.clear()

    st.session_state.current_page = page
    st.rerun()  # rerun نظيف بدون أي محتوى قديم

# ── Render page ────────────────────────────────────────────────
main = st.container()

with main:
    if page == "📊 Analytics":
        import pages.analytics as analytics
        analytics.show()
    elif page == "⚡ Live Streaming":
        import pages.streaming as streaming
        streaming.show()
