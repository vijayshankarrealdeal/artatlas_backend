import multiprocessing
import time
import json
import re
import os
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
BASE_GALLERIES_URL = "https://artvee.com/galleries/"
TOTAL_GALLERY_PAGES = 64 # As specified
MAX_WORKERS = multiprocessing.cpu_count() # Number of parallel browser instances
# MAX_COLLECTIONS_PER_GALLERY_PAGE = 2 # For testing, set to None for all
# MAX_ARTWORK_PAGES_PER_COLLECTION = 1 # For testing, set to None for all
MAX_COLLECTIONS_PER_GALLERY_PAGE = None
MAX_ARTWORK_PAGES_PER_COLLECTION = None
OUTPUT_FILE = "artvee_galleries_data.json"

# --- Helper Functions (mostly unchanged, but will be called by workers) ---
def setup_worker_driver(): # Renamed for clarity
    """Sets up a Selenium WebDriver instance for a worker process."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    # It can be good to vary user agents slightly if running many workers, but for now, one is fine.
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument('--log-level=3') # Suppress console logs from Chrome/ChromeDriver
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def parse_background_image_url(style_string):
    if not style_string:
        return None
    match = re.search(r"url\((.*?)\)", style_string)
    if match:
        url = match.group(1).strip('\'"')
        if url.startswith('/') and not url.startswith('//'):
            return f"https://artvee.com{url}"
        return url
    return None

def scrape_artwork_details_for_worker(driver, collection_name_for_progress):
    """Scrapes artwork details from the current collection page (for worker)."""
    artworks_on_page = []
    try:
        artwork_elements_container = WebDriverWait(driver, 15).until( # Increased timeout slightly
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.elements-grid.woodmart-portfolio-holder"))
        )
        artwork_elements = artwork_elements_container.find_elements(By.CSS_SELECTOR, "article.product-grid-item")

        for i, art_el in enumerate(artwork_elements):
            # This print will be from a worker, might interleave.
            # if (i + 1) % 5 == 0 or i == 0 or (i + 1) == len(artwork_elements) :
            #     print(f"        Worker ({os.getpid()}) scraping artwork {i+1}/{len(artwork_elements)} for '{collection_name_for_progress}'...", end='\r')

            artwork_data = {}
            try:
                title_anchor = art_el.find_element(By.CSS_SELECTOR, "h3.entry-title a")
                artwork_data["artwork_title"] = title_anchor.text.strip()
                artwork_data["artwork_url"] = title_anchor.get_attribute("href")
            except NoSuchElementException: artwork_data["artwork_title"], artwork_data["artwork_url"] = None, None
            try:
                artist_anchor = art_el.find_element(By.CSS_SELECTOR, "div.woodmart-product-brands-links a")
                artwork_data["artist_name"] = artist_anchor.text.strip()
                artwork_data["artist_url"] = artist_anchor.get_attribute("href")
            except NoSuchElementException: artwork_data["artist_name"], artwork_data["artist_url"] = None, None
            try:
                img_tag = art_el.find_element(By.CSS_SELECTOR, "div.product-element-top img")
                artwork_data["image_url"] = img_tag.get_attribute("src")
                if not artwork_data["image_url"] or "data:image" in artwork_data["image_url"]:
                     artwork_data["image_url"] = img_tag.get_attribute("data-wood-src")
                     if artwork_data["image_url"] and not artwork_data["image_url"].startswith("http"):
                        artwork_data["image_url"] = f"https://mdl.artvee.com/ft/{artwork_data['image_url']}"
            except NoSuchElementException: artwork_data["image_url"] = None
            try:
                category_anchor = art_el.find_element(By.CSS_SELECTOR, "div.woodmart-product-cats a")
                artwork_data["category"] = category_anchor.text.strip()
            except NoSuchElementException: artwork_data["category"] = None
            artwork_data["year"] = None
            if artwork_data["artwork_title"]:
                year_match = re.search(r'\((\d{4})\)$|\((\d{4})[-\u2013]\d{2,4}\)$|\(Circa (\d{4}).*?\)$', artwork_data["artwork_title"])
                if year_match: artwork_data["year"] = year_match.group(1) or year_match.group(2) or year_match.group(3)
            artworks_on_page.append(artwork_data)
        # print(" " * 100, end='\r') # Clear worker's artwork progress line
    except TimeoutException: pass # Error message handled by caller
    except Exception: pass # Error message handled by caller
    return artworks_on_page

def actual_scrape_single_collection(driver, collection_details):
    """The logic to scrape a single collection, used by the worker."""
    collection_url = collection_details["collection_url"]
    collection_name = collection_details["name"]
    artworks_in_this_collection = []
    artwork_page_num = 1

    try:
        driver.get(collection_url)
    except Exception as e:
        # This print will be from a worker.
        print(f"[Worker {os.getpid()}] Error navigating to collection {collection_name}: {e}")
        return artworks_in_this_collection # Return empty

    # Estimate total artwork pages for better progress display
    total_artwork_pages_estimated = "N/A"
    if collection_details.get("items_count_galleries_page"):
        try:
            item_count_str = collection_details["items_count_galleries_page"].replace(" Items", "")
            total_items = int(item_count_str)
            items_per_page_rough_estimate = 20 # Adjust if known
            est_pages = (total_items + items_per_page_rough_estimate - 1) // items_per_page_rough_estimate
            total_artwork_pages_estimated = est_pages if est_pages > 0 else 1
            if MAX_ARTWORK_PAGES_PER_COLLECTION and MAX_ARTWORK_PAGES_PER_COLLECTION < total_artwork_pages_estimated:
                total_artwork_pages_estimated = MAX_ARTWORK_PAGES_PER_COLLECTION
        except ValueError: pass


    while True:
        if MAX_ARTWORK_PAGES_PER_COLLECTION and artwork_page_num > MAX_ARTWORK_PAGES_PER_COLLECTION:
            # print(f"[Worker {os.getpid()}] Max artwork pages for '{collection_name}'.") # Worker print
            break
        
        # progress_str_worker = f"page {artwork_page_num}"
        # if total_artwork_pages_estimated != "N/A": progress_str_worker += f"/{total_artwork_pages_estimated}"
        # print(f"    [Worker {os.getpid()}] Scraping artwork {progress_str_worker} for '{collection_name}'")


        try:
            WebDriverWait(driver, 20).until( # Slightly longer wait for collection page content
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.elements-grid"))
            )
            time.sleep(1) # Short sleep after load
        except TimeoutException:
            # print(f"    [Worker {os.getpid()}] Timeout on artwork page {artwork_page_num} for '{collection_name}'.") # Worker print
            break

        artworks_from_this_page = scrape_artwork_details_for_worker(driver, collection_name)
        if not artworks_from_this_page and artwork_page_num > 1:
            # print(f"    [Worker {os.getpid()}] No artworks on page {artwork_page_num} for '{collection_name}', assuming end.") # Worker print
            break
        artworks_in_this_collection.extend(artworks_from_this_page)

        try:
            next_page_link = driver.find_element(By.XPATH, "//div[@class='wp-pagenavi']//a[@class='nextpostslink']")
            next_page_url = next_page_link.get_attribute("href")
            if next_page_url and next_page_url != driver.current_url :
                driver.get(next_page_url)
                artwork_page_num += 1
                time.sleep(1.5) # Politeness for artwork pagination
            else:
                break
        except NoSuchElementException: break
        except StaleElementReferenceException: break
        except Exception as e:
            # print(f"    [Worker {os.getpid()}] Error paginating artworks for '{collection_name}': {e}") # Worker print
            break
    return artworks_in_this_collection

# --- Worker Process Function ---
def worker_process_collection(collection_detail_object):
    """
    This function is executed by each worker process.
    It scrapes one full collection.
    """
    worker_driver = None
    try:
        # print(f"[Worker {os.getpid()}] Starting for collection: {collection_detail_object['name']}") # Debug worker start
        worker_driver = setup_worker_driver()
        artworks = actual_scrape_single_collection(worker_driver, collection_detail_object)
        collection_detail_object["artworks"] = artworks
        # print(f"[Worker {os.getpid()}] Finished collection: {collection_detail_object['name']}. Artworks: {len(artworks)}") # Debug worker end
        return collection_detail_object
    except Exception as e:
        print(f"[Worker {os.getpid()}] UNHANDLED EXCEPTION for collection {collection_detail_object.get('name', 'Unknown')}: {e}")
        # Return the original object but potentially with empty artworks, or a special error marker
        collection_detail_object["artworks"] = [] 
        collection_detail_object["error"] = str(e)
        return collection_detail_object
    finally:
        if worker_driver:
            worker_driver.quit()

# --- Data Loading/Saving (for resuming) ---
def load_scraped_data(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {filepath}. Starting fresh.")
            return []
        except Exception as e:
            print(f"Warning: Error loading {filepath}: {e}. Starting fresh.")
            return []
    return []

def save_scraped_data(filepath, data):
    try:
        temp_filepath = filepath + ".tmp"
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(temp_filepath, filepath)
    except Exception as e:
        print(f"CRITICAL: Error saving data to {filepath}: {e}")
        # Consider a backup save mechanism if os.replace fails
        if os.path.exists(temp_filepath):
            try: os.remove(temp_filepath)
            except OSError: pass


# --- Main Orchestration ---
def main():
    # --- Phase 1: Gather all collection URLs to process (sequentially by main process) ---
    print("--- Phase 1: Gathering all collection metadata ---")
    main_driver_for_listing = setup_worker_driver() # Main process uses a driver for listing
    
    all_collections_metadata_to_process = []
    existing_data = load_scraped_data(OUTPUT_FILE)
    processed_collection_urls = {coll.get("collection_url") for coll in existing_data if coll.get("collection_url")}
    print(f"Found {len(processed_collection_urls)} collections already processed in {OUTPUT_FILE}.")

    current_gallery_page_num = 1
    galleries_page_url = BASE_GALLERIES_URL
    
    while galleries_page_url and current_gallery_page_num <= TOTAL_GALLERY_PAGES:
        print(f"Gathering from Gallery Page {current_gallery_page_num}/{TOTAL_GALLERY_PAGES}: {galleries_page_url}")
        try:
            main_driver_for_listing.get(galleries_page_url)
            WebDriverWait(main_driver_for_listing, 25).until( # Longer wait for gallery list
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.woodmart-portfolio-holder"))
            )
            time.sleep(2)
        except Exception as e:
            print(f"Error loading gallery page {galleries_page_url} for listing: {e}. Attempting to find next.")
            try:
                current_url_before_find = main_driver_for_listing.current_url
                next_gallery_page_element = main_driver_for_listing.find_element(By.XPATH, "//div[@class='woodmart-pagination']//a[contains(text(), '›')]")
                next_url = next_gallery_page_element.get_attribute("href")
                if next_url and next_url != current_url_before_find: galleries_page_url = next_url
                else: galleries_page_url = None
            except Exception: galleries_page_url = None
            current_gallery_page_num += 1
            if galleries_page_url: time.sleep(1)
            continue

        gallery_collection_articles = main_driver_for_listing.find_elements(By.CSS_SELECTOR, "article.portfolio-entry")
        for i, article_el in enumerate(gallery_collection_articles):
            if MAX_COLLECTIONS_PER_GALLERY_PAGE is not None and i >= MAX_COLLECTIONS_PER_GALLERY_PAGE:
                break 
            try:
                coll_el = article_el.find_element(By.CSS_SELECTOR, "div.snax-collection")
                title_el = coll_el.find_element(By.CSS_SELECTOR, "h3.snax-collection-title a")
                collection_name = title_el.text.strip()
                collection_url = title_el.get_attribute("href")

                if collection_url in processed_collection_urls:
                    # print(f"  Skipping already processed collection: {collection_name}")
                    continue

                curator = "N/A"
                try: curator_el = coll_el.find_element(By.CSS_SELECTOR, "span.snax-entry-author strong"); curator = curator_el.text.strip().replace("By ", "")
                except NoSuchElementException: pass
                item_count = "N/A"
                try: item_count_el = coll_el.find_element(By.CSS_SELECTOR, "span.snax-collection-item-count"); item_count = item_count_el.text.strip()
                except NoSuchElementException: pass
                collection_image_url = None
                try: first_featg = article_el.find_element(By.CSS_SELECTOR, "div.scol-bt div.featg"); style = first_featg.get_attribute("style"); collection_image_url = parse_background_image_url(style)
                except NoSuchElementException: pass
                
                all_collections_metadata_to_process.append({
                    "name": collection_name, "collection_url": collection_url, "curator": curator,
                    "title": collection_name, "image_url": collection_image_url,
                    "items_count_galleries_page": item_count, "artworks": [] # artworks to be filled by worker
                })
            except Exception as e:
                print(f"  Error extracting collection metadata on gallery page {current_gallery_page_num}: {e}")
        
        try:
            next_gallery_page_element = main_driver_for_listing.find_element(By.XPATH, "//div[@class='woodmart-pagination']//a[contains(text(), '›')]")
            galleries_page_url = next_gallery_page_element.get_attribute("href")
        except NoSuchElementException: galleries_page_url = None; print("No 'next' (›) gallery page link found.")
        except StaleElementReferenceException: galleries_page_url = None; print("Stale next gallery page link.")
        current_gallery_page_num += 1
        if galleries_page_url: time.sleep(2) # Politeness for gallery pagination
    
    main_driver_for_listing.quit()
    print(f"--- Phase 1 Complete: Gathered {len(all_collections_metadata_to_process)} new collections to scrape. ---")

    if not all_collections_metadata_to_process:
        print("No new collections to process. Exiting.")
        return

    # --- Phase 2: Process collections in parallel ---
    print(f"\n--- Phase 2: Processing {len(all_collections_metadata_to_process)} collections using up to {MAX_WORKERS} workers ---")
    
    # `existing_data` already contains previously scraped items. We append new results to it.
    final_output_data = existing_data 
    
    completed_count = 0
    total_to_process = len(all_collections_metadata_to_process)

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_collection = {
            executor.submit(worker_process_collection, collection_meta): collection_meta 
            for collection_meta in all_collections_metadata_to_process
        }

        for future in concurrent.futures.as_completed(future_to_collection):
            collection_meta_submitted = future_to_collection[future]
            try:
                processed_collection_object = future.result() # This is the dict returned by worker
                if processed_collection_object:
                    if "error" not in processed_collection_object or not processed_collection_object["artworks"]: # Only add if no major error or if artworks were found
                         final_output_data.append(processed_collection_object)
                         # No need to add to processed_collection_urls here, as it was checked before submission
                    
                    save_scraped_data(OUTPUT_FILE, final_output_data)
                    completed_count += 1
                    print(f"PROGRESS: Collection '{processed_collection_object.get('name', 'Unknown')}' processed and saved. "
                          f"({completed_count}/{total_to_process} completed). "
                          f"Artworks: {len(processed_collection_object.get('artworks', []))}. "
                          f"Total in file: {len(final_output_data)}.")
                    if "error" in processed_collection_object:
                        print(f"  WARNING: Collection '{processed_collection_object['name']}' had an error during worker processing: {processed_collection_object['error']}")

                else: # Should not happen if worker returns something
                    completed_count += 1
                    print(f"PROGRESS: Collection '{collection_meta_submitted.get('name', 'Unknown')}' returned no data from worker. "
                          f"({completed_count}/{total_to_process} completed).")


            except Exception as exc:
                completed_count += 1
                print(f"EXCEPTION processing collection '{collection_meta_submitted.get('name', 'Unknown')}': {exc}. "
                      f"({completed_count}/{total_to_process} attempted).")

    print(f"\n--- Scraping Session Ended ---")
    print(f"Final total collections in {OUTPUT_FILE}: {len(final_output_data)}")

if __name__ == "__main__":
    # This is crucial for multiprocessing on Windows.
    # On other OSes, it's good practice.
    multiprocessing.freeze_support() 
    main()