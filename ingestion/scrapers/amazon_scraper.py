import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def scrape_amazon_search(search_url, pages=3):
    try:
        products = []

        for page in range(1, pages + 1):
            url = f"{search_url}&page={page}"
            response = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(response.content, "html.parser")
            items = soup.find_all("div", {"data-component-type": "s-search-result"})

            for item in items:
                title = item.find("h2")
                price_whole = item.find("span", {"class": "a-price-whole"})
                price_fraction = item.find("span", {"class": "a-price-fraction"})
                rating = item.find("span", {"class": "a-icon-alt"})
                link = item.find("a", {"class": "a-link-normal"}, href=True)
                image = item.find("img", {"class": "s-image"})

                if not title:
                    continue

                price = None
                if price_whole:
                    try:
                        price_str = price_whole.get_text(strip=True).replace(",", "")
                        fraction_str = price_fraction.get_text(strip=True) if price_fraction else "00"
                        price = float(f"{price_str}.{fraction_str}")
                    except:
                        price = None

                product = {
                    "source": "amazon",
                    "category": search_url.split("k=")[-1].split("&")[0],
                    "title": title.get_text(strip=True),
                    "price": price,
                    "rating": rating.get_text(strip=True) if rating else None,
                    "url": "https://www.amazon.eg" + link["href"] if link else None,
                    "image": image["src"] if image else None,
                    "scraped_at": datetime.utcnow().isoformat()
                }
                products.append(product)

            print(f"Amazon page {page}: {len(items)} products")
            time.sleep(2)

        print(f"Total from Amazon: {len(products)} products")
        return products

    except Exception as e:
        print(f"Error scraping Amazon: {e}")
        return []

if __name__ == "__main__":
    products = scrape_amazon_search("https://www.amazon.eg/s?k=laptop")
    print(json.dumps(products[:3], indent=2, ensure_ascii=False))