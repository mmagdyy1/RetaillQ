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
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🛒 RetailIQ")
    st.markdown("---")
    page = st.radio("", ["📊 Analytics", "⚡ Live Streaming"], label_visibility="collapsed")

if page == "📊 Analytics":
    import pages.analytics as analytics
    analytics.show()
elif page == "⚡ Live Streaming":
    st.info("🚧 Streaming page coming soon...")
