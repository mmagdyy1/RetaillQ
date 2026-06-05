import boto3
import pandas as pd
import snowflake.connector
import io
import os
import re
import hashlib
import datetime

# AWS Config
AWS_ACCESS_KEY_ID     = "AKIA5NRD5HQT35JDETQ2"
AWS_SECRET_ACCESS_KEY = "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"
S3_BUCKET             = "retailiq-datalake"
S3_PREFIX             = "raw/products/"

# Snowflake Config
SF_USER      = "MMAGDYY1"
SF_PASSWORD  = "Mohamed12345@#"
SF_ACCOUNT   = "kpvhttk-ir63402"
SF_DATABASE  = "RETAILQ"
SF_WAREHOUSE = "COMPUTE_WH"

def read_parquet_from_s3():
    print("Reading from S3...")
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name="us-east-1"
    )
    objects = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    if "Contents" not in objects:
        print("No files found in S3.")
        return None
    dfs = []
    for obj in objects["Contents"]:
        key = obj["Key"]
        if key.endswith(".parquet"):
            response = s3.get_object(Bucket=S3_BUCKET, Key=key)
            df = pd.read_parquet(io.BytesIO(response["Body"].read()))
            dfs.append(df)
            print(f"  Read: {key} ({len(df)} rows)")
    if not dfs:
        return None
    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.drop_duplicates()
    print(f"Total rows: {len(combined)}")
    return combined

def make_product_id(row):
    key = f"{row.get('source','')}_{row.get('title','')}_{row.get('price','')}".lower()
    return hashlib.md5(key.encode()).hexdigest()

def clean_discount(val):
    if pd.isna(val) or str(val).strip().lower() in ["", "none", "nan"]:
        return None
    match = re.search(r"(\d+(\.\d+)?)", str(val))
    return float(match.group(1)) if match else None

def clean_rating(val):
    if pd.isna(val) or str(val).strip().lower() in ["", "none", "nan"]:
        return None
    match = re.search(r"(\d+(\.\d+)?)", str(val))
    return float(match.group(1)) if match else None

def clean_reviews(val):
    if pd.isna(val) or str(val).strip().lower() in ["", "none", "nan"]:
        return "0"
    cleaned = re.sub(r"[(),\s]", "", str(val))
    return cleaned if cleaned.isdigit() else "0"

# تطبيع أسماء الكاتيجوريز — يمنع مشكلة "laptop" vs "laptops"
CATEGORY_MAP = {
    "laptop":     "laptops",
    "mobile":     "mobiles",
    "tablet":     "tablets",
    "tv":         "televisions",
    "headphone":  "headphones",
}

def normalize_category(val):
    if pd.isna(val):
        return val
    return CATEGORY_MAP.get(str(val).strip().lower(), str(val).strip().lower())

def clean_data(df):
    print("Cleaning data...")
    df = df.dropna(subset=["title", "price"])
    df["price"]      = pd.to_numeric(df["price"], errors="coerce")
    df["old_price"]  = pd.to_numeric(df["old_price"], errors="coerce")
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df = df[df["price"] > 0]
    df["category"]   = df["category"].apply(normalize_category)
    df["product_id"] = df.apply(make_product_id, axis=1)
    df["discount"] = df["discount"].apply(clean_discount)
    mask = df["discount"].isna() & df["old_price"].notna() & (df["old_price"] > df["price"])
    df.loc[mask, "discount"] = ((df["old_price"] - df["price"]) / df["old_price"] * 100).round(1)
    df["discount"] = df["discount"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "0%")
    df["rating"]  = df["rating"].apply(clean_rating)
    df["reviews"] = df["reviews"].apply(clean_reviews)
    print(f"Clean rows: {len(df)}")
    return df

def get_conn(schema="SILVER"):
    return snowflake.connector.connect(
        user=SF_USER, password=SF_PASSWORD, account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE, database=SF_DATABASE, schema=schema
    )

# ──────────────────────────────────────────────────────────────
# SILVER — MERGE على (product_id, DATE(scraped_at))
# نفس المنتج في نفس اليوم → UPDATE السعر
# منتج جديد أو يوم جديد → INSERT
# ──────────────────────────────────────────────────────────────
def load_silver(df):
    print("Loading Silver (MERGE)...")
    conn = get_conn("SILVER")
    cur  = conn.cursor()

    # Staging table مؤقتة للـ session
    cur.execute("""
        CREATE OR REPLACE TEMPORARY TABLE SILVER_STAGING (
            product_id  VARCHAR,
            src         VARCHAR,
            category    VARCHAR,
            title       VARCHAR,
            price       FLOAT,
            old_price   FLOAT,
            discount    VARCHAR,
            rating      FLOAT,
            reviews     VARCHAR,
            url         VARCHAR,
            image       VARCHAR,
            scraped_at  TIMESTAMP_NTZ
        )
    """)

    # Dedup: لو نفس المنتج اتسحب أكتر من مرة في نفس اليوم → خد آخر record
    df_dedup = df.copy()
    df_dedup["scraped_date"] = df_dedup["scraped_at"].dt.date
    df_dedup = (
        df_dedup
        .sort_values("scraped_at")
        .drop_duplicates(subset=["product_id", "scraped_date"], keep="last")
        .drop(columns=["scraped_date"])
    )
    print(f"  After dedup: {len(df_dedup)} rows (was {len(df)})")

    rows = []
    for _, row in df_dedup.iterrows():
        rows.append((
            str(row.get("product_id", "")),
            str(row.get("source", "")),
            str(row.get("category", "")),
            str(row.get("title", "")),
            float(row["price"])     if pd.notna(row["price"])          else None,
            float(row["old_price"]) if pd.notna(row.get("old_price"))  else None,
            str(row.get("discount", "0%")),
            float(row["rating"])    if pd.notna(row.get("rating"))     else None,
            str(row.get("reviews", "0")),
            str(row.get("url", "")),
            str(row.get("image", "")),
            str(row["scraped_at"])  if pd.notna(row.get("scraped_at")) else None,
        ))

    cur.executemany(
        "INSERT INTO SILVER_STAGING VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        rows
    )

    # Dedup جوه Snowflake: لو نفس المنتج في نفس اليوم أكتر من مرة → خد الأحدث
    cur.execute("""
        CREATE OR REPLACE TEMPORARY TABLE SILVER_STAGING_DEDUP AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, DATE(scraped_at)
                       ORDER BY scraped_at DESC NULLS LAST
                   ) AS rn
            FROM SILVER_STAGING
            WHERE scraped_at IS NOT NULL
        )
        WHERE rn = 1
    """)

    cur.execute("""
        MERGE INTO RETAILQ.SILVER.PRODUCTS AS tgt
        USING SILVER_STAGING_DEDUP AS stg
        ON  tgt.product_id = stg.product_id
        AND DATE(tgt.scraped_at) = DATE(stg.scraped_at)
        WHEN MATCHED THEN UPDATE SET
            category   = stg.category,
            price      = stg.price,
            old_price  = stg.old_price,
            discount   = stg.discount,
            rating     = stg.rating,
            reviews    = stg.reviews,
            scraped_at = stg.scraped_at
        WHEN NOT MATCHED THEN INSERT
            (product_id, source, category, title, price, old_price,
             discount, rating, reviews, url, image, scraped_at)
        VALUES
            (stg.product_id, stg.src, stg.category, stg.title,
             stg.price, stg.old_price, stg.discount, stg.rating,
             stg.reviews, stg.url, stg.image, stg.scraped_at)
    """)

    cur.execute("SELECT COUNT(*) FROM RETAILQ.SILVER.PRODUCTS")
    print(f"  Silver total rows: {cur.fetchone()[0]}")
    cur.close()
    conn.close()

# ──────────────────────────────────────────────────────────────
# GOLD STAR SCHEMA
# ──────────────────────────────────────────────────────────────
def load_star_schema(df):
    print("Building Star Schema...")
    conn = get_conn("GOLD")
    cur  = conn.cursor()

    # ── DIM_PRODUCT — MERGE (SCD Type 1) ─────────────────────
    # محتفظين بكل المنتجات اللي شفناها من أول المشروع
    # لو بيانات المنتج اتغيرت → UPDATE (title/url/image)
    # لو منتج جديد → INSERT
    cur.execute("""
        CREATE OR REPLACE TEMPORARY TABLE DIM_PRODUCT_STAGING (
            product_id VARCHAR, title VARCHAR, url VARCHAR, image VARCHAR
        )
    """)
    products = df[["product_id","title","url","image"]].drop_duplicates("product_id")
    cur.executemany(
        "INSERT INTO DIM_PRODUCT_STAGING VALUES (%s,%s,%s,%s)",
        [(r.product_id, r.title, r.url, r.image) for _, r in products.iterrows()]
    )
    cur.execute("""
        MERGE INTO RETAILQ.GOLD.DIM_PRODUCT AS tgt
        USING DIM_PRODUCT_STAGING AS stg
        ON tgt.product_id = stg.product_id
        WHEN MATCHED THEN UPDATE SET
            title = stg.title,
            url   = stg.url,
            image = stg.image
        WHEN NOT MATCHED THEN INSERT (product_id, title, url, image)
        VALUES (stg.product_id, stg.title, stg.url, stg.image)
    """)
    cur.execute("SELECT COUNT(*) FROM RETAILQ.GOLD.DIM_PRODUCT")
    print(f"  DIM_PRODUCT: {cur.fetchone()[0]} total rows.")

    # ── DIM_SOURCE — MERGE (insert new only) ─────────────────
    # بنحتفظ بالـ source_id القديم علشان ما نكسرش الـ FK في FACT
    cur.execute("""
        CREATE OR REPLACE TEMPORARY TABLE DIM_SOURCE_STAGING (
            source_name VARCHAR
        )
    """)
    sources = df["source"].dropna().unique().tolist()
    cur.executemany(
        "INSERT INTO DIM_SOURCE_STAGING VALUES (%s)",
        [(s,) for s in sources]
    )
    cur.execute("""
        MERGE INTO RETAILQ.GOLD.DIM_SOURCE AS tgt
        USING DIM_SOURCE_STAGING AS stg
        ON tgt.source_name = stg.source_name
        WHEN NOT MATCHED THEN INSERT (source_name)
        VALUES (stg.source_name)
    """)
    cur.execute("SELECT COUNT(*) FROM RETAILQ.GOLD.DIM_SOURCE")
    print(f"  DIM_SOURCE: {cur.fetchone()[0]} rows.")

    # ── DIM_CATEGORY — MERGE (insert new only) ───────────────
    # نفس منطق DIM_SOURCE
    cur.execute("""
        CREATE OR REPLACE TEMPORARY TABLE DIM_CATEGORY_STAGING (
            category_name VARCHAR
        )
    """)
    cats = df["category"].dropna().unique().tolist()
    cur.executemany(
        "INSERT INTO DIM_CATEGORY_STAGING VALUES (%s)",
        [(c,) for c in cats]
    )
    cur.execute("""
        MERGE INTO RETAILQ.GOLD.DIM_CATEGORY AS tgt
        USING DIM_CATEGORY_STAGING AS stg
        ON tgt.category_name = stg.category_name
        WHEN NOT MATCHED THEN INSERT (category_name)
        VALUES (stg.category_name)
    """)
    cur.execute("SELECT COUNT(*) FROM RETAILQ.GOLD.DIM_CATEGORY")
    print(f"  DIM_CATEGORY: {cur.fetchone()[0]} rows.")

    # ── DIM_DATE — INSERT new dates only ─────────────────────
    # ما بنمسحش التواريخ القديمة — بنضيف الجديد بس
    dates = df["scraped_at"].dropna().dt.date.unique()
    date_rows = []
    for d in dates:
        dt = pd.Timestamp(d)
        date_id = int(dt.strftime("%Y%m%d"))
        date_rows.append((
            date_id, str(d),
            dt.day, dt.month, dt.year, dt.quarter,
            dt.strftime("%B"), dt.strftime("%A"),
            date_id
        ))
    inserted_dates = 0
    for row in date_rows:
        cur.execute("""
            INSERT INTO RETAILQ.GOLD.DIM_DATE
                (date_id, full_date, day, month, year, quarter, month_name, day_name)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM RETAILQ.GOLD.DIM_DATE WHERE date_id = %s
            )
        """, row)
        inserted_dates += 1
    print(f"  DIM_DATE: processed {inserted_dates} dates.")

    # ── FACT_PRICES — MERGE على (product_id, source_id, date_id) ─
    # ما بنكررش نفس المنتج من نفس المصدر في نفس اليوم
    # بيتراكم مع الوقت → price history حقيقي
    cur.execute("""
        MERGE INTO RETAILQ.GOLD.FACT_PRICES AS tgt
        USING (
            SELECT
                p.product_id,
                s.source_id,
                c.category_id,
                CAST(TO_CHAR(sp.scraped_at, 'YYYYMMDD') AS NUMBER) AS date_id,
                sp.price, sp.old_price, sp.discount,
                sp.rating, sp.reviews, sp.scraped_at
            FROM RETAILQ.SILVER.PRODUCTS sp
            JOIN RETAILQ.GOLD.DIM_PRODUCT  p ON p.product_id    = sp.product_id
            JOIN RETAILQ.GOLD.DIM_SOURCE   s ON s.source_name   = sp.source
            JOIN RETAILQ.GOLD.DIM_CATEGORY c ON c.category_name = sp.category
            WHERE sp.scraped_at IS NOT NULL
        ) AS src
        ON  tgt.product_id = src.product_id
        AND tgt.source_id  = src.source_id
        AND tgt.date_id    = src.date_id
        WHEN NOT MATCHED THEN INSERT
            (product_id, source_id, category_id, date_id,
             price, old_price, discount, rating, reviews, scraped_at)
        VALUES
            (src.product_id, src.source_id, src.category_id, src.date_id,
             src.price, src.old_price, src.discount,
             src.rating, src.reviews, src.scraped_at)
    """)
    cur.execute("SELECT COUNT(*) FROM RETAILQ.GOLD.FACT_PRICES")
    print(f"  FACT_PRICES: {cur.fetchone()[0]} total rows.")

    # ── Gold Views ────────────────────────────────────────────
    print("Refreshing Gold views...")

    cur.execute("""
        CREATE OR REPLACE VIEW RETAILQ.GOLD.CATEGORY_TRENDS AS
        SELECT
            c.category_name AS category,
            s.source_name   AS source,
            AVG(f.price)    AS avg_price,
            MIN(f.price)    AS min_price,
            MAX(f.price)    AS max_price,
            COUNT(*)        AS product_count
        FROM RETAILQ.GOLD.FACT_PRICES f
        JOIN RETAILQ.GOLD.DIM_CATEGORY c ON c.category_id = f.category_id
        JOIN RETAILQ.GOLD.DIM_SOURCE   s ON s.source_id   = f.source_id
        GROUP BY c.category_name, s.source_name
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW RETAILQ.GOLD.TOP_DEALS AS
        SELECT
            p.title, s.source_name AS source, c.category_name AS category,
            f.price, f.old_price, f.discount, f.rating, p.url
        FROM RETAILQ.GOLD.FACT_PRICES f
        JOIN RETAILQ.GOLD.DIM_PRODUCT  p ON p.product_id   = f.product_id
        JOIN RETAILQ.GOLD.DIM_SOURCE   s ON s.source_id    = f.source_id
        JOIN RETAILQ.GOLD.DIM_CATEGORY c ON c.category_id  = f.category_id
        WHERE f.old_price IS NOT NULL AND f.old_price > f.price
        QUALIFY ROW_NUMBER() OVER (PARTITION BY p.title ORDER BY (f.old_price - f.price) DESC) = 1
        ORDER BY (f.old_price - f.price) DESC
        LIMIT 100
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW RETAILQ.GOLD.SOURCE_SUMMARY AS
        SELECT
            s.source_name            AS source,
            COUNT(*)                 AS total_products,
            AVG(f.price)             AS avg_price,
            MIN(f.price)             AS min_price,
            MAX(f.price)             AS max_price,
            COUNT(DISTINCT f.category_id) AS categories_count
        FROM RETAILQ.GOLD.FACT_PRICES f
        JOIN RETAILQ.GOLD.DIM_SOURCE s ON s.source_id = f.source_id
        GROUP BY s.source_name
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW RETAILQ.GOLD.TOP_RATED AS
        SELECT
            p.title, s.source_name AS source, c.category_name AS category,
            f.price, f.rating, f.reviews, p.url
        FROM RETAILQ.GOLD.FACT_PRICES f
        JOIN RETAILQ.GOLD.DIM_PRODUCT  p ON p.product_id  = f.product_id
        JOIN RETAILQ.GOLD.DIM_SOURCE   s ON s.source_id   = f.source_id
        JOIN RETAILQ.GOLD.DIM_CATEGORY c ON c.category_id = f.category_id
        WHERE f.rating IS NOT NULL AND f.rating > 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY c.category_name ORDER BY f.rating DESC NULLS LAST) <= 20
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW RETAILQ.GOLD.BEST_VALUE AS
        SELECT
            p.title, s.source_name AS source, c.category_name AS category,
            f.price, f.rating, f.discount,
            ROUND((f.rating / NULLIF(f.price,0)) * 10000, 4) AS value_score,
            p.url
        FROM RETAILQ.GOLD.FACT_PRICES f
        JOIN RETAILQ.GOLD.DIM_PRODUCT  p ON p.product_id  = f.product_id
        JOIN RETAILQ.GOLD.DIM_SOURCE   s ON s.source_id   = f.source_id
        JOIN RETAILQ.GOLD.DIM_CATEGORY c ON c.category_id = f.category_id
        WHERE f.rating IS NOT NULL AND f.rating > 0
          AND f.price >= (
              SELECT PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY price)
              FROM RETAILQ.SILVER.PRODUCTS sp2
              WHERE sp2.category = c.category_name
          )
        QUALIFY ROW_NUMBER() OVER (PARTITION BY c.category_name ORDER BY (f.rating / NULLIF(f.price,0)) DESC NULLS LAST) <= 20
    """)

    print("  All views refreshed.")
    cur.close()
    conn.close()

def run():
    df = read_parquet_from_s3()
    if df is None:
        return
    df = clean_data(df)
    load_silver(df)
    load_star_schema(df)
    print("Done!")

run()
