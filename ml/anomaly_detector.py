"""
Static Price Anomaly Detector
==============================
Focuses on REAL anomalies:
  1. Scraping errors  — price suspiciously low (bottom 1% of category)
  2. Fake discounts   — discount > 70% (suspicious original price)
  3. Price too low    — price < 1% of category median (data error)

Does NOT flag premium/expensive products as anomalies.

Output -> RETAILQ.GOLD.PRICE_ANOMALIES
"""

import pandas as pd
import numpy as np
import snowflake.connector

SF_USER      = "MMAGDYY1"
SF_PASSWORD  = "YOUR_SNOWFLAKE_PASSWORD"
SF_ACCOUNT   = "kpvhttk-ir63402"
SF_DATABASE  = "RETAILQ"
SF_WAREHOUSE = "COMPUTE_WH"

MAX_DISCOUNT     = 70.0   
MIN_PRODUCTS_CAT = 5      
MIN_PRICE_RATIO  = 0.05   

def get_conn(schema="SILVER"):
    return snowflake.connector.connect(
        user=SF_USER, password=SF_PASSWORD, account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE, database=SF_DATABASE, schema=schema
    )

def safe_float(v):
    try:
        f = float(v)
        return None if (f != f) else f
    except:
        return None

def load_silver():
    print("Loading Silver products...")
    conn = get_conn("SILVER")
    df = pd.read_sql("""
        SELECT product_id, source, category, title,
               price, old_price, discount, url
        FROM RETAILQ.SILVER.PRODUCTS
        WHERE price > 0
    """, conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    df["discount_num"] = pd.to_numeric(
        df["discount"].astype(str).str.replace("%","").str.replace("None","0"),
        errors="coerce"
    ).fillna(0)
    print(f"  Loaded {len(df)} products.")
    return df

def detect_scraping_errors(df):
    """
    Detect prices that are suspiciously LOW — likely scraping errors.
    A product priced at less than 1% of its category median is almost
    certainly a data error (e.g., laptop at EGP 5 instead of EGP 5,000).
    """
    anomalies = []
    for cat, grp in df.groupby("category"):
        if len(grp) < MIN_PRODUCTS_CAT:
            continue
        median_p = grp["price"].median()
        
        threshold = median_p * MIN_PRICE_RATIO
        flagged   = grp[grp["price"] < threshold]
        for _, r in flagged.iterrows():
            z = (r["price"] - grp["price"].mean()) / grp["price"].std() if grp["price"].std() > 0 else 0
            anomalies.append({
                "product_id":    r["product_id"],
                "source":        r["source"],
                "category":      cat,
                "title":         r["title"],
                "price":         r["price"],
                "avg_cat_price": round(median_p, 2),
                "std_cat_price": round(grp["price"].std(), 2),
                "z_score":       round(z, 3),
                "anomaly_type":  "SCRAPING_ERROR_PRICE_TOO_LOW",
                "severity":      "HIGH",
                "url":           r["url"],
            })
    print(f"  Scraping error anomalies: {len(anomalies)}")
    return anomalies

def detect_fake_discounts(df):
    """
    Detect products with unrealistically high discounts (>70%).
    This often indicates a fake original price to make the deal
    look better than it is — common dark pattern in e-commerce.
    """
    anomalies = []
    flagged = df[df["discount_num"] > MAX_DISCOUNT]
    for _, r in flagged.iterrows():
        cat_grp = df[df["category"] == r["category"]]
        median_p = cat_grp["price"].median()
        std_p    = cat_grp["price"].std()
        z = (r["price"] - cat_grp["price"].mean()) / std_p if std_p > 0 else 0
        anomalies.append({
            "product_id":    r["product_id"],
            "source":        r["source"],
            "category":      r["category"],
            "title":         r["title"],
            "price":         r["price"],
            "avg_cat_price": round(median_p, 2),
            "std_cat_price": round(std_p, 2) if std_p else 0,
            "z_score":       round(z, 3),
            "anomaly_type":  f"SUSPICIOUS_DISCOUNT_{int(r['discount_num'])}PCT",
            "severity":      "HIGH" if r["discount_num"] > 85 else "MEDIUM",
            "url":           r["url"],
        })
    print(f"  Fake discount anomalies: {len(anomalies)}")
    return anomalies

def detect_impossible_prices(df):
    """
    Detect products where old_price exists but is LESS than price
    (meaning the 'discount' is actually a price increase — data error).
    """
    anomalies = []
    flagged = df[df["old_price"].notna() & (df["old_price"] < df["price"])]
    for _, r in flagged.iterrows():
        cat_grp  = df[df["category"] == r["category"]]
        median_p = cat_grp["price"].median()
        anomalies.append({
            "product_id":    r["product_id"],
            "source":        r["source"],
            "category":      r["category"],
            "title":         r["title"],
            "price":         r["price"],
            "avg_cat_price": round(median_p, 2),
            "std_cat_price": 0,
            "z_score":       0,
            "anomaly_type":  "OLD_PRICE_LESS_THAN_CURRENT",
            "severity":      "MEDIUM",
            "url":           r["url"],
        })
    print(f"  Impossible price anomalies: {len(anomalies)}")
    return anomalies

def combine_anomalies(all_lists):
    combined = []
    for lst in all_lists:
        combined.extend(lst)
    df = pd.DataFrame(combined)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["product_id","source"], keep="first")
    df = df.reset_index(drop=True)
    print(f"\nTotal unique anomalies: {len(df)}")
    return df

def save_anomalies(df):
    if df.empty:
        print("No anomalies to save.")
        return
    print("Saving to GOLD.PRICE_ANOMALIES...")
    conn = get_conn("GOLD")
    cur  = conn.cursor()
    cur.execute("TRUNCATE TABLE RETAILQ.GOLD.PRICE_ANOMALIES")
    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r.get("product_id","")),
            str(r.get("source","")),
            str(r.get("category","")),
            str(r.get("title","")),
            safe_float(r.get("price")),
            safe_float(r.get("avg_cat_price")),
            safe_float(r.get("std_cat_price")),
            safe_float(r.get("z_score")),
            str(r.get("anomaly_type","")),
            str(r.get("severity","")),
            str(r.get("url","")),
        ))
    cur.executemany("""
        INSERT INTO RETAILQ.GOLD.PRICE_ANOMALIES
        (product_id, source, category, title, price,
         avg_cat_price, std_cat_price, z_score,
         anomaly_type, severity, url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, rows)
    print(f"  Saved {len(rows)} anomalies.")
    cur.close()
    conn.close()

def print_summary(df):
    if df.empty:
        return
    print("\n── Anomaly Summary ──────────────────────")
    print(df.groupby(["severity","anomaly_type"]).size()
          .reset_index(name="count").to_string(index=False))
    print(f"\nHigh:   {len(df[df['severity']=='HIGH'])}")
    print(f"Medium: {len(df[df['severity']=='MEDIUM'])}")

def run():
    df = load_silver()
    print("\nRunning anomaly detection...")
    scraping  = detect_scraping_errors(df)
    discounts = detect_fake_discounts(df)
    impossible = detect_impossible_prices(df)
    anomalies = combine_anomalies([scraping, discounts, impossible])
    print_summary(anomalies)
    save_anomalies(anomalies)
    print("\nDone!")

run()
