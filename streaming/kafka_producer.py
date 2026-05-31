from kafka import KafkaProducer
import json
import time
from datetime import datetime
from ingestion.scrapers.jumia_scraper import scrape_jumia_search
from ingestion.scrapers.noon_scraper import scrape_noon_search
from ingestion.scrapers.amazon_scraper import scrape_amazon_search
from dotenv import load_dotenv
import os

load_dotenv()

producer = KafkaProducer(
    bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

SEARCH_TERMS = [
    "laptop",
    "mobile",
    "tablet",
    "tv",
    "headphones"
]

def send_to_kafka(topic, data):
    sent = 0
    for item in data:
        if item and item.get("title"):
            producer.send(topic, value=item)
            sent += 1
    producer.flush()
    print(f"Sent {sent} valid products to {topic}")

def run_pipeline():
    while True:
        for term in SEARCH_TERMS:
            print(f"\n{'='*40}")
            print(f"Scraping: {term}")
            print(f"{'='*40}")

            jumia_data = scrape_jumia_search(
                f"https://www.jumia.com.eg/catalog/?q={term}", pages=3
            )
            send_to_kafka("raw.products", jumia_data)

            noon_data = scrape_noon_search(
                f"https://www.noon.com/egypt-en/search/?q={term}", pages=3
            )
            send_to_kafka("raw.products", noon_data)

            amazon_data = scrape_amazon_search(
                f"https://www.amazon.eg/s?k={term}", pages=3
            )
            send_to_kafka("raw.products", amazon_data)

            time.sleep(3)

        print("\nWaiting 5 minutes before next scrape...")
        time.sleep(300)

if __name__ == "__main__":
    run_pipeline()