import os
import asyncio
import json
import time
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from tqdm import tqdm

def allowed_by_robots(url):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = requests.get(robots_url, timeout=5)
        if r.status_code != 200:
            return True
        txt = r.text.lower()
       
        if "disallow: /" in txt:
            return False
        return True
    except Exception:
        return True


PROPRIETARY_MARKERS = ["instagram.com", "facebook.com", "whatsapp.com", "uber.com", "airbnb.com", "tiktok.com", "twitter.com", "x.com", "snapchat.com"]
def likely_proprietary_domain(url):
    p = urlparse(url).netloc.lower()
    return any(k in p for k in PROPRIETARY_MARKERS)

async def crawl(start_url, max_pages=30, max_depth=2, out_dir="crawl_output"):
    os.makedirs(out_dir, exist_ok=True)
    #if not allowed_by_robots(start_url):
    #   raise RuntimeError("Crawling disallowed by robots.txt for this site.")

    if likely_proprietary_domain(start_url):
        raise RuntimeError("Target domain appears to be a large proprietary app. Aborting (policy).")

    visited = set()
    queue = [(start_url, 0)]
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass

            try:
                content = await page.content()
            except Exception:
                content = ""
            timestamp = int(time.time())

            
            parsed = urlparse(url)
            safe_name = parsed.netloc + parsed.path.replace('/', '_') or "root"
            screenshot_path = os.path.join(out_dir, f"{safe_name[:120]}_{timestamp}.png")
            html_path = os.path.join(out_dir, f"{safe_name[:120]}_{timestamp}.html")
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
            except Exception:
                pass
            try:
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass

            
            soup = BeautifulSoup(content, "html.parser")
            links = set()
            for a in soup.find_all("a", href=True):
                href = a['href']
                if href.startswith("javascript:") or href.startswith("#"):
                    continue
                joined = urljoin(url, href)
                
                if urlparse(joined).netloc == urlparse(start_url).netloc:
                    links.add(joined.split('#')[0])

            results[url] = {
                "url": url,
                "screenshot": os.path.abspath(screenshot_path) if os.path.exists(screenshot_path) else None,
                "html": os.path.abspath(html_path),
                "text_snippet": soup.get_text(separator=" ", strip=True)[:2000],
                "links": list(links),
            }

            visited.add(url)
            
            for l in links:
                if l not in visited and len(visited) + len(queue) < max_pages:
                    queue.append((l, depth + 1))

        await browser.close()
    return results


if __name__ == "__main__":
    import argparse, asyncio
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--out", default="crawl_output")
    parser.add_argument("--max_pages", type=int, default=20)
    parser.add_argument("--max_depth", type=int, default=2)
    args = parser.parse_args()
    res = asyncio.run(crawl(args.url, max_pages=args.max_pages, max_depth=args.max_depth, out_dir=args.out))
    with open(os.path.join(args.out, "crawl_index.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print("Crawl complete. Output in", args.out)
