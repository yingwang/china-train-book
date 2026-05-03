"""Fetch CC-licensed city hero images from Wikimedia Commons.

Run: python3 scripts/fetch_city_images.py
"""
from __future__ import annotations
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
IMG_DIR = ROOT / "docs" / "images" / "cities"
CHAPTERS = ROOT / "docs" / "chapters"
CREDITS = ROOT / "docs" / "images" / "CREDITS.md"

# (chapter_file, city_heading, slug, [search queries])
TARGETS = [
    ("01-hangzhou.md", None, "hangzhou", ["West Lake Hangzhou", "Hangzhou skyline"]),
    ("02-near.md", "上海", "shanghai", ["The Bund Shanghai", "Shanghai skyline night"]),
    ("02-near.md", "苏州", "suzhou", ["Suzhou Humble Administrator garden", "Suzhou canal"]),
    ("02-near.md", "南京", "nanjing", ["Nanjing Confucius Temple", "Ming Xiaoling"]),
    ("02-near.md", "绍兴", "shaoxing", ["Shaoxing canal", "Lu Xun Native Place"]),
    ("02-near.md", "宁波", "ningbo", ["Ningbo Tianyi Pavilion", "Ningbo skyline"]),
    ("02-near.md", "黄山", "huangshan", ["Huangshan mountain pine", "Yellow Mountain China"]),
    ("03-mid.md", "北京", "beijing", ["Forbidden City Beijing", "Tiananmen"]),
    ("03-mid.md", "武汉", "wuhan", ["Yellow Crane Tower Wuhan", "Wuhan skyline"]),
    ("03-mid.md", "厦门", "xiamen", ["Gulangyu island Xiamen", "Xiamen Hulishan"]),
    ("03-mid.md", "福州", "fuzhou", ["Fuzhou Sanfang Qixiang", "Fuzhou skyline"]),
    ("03-mid.md", "长沙", "changsha", ["Yuelu mountain Changsha", "Changsha skyline"]),
    ("04-far.md", "西安", "xian", ["Xi'an city wall", "Terracotta Army"]),
    ("04-far.md", "成都", "chengdu", ["Chengdu giant panda", "Wuhou shrine Chengdu"]),
    ("04-far.md", "重庆", "chongqing", ["Chongqing skyline night", "Hongya Cave"]),
    ("04-far.md", "广州", "guangzhou", ["Canton Tower Guangzhou", "Chen Clan Academy"]),
    ("04-far.md", "深圳", "shenzhen", ["Shenzhen skyline night", "Shenzhen city"]),
    ("04-far.md", "桂林", "guilin", ["Li River Guilin", "Yangshuo karst"]),
]

ACCEPTABLE = {
    "CC BY 2.0","CC BY 2.5","CC BY 3.0","CC BY 4.0",
    "CC BY-SA 2.0","CC BY-SA 2.5","CC BY-SA 3.0","CC BY-SA 4.0",
    "CC0","PDM","Public domain",
}
TITLE_REJECT = ["map", "logo", "flag", "diagram", "calligraphy", "manuscript",
                "scroll", "painting", "statue", "coin", "banknote",
                "platform", "train", "metro", "subway"]

UA = "ChinaTrainGuideImageFetcher/1.0 (https://github.com/yingwang/china-train-book)"


def search(q, limit=20):
    p = {"action":"query","format":"json","generator":"search","gsrsearch":q,
         "gsrnamespace":"6","gsrlimit":str(limit),"prop":"imageinfo",
         "iiprop":"url|extmetadata|size|mime"}
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return list(json.load(r).get("query",{}).get("pages",{}).values())


def strip_html(s):
    s = re.sub(r"<[^>]+>","",s or "")
    return re.sub(r"\s+"," ",s).strip()


def pick(results):
    candidates = []
    for p in results:
        info = (p.get("imageinfo") or [{}])[0]
        em = info.get("extmetadata") or {}
        ls = (em.get("LicenseShortName") or {}).get("value","")
        mime = info.get("mime","")
        w, h = info.get("width",0) or 0, info.get("height",0) or 0
        title = p.get("title","")
        if ls not in ACCEPTABLE: continue
        if mime not in {"image/jpeg","image/png","image/webp"}: continue
        if max(w,h) < 1200: continue
        if any(kw in title.lower() for kw in TITLE_REJECT): continue
        candidates.append((w*h, p, info, em, ls))
    if not candidates: return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, page, info, em, ls = candidates[0]
    return {"title":page.get("title"),"url":info.get("url").split("?")[0],
            "license":ls,"author":strip_html((em.get("Artist") or {}).get("value","")),
            "width":info.get("width"),"height":info.get("height"),"mime":info.get("mime")}


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent":UA})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        while c := r.read(64*1024): f.write(c)


def insert(chapter_path: Path, heading: str | None, image_md: str) -> bool:
    text = chapter_path.read_text()
    if heading is None:
        # insert after H1 (top of file) for chapter without sub-cities
        m = re.search(r"^# .+$", text, re.MULTILINE)
        if not m: return False
        # insert after first paragraph (first blank line after H1)
        idx = text.find("\n\n", m.end())
        if idx < 0: return False
        new = text[:idx+2] + image_md + "\n\n" + text[idx+2:]
        chapter_path.write_text(new)
        return True
    line = f"## {heading}"
    if line + "\n" not in text: return False
    new = text.replace(line + "\n", line + "\n\n" + image_md + "\n", 1)
    if new == text: return False
    chapter_path.write_text(new)
    return True


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    new_credits = []
    ok = fail = 0
    for chapter, heading, slug, queries in TARGETS:
        existing = list(IMG_DIR.glob(f"{slug}.*"))
        if existing:
            print(f"[skip] {slug} (exists)")
            continue
        chosen = None
        for q in queries:
            try:
                r = search(q)
            except Exception as e:
                print(f"[warn] {slug}: '{q}': {e}", file=sys.stderr); continue
            chosen = pick(r)
            if chosen:
                chosen["query"] = q
                break
            time.sleep(0.3)
        if not chosen:
            print(f"[fail] {slug}"); fail += 1; continue
        ext = {"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}[chosen["mime"]]
        dest = IMG_DIR / f"{slug}.{ext}"
        try:
            download(chosen["url"], dest)
        except Exception as e:
            print(f"[fail dl] {slug}: {e}"); fail += 1; continue

        rel = f"../images/cities/{dest.name}"
        img_md = f'![{slug}]({rel})' + '{ width="640" .center }'
        chapter_path = CHAPTERS / chapter
        inserted = insert(chapter_path, heading, img_md)

        commons_url = f"https://commons.wikimedia.org/wiki/{chosen['title'].replace(' ','_')}"
        new_credits.append(
            f"## {slug}\n\n"
            f"- File: `images/cities/{dest.name}`\n"
            f"- Original: [{chosen['title']}]({commons_url})\n"
            f"- Author: {chosen['author'] or 'Unknown'}\n"
            f"- License: {chosen['license']}\n"
            f"- Search query: `{chosen['query']}`\n"
        )
        print(f"[ok] {slug}: {chosen['title']} [{chosen['license']}]  inserted={inserted}")
        ok += 1
        time.sleep(0.5)

    if new_credits:
        text = CREDITS.read_text() + "\n\n" + "\n".join(new_credits)
        CREDITS.write_text(text)
    print(f"\nok={ok} fail={fail}")


if __name__ == "__main__":
    main()
