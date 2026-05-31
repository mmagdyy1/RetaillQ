import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "referer": "https://www.noon.com/",
}

def scrape_noon_search(search_url, pages=3):
    try:
        products = []

        for page in range(1, pages + 1):
            url = f"{search_url}&page={page}"
            try:
                response = requests.get(url, headers=HEADERS, timeout=20)
                soup = BeautifulSoup(response.content, "html.parser")
                items = soup.find_all("div", {"class": "productContainer"})

                if not items:
                    items = soup.find_all("div", {"data-qa": "product-item"})

                for item in items:
                    title = item.find("div", {"class": "name"}) or item.find("h2")
                    price = item.find("span", {"class": "price"}) or item.find("strong")
                    link = item.find("a", href=True)

                    if not title:
                        continue

                    price_val = None
                    if price:
                        try:
                            price_val = float(
                                price.get_text(strip=True)
                                .replace(",", "")
                                .replace("EGP", "")
                                .replace("ج.م", "")
                                .strip()
                            )
                        except:
                            price_val = None

                    product = {
                        "source": "noon",
                        "category": search_url.split("q=")[-1].split("&")[0],
                        "title": title.get_text(strip=True),
                        "price": price_val,
                        "url": "https://www.noon.com" + link["href"] if link else None,
                        "scraped_at": datetime.utcnow().isoformat()
                    }
                    products.append(product)

                print(f"Noon page {page}: {len(items)} products")
                time.sleep(3)

            except requests.Timeout:
                print(f"Noon page {page}: timeout, skipping")
                continue

        print(f"Total from Noon: {len(products)} products")
        return products

    except Exception as e:
        print(f"Error scraping Noon: {e}")
        return []

if __name__ == "__main__":
    products = scrape_noon_search("https://www.noon.com/egypt-en/search/?q=laptop")
    print(json.dumps(products[:3], indent=2, ensure_ascii=False))