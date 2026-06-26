"""Extract card images from the official Card_ID_List_EN.pdf.

Usage (from WSL):
    python3 experiments/web/extract_card_images.py

Prerequisites:
    pip install pymupdf pillow numpy
    kaggle competitions download -f "Card_ID List_EN.pdf" pokemon-tcg-ai-battle

Extracts images for cards missing from card_images.json (pokemontcg.io)
into experiments/web/card_imgs/ for the web sandbox fallback.
"""
import csv, os, sys, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
PDF_PATH = os.path.join(PROJECT_ROOT, "reference", "Card_ID_List_EN.pdf")
CSV_PATH = os.path.join(PROJECT_ROOT, "reference", "EN_Card_Data.csv")
IMG_MAP_PATH = os.path.join(SCRIPT_DIR, "card_images.json")
OUT_DIR = os.path.join(SCRIPT_DIR, "card_imgs")
AGENTS_DIR = os.path.join(SCRIPT_DIR, "agents")

try:
    import fitz
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError:
    print("pip install pymupdf pillow numpy")
    sys.exit(1)

if not os.path.exists(PDF_PATH):
    print("PDF not found: %s" % PDF_PATH)
    print("Download: kaggle competitions download -f 'Card_ID List_EN.pdf' pokemon-tcg-ai-battle")
    sys.exit(1)

os.makedirs(OUT_DIR, exist_ok=True)

with open(IMG_MAP_PATH, encoding="utf-8") as f:
    existing_map = json.load(f)

card_pages = {}
seen = set()
with open(CSV_PATH, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        cid = (row.get("Card ID") or "").strip()
        if cid.isdigit() and int(cid) not in seen:
            card_pages[int(cid)] = 39 + len(seen)
            seen.add(int(cid))

print("Total cards in CSV: %d" % len(card_pages))

missing_ids = set()
if os.path.isdir(AGENTS_DIR):
    for deck_name in os.listdir(AGENTS_DIR):
        deck_csv = os.path.join(AGENTS_DIR, deck_name, "deck.csv")
        if not os.path.exists(deck_csv):
            continue
        with open(deck_csv) as f:
            for line in f:
                cid = line.strip()
                if cid and cid not in existing_map:
                    missing_ids.add(int(cid))

if not missing_ids:
    all_ids = set(card_pages.keys()) - set(int(k) for k in existing_map)
    missing_ids = all_ids

print("Cards to extract: %d" % len(missing_ids))


def crop_card(page_img, expected_aspect=0.714):
    arr = np.asarray(page_img.convert("RGB"))
    h, w = arr.shape[:2]
    x0, x1, y0, y1 = int(w * 0.05), int(w * 0.95), int(h * 0.02), int(h * 0.72)
    roi = arr[y0:y1, x0:x1, :]
    darkness = np.max(255 - roi.astype(np.int16), axis=2)
    mask = darkness > 18
    row_counts = mask.sum(axis=1)
    col_counts = mask.sum(axis=0)
    if row_counts.max() <= 0 or col_counts.max() <= 0:
        left, right, top, bottom = int(w * 0.36), int(w * 0.64), int(h * 0.07), int(h * 0.62)
    else:
        rt = max(10, int(row_counts.max() * 0.055))
        ct = max(10, int(col_counts.max() * 0.055))
        ys = np.where(row_counts > rt)[0]
        xs = np.where(col_counts > ct)[0]
        if len(xs) < 10 or len(ys) < 10:
            left, right, top, bottom = int(w * 0.36), int(w * 0.64), int(h * 0.07), int(h * 0.62)
        else:
            left = x0 + int(xs.min())
            right = x0 + int(xs.max()) + 1
            top = y0 + int(ys.min())
            bottom = y0 + int(ys.max()) + 1
            pad = max(8, int(max(w, h) * 0.004))
            left = max(0, left - pad)
            right = min(w, right + pad)
            top = max(0, top - pad)
            bottom = min(h, bottom + pad)
    box_w, box_h = right - left, bottom - top
    if box_w <= 0 or box_h <= 0:
        return page_img
    aspect = box_w / box_h
    cx = (left + right) / 2
    if aspect > expected_aspect * 1.18:
        tw = int(round(box_h * expected_aspect))
        left = int(round(cx - tw / 2))
        right = left + tw
    elif aspect < expected_aspect * 0.82:
        tw = int(round(box_h * expected_aspect))
        left = int(round(cx - tw / 2))
        right = left + tw
    if left < 0:
        right -= left
        left = 0
    if right > w:
        left = max(0, left - (right - w))
        right = w
    fp = max(2, int(max(w, h) * 0.0015))
    left = max(0, left - fp)
    right = min(w, right + fp)
    top = max(0, top - fp)
    bottom = min(h, bottom + fp)
    return page_img.crop((left, top, right, bottom))


pdf = fitz.open(PDF_PATH)
extracted = 0
for cid in sorted(missing_ids):
    if cid not in card_pages:
        continue
    out_path = os.path.join(OUT_DIR, "%d.png" % cid)
    if os.path.exists(out_path):
        extracted += 1
        continue
    page_idx = card_pages[cid]
    try:
        page = pdf.load_page(page_idx)
        zoom = 4
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        draw = ImageDraw.Draw(img)
        for wd in page.get_text("words"):
            wx0, wy0, wx1, wy1 = (c * zoom for c in wd[:4])
            draw.rectangle([wx0 - 3, wy0 - 3, wx1 + 3, wy1 + 3], fill=(255, 255, 255))
        cropped = crop_card(img)
        cropped.save(out_path)
        extracted += 1
        print("  %d: extracted (%dx%d)" % (cid, cropped.width, cropped.height))
    except Exception as e:
        print("  %d: ERROR %s" % (cid, e))

pdf.close()
print("Done: %d/%d extracted" % (extracted, len(missing_ids)))
