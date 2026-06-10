import streamlit as st
import json
import time
import re
import os
import pandas as pd
from kafka import KafkaConsumer
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


KAFKA_BROKER = (
    os.getenv("KAFKA_BOOTSTRAP_SERVERS") or
    os.getenv("KAFKA_BOOTSTRAP_SERVERS_INTERNAL") or
    "localhost:9092"
)
TOPIC        = "raw.products"
CARD_BG      = "
ACCENT       = "
COLORS       = {"jumia": "#FF6B35", "noon": "#FECC00", "amazon": "


def inject_css():
    st.markdown(f"""
    <style>
      .kpi-card {{
        background:{CARD_BG}; border-radius:16px; padding:20px;
        text-align:center; border:1px solid 
      }}
      .kpi-label {{ font-size:.78rem; color:
      .kpi-value {{ font-size:1.8rem; font-weight:800; color:
      .kpi-sub   {{ font-size:.72rem; color:

      .section-title {{
        font-size:1.15rem; font-weight:700; color:
        border-left:4px solid {ACCENT}; padding-left:12px; margin:28px 0 12px;
      }}

      .kafka-connected {{
        background:#1a2e1a; border:1px solid 
        padding:8px 16px; font-size:.85rem; color:
        display:inline-flex; align-items:center; gap:8px;
      }}
      .kafka-disconnected {{
        background:#2e1a1a; border:1px solid 
        padding:8px 16px; font-size:.85rem; color:
        display:inline-flex; align-items:center; gap:8px;
      }}

      .live-dot {{
        display:inline-block; width:9px; height:9px; border-radius:50%;
        background:
      }}
      @keyframes pulse {{
        0%   {{ box-shadow:0 0 0 0 rgba(46,204,113,.6); }}
        70%  {{ box-shadow:0 0 0 8px rgba(46,204,113,0); }}
        100% {{ box-shadow:0 0 0 0 rgba(46,204,113,0); }}
      }}
    </style>
    """, unsafe_allow_html=True)

def kpi(label, value, sub="", color="
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub" style="color:{color}">{sub}</div>
    </div>""", unsafe_allow_html=True)


def get_consumer():
    if "kafka_consumer" not in st.session_state:
        try:
            st.session_state.kafka_consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                auto_offset_reset="latest",
                enable_auto_commit=False,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                group_id=None,
                fetch_max_wait_ms=500,
                max_poll_records=500,
            )
            st.session_state.kafka_connected = True
        except Exception:
            st.session_state.kafka_consumer  = None
            st.session_state.kafka_connected = False
    return st.session_state.kafka_consumer

def fetch_messages():
    consumer = get_consumer()
    if consumer is None:
        return []
    try:
        records = consumer.poll(timeout_ms=2000, max_records=500)
        msgs = []
        for tp, messages in records.items():
            for msg in messages:
                msgs.append(msg.value)
        if "msg_count" not in st.session_state:
            st.session_state.msg_count = 0
        st.session_state.msg_count += len(msgs)
        return msgs
    except Exception:
        st.session_state.kafka_connected = False
        return []


def accumulate(existing: pd.DataFrame, new_msgs: list) -> pd.DataFrame:
    if not new_msgs:
        return existing
    new_df = pd.DataFrame(new_msgs)
    new_df["fetched_at"] = datetime.now().strftime("%H:%M:%S")
    combined = pd.concat([existing, new_df], ignore_index=True)
    if "title" in combined.columns and "source" in combined.columns:
        combined = combined.sort_values("fetched_at").drop_duplicates(
            subset=["title", "source"], keep="last"
        ).reset_index(drop=True)
    return combined


def extract_specs(title):
    t = str(title).lower()
    specs = re.findall(r'\d+\.?\d*\s*(?:gb|tb|ssd|hdd|mp|inch|"|hz|mah|k\b)', t)
    return frozenset(specs)

def normalize_title(title):
    t = str(title).lower()
    for noise in [" - jumia", " - noon", " - amazon", "jumia", "noon", "amazon",
                  "(rom:", "rom:", "ram:", " -"]:
        t = t.replace(noise, "")
    t = re.sub(r'\(.*?\)', '', t)
    words = t.strip().split()
    return " ".join(words[:6])

def get_price_comparison(df):
    if "category" not in df.columns or "url" not in df.columns:
        return pd.DataFrame()
    d = df.copy()
    d["title_key"] = d["title"].apply(normalize_title)
    d["specs"]     = d["title"].apply(extract_specs)

    pivot = d.pivot_table(
        index=["title_key", "category"], columns="source", values="price", aggfunc="min"
    ).reset_index()
    pivot.columns.name = None

    specs_map = d.groupby(["title_key","source"])["specs"].first().reset_index()

    url_pivot = d.groupby(["title_key","source"])["url"].first().reset_index()
    url_pivot = url_pivot.pivot(index="title_key", columns="source", values="url").reset_index()
    url_pivot.columns = ["title_key"] + [f"{c}_url" for c in url_pivot.columns[1:]]
    url_pivot.columns.name = None
    pivot = pivot.merge(url_pivot, on="title_key", how="left")

    src_cols = [c for c in ["jumia","noon","amazon"] if c in pivot.columns]
    pivot["platforms"] = pivot[src_cols].notna().sum(axis=1)
    multi = pivot[pivot["platforms"] >= 2].copy()
    if multi.empty:
        return multi

    def specs_compatible(title_key):
        rows = specs_map[specs_map["title_key"] == title_key]
        non_empty = [s for s in rows["specs"] if len(s) > 0]
        if len(non_empty) < 2:
            return True
        return len(set(non_empty)) == 1

    multi["specs_ok"] = multi["title_key"].apply(specs_compatible)
    multi = multi[multi["specs_ok"]].copy()
    if multi.empty:
        return multi

    multi["min_price"]  = multi[src_cols].min(axis=1)
    multi["max_price"]  = multi[src_cols].max(axis=1)
    multi["saving"]     = multi["max_price"] - multi["min_price"]
    multi["saving_pct"] = (multi["saving"] / multi["max_price"] * 100).round(1)

    multi = multi[
        (multi["saving_pct"] <= 40) &
        (multi["min_price"] >= multi["max_price"] * 0.60)
    ].copy()

    multi = multi.rename(columns={"title_key": "title"})
    return multi.sort_values("saving_pct", ascending=False)

def get_best_deals(df):
    if "discount" not in df.columns:
        return pd.DataFrame()
    d = df.copy()
    d["discount_num"] = pd.to_numeric(
        d["discount"].astype(str).str.replace("%","").str.replace("None","0"),
        errors="coerce"
    ).fillna(0)
    return d[d["discount_num"] > 0].sort_values("discount_num", ascending=False).head(20)

def get_cheapest_source(df):
    if "category" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby(["category","source"])["price"].mean().reset_index()
    grp.columns = ["category","source","avg_price"]
    idx = grp.groupby("category")["avg_price"].idxmin()
    return grp.loc[idx].sort_values("avg_price")


def show():
    inject_css()

    
    st.markdown("""
    <div style="padding:16px 0 8px">
        <h1 style="font-size:2rem;font-weight:900;margin:0">
            ⚡ <span style="color:
            <span class="live-dot"></span>
        </h1>
        <p style="color:
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    
    connected = st.session_state.get("kafka_connected", None)
    status_col, c1, c2, c3 = st.columns([3, 2, 1, 1])

    with status_col:
        if connected is True:
            st.markdown(f'<div class="kafka-connected">🟢 Kafka Connected &nbsp;|&nbsp; Broker: {KAFKA_BROKER}</div>', unsafe_allow_html=True)
        elif connected is False:
            st.markdown(f'<div class="kafka-disconnected">🔴 Kafka Disconnected &nbsp;|&nbsp; {KAFKA_BROKER}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="kafka-disconnected">⚪ Kafka: Not connected yet</div>', unsafe_allow_html=True)
    with c1:
        auto = st.toggle("Auto Refresh (5s)", value=True)
    with c2:
        manual = st.button("🔄 Refresh")
    with c3:
        if st.button("🗑️ Clear"):
            st.session_state.stream_df = pd.DataFrame()
            st.session_state.msg_count = 0
            if "kafka_consumer" in st.session_state:
                del st.session_state["kafka_consumer"]
            st.rerun()

    
    if "stream_df" not in st.session_state:
        st.session_state.stream_df = pd.DataFrame()
    if "msg_count" not in st.session_state:
        st.session_state.msg_count = 0

    
    if auto or manual:
        msgs = fetch_messages()
        if msgs:
            st.session_state.stream_df = accumulate(st.session_state.stream_df, msgs)

    df = st.session_state.stream_df

    if df.empty:
        st.info("⏳ Waiting for data from Kafka... Make sure kafka_producer.py is running.")
        if auto:
            time.sleep(3)
            st.rerun()
        return

    
    df.columns = [c.lower() for c in df.columns]
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
    if "discount" not in df.columns:
        df["discount"] = "0%"
    df["discount"] = df["discount"].fillna("0%").replace("None","0%")

    
    with st.sidebar:
        st.markdown("### 🔍 Live Filters")
        all_cats = sorted(df["category"].dropna().unique().tolist()) if "category" in df.columns else []
        sel_cats = st.multiselect("Category", all_cats, default=all_cats)
        all_src  = sorted(df["source"].dropna().unique().tolist()) if "source" in df.columns else []
        sel_src  = st.multiselect("Platform", all_src, default=all_src)

    if sel_cats: df = df[df["category"].isin(sel_cats)]
    if sel_src:  df = df[df["source"].isin(sel_src)]

    
    st.markdown('<div class="section-title">📊 Live Market Overview</div>', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)

    disc = df.copy()
    disc["disc_num"] = pd.to_numeric(
        disc["discount"].astype(str).str.replace("%","").str.replace("None","0"),
        errors="coerce"
    ).fillna(0)
    deals_count = int((disc["disc_num"] > 0).sum())

    with k1: kpi("Tracked Products", f"{len(df):,}", "unique live")
    with k2: kpi("Categories", str(df["category"].nunique() if "category" in df.columns else 0), "active", "
    with k3: kpi("Platforms", str(df["source"].nunique() if "source" in df.columns else 0), "connected", "
    with k4: kpi("Products w/ Deals", f"{deals_count:,}", "have discount", "

    
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-title">📡 Live Platform Activity</div>', unsafe_allow_html=True)
        if "source" in df.columns:
            src_counts = df.groupby("source").size().reset_index(name="count")
            fig_act = px.pie(
                src_counts, values="count", names="source",
                color="source", color_discrete_map=COLORS,
                hole=0.5, template="plotly_dark",
            )
            fig_act.update_layout(
                paper_bgcolor=CARD_BG, height=300,
                margin=dict(l=0,r=0,t=10,b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2),
            )
            fig_act.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_act, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-title">🏆 Cheapest Platform per Category</div>', unsafe_allow_html=True)
        cheap = get_cheapest_source(df)
        if not cheap.empty:
            fig_cheap = px.bar(
                cheap, x="category", y="avg_price", color="source",
                color_discrete_map=COLORS, template="plotly_dark",
                labels={"avg_price":"Avg Price (EGP)","category":"Category"},
                text=cheap["source"].str.capitalize(),
            )
            fig_cheap.update_layout(
                paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
                height=300, margin=dict(l=0,r=0,t=10,b=0), showlegend=False
            )
            fig_cheap.update_traces(textposition="outside")
            st.plotly_chart(fig_cheap, use_container_width=True)

    
    st.markdown('<div class="section-title">⚖️ Same Product — Price Comparison Across Platforms</div>', unsafe_allow_html=True)
    comp = get_price_comparison(df)
    if comp.empty:
        st.info("⏳ Waiting for same products from multiple platforms to appear...")
    else:
        src_cols = [c for c in ["jumia","noon","amazon"] if c in comp.columns]
        url_cols = [f"{c}_url" for c in src_cols if f"{c}_url" in comp.columns]
        col_cfg  = {
            "title":      st.column_config.TextColumn("Product", width="large"),
            "saving_pct": st.column_config.NumberColumn("💰 Save %", format="%.1f%%"),
            "saving":     st.column_config.NumberColumn("Save (EGP)", format="EGP %.0f"),
        }
        for s in src_cols:
            col_cfg[s] = st.column_config.NumberColumn(s.capitalize(), format="EGP %.0f")
        for u in url_cols:
            col_cfg[u] = st.column_config.LinkColumn(f"🔗 {u.replace('_url','').capitalize()}")

        show_cols = ["title"] + src_cols + url_cols + ["saving","saving_pct"]
        show_cols = [c for c in show_cols if c in comp.columns]
        st.dataframe(comp[show_cols].head(20).reset_index(drop=True),
                     use_container_width=True, height=380, column_config=col_cfg)
        st.caption("⚠️ Matching based on product name similarity. Always verify via links before purchase.")

    
    st.markdown('<div class="section-title">📦 Live Price Distribution by Category</div>', unsafe_allow_html=True)
    if "category" in df.columns and "price" in df.columns:
        df_valid = df.dropna(subset=["price","category"])
        if not df_valid.empty:
            fig_box = px.box(
                df_valid, x="category", y="price", color="source",
                color_discrete_map=COLORS, template="plotly_dark",
                labels={"price": "Price (EGP)", "category": "Category"},
                points=False,
            )
            fig_box.update_layout(
                paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
                height=380, margin=dict(l=0,r=0,t=10,b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_box, use_container_width=True)

    
    st.markdown('<div class="section-title">🔥 Best Deals Now</div>', unsafe_allow_html=True)
    deals = get_best_deals(df)
    if not deals.empty:
        show = [c for c in ["title","source","category","price","old_price","discount"] if c in deals.columns]
        st.dataframe(
            deals[show].head(15).reset_index(drop=True),
            use_container_width=True, height=350,
            column_config={
                "title":     st.column_config.TextColumn("Product", width="large"),
                "price":     st.column_config.NumberColumn("Price", format="EGP %.0f"),
                "old_price": st.column_config.NumberColumn("Old Price", format="EGP %.0f"),
                "discount":  st.column_config.TextColumn("Discount"),
                "source":    st.column_config.TextColumn("Platform"),
            }
        )

    
    st.markdown('<div class="section-title">🔴 Live Feed</div>', unsafe_allow_html=True)
    total_msgs = st.session_state.get("msg_count", 0)
    st.caption(f"Total messages received this session: {total_msgs:,}")
    feed_cols = [c for c in ["fetched_at","source","category","title","price","discount"] if c in df.columns]
    st.dataframe(
        df[feed_cols].sort_values("fetched_at", ascending=False).head(30).reset_index(drop=True),
        use_container_width=True, height=280,
        column_config={
            "fetched_at": st.column_config.TextColumn("Time"),
            "title":      st.column_config.TextColumn("Product", width="large"),
            "price":      st.column_config.NumberColumn("Price (EGP)", format="EGP %.0f"),
            "source":     st.column_config.TextColumn("Platform"),
            "discount":   st.column_config.TextColumn("Discount"),
        }
    )

    
    if auto:
        time.sleep(5)
        st.rerun()
