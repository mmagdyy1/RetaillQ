from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_experimental_option("debuggerAddress", "localhost:9222")
driver = webdriver.Chrome(options=options)

driver.get("https://www.carrefouregypt.com/mafegy/en/search?keyword=laptop")
time.sleep(5)

with open("carrefour_debug.html", "w", encoding="utf-8") as f:
    f.write(driver.page_source)

print("Done!")