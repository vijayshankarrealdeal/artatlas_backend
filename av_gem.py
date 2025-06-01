import time
import json
import re # For parsing style attributes
import os # For checking file existence
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
BASE_GALLERIES_URL = "https://artvee.com/galleries/"
# User has set it to 64, which seems to be the total based on their HTML.
TOTAL_GALLERY_PAGES = 64
MAX_COLLECTIONS_PER_GALLERY_PAGE = None # None means process all on page
MAX_ARTWORK_PAGES_PER_COLLECTION = None # None means process all pages in a collection
OUTPUT_FILE = "artvee_galleries_data.json"

def setup_driver():
    """Sets up the Selenium WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def parse_background_image_url(style_string):
    if not style_string:
        return None
    match = re.search(r"url\((.*?)\)", style_string)
    if match:
        url = match.group(1).strip('\'"')
        # Ensure full URL for relative paths like '/saconud/...'
        if url.startswith('/') and not url.startswith('//'):
            return f"https://artvee.com{url}"
        return url
    return None

def scrape_artwork_details(driver, collection_name_for_progress):
    """
    Scrapes artwork details from the current collection page.
    """
    artworks_on_page = []
    try:
        artwork_elements_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.elements-grid.woodmart-portfolio-holder"))
        )
        artwork_elements = artwork_elements_container.find_elements(By.CSS_SELECTOR, "article.product-grid-item")

        for i, art_el in enumerate(artwork_elements):
            # Minimal progress for artworks on this page to avoid too much console clutter
            if (i + 1) % 10 == 0 or i == 0 or (i + 1) == len(artwork_elements) : # Print for first, every 10th, and last
                print(f"        Scraping artwork {i+1}/{len(artwork_elements)} on this page for '{collection_name_for_progress}'...", end='\r')

            artwork_data = {}
            try:
                title_anchor = art_el.find_element(By.CSS_SELECTOR, "h3.entry-title a")
                artwork_data["artwork_title"] = title_anchor.text.strip()
                artwork_data["artwork_url"] = title_anchor.get_attribute("href")
            except NoSuchElementException:
                artwork_data["artwork_title"] = None
                artwork_data["artwork_url"] = None

            try:
                artist_anchor = art_el.find_element(By.CSS_SELECTOR, "div.woodmart-product-brands-links a")
                artwork_data["artist_name"] = artist_anchor.text.strip()
                artwork_data["artist_url"] = artist_anchor.get_attribute("href")
            except NoSuchElementException:
                artwork_data["artist_name"] = None
                artwork_data["artist_url"] = None

            try:
                img_tag = art_el.find_element(By.CSS_SELECTOR, "div.product-element-top img")
                artwork_data["image_url"] = img_tag.get_attribute("src")
                if not artwork_data["image_url"] or "data:image" in artwork_data["image_url"]:
                     artwork_data["image_url"] = img_tag.get_attribute("data-wood-src")
                     if artwork_data["image_url"] and not artwork_data["image_url"].startswith("http"):
                        artwork_data["image_url"] = f"https://mdl.artvee.com/ft/{artwork_data['image_url']}"
            except NoSuchElementException:
                artwork_data["image_url"] = None

            try:
                category_anchor = art_el.find_element(By.CSS_SELECTOR, "div.woodmart-product-cats a")
                artwork_data["category"] = category_anchor.text.strip()
            except NoSuchElementException:
                artwork_data["category"] = None
            
            artwork_data["year"] = None
            if artwork_data["artwork_title"]:
                year_match = re.search(r'\((\d{4})\)$|\((\d{4})[-\u2013]\d{2,4}\)$|\(Circa (\d{4}).*?\)$', artwork_data["artwork_title"])
                if year_match:
                    artwork_data["year"] = year_match.group(1) or year_match.group(2) or year_match.group(3)
            
            artworks_on_page.append(artwork_data)
        print(" " * 80, end='\r') # Clear the artwork progress line

    except TimeoutException:
        print(f"      Timeout waiting for artwork elements container for '{collection_name_for_progress}'.")
    except Exception as e:
        print(f"      Error scraping artwork details on page for '{collection_name_for_progress}': {e}")
    return artworks_on_page


def scrape_single_collection(driver, collection_details):
    """Scrapes all artworks from a single collection page, handling its pagination."""
    collection_url = collection_details["collection_url"]
    collection_name = collection_details["name"]
    
    print(f"  Scraping collection: '{collection_name}' ({collection_url})")
    
    try:
        driver.get(collection_url)
    except Exception as e:
        print(f"    Error navigating to collection URL {collection_url}: {e}")
        return [] 

    artworks_in_this_collection = []
    artwork_page_num = 1
    
    total_artwork_pages_estimated = "N/A"
    if collection_details.get("items_count_galleries_page"):
        try:
            item_count_str = collection_details["items_count_galleries_page"].replace(" Items", "")
            total_items = int(item_count_str)
            # This is an estimate; the actual number of elements found on page is more reliable.
            # Check how many items are actually on a page for a better estimate.
            # For now, let's assume it could be up to 20-30.
            # Example: if a page has 20 items, and item_count says "80 Items", estimate 4 pages.
            # This estimate helps for progress display if MAX_ARTWORK_PAGES_PER_COLLECTION is None.
            # We will find actual items on first page to refine this if needed.
            items_per_page_rough_estimate = 20 
            total_artwork_pages_estimated = (total_items + items_per_page_rough_estimate - 1) // items_per_page_rough_estimate
            if MAX_ARTWORK_PAGES_PER_COLLECTION and MAX_ARTWORK_PAGES_PER_COLLECTION < total_artwork_pages_estimated:
                total_artwork_pages_estimated = MAX_ARTWORK_PAGES_PER_COLLECTION
        except ValueError:
            pass

    while True:
        if MAX_ARTWORK_PAGES_PER_COLLECTION and artwork_page_num > MAX_ARTWORK_PAGES_PER_COLLECTION:
            print(f"    Reached max artwork pages ({MAX_ARTWORK_PAGES_PER_COLLECTION}) for collection '{collection_name}'. Stopping.")
            break
        
        progress_str = f"page {artwork_page_num}"
        if total_artwork_pages_estimated != "N/A":
            progress_str += f"/{total_artwork_pages_estimated}"
        print(f"    Scraping artwork {progress_str} for collection '{collection_name}'")
        
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.elements-grid"))
            )
            time.sleep(2) 
        except TimeoutException:
            print(f"    Timeout waiting for main content on artwork page {artwork_page_num} for '{collection_name}'.")
            break

        artworks_from_this_page = scrape_artwork_details(driver, collection_name)
        if not artworks_from_this_page and artwork_page_num > 1: # No artworks on a subsequent page, likely end
            print(f"    No artworks found on page {artwork_page_num} for '{collection_name}', assuming end of collection.")
            break
        artworks_in_this_collection.extend(artworks_from_this_page)

        try:
            next_page_link = driver.find_element(By.XPATH, "//div[@class='wp-pagenavi']//a[@class='nextpostslink']")
            next_page_url = next_page_link.get_attribute("href")
            if next_page_url and next_page_url != driver.current_url : # Ensure it's a new URL
                driver.get(next_page_url)
                artwork_page_num += 1
                time.sleep(2) 
            else:
                print(f"    No 'href' or same URL for next artwork page link. End of collection '{collection_name}'.")
                break
        except NoSuchElementException:
            print(f"    No more artwork pages for collection '{collection_name}'.")
            break
        except StaleElementReferenceException:
            print(f"    Stale element for next page link in collection '{collection_name}'. Breaking.")
            break 
        except Exception as e:
            print(f"    Error finding/clicking next artwork page for collection '{collection_name}': {e}")
            break
            
    return artworks_in_this_collection

def load_scraped_data(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {filepath}. Starting fresh for this file.")
            return []
    return []

def save_scraped_data(filepath, data):
    try:
        # Create a temporary file for writing to avoid corrupting the original on error
        temp_filepath = filepath + ".tmp"
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(temp_filepath, filepath) # Atomic replace if possible
    except IOError as e:
        print(f"Error saving data to {filepath}: {e}")
    except Exception as e: # Catch other potential errors during save
        print(f"An unexpected error occurred during saving to {filepath}: {e}")
        if os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath) # Clean up temp file if replace failed
            except OSError:
                pass


def main():
    driver = setup_driver()
    
    all_collections_output_data = load_scraped_data(OUTPUT_FILE)
    processed_collection_urls = {coll.get("collection_url") for coll in all_collections_output_data if coll.get("collection_url")}
    
    print(f"Resuming scrape. Found {len(processed_collection_urls)} collections already processed in {OUTPUT_FILE}.")

    current_gallery_page_num = 1
    galleries_page_url = BASE_GALLERIES_URL

    while galleries_page_url and current_gallery_page_num <= TOTAL_GALLERY_PAGES :
        print(f"\n>>> Gallery Page {current_gallery_page_num}/{TOTAL_GALLERY_PAGES}: {galleries_page_url}")
        
        try:
            driver.get(galleries_page_url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.woodmart-portfolio-holder"))
            )
            time.sleep(3) 
        except Exception as e:
            print(f"Error loading gallery page {galleries_page_url}: {e}. Attempting to find next page link.")
            try:
                # This part might be brittle if the whole page didn't load.
                # It assumes pagination might still be findable.
                current_url_before_find = driver.current_url
                next_gallery_page_element = driver.find_element(By.XPATH, "//div[@class='woodmart-pagination']//a[contains(text(), '›')]")
                next_url = next_gallery_page_element.get_attribute("href")
                if next_url and next_url != current_url_before_find:
                    galleries_page_url = next_url
                else: # No valid next link, or it points to the same errored page
                    galleries_page_url = None
            except Exception: # Broad exception if finding next link also fails
                print("Could not find next gallery page link after error. Ending gallery pagination.")
                galleries_page_url = None # End outer loop
            current_gallery_page_num += 1
            if galleries_page_url: time.sleep(1)
            continue

        gallery_collection_articles = driver.find_elements(By.CSS_SELECTOR, "article.portfolio-entry")
        total_collections_on_this_page = len(gallery_collection_articles)
        print(f"Found {total_collections_on_this_page} collection articles on this gallery page.")

        collections_metadata_on_this_page = []
        for i, article_el in enumerate(gallery_collection_articles):
            if MAX_COLLECTIONS_PER_GALLERY_PAGE is not None and i >= MAX_COLLECTIONS_PER_GALLERY_PAGE:
                print(f"  Reached max collections per gallery page ({MAX_COLLECTIONS_PER_GALLERY_PAGE}). Skipping rest.")
                break
            try:
                coll_el = article_el.find_element(By.CSS_SELECTOR, "div.snax-collection")
                title_el = coll_el.find_element(By.CSS_SELECTOR, "h3.snax-collection-title a")
                collection_name = title_el.text.strip()
                collection_url = title_el.get_attribute("href")

                curator = "N/A"
                try:
                    curator_el = coll_el.find_element(By.CSS_SELECTOR, "span.snax-entry-author strong")
                    curator = curator_el.text.strip().replace("By ", "")
                except NoSuchElementException: pass

                item_count = "N/A"
                try:
                    item_count_el = coll_el.find_element(By.CSS_SELECTOR, "span.snax-collection-item-count")
                    item_count = item_count_el.text.strip()
                except NoSuchElementException: pass
                
                collection_image_url_galleries_page = None
                try:
                    first_featg_div = article_el.find_element(By.CSS_SELECTOR, "div.scol-bt div.featg")
                    style_attr = first_featg_div.get_attribute("style")
                    collection_image_url_galleries_page = parse_background_image_url(style_attr)
                except NoSuchElementException: pass
                
                collections_metadata_on_this_page.append({
                    "name": collection_name,
                    "collection_url": collection_url,
                    "curator": curator,
                    "title": collection_name, 
                    "image_url": collection_image_url_galleries_page,
                    "items_count_galleries_page": item_count,
                    "artworks": []
                })
            except Exception as e:
                print(f"  Error extracting basic data for a collection item on gallery page {current_gallery_page_num}: {e}")
        
        for idx, collection_detail_object in enumerate(collections_metadata_on_this_page):
            print(f"  Processing collection {idx + 1}/{len(collections_metadata_on_this_page)} on gallery page {current_gallery_page_num}: '{collection_detail_object['name']}'")

            if collection_detail_object["collection_url"] in processed_collection_urls:
                print(f"    Skipping '{collection_detail_object['name']}' as it's already processed.")
                continue
            
            scraped_artworks_list = scrape_single_collection(driver, collection_detail_object)
            
            collection_detail_object["artworks"] = scraped_artworks_list
            all_collections_output_data.append(collection_detail_object)
            processed_collection_urls.add(collection_detail_object["collection_url"])
            
            save_scraped_data(OUTPUT_FILE, all_collections_output_data)
            print(f"    Saved data for '{collection_detail_object['name']}'. Total collections in file: {len(all_collections_output_data)}")
            
            # print(f"    Returning to gallery page: {galleries_page_url} after scraping collection.")
            driver.get(galleries_page_url) 
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.woodmart-portfolio-holder")))
                time.sleep(1)
            except TimeoutException:
                print(f"    Timeout re-loading gallery page {galleries_page_url}. Critical error.")
                galleries_page_url = None 
                break 

        if not galleries_page_url: 
            break

        try:
            next_gallery_page_element = driver.find_element(By.XPATH, "//div[@class='woodmart-pagination']//a[contains(text(), '›')]")
            galleries_page_url = next_gallery_page_element.get_attribute("href")
            if not galleries_page_url:
                 galleries_page_url = None
                 print("No href attribute on 'next' gallery page link.")
        except NoSuchElementException:
            print("No 'next' (›) gallery page link found. End of galleries.")
            galleries_page_url = None
        except StaleElementReferenceException:
            print("Stale element for gallery next page link. Assuming end or issue.")
            galleries_page_url = None

        current_gallery_page_num += 1
        if galleries_page_url: time.sleep(3)

    driver.quit()

    save_scraped_data(OUTPUT_FILE, all_collections_output_data)
    print(f"\n--- Scraping Session Ended ---")
    print(f"Total collections in {OUTPUT_FILE}: {len(all_collections_output_data)}")


if __name__ == "__main__":
    main()