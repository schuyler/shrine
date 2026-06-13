#!/usr/bin/env python3
"""
fetch_nature_pack.py — download CC0 ambient nature beds from Freesound.

Pulls continuous ambient material in four categories (wind, water, rain, fire)
to use as looping beds. Download-only: it fetches files and writes a manifest;
it does not loop them. (Loop them yourself — sox `splice` crossfade works well.)

AUTH / QUALITY NOTE
-------------------
Authenticates with a Freesound API *token* (env var FREESOUND_API_TOKEN).
Token auth can search metadata and fetch HQ previews, but it CANNOT download the
lossless originals — that endpoint requires full OAuth2. So this grabs the HQ OGG
preview: stereo, ~192 kbps Vorbis, 44.1 kHz. Decoded to PCM and looped, that is
effectively transparent for this medium. If you need true lossless, run
Freesound's OAuth2 flow or hand-pick originals from the site.

Selection is enforced BOTH server-side (in the query filter) and again in-code,
so every downloaded file is guaranteed:
  - CC0 (public-domain dedication)
  - stereo (2 channels)
  - raw duration >= --min-duration (headroom to cut a clean loop)

Output:
  <out>/<category>/<id>_<name>.ogg
  <out>/manifest.csv

Usage:
  export FREESOUND_API_TOKEN=...
  python3 fetch_nature_pack.py                  # 3 per category -> ./nature_pack
  python3 fetch_nature_pack.py -n 5 -o beds     # 5 per category -> ./beds
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_SEARCH = "https://freesound.org/apiv2/search/text/"

FIELDS = ("id,name,username,license,channels,samplerate,bitdepth,"
          "duration,type,avg_rating,num_ratings,previews")

# Queries biased toward continuous, transient-light beds.
CATEGORIES = {
    "wind":  "wind ambient",
    "water": "water stream river ambient",
    "rain":  "rain ambient",
    "fire":  "fire crackling campfire",
}

# Verified-valid Freesound sort values: downloads_desc, rating_desc,
# num_ratings_desc, score. downloads_desc = community-vetted popularity.
SORT = "downloads_desc"

PAGE_SIZE = 50         # results per search page
MAX_PAGES = 4          # cap pages scanned per category
REQUEST_PAUSE = 0.5    # seconds between network calls (politeness / rate limit)

CC0_MARKER = "publicdomain/zero"   # substring of the CC0 license URL


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def get_token():
    tok = os.environ.get("FREESOUND_API_TOKEN", "").strip()
    if not tok:
        die("FREESOUND_API_TOKEN is not set. `export FREESOUND_API_TOKEN=...` and re-run.")
    return tok


def http_get(url, token=None, binary=False):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Token {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return data if binary else json.loads(data.decode("utf-8"))


def search_page(token, query, page, min_dur):
    params = {
        "query": query,
        "filter": f'license:"Creative Commons 0" channels:2 duration:[{min_dur:g} TO *]',
        "sort": SORT,
        "fields": FIELDS,
        "page_size": PAGE_SIZE,
        "page": page,
    }
    url = API_SEARCH + "?" + urllib.parse.urlencode(params)
    return http_get(url, token=token)


def is_cc0(license_url):
    return CC0_MARKER in (license_url or "").lower()


def acceptable(r, min_dur):
    # In-code re-check — never trust the query filter alone.
    return (
        is_cc0(r.get("license"))
        and r.get("channels") == 2
        and float(r.get("duration") or 0) >= min_dur
        and r.get("previews", {}).get("preview-hq-ogg")
    )


def safe_name(name):
    base = re.sub(r"\.[A-Za-z0-9]+$", "", name)      # drop file extension
    base = re.sub(r"[^\w\- ]+", "", base).strip()    # strip odd characters
    base = re.sub(r"\s+", "_", base)
    return (base or "sound")[:60]


def download_preview(url, dest, token):
    # CDN previews are public; retry with auth only if the CDN ever rejects us.
    try:
        data = http_get(url, token=None, binary=True)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            data = http_get(url, token=token, binary=True)
        else:
            raise
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser(
        description="Download CC0 stereo ambient nature beds from Freesound.")
    ap.add_argument("-n", "--per-category", type=int, default=3,
                    help="files per category (default 3)")
    ap.add_argument("-o", "--out", default="nature_pack",
                    help="output directory (default ./nature_pack)")
    ap.add_argument("--min-duration", type=float, default=30.0,
                    help="minimum raw seconds (default 30)")
    args = ap.parse_args()

    if args.per_category < 1:
        die("--per-category must be >= 1")

    token = get_token()
    os.makedirs(args.out, exist_ok=True)

    manifest = []
    seen_ids = set()

    for category, query in CATEGORIES.items():
        print(f"\n== {category} ==  query: {query!r}")
        cat_dir = os.path.join(args.out, category)
        os.makedirs(cat_dir, exist_ok=True)
        got = 0
        page = 1

        while got < args.per_category and page <= MAX_PAGES:
            try:
                result = search_page(token, query, page, args.min_duration)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    die("Freesound returned 401 — token missing or invalid.")
                print(f"  search page {page} failed: HTTP {e.code}; stopping category")
                break
            except urllib.error.URLError as e:
                print(f"  search page {page} network error: {e}; stopping category")
                break

            results = result.get("results", [])
            if not results:
                break

            for r in results:
                if got >= args.per_category:
                    break
                rid = r.get("id")
                if rid in seen_ids or not acceptable(r, args.min_duration):
                    continue

                ogg_url = r["previews"]["preview-hq-ogg"]
                fname = f"{rid}_{safe_name(r.get('name', ''))}.ogg"
                dest = os.path.join(cat_dir, fname)
                try:
                    size = download_preview(ogg_url, dest, token)
                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    print(f"  [skip] id {rid}: download failed ({e})")
                    continue

                seen_ids.add(rid)
                got += 1
                dur = float(r.get("duration") or 0)
                print(f"  [ok] {fname}  ({dur:.1f}s, {size // 1024} KiB)")
                manifest.append({
                    "id": rid,
                    "category": category,
                    "name": r.get("name", ""),
                    "author": r.get("username", ""),
                    "license": r.get("license", ""),
                    "freesound_url": f"https://freesound.org/s/{rid}/",
                    "duration_s": f"{dur:.2f}",
                    "channels": r.get("channels", ""),
                    "samplerate": r.get("samplerate", ""),
                    "avg_rating": r.get("avg_rating", ""),
                    "num_ratings": r.get("num_ratings", ""),
                    "file": os.path.join(category, fname),
                })
                time.sleep(REQUEST_PAUSE)

            page += 1
            time.sleep(REQUEST_PAUSE)

        if got < args.per_category:
            print(f"  note: found only {got}/{args.per_category} for {category}")

    if manifest:
        man_path = os.path.join(args.out, "manifest.csv")
        with open(man_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(manifest[0].keys()))
            w.writeheader()
            w.writerows(manifest)
        print(f"\ndone: {len(manifest)} files. manifest -> {man_path}")
    else:
        print("\ndone: no files downloaded.")


if __name__ == "__main__":
    main()
