import boto3
import pandas as pd
import snowflake.connector
import io
import os
import re
import hashlib

# AWS Config
AWS_ACCESS_KEY_ID     = "YOUR_AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY = "p9sJFXL5tWKPytGyhanZp9PGrKG3o2kMq+NZDcgr"
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
    """Generate stable unique ID from source + title + price"""
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
    """Remove parentheses/commas, return number. e.g. '(1,234)' -> '1234', empty -> '0'"""
    if pd.isna(val) or str(val).strip().lower() in ["", "none", "nan"]:
        return "0"
    cleaned = re.sub(r"[(),\s]", "", str(val))
    return cleaned if cleaned.isdigit() else "0"

def clean_data(df):
    print("Cleaning data...")

    df = df.dropna(subset=["title", "price"])
    df["price"]      = pd.to_numeric(df["price"], errors="coerce")
    df["old_price"]  = pd.to_numeric(df["old_price"], errors="coerce")
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df = df[df["price"] > 0]

    # Stable product_id from hash
    df["product_id"] = df.apply(make_product_id, axis=1)

    # Discount: extract number, calculate if missing, format as "17.0%", null → "0%"
    df["discount"] = df["discount"].apply(clean_discount)
    mask = df["discount"].isna() & df["old_price"].notna() & (df["old_price"] > df["price"])
    df.loc[mask, "discount"] = ((df["old_price"] - df["price"]) / df["old_price"] * 100).round(1)
    df["discount"] = df["discount"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "0%")

    # Rating: numeric only
    df["rating"] = df["rating"].apply(clean_rating)

    # Reviews: number only, empty → "0"
    df["reviews"] = df["reviews"].apply(clean_reviews)

    print(f"Clean rows: {len(df)}")
    return df

def load_to_snowflake(df):
    print("Connecting to Snowflake...")
    conn = snowflake.connector.connect(
        user=SF_USER,
        password=SF_PASSWORD,
        account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
        schema="SILVER"
    )
    cursor = conn.cursor()

    cursor.execute("TRUNCATE TABLE RETAILQ.SILVER.PRODUCTS")

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("product_id", "")),
            str(row.get("source", "")),
            str(row.get("category", "")),
            str(row.get("title", "")),
            float(row["price"]) if pd.notna(row["price"]) else None,
            float(row["old_price"]) if pd.notna(row.get("old_price")) else None,
            str(row.get("discount", "")) if pd.notna(row.get("discount")) else None,
            float(row["rating"]) if pd.notna(row.get("rating")) else None,
            str(row.get("reviews", "")),
            str(row.get("url", "")),
            str(row.get("image", "")),
            str(row["scraped_at"]) if pd.notna(row.get("scraped_at")) else None,
        ))

    cursor.executemany("""
        INSERT INTO RETAILQ.SILVER.PRODUCTS
        (product_id, source, category, title, price, old_price,
         discount, rating, reviews, url, image, scraped_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, rows)

    print(f"Inserted {len(rows)} rows into Silver.")
    cursor.close()
    conn.close()

def build_gold(conn):
    print("Building Gold tables...")
    cursor = conn.cursor()

    # CATEGORY_TRENDS
    cursor.execute("TRUNCATE TABLE RETAILQ.GOLD.CATEGORY_TRENDS")
    cursor.execute("""
        INSERT INTO RETAILQ.GOLD.CATEGORY_TRENDS
        SELECT
            category,
            source,
            AVG(price)   AS avg_price,
            MIN(price)   AS min_price,
            MAX(price)   AS max_price,
            COUNT(*)     AS product_count,
            CURRENT_TIMESTAMP()
        FROM RETAILQ.SILVER.PRODUCTS
        GROUP BY category, source
    """)
    print("  CATEGORY_TRENDS done.")

    # TOP_DEALS
    cursor.execute("TRUNCATE TABLE RETAILQ.GOLD.TOP_DEALS")
    cursor.execute("""
        INSERT INTO RETAILQ.GOLD.TOP_DEALS
        SELECT
            source,
            category,
            title,
            price,
            old_price,
            discount,
            rating,
            url,
            CURRENT_TIMESTAMP()
        FROM RETAILQ.SILVER.PRODUCTS
        WHERE old_price IS NOT NULL
          AND old_price > price
          AND price > 0
        ORDER BY (old_price - price) DESC
        LIMIT 100
    """)
    print("  TOP_DEALS done.")

    # SOURCE_SUMMARY
    cursor.execute("TRUNCATE TABLE RETAILQ.GOLD.SOURCE_SUMMARY")
    cursor.execute("""
        INSERT INTO RETAILQ.GOLD.SOURCE_SUMMARY
        SELECT
            source,
            COUNT(*)                    AS total_products,
            AVG(price)                  AS avg_price,
            MIN(price)                  AS min_price,
            MAX(price)                  AS max_price,
            COUNT(DISTINCT category)    AS categories_count,
            CURRENT_TIMESTAMP()
        FROM RETAILQ.SILVER.PRODUCTS
        GROUP BY source
    """)
    print("  SOURCE_SUMMARY done.")

    # TOP_RATED
    cursor.execute("TRUNCATE TABLE RETAILQ.GOLD.TOP_RATED")
    cursor.execute("""
        INSERT INTO RETAILQ.GOLD.TOP_RATED
        SELECT
            source,
            category,
            title,
            price,
            rating,
            reviews,
            url,
            CURRENT_TIMESTAMP()
        FROM RETAILQ.SILVER.PRODUCTS
        WHERE rating IS NOT NULL
          AND rating > 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY category ORDER BY rating DESC NULLS LAST) <= 20
    """)
    print("  TOP_RATED done.")

    # BEST_VALUE
    cursor.execute("TRUNCATE TABLE RETAILQ.GOLD.BEST_VALUE")
    cursor.execute("""
        INSERT INTO RETAILQ.GOLD.BEST_VALUE
        SELECT
            source,
            category,
            title,
            price,
            rating,
            discount,
            url,
            ROUND((rating / NULLIF(price, 0)) * 10000, 4) AS value_score,
            CURRENT_TIMESTAMP()
        FROM RETAILQ.SILVER.PRODUCTS
        WHERE rating IS NOT NULL
          AND rating > 0
          AND price > 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY category ORDER BY (rating / NULLIF(price, 0)) DESC NULLS LAST) <= 20
    """)
    print("  BEST_VALUE done.")

    print("Gold tables updated.")
    cursor.close()

def run():
    df = read_parquet_from_s3()
    if df is None:
        return
    df = clean_data(df)
    load_to_snowflake(df)

    conn = snowflake.connector.connect(
        user=SF_USER,
        password=SF_PASSWORD,
        account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
        schema="GOLD"
    )
    build_gold(conn)
    conn.close()
    print("Done!")

run()
