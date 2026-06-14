#!/usr/bin/env python3
import os
import re
import urllib.request
import urllib.parse
import json
import html
import time

# Configuration
DEFAULT_SECRET = "7fK9xLm2Qp8Vn4RsY1ZaT6Hd"
DEFAULT_TARGET_URL = "http://localhost:3000/api/telegram/webhook"

DEALS_CATEGORIES = [
    {"name": "Today's Best Deals", "url": "https://earnkaro.com/top-selling-products/today-best-deals", "category": None},
    {"name": "Flash Deals", "url": "https://earnkaro.com/top-selling-products/flash-deals", "category": None},
    {"name": "Best in Fashion", "url": "https://earnkaro.com/top-selling-products/best-in-fashion-tsp", "category": "fashion"},
    {"name": "Ajio Sale Offers", "url": "https://earnkaro.com/top-selling-products/ajio-sale-tsp", "category": "fashion"},
    {"name": "Trending Offers", "url": "https://earnkaro.com/product/trending-offers", "category": None},
    {"name": "Finance Deals", "url": "https://earnkaro.com/top-selling-products/finance-deals", "category": "finance"}
]

def get_env_secret():
    """Reads the webhook secret token from .env.local file if it exists."""
    secret = DEFAULT_SECRET
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('TELEGRAM_WEBHOOK_SECRET='):
                        secret = line.split('=', 1)[1].strip()
                        secret = secret.strip('"').strip("'")
                        break
        except Exception as e:
            print(f"[-] Error reading webhook secret from .env.local: {e}")
    return secret

def get_env_cookies():
    """Reads the EarnKaro cookies from .env.local file if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    cookies = ""
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('EARNKARO_COOKIES='):
                        cookies = line.split('=', 1)[1].strip()
                        cookies = cookies.strip('"').strip("'")
                        break
        except Exception as e:
            pass
    return cookies

def get_rid_from_token():
    """Reads and decodes the EARNKARO_API_TOKEN from .env.local to extract the primary RID."""
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    token = ""
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('EARNKARO_API_TOKEN='):
                        token = line.split('=', 1)[1].strip()
                        token = token.strip('"').strip("'")
                        break
        except Exception as e:
            print(f"[-] Error reading EARNKARO_API_TOKEN from .env.local: {e}")
            
    if not token:
        return None
        
    try:
        import base64
        import json
        parts = token.split('.')
        if len(parts) >= 2:
            payload = parts[1]
            # Add base64 padding if missing
            payload += '=' * (-len(payload) % 4)
            decoded = base64.b64decode(payload).decode('utf-8', errors='ignore')
            data = json.loads(decoded)
            return data.get('earnkaro')
    except Exception as e:
        print(f"[-] Error decoding EARNKARO_API_TOKEN: {e}")
        
    return None


def save_cookies_to_env(cookies):
    """Saves the cookies to .env.local file."""
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    lines = []
    updated = False
    
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('EARNKARO_COOKIES='):
                        lines.append(f'EARNKARO_COOKIES="{cookies}"\n')
                        updated = True
                    else:
                        lines.append(line)
        except Exception:
            pass
            
    if not updated:
        lines.append(f'\n# Scraper Session Cookies\nEARNKARO_COOKIES="{cookies}"\n')
        
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("[+] Saved cookies to .env.local for future runs.")
    except Exception as e:
        print(f"[-] Failed to save cookies to .env.local: {e}")

def resolve_tracking_link(url, cookies_str, max_depth=5):
    """
    Resolves the JavaScript-redirect (var cashbackUrl) in EarnKaro tracking pages 
    to extract the original retailer product link.
    """
    if max_depth <= 0:
        return url
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookies_str
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            final_url = response.geturl()
            content = response.read().decode('utf-8', errors='ignore')
            
            # Find the cashbackUrl in script block
            cashback_match = re.search(r'var\s+cashbackUrl\s*=\s*["\']([^"\']+)["\']', content)
            if cashback_match:
                next_url = cashback_match.group(1)
                
                # Check if it has a redirect or target query parameter
                parsed = urllib.parse.urlparse(next_url)
                query = urllib.parse.parse_qs(parsed.query)
                for p in ['redirect', 'dl', 'url', 'u', 'dest', 'link', 'goto', 'target', 'to']:
                    if p in query:
                        target = query[p][0]
                        if target.startswith('http'):
                            return target
                            
                # Otherwise recurse
                return resolve_tracking_link(next_url, cookies_str, max_depth - 1)
            else:
                # Fallback to query params on the final resolved URL
                parsed_final = urllib.parse.urlparse(final_url)
                query_final = urllib.parse.parse_qs(parsed_final.query)
                for p in ['redirect', 'dl', 'url', 'u', 'dest', 'link', 'goto', 'target', 'to']:
                    if p in query_final:
                        target = query_final[p][0]
                        if target.startswith('http'):
                            return target
                return final_url
    except Exception:
        return url

def clean_title(title_line):
    """Cleans emojis, price tags, and formatting from a text line."""
    line = re.sub(r'https?://[^\s]+', '', title_line)
    line = re.sub(r'[\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF]', '', line)
    line = re.sub(r'(?:rs\.?|₹|mrp:?\s?₹?|@)\s?\d[\d,]*', '', line, flags=re.IGNORECASE)
    line = re.sub(r'^[\s\-|:|•|🔗|✅|💥]+|[\s\-|:|•|🔗|✅|💥]+$', '', line).strip()
    return line

def clean_url_python(url):
    """Removes tracking parameters and normalizes the product URL in Python."""
    try:
        parsed = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        
        hostname = (parsed.hostname or "").lower()
        
        # Determine store and how to clean
        is_flipkart = 'flipkart.' in hostname or 'shopsy.' in hostname or 'fkrt.cc' in hostname
        is_amazon = 'amazon.' in hostname or 'amzn.to' in hostname
        is_myntra = 'myntra.' in hostname or 'myntr.in' in hostname
        is_ajio = 'ajio.' in hostname
        is_meesho = 'meesho.' in hostname
        is_croma = 'croma.' in hostname
        is_nykaa = 'nykaa.' in hostname
        
        new_params = {}
        
        if is_flipkart:
            # Keep only 'pid'
            if 'pid' in query_params:
                new_params['pid'] = query_params['pid']
        elif is_amazon or is_myntra or is_ajio or is_meesho or is_croma or is_nykaa:
            # Keep nothing
            pass
        else:
            # Keep everything except known tracking parameters for other stores
            tracking_keys = {
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
                'clickid', 'click_id', 'clickid',
                'affid', 'aff_id', 'aff_click_id',
                'subid', 'subid1', 'subid2', 'subid3', 'subid',
                'gclid', 'fbclid', 'dclid', 'msclkid',
                'tag', 'linkcode',
                '_gl', '_gcl_au',
                'ref', 'ref_',
                'customertype', 'curated', 'curatedid', 'gridcolumns', 'sort',
                'offer_id', 'attribution_window', 'return_cancellation_window', 'pid'
            }
            for k, v in query_params.items():
                if k.lower() not in tracking_keys:
                    new_params[k] = v
                    
        # Reconstruct query string
        new_query = urllib.parse.urlencode(new_params, doseq=True)
        
        # Build clean URL
        clean_parts = parsed._replace(query=new_query, fragment='')
        return urllib.parse.urlunparse(clean_parts)
    except Exception:
        return url

def get_store_from_url(url):
    """Maps domain names to known store slugs."""
    try:
        parsed = urllib.parse.urlparse(url.lower())
        hostname = parsed.hostname or ""
        if 'amazon.' in hostname or 'amzn.to' in hostname:
            return 'amazon'
        if 'flipkart.' in hostname or 'shopsy.' in hostname or 'fkrt.cc' in hostname:
            return 'flipkart'
        if 'myntra.' in hostname or 'myntr.in' in hostname:
            return 'myntra'
        if 'ajio.' in hostname:
            return 'ajio'
        if 'meesho.' in hostname:
            return 'meesho'
        if 'croma.' in hostname:
            return 'croma'
        if 'nykaa.' in hostname:
            return 'nykaa'
        if '1mg' in hostname or 'tata1mg' in hostname:
            return 'tata-1mg'
        return 'other'
    except Exception:
        return 'other'

def get_category_from_text(title, text):
    """Infers the category slug from text keywords."""
    content = f"{title} {text}".lower()
    if any(k in content for k in ['phone', 'mobile', 'iphone', 'samsung', 'realme', 'redmi', 'oneplus', 'smartphone']):
        return 'mobiles'
    if any(k in content for k in ['laptop', 'macbook', 'computer', 'desktop']):
        return 'laptops'
    if any(k in content for k in ['tv', 'television', 'audio', 'speaker', 'headphone', 'earphone', 'airpods', 'earbuds', 'airdopes', 'buds', 'tws', 'camera', 'smartwatch', 'smart light', 'bulb', 'power bank']):
        return 'electronics'
    if any(k in content for k in ['refrigerator', 'fridge', 'washing machine', 'ac', 'air conditioner', 'cooler', 'geyser', 'microwave', 'oven']):
        return 'appliances'
    if any(k in content for k in ['tshirt', 'shirt', 'jeans', 'top', 'dress', 'kurta', 'saree', 'shoes', 'sneakers', 'sandals', 'jacket', 'clothing', 'apparel', 'bag', 'backpack']):
        return 'fashion'
    if any(k in content for k in ['lipstick', 'makeup', 'eyeliner', 'kajal', 'cream', 'serum', 'facewash', 'face wash', 'sunscreen', 'moisturizer', 'perfume', 'deodorant', 'hair oil', 'shampoo', 'conditioner']):
        return 'beauty'
    if any(k in content for k in ['supplement', 'protein', 'whey', 'multivitamin', 'vitamin', 'capsule', 'tablet', 'health', 'medicine', 'condom']):
        return 'health'
    if any(k in content for k in ['bedsheet', 'blanket', 'pillow', 'cushion', 'curtain', 'towel', 'mattress', 'sofa', 'chair', 'table', 'desk', 'decor', 'lamp', 'clock']):
        return 'home'
    if any(k in content for k in ['cookware', 'pan', 'tawa', 'cooker', 'kettle', 'stove', 'blender', 'mixer', 'grinder', 'toaster', 'bottle', 'lunch box', 'spoon', 'fork', 'knife']):
        return 'kitchen'
    if any(k in content for k in ['tea', 'coffee', 'juice', 'cola', 'biscuit', 'cookie', 'chips', 'namkeen', 'snack', 'chocolate', 'oil', 'sugar', 'soap', 'detergent']):
        return 'grocery'
    return 'other'

def fetch_earnkaro_deals(cookies_str):
    """Fetches deals payload from the authenticated EarnKaro deals sections."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookies_str
    }
    
    deals = []
    
    # Try to extract the RID from the affiliate token first (guarantees your account is credited)
    user_rid = get_rid_from_token()
    if user_rid:
        print(f"    [+] Using primary Referral ID from API Token: {user_rid}")
    else:
        # Fallback to cookies RID
        rid_match = re.search(r'RID=(\d+)', cookies_str)
        user_rid = rid_match.group(1) if rid_match else ""
        if user_rid:
            print(f"    [+] Using fallback Referral ID from Cookies: {user_rid}")
    
    for category_info in DEALS_CATEGORIES:
        print(f"\n[*] Scraping category: {category_info['name']}...")
        
        category_deals_count = 0
        limit = category_info.get("limit")
        
        # Scrape page 1 and page 2 for each category to get more deals
        for page in [1, 2]:
            if limit and category_deals_count >= limit:
                break
                
            page_url = f"{category_info['url']}?paging={page}"
            req = urllib.request.Request(page_url, headers=headers)
            
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    content = response.read().decode('utf-8')
                    next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]*?)</script>', content)
                    
                    if next_data_match:
                        parsed = json.loads(next_data_match.group(1))
                        data = parsed.get('props', {}).get('pageProps', {}).get('data', [])
                        
                        if not data:
                            print(f"    [-] Page {page} returned 0 deals. Skipping.")
                            continue
                            
                        print(f"    [+] Loaded Page {page}. Found {len(data)} deal items.")
                        
                        for item in data:
                            if limit and category_deals_count >= limit:
                                break
                                
                            attrs = item.get('attributes', {})
                            if not attrs:
                                continue
                                
                            title = clean_title(attrs.get('name', ''))
                            
                            price_str = attrs.get('category_price_starting_from')
                            price = int(float(price_str)) if price_str else None
                            
                            # Parse original price & discount
                            price_info = attrs.get('price', {}) or {}
                            original_price_str = price_info.get('original_price')
                            original_price = int(float(original_price_str)) if original_price_str else None
                            discount = price_info.get('discount_percentage')
                            
                            if discount:
                                discount = int(discount)
                                
                            # Re-calculate or fix pricing inconsistencies (e.g. dummy 100 Rs. values)
                            if price and original_price:
                                if original_price <= price:
                                    if discount and 0 < discount < 100:
                                        original_price = int(price / (1 - (discount / 100)))
                                    else:
                                        original_price = None
                                elif not discount:
                                    discount = int(((original_price - price) / original_price) * 100)
                            elif price and discount and not original_price:
                                if 0 < discount < 100:
                                    original_price = int(price / (1 - (discount / 100)))
                                    
                            image = attrs.get('image_url')
                            cashback_url = attrs.get('cashback_url', '')
                            
                            # Ensure the user's RID is appended to the tracking link
                            if cashback_url and user_rid and not cashback_url.endswith(user_rid):
                                cashback_url = cashback_url + user_rid
                                
                            # Deduplicate check: don't add the same cashback_url twice in this session
                            if any(d['cashback_url'] == cashback_url for d in deals):
                                continue
                                
                            category = category_info['category'] or get_category_from_text(title, title)
                            
                            deals.append({
                                'title': title,
                                'price': price,
                                'original_price': original_price,
                                'discount': discount,
                                'image': image,
                                'cashback_url': cashback_url,
                                'category': category
                            })
                            category_deals_count += 1
                    else:
                        print(f"    [-] Script tag __NEXT_DATA__ not found on Page {page}.")
            except Exception as e:
                print(f"    [x] Failed to scrape {page_url}: {e}")
                
    return deals

def push_deal_to_webhook(deal, secret_token, target_url):
    """Sends the formatted deal payload to the target webhook."""
    # Ensure title is above the URL so the webhook's title override logic extracts it
    text_lines = [
        deal['title'],
        deal['resolved_url']
    ]
    
    if deal['price']:
        text_lines.append(f"Price: Rs. {deal['price']}")
    if deal['original_price']:
        text_lines.append(f"MRP: Rs. {deal['original_price']}")
    if deal['discount']:
        text_lines.append(f"Discount: {deal['discount']}% Off")
    if deal['image']:
        text_lines.append(f"Image: {deal['image']}")
    if deal['category']:
        text_lines.append(f"Category: {deal['category']}")
        
    message_text = "\n".join(text_lines)
    
    payload = {
        "message": {
            "message_id": 9999 + int(os.urandom(2).hex(), 16),
            "chat": {
                "id": -1009999999,
                "title": "EarnKaro Website Scraper",
                "type": "channel"
            },
            "text": message_text
        }
    }
    
    req_url = f"{target_url}?token={secret_token}"
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(
        req_url,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'DealNestScraperPython/3.0'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            return True, res_json
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("         DEALNEST AUTOMATIC SCRA- IMPORT ENGINE")
    print("=" * 60)
    
    secret = get_env_secret()
    print(f"[+] Loaded Webhook Token: ...{secret[-6:] if len(secret) > 6 else secret}")
    
    # Load cookies from env or prompt
    cookies = get_env_cookies()
    if not cookies:
        print("\n[!] Session cookies not found in .env.local.")
        cookies = input("Paste your EarnKaro document.cookie string: ").strip()
        if not cookies:
            print("[-] No cookies provided. Scraping will return 0 deals. Exiting.")
            return
        # Save cookies to .env.local for future runs
        save_cookies_to_env(cookies)
    else:
        print("[+] Loaded Session Cookies from .env.local")
        
    import sys
    if not sys.stdin.isatty():
        target_url = DEFAULT_TARGET_URL
        print(f"\n[+] Non-interactive mode: Using default target URL: {target_url}")
    else:
        try:
            target_url = input(f"\nEnter target webhook URL [{DEFAULT_TARGET_URL}]: ").strip()
            if not target_url:
                target_url = DEFAULT_TARGET_URL
        except (EOFError, KeyboardInterrupt):
            target_url = DEFAULT_TARGET_URL
            print(f"\n[+] Using default target URL: {target_url}")
        
    # Fetch deals from web portal
    deals_list = fetch_earnkaro_deals(cookies)
    if not deals_list:
        print("[-] No deals found. Please verify your cookies are correct and not expired.")
        return
        
    print(f"\n[*] Resolving redirect links and importing {len(deals_list)} deals...")
    
    success_count = 0
    duplicate_count = 0
    fail_count = 0
    
    # Track resolved URLs to prevent sending duplicates during the run
    seen_resolved_urls = set()
    
    for idx, raw_deal in enumerate(deals_list, 1):
        # Clean title for safe Windows console output printing
        safe_title = raw_deal['title'][:50].encode('ascii', 'ignore').decode('ascii')
        print(f"\n[{idx}/{len(deals_list)}] Processing: {safe_title}...")
        
        # 1. Expand the tracking link to retrieve clean merchant URL
        print("    [*] Resolving redirect tracking link...")
        resolved = resolve_tracking_link(raw_deal['cashback_url'], cookies)
        
        # Clean URL in Python
        cleaned_url = clean_url_python(resolved)
        raw_deal['resolved_url'] = cleaned_url
        
        # Local deduplication check
        if cleaned_url in seen_resolved_urls:
            print("    [-] Skipped: Duplicate resolved URL in this session.")
            duplicate_count += 1
            continue
            
        seen_resolved_urls.add(cleaned_url)
        
        store_slug = get_store_from_url(cleaned_url)
        print(f"    [+] Store: {store_slug.upper()} | Resolved URL: {cleaned_url[:60]}...")
        
        # 2. Push to webhook
        success, response = push_deal_to_webhook(raw_deal, secret, target_url)
        if success:
            details = response.get('details', [])
            reason = response.get('reason', '')
            
            # Check if duplicate
            is_dup = False
            for detail in details:
                if "duplicate" in str(detail.get('error', '')).lower():
                    is_dup = True
                    break
            if "duplicate" in reason.lower():
                is_dup = True
                
            if is_dup:
                print("    [-] Skipped: Deal already exists in database.")
                duplicate_count += 1
            else:
                print("    [+] Success: Imported successfully!")
                success_count += 1
        else:
            print(f"    [x] Failed: {response}")
            fail_count += 1
            
        # Polite delay to prevent API rate limits/timeouts
        time.sleep(1.5)
            
    print("\n" + "=" * 60)
    print("                 IMPORT SUMMARY RESULTS")
    print("=" * 60)
    print(f"Total processed:  {len(deals_list)}")
    print(f"Newly Imported:   {success_count}")
    print(f"Duplicates:       {duplicate_count}")
    print(f"Failed:           {fail_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()

