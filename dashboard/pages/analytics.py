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

      .kpi-alert {{
        background:#2e1a1a;
        border:1px solid #e74c3c;
        border-radius:16px;
        padding:24px 20px;
        text-align:center;
        box-shadow:0 4px 20px rgba(231,76,60,.2);
      }}

      .section-title {{
        font-size:1.3rem; font-weight:700; color:#fff;
        border-left:4px solid {ACCENT};
        padding-left:12px; margin:32px 0 16px;
      }}

      .freshness-bar {{
        background:{CARD_BG}; border-radius:10px; padding:10px 18px;
        border:1px solid #2a2d3e; display:flex; align-items:center;
        gap:10px; font-size:.85rem; color:#9399b2; margin-bottom:8px;
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

# ── KPI helpers ────────────────────────────────────────────────
def kpi(label, value, sub=""):
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

def kpi_alert(label, value, sub=""):
    st.markdown(f"""
    <div class="kpi-alert">
        <div class="kpi-label" style="color:#e74c3c">{label}</div>
        <div class="kpi-value" style="color:#e74c3c">{value}</div>
        <div class="kpi-sub" style="color:#e74c3c88">{sub}</div>
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
        anomalies = query("SELECT * FROM RETAILQ.GOLD.PRICE_ANOMALIES")
        freshness = query("SELECT MAX(scraped_at) AS last_update, COUNT(*) AS total FROM RETAILQ.SILVER.PRODUCTS")
        price_history = query("""
            SELECT
                d.full_date      AS date,
                c.category_name  AS category,
                s.source_name    AS source,
                AVG(f.price)     AS avg_price,
                MIN(f.price)     AS min_price,
                MAX(f.price)     AS max_price,
                COUNT(*)         AS product_count
            FROM RETAILQ.GOLD.FACT_PRICES f
            JOIN RETAILQ.GOLD.DIM_DATE     d ON d.date_id     = f.date_id
            JOIN RETAILQ.GOLD.DIM_CATEGORY c ON c.category_id = f.category_id
            JOIN RETAILQ.GOLD.DIM_SOURCE   s ON s.source_id   = f.source_id
            GROUP BY d.full_date, c.category_name, s.source_name
            ORDER BY d.full_date
        """)
        discount_dist = query("""
            SELECT
                s.source_name  AS source,
                CASE
                    WHEN CAST(REPLACE(sp.discount,'%','') AS FLOAT) = 0    THEN 'No Discount'
                    WHEN CAST(REPLACE(sp.discount,'%','') AS FLOAT) < 20   THEN '1–20%'
                    WHEN CAST(REPLACE(sp.discount,'%','') AS FLOAT) < 40   THEN '20–40%'
                    WHEN CAST(REPLACE(sp.discount,'%','') AS FLOAT) < 60   THEN '40–60%'
                    ELSE '60%+'
                END AS discount_range,
                COUNT(*) AS product_count
            FROM RETAILQ.SILVER.PRODUCTS sp
            JOIN RETAILQ.GOLD.DIM_SOURCE s ON s.source_name = sp.source
            WHERE sp.discount IS NOT NULL
            GROUP BY s.source_name, discount_range
        """)

    for df in [summary, trends, deals, top_rated, best_val, anomalies, freshness, price_history, discount_dist]:
        df.columns = [c.lower() for c in df.columns]

    # ── Sidebar filters ────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔍 Filters")
        all_cats = sorted(trends["category"].unique().tolist())
        sel_cats = st.multiselect("Category", all_cats, default=all_cats)
        all_src  = sorted(trends["source"].unique().tolist())
        sel_src  = st.multiselect("Source", all_src, default=all_src)
        st.markdown("---")
        st.caption("Data refreshes every 5 min")

    if not sel_cats: sel_cats = all_cats
    if not sel_src:  sel_src  = all_src

    trends_f    = trends[trends["category"].isin(sel_cats) & trends["source"].isin(sel_src)]
    deals_f     = deals[deals["category"].isin(sel_cats)   & deals["source"].isin(sel_src)]
    top_rated_f = top_rated[top_rated["category"].isin(sel_cats)]
    best_val_f  = best_val[best_val["category"].isin(sel_cats)]

    # ── Data Freshness bar ─────────────────────────────────────
    if not freshness.empty:
        last_update = freshness["last_update"].iloc[0]
        total_silver = int(freshness["total"].iloc[0])
        st.markdown(f"""
        <div class="freshness-bar">
            🕐 <b>Last updated:</b> {last_update} &nbsp;|&nbsp;
            🗄️ <b>Total records in Silver:</b> {total_silver:,} &nbsp;|&nbsp;
            ✅ Pipeline Active
        </div>
        """, unsafe_allow_html=True)

    # ── 1. KPI row ─────────────────────────────────────────────
    st.markdown('<div class="section-title">📈 Platform Overview</div>', unsafe_allow_html=True)
    total_products = int(summary["total_products"].sum()) if not summary.empty else 0
    high_anomalies = int((anomalies["severity"] == "HIGH").sum()) if not anomalies.empty else 0

    cols = st.columns(len(summary) + 2)
    with cols[0]:
        kpi("Total Products", f"{total_products:,}", "across all platforms")
    for i, (_, row) in enumerate(summary.iterrows(), 1):
        with cols[i]:
            kpi(row["source"].capitalize(), f"{int(row['total_products']):,}", f"Avg: EGP {row['avg_price']:,.0f}")
    with cols[-1]:
        kpi_alert("🚨 HIGH Anomalies", str(high_anomalies), "requires attention")

    # ── 2. Price History Over Time ─────────────────────────────
    st.markdown('<div class="section-title">📈 Price History Over Time</div>', unsafe_allow_html=True)
    if not price_history.empty and len(price_history["date"].unique()) > 1:
        ph = price_history[
            price_history["category"].isin(sel_cats) &
            price_history["source"].isin(sel_src)
        ]
        if not ph.empty:
            fig_hist = px.line(
                ph, x="date", y="avg_price",
                color="category", line_dash="source",
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"avg_price": "Avg Price (EGP)", "date": "Date", "category": "Category"},
                template="plotly_dark",
            )
            fig_hist.update_layout(
                paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
                height=400, margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("📅 Price history will appear after data accumulates across multiple days. Keep the pipeline running!")

    # ── 3. Platform Price Gap ──────────────────────────────────
    st.markdown('<div class="section-title">⚖️ Platform Price Gap per Category</div>', unsafe_allow_html=True)
    if not trends_f.empty:
        gap = trends_f.groupby("category").agg(
            min_price=("avg_price", "min"),
            max_price=("avg_price", "max"),
        ).reset_index()
        gap["gap_pct"] = ((gap["max_price"] - gap["min_price"]) / gap["max_price"] * 100).round(1)
        gap = gap.sort_values("gap_pct", ascending=True)

        fig_gap = go.Figure()
        fig_gap.add_trace(go.Bar(
            x=gap["gap_pct"], y=gap["category"],
            orientation="h",
            marker=dict(
                color=gap["gap_pct"],
                colorscale=[[0, "#2ecc71"], [0.5, "#f39c12"], [1, "#e74c3c"]],
                showscale=False,
            ),
            text=[f"{v:.1f}%" for v in gap["gap_pct"]],
            textposition="outside",
        ))
        fig_gap.update_layout(
            template="plotly_dark", paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
            height=300, margin=dict(l=0, r=60, t=10, b=0),
            xaxis_title="Price Gap % Between Cheapest & Most Expensive Platform",
        )
        st.plotly_chart(fig_gap, use_container_width=True)
        st.caption("🟢 Low gap = platforms are competitive  |  🔴 High gap = big savings by choosing the right platform")

    # ── 4. Avg Price by Category & Source ─────────────────────
    st.markdown('<div class="section-title">🏷️ Average Price by Category & Source</div>', unsafe_allow_html=True)
    if not trends_f.empty:
        fig = px.bar(
            trends_f, x="category", y="avg_price", color="source",
            barmode="group", color_discrete_map=COLORS,
            labels={"avg_price": "Avg Price (EGP)", "category": "Category", "source": "Platform"},
            template="plotly_dark",
        )
        fig.update_layout(
            paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=0, r=0, t=10, b=0), height=380, xaxis_tickangle=-30,
        )
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    # ── 5. Price Range by Category ────────────────────────────
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

    # ── 6. Price Anomalies ─────────────────────────────────────
    st.markdown('<div class="section-title">🚨 Price Anomalies Detected by ML</div>', unsafe_allow_html=True)
    if not anomalies.empty:
        col_a, col_b = st.columns([2, 3])
        with col_a:
            sev_counts = anomalies.groupby("severity").size().reset_index(name="count")
            fig_sev = px.pie(
                sev_counts, values="count", names="severity",
                color="severity",
                color_discrete_map={"HIGH": "#e74c3c", "MEDIUM": "#f39c12"},
                hole=0.55, template="plotly_dark", title="By Severity"
            )
            fig_sev.update_layout(paper_bgcolor=CARD_BG, height=300, margin=dict(l=0,r=0,t=40,b=0))
            fig_sev.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_sev, use_container_width=True)
        with col_b:
            cat_sev = anomalies.groupby(["category","severity"]).size().reset_index(name="count")
            fig_cat = px.bar(
                cat_sev, x="category", y="count", color="severity",
                color_discrete_map={"HIGH": "#e74c3c", "MEDIUM": "#f39c12"},
                barmode="stack", template="plotly_dark",
                labels={"count": "Anomalies", "category": "Category"},
                title="By Category"
            )
            fig_cat.update_layout(
                paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
                height=300, margin=dict(l=0,r=0,t=40,b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_cat, use_container_width=True)

        show_a = ["title","source","category","price","avg_cat_price","anomaly_type","severity","url"]
        show_a = [c for c in show_a if c in anomalies.columns]
        st.dataframe(
            anomalies[show_a].sort_values("severity").head(20).reset_index(drop=True),
            use_container_width=True, height=350,
            column_config={
                "title":         st.column_config.TextColumn("Product", width="large"),
                "price":         st.column_config.NumberColumn("Price (EGP)", format="EGP %.0f"),
                "avg_cat_price": st.column_config.NumberColumn("Category Avg", format="EGP %.0f"),
                "anomaly_type":  st.column_config.TextColumn("Anomaly Type"),
                "severity":      st.column_config.TextColumn("Severity"),
                "url":           st.column_config.LinkColumn("Link"),
            }
        )

    # ── 7. Top Deals + Discount Distribution ──────────────────
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
        st.markdown('<div class="section-title">🎯 Discount Distribution by Platform</div>', unsafe_allow_html=True)
        if not discount_dist.empty:
            order = ["No Discount", "1–20%", "20–40%", "40–60%", "60%+"]
            discount_dist["discount_range"] = pd.Categorical(
                discount_dist["discount_range"], categories=order, ordered=True
            )
            discount_dist = discount_dist.sort_values("discount_range")
            fig_disc = px.bar(
                discount_dist, x="discount_range", y="product_count", color="source",
                barmode="group", color_discrete_map=COLORS,
                template="plotly_dark",
                labels={"product_count": "Products", "discount_range": "Discount Range"},
            )
            fig_disc.update_layout(
                paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
                height=420, margin=dict(l=0,r=0,t=10,b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_disc, use_container_width=True)

    # ── 8. Product Share pie ───────────────────────────────────
    st.markdown('<div class="section-title">🛒 Product Share by Platform</div>', unsafe_allow_html=True)
    if not summary.empty:
        fig3 = px.pie(
            summary, values="total_products", names="source",
            color="source", color_discrete_map=COLORS,
            hole=0.55, template="plotly_dark",
        )
        fig3.update_layout(
            paper_bgcolor=CARD_BG, height=350,
            margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", yanchor="bottom", y=-0.15),
        )
        fig3.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig3, use_container_width=True)

    # ── 9. Top Rated ──────────────────────────────────────────
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

    # ── 10. Best Value ─────────────────────────────────────────
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
