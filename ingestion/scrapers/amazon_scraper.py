import json
import time
import re
import random
import os
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
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver

def extract_product_id(url):
    if not url:
        return None
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        return f"{match.group(1)}_amazon"
    match = re.search(r'%2Fdp%2F([A-Z0-9]{10})', url)
    if match:
        return f"{match.group(1)}_amazon"
    return None

def clean_url(url):
    if not url:
        return None
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        return f"https://www.amazon.eg/dp/{match.group(1)}"
    match = re.search(r'%2Fdp%2F([A-Z0-9]{10})', url)
    if match:
        return f"https://www.amazon.eg/dp/{match.group(1)}"
    if url.startswith("/"):
        return "https://www.amazon.eg" + url
    return url

def scrape_amazon_search(search_url, pages=5, category_name=None, driver=None):
    products = []
    owns_driver = driver is None
    if owns_driver:
        driver = get_driver()

    try:
        for page in range(1, pages + 1):
            url = f"{search_url}&page={page}"
            try:
                driver.get(url)

                # انتظر لحد ما المنتجات تظهر
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
                    )
                )

                # scroll خفيف علشان الصور تتحمّل
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, 800);")
                    time.sleep(0.5)
                time.sleep(1)

                soup = BeautifulSoup(driver.page_source, "html.parser")

                # CAPTCHA check
                captcha = soup.find("form", {"action": "/errors/validateCaptcha"})
                if captcha:
                    print(f"Amazon page {page}: CAPTCHA detected, skipping")
                    continue

                items = soup.find_all("div", {"data-component-type": "s-search-result"})

                for item in items:
                    # Title
                    title_tag = item.find("h2", {"class": "a-size-base-plus a-spacing-none a-color-base a-text-normal"})
                    if not title_tag:
                        title_tag = item.find("h2")
                    if not title_tag:
                        continue
                    title = f"{title_tag.get_text(strip=True)} - amazon"

                    # Current Price
                    price = None
                    price_tag = item.find("span", {"class": "a-price-whole"})
                    if price_tag:
                        try:
                            fraction_tag = item.find("span", {"class": "a-price-fraction"})
                            whole_str = price_tag.get_text(strip=True).replace(",", "").replace(".", "")
                            frac_str = fraction_tag.get_text(strip=True) if fraction_tag else "00"
                            price = float(f"{whole_str}.{frac_str}")
                        except:
                            pass

                    if not price:
                        offscreen = item.find("span", {"class": "a-offscreen"})
                        if offscreen:
                            try:
                                price = float(
                                    offscreen.get_text(strip=True)
                                    .replace(",", "").replace("EGP", "").strip()
                                )
                            except:
                                pass

                    # Old Price
                    old_price = None
                    old_price_tag = item.find("span", {"class": "a-price a-text-price"})
                    if old_price_tag:
                        try:
                            old_price_whole = old_price_tag.find("span", {"class": "a-price-whole"})
                            if old_price_whole:
                                old_price = float(
                                    old_price_whole.get_text(strip=True)
                                    .replace(",", "").replace(".", "").strip()
                                )
                            else:
                                old_offscreen = old_price_tag.find("span", {"class": "a-offscreen"})
                                if old_offscreen:
                                    old_price = float(
                                        old_offscreen.get_text(strip=True)
                                        .replace(",", "").replace("EGP", "").strip()
                                    )
                        except:
                            pass

                    # Rating
                    rating = None
                    rating_tag = item.find("i", {"class": lambda x: x and "a-star-mini" in x})
                    if rating_tag:
                        rating = rating_tag.get_text(strip=True)

                    # Reviews
                    reviews = None
                    reviews_tag = item.find("span", {"class": "a-size-mini puis-normal-weight-text s-underline-text"})
                    if reviews_tag:
                        reviews = reviews_tag.get_text(strip=True)

                    # Link
                    link_tag = item.find("a", {"class": "a-link-normal s-no-hover s-underline-text s-underline-link-text s-link-style a-text-normal"})
                    if not link_tag:
                        link_tag = item.find("a", {"class": "a-link-normal s-no-outline"})
                    raw_link = link_tag["href"] if link_tag else None
                    link = clean_url(raw_link)
                    product_id = extract_product_id(raw_link)

                    # Image
                    image = None
                    img_tag = item.find("img", {"class": "s-image"})
                    if img_tag:
                        image = img_tag.get("src")

                    product = {
                        "product_id": product_id,
                        "source": "amazon",
                        "category": category_name or search_url.split("k=")[-1].split("&")[0],
                        "title": title,
                        "price": price,
                        "old_price": old_price,
                        "rating": rating,
                        "reviews": reviews,
                        "url": link,
                        "image": image,
                        "scraped_at": datetime.utcnow().isoformat()
                    }
                    products.append(product)

                print(f"Amazon page {page}: {len(items)} products")
                time.sleep(random.uniform(3, 6))

            except Exception as e:
                print(f"Amazon page {page}: error — {e}")
                continue

    finally:
        if owns_driver:
            driver.quit()

    print(f"Total from Amazon: {len(products)} products")
    return products


if __name__ == "__main__":
    products = scrape_amazon_search("https://www.amazon.eg/s?k=laptop")
    print(json.dumps(products[:3], indent=2, ensure_ascii=False))
