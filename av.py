import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# Configuration
SAVE_FILE = "artvee_data.json"
MAX_GALLERY_WORKERS = 16  # Adjust based on your CPU capabilities

# Load existing data to resume on restart
if os.path.exists(SAVE_FILE):
    with open(SAVE_FILE, "r", encoding="utf-8") as f:
        saved_galleries = json.load(f)
else:
    saved_galleries = []

done_urls = {g['url'] for g in saved_galleries}

# Sequentially collect gallery metadata
def scrape_galleries(base_url="https://artvee.com/galleries/page/{}", pages=64):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    galleries = []

    for i in tqdm(range(1, pages + 1), desc="Loading gallery pages"):
        url = base_url.format(i)
        driver.get(url)
        time.sleep(2)

        entries = driver.find_elements(By.CSS_SELECTOR, ".portfolio-entry")
        for e in entries:
            try:
                link_el = e.find_element(By.CSS_SELECTOR, "h3.snax-collection-title a")
                href = link_el.get_attribute("href")
                if href in done_urls:
                    continue  # Skip already-scraped galleries

                name = link_el.text
                # Main thumbnail
                img_style = e.find_element(By.CSS_SELECTOR, ".featg").get_attribute("style")
                image_url = img_style.split("url(")[1].rstrip(")").replace('"', '')
                creator = e.find_element(By.CSS_SELECTOR, ".snax-entry-author strong").text
                count_text = e.find_element(By.CSS_SELECTOR, ".snax-collection-item-count").text
                item_count = int(count_text.split()[0])

                galleries.append({
                    "name": name,
                    "url": href,
                    "image_url": image_url,
                    "creator": creator,
                    "item_count": item_count
                })
            except Exception:
                continue

    driver.quit()
    return galleries

# Worker function: scrape all artworks inside one gallery
def process_gallery(gallery):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(gallery['url'])
    time.sleep(2)

    artworks = []
    while True:
        items = driver.find_elements(By.CSS_SELECTOR, ".product-grid-item")
        for it in items:
            try:
                title_el = it.find_element(By.CSS_SELECTOR, ".entry-title a")
                title = title_el.text
                link = title_el.get_attribute("href")
                img_url = it.find_element(By.CSS_SELECTOR, "img").get_attribute("src")
                artist = it.find_element(By.CSS_SELECTOR, ".woodmart-product-brands-links").text
                category = it.find_element(By.CSS_SELECTOR, ".woodmart-product-cats").text
                artworks.append({
                    "title": title,
                    "link": link,
                    "image": img_url,
                    "artist": artist,
                    "category": category
                })
            except Exception:
                continue

        # paginate inside the gallery
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, ".wp-pagenavi a.nextpostslink")
            next_url = next_btn.get_attribute("href")
            driver.get(next_url)
            time.sleep(2)
        except:
            break

    driver.quit()
    gallery['artwork'] = artworks
    return gallery

# Main
if __name__ == "__main__":
    # Step 1: Get gallery list
    galleries_to_scrape = scrape_galleries()

    # Step 2: Scrape galleries in parallel
    with ProcessPoolExecutor(max_workers=MAX_GALLERY_WORKERS) as executor:
        future_map = {executor.submit(process_gallery, g): g for g in galleries_to_scrape}

        for future in tqdm(as_completed(future_map), total=len(future_map), desc="Scraping galleries"):
            try:
                result = future.result()
                saved_galleries.append(result)
                # On-the-fly save after each gallery
                with open(SAVE_FILE, "w", encoding="utf-8") as f:
                    json.dump(saved_galleries, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Error scraping {future_map[future]['url']}: {e}")

    print(f"All done. Data saved to {SAVE_FILE}")
