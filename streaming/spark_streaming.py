from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, to_timestamp, when, round as spark_round
from pyspark.sql.types import (
    StructType, StructField, StringType, FloatType
)
import os
from dotenv import load_dotenv

load_dotenv()

KAFKA_SERVERS   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
POSTGRES_URL    = os.getenv("POSTGRES_URL", "jdbc:postgresql://localhost:5432/retailiq")
POSTGRES_USER   = os.getenv("POSTGRES_USER", "retailiq")
POSTGRES_PASS   = os.getenv("POSTGRES_PASSWORD", "retailiq123")

PRODUCT_SCHEMA = StructType([
    StructField("product_id",  StringType(),  True),
    StructField("source",      StringType(),  True),
    StructField("category",    StringType(),  True),
    StructField("title",       StringType(),  True),
    StructField("price",       FloatType(),   True),
    StructField("old_price",   FloatType(),   True),
    StructField("discount",    StringType(),  True),
    StructField("rating",      StringType(),  True),
    StructField("reviews",     StringType(),  True),
    StructField("url",         StringType(),  True),
    StructField("image",       StringType(),  True),
    StructField("scraped_at",  StringType(),  True),
])

def create_spark_session():
    return (
        SparkSession.builder
        .appName("RetailIQ-Streaming")
        .config("spark.jars.packages",
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
                "org.postgresql:postgresql:42.6.0")
        .getOrCreate()
    )

def write_to_postgres(batch_df, batch_id):
    if batch_df.isEmpty():
        return

    count = batch_df.count()
    print(f"Batch {batch_id}: {count} records → PostgreSQL")

    (
        batch_df.write
        .format("jdbc")
        .option("url", POSTGRES_URL)
        .option("dbtable", "products_stream")
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASS)
        .option("driver", "org.postgresql.Driver")
        .mode("append")
        .save()
    )

    print(f"Batch {batch_id}: written to PostgreSQL ✅")

def run_streaming():
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    # قرا من Kafka
    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("subscribe", "raw.products")
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # Parse JSON + Clean
    parsed_stream = (
        raw_stream
        .select(from_json(col("value").cast("string"), PRODUCT_SCHEMA).alias("data"))
        .select("data.*")
        .filter(col("title").isNotNull())
        .filter(col("price").isNotNull())
        # حساب discount_pct
        .withColumn("discount_pct",
            when(
                (col("old_price").isNotNull()) & (col("old_price") > 0),
                spark_round(((col("old_price") - col("price")) / col("old_price")) * 100, 2)
            ).otherwise(None)
        )
        # تحويل scraped_at لـ timestamp
        .withColumn("scraped_at", to_timestamp(col("scraped_at")))
    )

    # اكتب على PostgreSQL كل 30 ثانية
    query = (
        parsed_stream.writeStream
        .foreachBatch(write_to_postgres)
        .option("checkpointLocation", "/tmp/checkpoint/products_stream")
        .trigger(processingTime="30 seconds")
        .start()
    )

    print(f"Streaming started → PostgreSQL ({POSTGRES_URL})")
    query.awaitTermination()

if __name__ == "__main__":
    run_streaming()