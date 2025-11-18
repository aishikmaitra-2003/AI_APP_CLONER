import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def extract_components_from_html(html_content, url=None):
    soup = BeautifulSoup(html_content, "html.parser")
    comps = {"url": url, "title": soup.title.string if soup.title else "", "components": []}

    
    for b in soup.find_all(["button", "a", "input"]):
        tag = b.name
        text = (b.get_text() or b.get('value') or b.get('aria-label') or "").strip()
        role = "link" if tag == "a" else "button" if tag == "button" else "input"
        
        itype = b.get('type') or ""
        comps["components"].append({
            "type": "clickable",
            "tag": tag,
            "role": role,
            "input_type": itype,
            "text": text[:200],
            "id": b.get('id'),
            "classes": b.get('class') or []
        })

    
    for form in soup.find_all("form"):
        fields = []
        for inp in form.find_all(["input", "textarea", "select"]):
            fields.append({
                "name": inp.get('name'),
                "type": inp.get('type') or inp.name,
                "placeholder": inp.get('placeholder') or "",
                "required": bool(inp.get('required')),
            })
        comps["components"].append({
            "type": "form",
            "id": form.get('id'),
            "action": form.get('action'),
            "method": form.get('method') or "get",
            "fields": fields
        })

   
    navs = soup.find_all("nav")
    for nav in navs:
        links = [a.get_text(strip=True) for a in nav.find_all("a", href=True)]
        comps["components"].append({
            "type": "nav",
            "links": links[:30]
        })

    
    for ul in soup.find_all(["ul", "ol"]):
        items = [li.get_text(strip=True) for li in ul.find_all("li")]
        comps["components"].append({
            "type": "list",
            "num_items": len(items),
            "sample_items": items[:10]
        })

    
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = []
        for tr in table.find_all("tr")[:5]:
            rows.append([td.get_text(strip=True) for td in tr.find_all("td")])
        comps["components"].append({
            "type": "table",
            "headers": headers,
            "sample_rows": rows
        })

    
    imgs = soup.find_all("img")
    if imgs:
        comps["components"].append({
            "type": "images",
            "count": len(imgs),
            "samples": [img.get('src') for img in imgs[:10]]
        })

    
    headings = []
    for h in ['h1','h2','h3','h4']:
        for tag in soup.find_all(h):
            headings.append({"tag": h, "text": tag.get_text(strip=True)[:150]})
    if headings:
        comps["components"].append({"type":"headings", "items": headings[:50]})

    
    if soup.find('input', {'type':'password'}):
        comps.setdefault("features", []).append("authentication/login_form_detected")

    
    if soup.find('input', {'type':'search'}) or soup.find('input', {'name':'q'}):
        comps.setdefault("features", []).append("search_feature_detected")

    return comps

def extract_from_crawl_index(crawl_index_path):
    with open(crawl_index_path, "r", encoding="utf-8") as f:
        idx = json.load(f)
    pages = []
    for url, meta in idx.items():
        try:
            with open(meta["html"], "r", encoding="utf-8") as fh:
                html = fh.read()
        except Exception:
            html = meta.get("text_snippet", "")
        comps = extract_components_from_html(html, url=url)
        pages.append(comps)
    return {"pages": pages, "domain": urlparse(list(idx.keys())[0]).netloc}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("crawl_index")
    parser.add_argument("--out", default="ux_spec.json")
    args = parser.parse_args()
    spec = extract_from_crawl_index(args.crawl_index)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    print("UX spec written to", args.out)
