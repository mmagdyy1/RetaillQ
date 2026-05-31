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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def scrape_jumia_search(search_url, pages=3):
    try:
        products = []

        for page in range(1, pages + 1):
            url = f"{search_url}&page={page}"
            try:
                response = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(response.content, "html.parser")
                items = soup.find_all("article", {"class": "prd"})

                for item in items:
                    title = item.find("h3", {"class": "name"})
                    price = item.find("div", {"class": "prc"})
                    old_price = item.find("div", {"class": "old"})
                    discount = item.find("div", {"class": "bdg _dsct"})
                    rating = item.find("div", {"class": "stars _s"})
                    link = item.find("a", {"class": "core"}, href=True)
                    image = item.find("img", {"class": "img"})

                    if not title:
                        continue

                    price_val = None
                    if price:
                        try:
                            price_val = float(
                                price.get_text(strip=True)
                                .replace(",", "")
                                .replace("EGP", "")
                                .strip()
                            )
                        except:
                            price_val = None

                    old_price_val = None
                    if old_price:
                        try:
                            old_price_val = float(
                                old_price.get_text(strip=True)
                                .replace(",", "")
                                .replace("EGP", "")
                                .strip()
                            )
                        except:
                            old_price_val = None

                    product = {
                        "source": "jumia",
                        "category": search_url.split("q=")[-1].split("&")[0],
                        "title": title.get_text(strip=True),
                        "price": price_val,
                        "old_price": old_price_val,
                        "discount": discount.get_text(strip=True) if discount else None,
                        "rating": rating.get_text(strip=True) if rating else None,
                        "url": "https://www.jumia.com.eg" + link["href"] if link else None,
                        "image": image["data-src"] if image and image.get("data-src") else None,
                        "scraped_at": datetime.utcnow().isoformat()
                    }
                    products.append(product)

                print(f"Jumia page {page}: {len(items)} products")
                time.sleep(2)

            except requests.Timeout:
                print(f"Jumia page {page}: timeout, skipping")
                continue

        print(f"Total from Jumia: {len(products)} products")
        return products

    except Exception as e:
        print(f"Error scraping Jumia: {e}")
        return []

def scrape_jumia_product(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, "html.parser")

        title = soup.find("h1", {"class": "-fs20 -pts -pbxs"})
        price = soup.find("span", {"class": "-b -ltr -tal -fs24"})
        availability = soup.find("div", {"class": "-pbs"})

        product = {
            "source": "jumia",
            "url": url,
            "title": title.get_text(strip=True) if title else None,
            "price": float(
                price.get_text(strip=True)
                .replace(",", "")
                .replace("EGP", "")
                .strip()
            ) if price else None,
            "availability": availability.get_text(strip=True) if availability else None,
            "scraped_at": datetime.utcnow().isoformat()
        }

        print(f"Scraped: {product['title']} - {product['price']}")
        return product

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

if __name__ == "__main__":
    products = scrape_jumia_search("https://www.jumia.com.eg/catalog/?q=laptop")
    print(json.dumps(products[:3], indent=2, ensure_ascii=False))