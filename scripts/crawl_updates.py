import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
OUTPUT_PATH = "data/updates.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# 서울시 관심 부서 키워드
SEOUL_DEPTS = ["미래공간기획관", "균형발전", "도시공간", "주택실", "주택정책과"]

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
    {
        "id": "seoul_press",
        "name": "보도자료",
        "org": "서울특별시",
        "url": "https://www.seoul.go.kr/news/news_report.do",
        "type": "seoul",
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
    rows = soup.select("ul.board_list li") or soup.select("div.board_list li") or soup.select("li.item")
    if not rows:
        links = soup.select("a[href*='briefView'], a[href*='pub_list_no'], a[href*='briefs']")
        for a in links[:10]:
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            href = a.get("href", "")
            url = "https://www.krihs.re.kr" + href if href.startswith("/") else href
            items.append({"title": title, "url": url, "date": ""})
        return items
    for li in rows[:10]:
        a = li.select_one("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        if len(title) < 5:
            continue
        href = a.get("href", "")
        url = "https://www.krihs.re.kr" + href if href.startswith("/") else href
        date_el = li.select_one(".date, em, span.date")
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


def parse_seoul_page(soup):
    """서울시 보도자료 1페이지 파싱 — 관심 부서 필터링"""
    items = []
    rows = soup.select("table tbody tr")
    for row in rows:
        cols = row.select("td")
        if len(cols) < 4:
            continue
        title_td = cols[1]
        title_text = title_td.get_text(strip=True).replace("파일있음", "").strip()
        if not title_text or len(title_text) < 5:
            continue
        dept = cols[2].get_text(strip=True)
        date = cols[3].get_text(strip=True)

        # 관심 부서 필터
        if not any(k in dept for k in SEOUL_DEPTS):
            continue

        # 게시글 번호 추출
        a_tag = title_td.select_one("a")
        bbs_no = ""
        if a_tag:
            href = a_tag.get("href", "") or ""
            onclick = a_tag.get("onclick", "") or ""
            m = re.search(r"fnTbbsView\('(\d+)'\)", href + onclick)
            if m:
                bbs_no = m.group(1)

        post_url = (
            f"https://www.seoul.go.kr/news/news_report.do#view/{bbs_no}"
            if bbs_no
            else "https://www.seoul.go.kr/news/news_report.do"
        )
        items.append({
            "title": title_text,
            "url": post_url,
            "date": date,
            "dept": dept,
        })
    return items


def crawl_seoul(base_url, max_pages=10, target=10):
    """여러 페이지를 순회하며 관심 부서 글 target건 수집"""
    items = []
    for page in range(1, max_pages + 1):
        url = f"{base_url}?curPage={page}&bbsNo=158"
        print(f"  서울시 {page}페이지 크롤링...")
        soup = fetch(url)
        if not soup:
            break
        page_items = parse_seoul_page(soup)
        items.extend(page_items)
        if len(items) >= target:
            break
    return items[:target]


def crawl_source(source):
    print(f"크롤링: {source['org']} - {source['name']}")
    t = source["type"]

    if t == "seoul":
        items = crawl_seoul(source["url"], max_pages=10, target=10)
    else:
        soup = fetch(source["url"])
        if not soup:
            return []
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
