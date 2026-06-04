import json
import time
import re
import random
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

load_dotenv()

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def extract_product_id(url):
    if not url:
        return None
    # /N41964615A/p/ or /N70298796V/p/
    match = re.search(r'/([A-Z][A-Z0-9]+)/p/', url)
    if match:
        return f"{match.group(1)}_noon"
    return None

def clean_url(url):
    if not url:
        return None
    if url.startswith("/"):
        return "https://www.noon.com" + url
    return url

def parse_rating_reviews(item):
    """
    rating في div[class*="textCtr"] — reviews في span جوا div[class*="countCtr"]
    """
    rating = None
    reviews = None

    # Rating — div[class*="textCtr"] بيحتوي على "4.6"
    rating_tag = item.find("div", {"class": lambda x: x and "textCtr" in x})
    if rating_tag:
        rating = rating_tag.get_text(strip=True)

    # Reviews — span جوا div[class*="countCtr"] بيحتوي على "5.6K"
    count_container = item.find("div", {"class": lambda x: x and "countCtr" in x})
    if count_container:
        span = count_container.find("span")
        if span:
            reviews = span.get_text(strip=True)

    return rating, reviews

def scrape_noon_search(search_url, pages=3, category_name=None, driver=None):
    products = []
    owns_driver = driver is None
    if owns_driver:
        driver = get_driver()

    try:
        for page in range(1, pages + 1):
            url = f"{search_url}&page={page}"
            try:
                driver.get(url)

                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-qa='plp-product-box']"))
                )

                # scroll لتحميل الصور الـ lazy
                for _ in range(5):
                    driver.execute_script("window.scrollBy(0, 600);")
                    time.sleep(0.6)
                time.sleep(1.5)

                soup = BeautifulSoup(driver.page_source, "html.parser")
                items = soup.find_all("div", {"data-qa": "plp-product-box"})

                for item in items:
                    # Title
                    title_tag = item.find("h2", {"data-qa": "plp-product-box-name"})
                    if not title_tag:
                        continue
                    title = f"{title_tag.get_text(strip=True)} - noon"

                    # Current Price
                    price = None
                    price_container = item.find("div", {"data-qa": "plp-product-box-price"})
                    if price_container:
                        price_strong = price_container.find("strong")
                        if price_strong:
                            try:
                                price = float(
                                    price_strong.get_text(strip=True)
                                    .replace(",", "")
                                    .replace("EGP", "")
                                    .strip()
                                )
                            except:
                                pass

                    # Old Price
                    old_price = None
                    old_price_tag = item.find("span", {"class": lambda x: x and "oldPrice" in x})
                    if not old_price_tag:
                        old_price_tag = item.find("span", {"class": lambda x: x and "strikeThrough" in x})
                    if old_price_tag:
                        try:
                            old_price = float(
                                old_price_tag.get_text(strip=True)
                                .replace(",", "")
                                .replace("EGP", "")
                                .strip()
                            )
                        except:
                            pass

                    # Discount
                    discount = None
                    discount_tag = item.find("span", {"class": lambda x: x and "discount" in x})
                    if discount_tag:
                        discount = discount_tag.get_text(strip=True)

                    # Rating + Reviews (مفصولين)
                    rating, reviews = parse_rating_reviews(item)

                    # Link
                    link_tag = item.find("a", href=True)
                    raw_link = link_tag["href"] if link_tag else None
                    link = clean_url(raw_link)
                    product_id = extract_product_id(link)

                    # Image — img[class*="productImage"] بعد lazy load
                    image = None
                    img_tag = item.find("img", {"class": lambda x: x and "productImage" in x})
                    if not img_tag:
                        img_tag = item.find("img")
                    if img_tag:
                        src = img_tag.get("src", "")
                        if src and "placeholder" not in src and "media-placeholder" not in src:
                            image = src

                    product = {
                        "product_id": product_id,
                        "source": "noon",
                        "category": category_name or search_url.split("q=")[-1].split("&")[0],
                        "title": title,
                        "price": price,
                        "old_price": old_price,
                        "discount": discount,
                        "rating": rating,
                        "reviews": reviews,
                        "url": link,
                        "image": image,
                        "scraped_at": datetime.utcnow().isoformat()
                    }
                    products.append(product)

                print(f"Noon page {page}: {len(items)} products")
                time.sleep(random.uniform(2, 4))

            except Exception as e:
                print(f"Noon page {page}: error — {e}")
                continue

    finally:
        if owns_driver:
            driver.quit()

    print(f"Total from Noon: {len(products)} products")
    return products

CATEGORIES = {
    "laptops":     "https://www.noon.com/egypt-en/search/?q=laptop",
    "mobiles":     "https://www.noon.com/egypt-en/search/?q=mobile",
    "televisions": "https://www.noon.com/egypt-en/search/?q=television",
    "headphones":  "https://www.noon.com/egypt-en/search/?q=headphones",
    "tablets":     "https://www.noon.com/egypt-en/search/?q=tablet",
}

def scrape_all_categories(pages=3):
    all_products = []
    driver = get_driver()
    try:
        for category, url in CATEGORIES.items():
            print(f"\n--- Scraping: {category} ---")
            products = scrape_noon_search(url, pages=pages, category_name=category, driver=driver)
            all_products.extend(products)
    finally:
        driver.quit()
    print(f"\nTotal all categories: {len(all_products)} products")
    return all_products

if __name__ == "__main__":
    all_products = scrape_all_categories(pages=3)
    print(json.dumps(all_products[:3], indent=2, ensure_ascii=False))