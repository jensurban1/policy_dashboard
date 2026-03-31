import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
OUTPUT_PATH = "data/updates.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

SOURCES = [
    {
        "id": "krihs_brief",
        "name": "국토정책 Brief",
        "org": "국토연구원",
        "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103050000&pub_kind=BR_1",
        "type": "krihs",
    },
    {
        "id": "krihs_working",
        "name": "워킹페이퍼",
        "org": "국토연구원",
        "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103090000&pub_kind=WKP",
        "type": "krihs",
    },
    {
        "id": "krihs_article",
        "name": "월간국토 Article",
        "org": "국토연구원",
        "url": "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1",
        "type": "krihs_article",
    },
    {
        "id": "nars_report",
        "name": "연구보고서",
        "org": "국회입법조사처",
        "url": "https://www.nars.go.kr/report/list.do?cmsCode=CM0043",
        "type": "nars",
    },
    {
        "id": "nars_research",
        "name": "정책연구용역",
        "org": "국회입법조사처",
        "url": "https://www.nars.go.kr/report/list.do?cmsCode=CM0010",
        "type": "nars",
    },
]


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def parse_krihs(soup):
    items = []
    links = soup.select("a[href*='briefView'], a[href*='pub_list_no'], a[href*='briefs']")
    if not links:
        links = soup.select("div.board_list a, ul.board_list a, li.item a")
    for a in links[:10]:
        title = a.get_text(strip=True)
        if len(title) < 5:
            continue
        href = a.get("href", "")
        url = "https://www.krihs.re.kr" + href if href.startswith("/") else href
        li = a.find_parent("li") or a.find_parent("tr")
        date_el = li.select_one(".date, em, span.date") if li else None
        date = date_el.get_text(strip=True) if date_el else ""
        items.append({"title": title, "url": url, "date": date})
    return items


def parse_krihs_article(soup):
    items = []
    links = soup.select("a[href*='articleView'], a[href*='articleDetail']")
    if not links:
        links = soup.select("div.cont_list a, ul.list_type a")
    for a in links[:10]:
        title = a.get_text(strip=True)
        if len(title) < 5:
            continue
        href = a.get("href", "")
        url = "https://www.krihs.re.kr" + href if href.startswith("/") else href
        items.append({"title": title, "url": url, "date": ""})
    return items


def parse_nars(soup):
    items = []
    rows = (
        soup.select("div.report_list li")
        or soup.select("ul.report_list li")
        or soup.select("div.board_list li")
        or soup.select("table tbody tr")
    )
    if not rows:
        links = soup.select("a[href*='brdView'], a[href*='reportView']")
        for a in links[:10]:
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            href = a.get("href", "")
            url = "https://www.nars.go.kr" + href if href.startswith("/") else href
            items.append({"title": title, "url": url, "date": ""})
        return items
    for row in rows[:10]:
        a = row.select_one("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        if len(title) < 5:
            continue
        href = a.get("href", "")
        url = "https://www.nars.go.kr" + href if href.startswith("/") else href
        date_el = row.select_one(".date, span.date, td.date")
        date = date_el.get_text(strip=True) if date_el else ""
        items.append({"title": title, "url": url, "date": date})
    return items


def crawl_source(source):
    print(f"크롤링: {source['org']} - {source['name']}")
    soup = fetch(source["url"])
    if not soup:
        return []
    t = source["type"]
    if t == "krihs":
        items = parse_krihs(soup)
    elif t == "krihs_article":
        items = parse_krihs_article(soup)
    elif t == "nars":
        items = parse_nars(soup)
    else:
        items = []
    print(f"  → {len(items)}건 수집")
    return items


def main():
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

    result = {
        "updated_at": datetime.now(KST).isoformat(),
        "sources": {}
    }

    for source in SOURCES:
        sid = source["id"]
        items = crawl_source(source)
        old_urls = {i["url"] for i in existing.get("sources", {}).get(sid, {}).get("items", [])}
        for item in items:
            item["is_new"] = bool(item["url"]) and item["url"] not in old_urls
        result["sources"][sid] = {
            "name": source["name"],
            "org": source["org"],
            "list_url": source["url"],
            "items": items,
            "crawled_at": TODAY,
        }

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(len(v["items"]) for v in result["sources"].values())
    new_count = sum(sum(1 for i in v["items"] if i.get("is_new")) for v in result["sources"].values())
    print(f"\n✅ 완료: 총 {total}건 / 신규 {new_count}건")


if __name__ == "__main__":
    main()
