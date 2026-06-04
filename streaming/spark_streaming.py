from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, to_timestamp
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
import os


schema = StructType([
    StructField("product_id", StringType(), True),
    StructField("source", StringType(), True),
    StructField("category", StringType(), True),
    StructField("title", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("old_price", DoubleType(), True),
    StructField("discount", StringType(), True),
    StructField("rating", StringType(), True),
    StructField("reviews", StringType(), True),
    StructField("url", StringType(), True),
    StructField("image", StringType(), True),
    StructField("scraped_at", StringType(), True),
])

def create_spark_session():
    builder = SparkSession.builder \
        .appName("RetailQ-Streaming") \
        .config("spark.jars.packages",
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
                "org.apache.hadoop:hadoop-aws:3.3.4,"
                "com.amazonaws:aws-java-sdk-bundle:1.12.262")

    aws_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")

    if aws_key and aws_secret:
        builder = builder \
            .config("spark.hadoop.fs.s3a.access.key", aws_key) \
            .config("spark.hadoop.fs.s3a.secret.key", aws_secret) \
            .config("spark.hadoop.fs.s3a.endpoint", "s3.amazonaws.com") \
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

    return builder.getOrCreate()

def process_batch(df, batch_id):
    print(f"\nBatch {batch_id}: {df.count()} records")

    valid_df = df.filter(col("price").isNotNull())
    print(f"Valid products: {valid_df.count()}")

    s3_bucket = os.getenv("S3_BUCKET")
    if s3_bucket:
        s3_path = f"s3a://{s3_bucket}/raw/products/"
        valid_df.write \
            .mode("append") \
            .parquet(s3_path)
        print(f"Saved to S3: {s3_path}")
    else:
        print("S3 not configured, skipping save.")

    valid_df.select("source", "category", "title", "price").show(5, truncate=50)

def run_streaming():
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    print("Starting Spark Streaming...")

    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", os.getenv("KAFKA_BOOTSTRAP_SERVERS_INTERNAL", "kafka:29092")) \
        .option("subscribe", "raw.products") \
        .option("startingOffsets", "latest") \
        .load()

    parsed_df = df.select(
        from_json(col("value").cast("string"), schema).alias("data")
    ).select("data.*")

    parsed_df = parsed_df.withColumn(
        "scraped_at", to_timestamp(col("scraped_at"))
    )

    query = parsed_df \
        .writeStream \
        .foreachBatch(process_batch) \
        .option("checkpointLocation", "/tmp/retailq_checkpoint") \
        .trigger(processingTime="30 seconds") \
        .start()

    print("Spark Streaming started! Waiting for data...")
    query.awaitTermination()

run_streaming()
