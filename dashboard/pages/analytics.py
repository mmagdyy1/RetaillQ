import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from snowflake_conn import query

# ── Color palette ──────────────────────────────────────────────
COLORS = {
    "jumia":  "#FF6B35",
    "noon":   "#FECC00",
    "amazon": "#00A8E1",
}
BG      = "#0f1117"
CARD_BG = "#1a1d27"
ACCENT  = "#6C63FF"

# ── CSS ────────────────────────────────────────────────────────
def inject_css():
    st.markdown(f"""
    <style>
      body, .main {{ background:{BG}; color:#fff; }}

      .kpi-card {{
        background:{CARD_BG};
        border-radius:16px;
        padding:24px 20px;
        text-align:center;
        border:1px solid #2a2d3e;
        box-shadow:0 4px 20px rgba(0,0,0,.4);
      }}
      .kpi-label {{ font-size:.8rem; color:#9399b2; text-transform:uppercase; letter-spacing:.1em; }}
      .kpi-value {{ font-size:2rem; font-weight:800; color:#fff; margin:6px 0; }}
      .kpi-sub   {{ font-size:.75rem; color:#6C63FF; }}

      .section-title {{
        font-size:1.3rem; font-weight:700; color:#fff;
        border-left:4px solid {ACCENT};
        padding-left:12px; margin:32px 0 16px;
      }}

      .badge {{
        display:inline-block; padding:3px 10px;
        border-radius:20px; font-size:.75rem; font-weight:600;
      }}
      .badge-jumia  {{ background:#FF6B3520; color:#FF6B35; }}
      .badge-noon   {{ background:#FECC0020; color:#FECC00; }}
      .badge-amazon {{ background:#00A8E120; color:#00A8E1; }}

      div[data-testid="stDataFrame"] {{ border-radius:12px; overflow:hidden; }}
    </style>
    """, unsafe_allow_html=True)

# ── KPI card helper ────────────────────────────────────────────
def kpi(label, value, sub=""):
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

# ── Main ───────────────────────────────────────────────────────
def show():
    inject_css()

    # Header
    st.markdown("""
    <div style="padding:20px 0 10px">
        <h1 style="font-size:2.2rem;font-weight:900;margin:0">
            📊 <span style="color:#6C63FF">RetailIQ</span> Analytics
        </h1>
        <p style="color:#9399b2;margin:4px 0 0">Real-time retail intelligence across Egypt's top e-commerce platforms</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    # ── Load data ──────────────────────────────────────────────
    with st.spinner("Loading data from Snowflake..."):
        summary   = query("SELECT * FROM RETAILQ.GOLD.SOURCE_SUMMARY")
        trends    = query("SELECT * FROM RETAILQ.GOLD.CATEGORY_TRENDS")
        deals     = query("SELECT * FROM RETAILQ.GOLD.TOP_DEALS")
        top_rated = query("SELECT * FROM RETAILQ.GOLD.TOP_RATED")
        best_val  = query("SELECT * FROM RETAILQ.GOLD.BEST_VALUE")

    # Normalise column names to lowercase
    for df in [summary, trends, deals, top_rated, best_val]:
        df.columns = [c.lower() for c in df.columns]

    # ── Sidebar filters ────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔍 Filters")
        all_cats = sorted(trends["category"].unique().tolist())
        sel_cats = st.multiselect("Category", all_cats, default=all_cats[:5] if len(all_cats) > 5 else all_cats)
        all_src  = sorted(trends["source"].unique().tolist())
        sel_src  = st.multiselect("Source", all_src, default=all_src)
        st.markdown("---")
        st.caption("Data refreshes every 5 min")

    if not sel_cats: sel_cats = all_cats
    if not sel_src:  sel_src  = all_src

    # Apply filters
    trends_f    = trends[trends["category"].isin(sel_cats) & trends["source"].isin(sel_src)]
    deals_f     = deals[deals["category"].isin(sel_cats)   & deals["source"].isin(sel_src)]
    top_rated_f = top_rated[top_rated["category"].isin(sel_cats)]
    best_val_f  = best_val[best_val["category"].isin(sel_cats)]

    # ── KPI row ────────────────────────────────────────────────
    st.markdown('<div class="section-title">📈 Platform Overview</div>', unsafe_allow_html=True)
    cols = st.columns(len(summary) + 1)

    total_products = int(summary["total_products"].sum())
    with cols[0]:
        kpi("Total Products", f"{total_products:,}", "across all platforms")

    for i, (_, row) in enumerate(summary.iterrows(), 1):
        src = row["source"].capitalize()
        with cols[i]:
            kpi(
                src,
                f"{int(row['total_products']):,}",
                f"Avg: EGP {row['avg_price']:,.0f}"
            )

    # ── Category Trends chart ──────────────────────────────────
    st.markdown('<div class="section-title">🏷️ Average Price by Category & Source</div>', unsafe_allow_html=True)

    if not trends_f.empty:
        fig = px.bar(
            trends_f,
            x="category", y="avg_price", color="source",
            barmode="group",
            color_discrete_map=COLORS,
            labels={"avg_price": "Avg Price (EGP)", "category": "Category", "source": "Platform"},
            template="plotly_dark",
        )
        fig.update_layout(
            paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=0, r=0, t=10, b=0),
            height=380,
            xaxis_tickangle=-30,
        )
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    # ── Price range chart ──────────────────────────────────────
    st.markdown('<div class="section-title">📉 Price Range by Category</div>', unsafe_allow_html=True)
    if not trends_f.empty:
        cat_agg = trends_f.groupby("category").agg(
            min_price=("min_price","min"),
            avg_price=("avg_price","mean"),
            max_price=("max_price","max"),
        ).reset_index()

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=cat_agg["category"], y=cat_agg["min_price"], name="Min",  marker_color="#2ecc71"))
        fig2.add_trace(go.Bar(x=cat_agg["category"], y=cat_agg["avg_price"], name="Avg",  marker_color=ACCENT))
        fig2.add_trace(go.Bar(x=cat_agg["category"], y=cat_agg["max_price"], name="Max",  marker_color="#e74c3c"))
        fig2.update_layout(
            barmode="group", template="plotly_dark",
            paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
            height=350, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_tickangle=-30,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Two columns: Top Deals + Source pie ───────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="section-title">🔥 Top Deals</div>', unsafe_allow_html=True)
        if not deals_f.empty:
            show_cols = ["title","source","category","price","old_price","discount","rating"]
            show_cols = [c for c in show_cols if c in deals_f.columns]
            st.dataframe(
                deals_f[show_cols].head(15).reset_index(drop=True),
                use_container_width=True, height=420,
                column_config={
                    "title":    st.column_config.TextColumn("Product", width="large"),
                    "price":    st.column_config.NumberColumn("Price (EGP)", format="EGP %.0f"),
                    "old_price":st.column_config.NumberColumn("Old Price",   format="EGP %.0f"),
                    "discount": st.column_config.TextColumn("Discount"),
                    "rating":   st.column_config.NumberColumn("⭐ Rating", format="%.1f"),
                    "source":   st.column_config.TextColumn("Platform"),
                }
            )

    with col_right:
        st.markdown('<div class="section-title">🛒 Product Share</div>', unsafe_allow_html=True)
        if not summary.empty:
            fig3 = px.pie(
                summary, values="total_products", names="source",
                color="source", color_discrete_map=COLORS,
                hole=0.55, template="plotly_dark",
            )
            fig3.update_layout(
                paper_bgcolor=CARD_BG, height=420,
                margin=dict(l=0,r=0,t=10,b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15),
                showlegend=True,
            )
            fig3.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig3, use_container_width=True)

    # ── Top Rated ──────────────────────────────────────────────
    st.markdown('<div class="section-title">⭐ Top Rated Products</div>', unsafe_allow_html=True)
    if not top_rated_f.empty:
        show_cols = ["title","source","category","price","rating","reviews","url"]
        show_cols = [c for c in show_cols if c in top_rated_f.columns]
        st.dataframe(
            top_rated_f[show_cols].sort_values("rating", ascending=False).head(20).reset_index(drop=True),
            use_container_width=True, height=380,
            column_config={
                "title":   st.column_config.TextColumn("Product", width="large"),
                "price":   st.column_config.NumberColumn("Price (EGP)", format="EGP %.0f"),
                "rating":  st.column_config.NumberColumn("⭐ Rating", format="%.1f"),
                "reviews": st.column_config.TextColumn("Reviews"),
                "url":     st.column_config.LinkColumn("Link"),
            }
        )

    # ── Best Value ─────────────────────────────────────────────
    st.markdown('<div class="section-title">💎 Best Value Products</div>', unsafe_allow_html=True)
    if not best_val_f.empty:
        show_cols = ["title","source","category","price","rating","discount","value_score","url"]
        show_cols = [c for c in show_cols if c in best_val_f.columns]
        st.dataframe(
            best_val_f[show_cols].sort_values("value_score", ascending=False).head(20).reset_index(drop=True),
            use_container_width=True, height=380,
            column_config={
                "title":       st.column_config.TextColumn("Product", width="large"),
                "price":       st.column_config.NumberColumn("Price (EGP)", format="EGP %.0f"),
                "rating":      st.column_config.NumberColumn("⭐ Rating", format="%.1f"),
                "discount":    st.column_config.TextColumn("Discount"),
                "value_score": st.column_config.NumberColumn("💎 Value Score", format="%.2f"),
                "url":         st.column_config.LinkColumn("Link"),
            }
        )
