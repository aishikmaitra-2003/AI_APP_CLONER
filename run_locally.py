import argparse
import json
import subprocess
import os
import sys
from crawler import crawl
from extractor import extract_from_crawl_index
from gen_alpha import generate_scaffold

import asyncio

def run_pipeline(url, outdir="run_output", max_pages=15, max_depth=2, app_name="GeneratedApp"):
    os.makedirs(outdir, exist_ok=True)
    crawl_out = os.path.join(outdir, "crawl")
    os.makedirs(crawl_out, exist_ok=True)

    print("Starting crawl (headless)...")
    loop = asyncio.get_event_loop()
    try:
        crawl_res = loop.run_until_complete(crawl(url, max_pages=max_pages, max_depth=max_depth, out_dir=crawl_out))
    except Exception as e:
        print("Crawl failed:", e)
        sys.exit(1)
    print("Crawl finished. Writing index...")
    index_path = os.path.join(crawl_out, "crawl_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(crawl_res, f, indent=2)

    print("Extracting UX spec...")
    
    spec_out = os.path.join(outdir, "ux_spec.json")
    from extractor import extract_from_crawl_index as extract_fn
    ux_spec = extract_fn(index_path)
    with open(spec_out, "w", encoding="utf-8") as f:
        json.dump(ux_spec, f, indent=2)
    print("UX spec written to", spec_out)

    print("Generating scaffold via LLM...")
    try:
        zip_path = generate_scaffold(ux_spec, app_name=app_name)
    except Exception as e:
        print("Scaffold generation failed:", e)
        sys.exit(1)
    print("Done — scaffold zip:", zip_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the app/site you own")
    parser.add_argument("--out", default="run_output")
    parser.add_argument("--max_pages", type=int, default=12)
    parser.add_argument("--max_depth", type=int, default=2)
    parser.add_argument("--name", default="GeneratedApp")
    args = parser.parse_args()
    run_pipeline(args.url, outdir=args.out, max_pages=args.max_pages, max_depth=args.max_depth, app_name=args.name)
