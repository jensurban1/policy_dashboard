import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
OUTPUT_PATH = "data/updates.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# ── 서울시 관심 부서 ──
SEOUL_DEPTS = [
    "미래공간담당관", "공공개발담당관", "용산입체도시담당관", "도시활력담당관",
    "균형발전기획관", "균형발전정책과", "도시정비과", "동남권사업과", "동북권사업과", "서부권사업과", "광화문광장사업과",
    "도시공간기획관", "도시공간전략과", "도시계획과", "도시계획상임기획과", "도시재창조과",
    "신속통합기획과", "도시관리과", "시설계획과", "토지관리과",
    "주택정책관", "건축기획관", "주택정책과", "임대주택과", "부동산정책개발센터",
    "공공주택과", "주거환경개선과", "건축기획과", "전략주택공급과", "공동주택과",
    "주거정비과", "재정비촉진과",
]

# ── 서울 25개 자치구 ──
SGG_LIST = [
    {"val": "11680", "txt": "강남구"}, {"val": "11740", "txt": "강동구"},
    {"val": "11305", "txt": "강북구"}, {"val": "11500", "txt": "강서구"},
    {"val": "11620", "txt": "관악구"}, {"val": "11215", "txt": "광진구"},
    {"val": "11530", "txt": "구로구"}, {"val": "11545", "txt": "금천구"},
    {"val": "11350", "txt": "노원구"}, {"val": "11320", "txt": "도봉구"},
    {"val": "11230", "txt": "동대문구"}, {"val": "11590", "txt": "동작구"},
    {"val": "11440", "txt": "마포구"}, {"val": "11410", "txt": "서대문구"},
    {"val": "11650", "txt": "서초구"}, {"val": "11200", "txt": "성동구"},
    {"val": "11290", "txt": "성북구"}, {"val": "11710", "txt": "송파구"},
    {"val": "11470", "txt": "양천구"}, {"val": "11560", "txt": "영등포구"},
    {"val": "11170", "txt": "용산구"}, {"val": "11380", "txt": "은평구"},
    {"val": "11110", "txt": "종로구"}, {"val": "11140", "txt": "중구"},
    {"val": "11260", "txt": "중랑구"},
]

NARS_SOURCES = [
    {"id": "nars_report",   "name": "연구보고서",   "org": "국회입법조사처", "url": "https://www.nars.go.kr/report/list.do?cmsCode=CM0043"},
    {"id": "nars_research", "name": "정책연구용역", "org": "국회입법조사처", "url": "https://www.nars.go.kr/report/list.do?cmsCode=CM0010"},
]


# ════════════════════════════════════════
# KRIHS — playwright 헤드리스 크롤링
# ════════════════════════════════════════

def crawl_krihs_all():
    """
    playwright로 KRIHS 3개 소스를 한 번에 크롤링.
    반환: {"krihs_brief": [...], "krihs_working": [...], "krihs_article": [...]}
    """
    from playwright.sync_api import sync_playwright

    KRIHS_SOURCES = [
        {
            "id": "krihs_brief",
            "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103050000&pub_kind=BR_1",
            "type": "board",   # div.board_list li 방식
        },
        {
            "id": "krihs_working",
            "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103090000&pub_kind=WKP",
            "type": "board",
        },
        {
            "id": "krihs_article",
            "url": "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1",
            "type": "table",   # table tbody tr 방식
        },
    ]

    results = {s["id"]: [] for s in KRIHS_SOURCES}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": HEADERS["User-Agent"]})

        for src in KRIHS_SOURCES:
            print(f"  KRIHS playwright: {src['id']} ...")
            try:
                page.goto(src["url"], wait_until="networkidle", timeout=30000)
                # 목록이 렌더링될 때까지 대기
                if src["type"] == "board":
                    page.wait_for_selector("div.board_list li", timeout=15000)
                    items = _parse_krihs_board(page)
                else:
                    page.wait_for_selector("table tbody tr", timeout=15000)
                    items = _parse_krihs_table(page)

                results[src["id"]] = items
                print(f"    → {len(items)}건")
            except Exception as e:
                print(f"    [ERROR] {src['id']}: {e}")
                results[src["id"]] = []

        browser.close()

    return results


def _parse_krihs_board(page):
    """div.board_list li 구조 파싱 (Brief·워킹페이퍼 공통)"""
    items = []
    lis = page.query_selector_all("div.board_list li")
    for li in lis[:10]:
        try:
            title_el = li.query_selector("strong.title")
            title = title_el.inner_text().strip() if title_el else ""
            if not title:
                continue

            # 날짜: span.date 텍스트에서 "발행일" 제거
            date_el = li.query_selector("span.date")
            date_raw = date_el.inner_text().strip() if date_el else ""
            date = re.sub(r"발행일\s*", "", date_raw).strip()

            # URL: href 속성에서 /library/.../contents/{id} 추출
            a_el = li.query_selector("a")
            href = a_el.get_attribute("href") if a_el else ""
            m = re.search(r"(/library/[^'\")\s]+)", href)
            url = "https://www.krihs.re.kr" + m.group(1) if m else "https://www.krihs.re.kr"

            items.append({"title": title, "url": url, "date": date})
        except Exception:
            continue
    return items


def _parse_krihs_table(page):
    """table tbody tr 구조 파싱 (월간국토 Article)"""
    items = []
    rows = page.query_selector_all("table tbody tr")
    for row in rows[:15]:
        try:
            tds = row.query_selector_all("td")
            if len(tds) < 2:
                continue

            # td[0] = 제목
            title = tds[0].inner_text().strip()
            if not title or len(title) < 3:
                continue

            # td[1] = 권호 (날짜 대용)
            vol = tds[1].inner_text().strip() if len(tds) > 1 else ""

            # 바로가기 a.btn_line — href에서 pmediaId 추출
            a_el = row.query_selector("a.btn_line")
            url = "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1"
            if a_el:
                href = a_el.get_attribute("href") or ""
                m = re.search(r"pmediaId=(\d+)", href)
                if m:
                    url = f"https://www.krihs.re.kr/library/api/media?pmediaId={m.group(1)}"
                else:
                    # fallback: /library/... 경로 통째로
                    m2 = re.search(r"(/library/[^'\")\s]+)", href)
                    if m2:
                        url = "https://www.krihs.re.kr" + m2.group(1)

            items.append({"title": title, "url": url, "date": vol})
        except Exception:
            continue
    return items


# ════════════════════════════════════════
# NARS
# ════════════════════════════════════════

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def parse_nars(soup):
    items = []
    rows = (
        soup.select("div.report_list li")
        or soup.select("ul.report_list li")
        or soup.select("div.board_list li")
        or soup.select("table tbody tr")
    )
    if not rows:
        for a in soup.select("a[href*='brdView'], a[href*='reportView']")[:10]:
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


# ════════════════════════════════════════
# 서울시 보도자료
# ════════════════════════════════════════

def parse_seoul_page(soup):
    items = []
    for row in soup.select("table tbody tr"):
        cols = row.select("td")
        if len(cols) < 4:
            continue
        title_td = cols[1]
        title_text = title_td.get_text(strip=True).replace("파일있음", "").strip()
        if not title_text or len(title_text) < 5:
            continue
        dept = cols[2].get_text(strip=True)
        date = cols[3].get_text(strip=True)
        if not any(k in dept for k in SEOUL_DEPTS):
            continue
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
        items.append({"title": title_text, "url": post_url, "date": date, "dept": dept})
    return items


def crawl_seoul(base_url, max_pages=10, target=50):
    items = []
    for page in range(1, max_pages + 1):
        url = f"{base_url}?curPage={page}&bbsNo=158"
        print(f"  서울시 {page}페이지...")
        soup = fetch(url)
        if not soup:
            break
        items.extend(parse_seoul_page(soup))
        if len(items) >= target:
            break
    cutoff = (datetime.now(KST) - timedelta(days=14)).strftime("%Y-%m-%d")
    return [i for i in items[:target] if i.get("date", "") >= cutoff]


# ════════════════════════════════════════
# 서울 도시계획포털
# ════════════════════════════════════════

def crawl_upmu():
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU5020600001?subTit=%EC%97%85%EB%AC%B4%EC%9E%90%EB%A3%8C&type=1&brdSeq="
    try:
        r = requests.get(
            "https://seoulboard.seoul.go.kr/front/bbs.json",
            params={"bbsNo": "318", "curPage": "1", "cntPerPage": "15",
                    "srchKey": "sj", "srchText": "", "srchBeginDt": "",
                    "srchEndDt": "", "srchCtgry": ""},
            headers=HEADERS, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [ERROR] 업무자료 API: {e}")
        return []

    items = []
    for item in (data.get("listVO") or {}).get("listObject") or []:
        title = (item.get("sj") or "").strip()
        if not title:
            continue
        ntt_no = str(item.get("nttNo") or "")
        items.append({
            "title": title,
            "url": f"{DETAIL_BASE}{ntt_no}" if ntt_no else "https://urban.seoul.go.kr/view/html/PMNU5020000001",
            "date": (item.get("writngDe") or "")[:10],
            "dept": (item.get("organDept") or "").strip(),
        })
    print(f"  → 업무자료 {len(items)}건")
    return items[:15]


def crawl_ntfc():
    API_URL = "https://urban.seoul.go.kr/ntfc/getNtfcList.json"
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU4030100001"
    SGG_MAP = {s["val"]: s["txt"] for s in SGG_LIST}
    try:
        r = requests.post(
            API_URL,
            json={"pageNo": 1, "pageSize": 30, "keywordList": [""],
                  "pubSiteCode": "", "organCode": "", "bgnDate": "",
                  "endDate": "", "srchType": "title", "noticeCode": ""},
            headers={**HEADERS, "Content-Type": "application/json"}, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [ERROR] 결정고시 API: {e}")
        return []

    items = []
    for item in data.get("content", []):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        notice_code = item.get("noticeCode", "")
        site_code = item.get("siteCode", "")
        site_cd = item.get("siteCd") or {}
        gu_name = site_cd.get("siteName", "") or SGG_MAP.get(site_code, "")
        items.append({
            "title": title,
            "url": f"{DETAIL_BASE}?noticeCode={notice_code}" if notice_code else DETAIL_BASE,
            "date": (item.get("noticeDate") or "")[:10],
            "gu": gu_name,
            "notice_no": item.get("noticeNo", ""),
        })
    print(f"  → 결정고시 {len(items)}건")
    return items


def crawl_wrtanc():
    API_URL = "https://urban.seoul.go.kr/wrtanc/getWrtancList.json"
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU4010100001"
    today = datetime.now(KST)
    bgn = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=180)).strftime("%Y-%m-%d")

    def fetch_gu(reading_area=""):
        payload = {
            "pageNo": 1, "pageSize": 50, "searchGubun": "ing",
            "announceNo": "-", "title": "", "pubSiteCode": "",
            "readingArea": reading_area, "bgnDate": bgn, "endDate": end,
            "onOff": "ALL", "sido": "", "announceNo1": "", "sidoR": "",
            "siteCode": "", "noticeBgnDt": " ", "noticeEndDt": " ",
        }
        try:
            r = requests.post(
                API_URL, json=payload,
                headers={**HEADERS, "Content-Type": "application/json"}, timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("content") or data.get("list") or data.get("resultList") or []
        except Exception as e:
            print(f"  [ERROR] 열람공고 API ({reading_area or '전체'}): {e}")
            return []

    def parse_item(item, gu_name=""):
        announce_code = item.get("announceCode", "")
        proj_code = item.get("projCode", "")
        url = (
            f"{DETAIL_BASE}?announceCode={announce_code}&projCode={proj_code}&searchGubun=ing"
            if announce_code else f"{DETAIL_BASE}?searchGubun=ing"
        )
        title = (item.get("projNm") or item.get("title") or item.get("announceTitle") or "").strip()
        date = (item.get("createDatetime", "")[:10] if item.get("createDatetime") else "")
        end_date = (item.get("noticeEndDt") or "").strip()
        if not gu_name:
            dept = item.get("dept") or {}
            gu_name = (dept.get("deptNm") or dept.get("deptName") or item.get("siteNm") or item.get("pubSiteNm") or "").strip()
        return {"title": title, "url": url, "date": date, "end_date": end_date, "gu": gu_name}

    result = {}
    print("  열람공고 전체 수집 중...")
    all_raw = fetch_gu("")
    result["all"] = [parse_item(i) for i in all_raw if i.get("projNm") or i.get("title")]
    print(f"    → 전체 {len(result['all'])}건")

    for sgg in SGG_LIST:
        raw = fetch_gu(sgg["val"])
        items = [parse_item(i, gu_name=sgg["txt"]) for i in raw if i.get("projNm") or i.get("title")]
        result[sgg["val"]] = items
        if items:
            print(f"    → {sgg['txt']} {len(items)}건")

    return result


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════

def main():
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

    result = {
        "updated_at": datetime.now(KST).isoformat(),
        "sources": {}
    }

    # ── KRIHS 3종 (playwright) ──
    print("\n크롤링: 국토연구원 (playwright 헤드리스)")
    krihs_data = crawl_krihs_all()

    krihs_meta = {
        "krihs_brief":   {"name": "국토정책 Brief",   "org": "국토연구원", "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103050000&pub_kind=BR_1"},
        "krihs_working": {"name": "워킹페이퍼",        "org": "국토연구원", "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103090000&pub_kind=WKP"},
        "krihs_article": {"name": "월간국토 Article", "org": "국토연구원", "url": "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1"},
    }
    for sid, items in krihs_data.items():
        meta = krihs_meta[sid]
        old_urls = {i["url"] for i in existing.get("sources", {}).get(sid, {}).get("items", [])}
        for item in items:
            item["is_new"] = bool(item["url"]) and item["url"] not in old_urls
        result["sources"][sid] = {
            "name": meta["name"], "org": meta["org"],
            "list_url": meta["url"], "items": items, "crawled_at": TODAY,
        }

    # ── NARS (requests) ──
    for src in NARS_SOURCES:
        print(f"\n크롤링: {src['org']} - {src['name']}")
        soup = fetch(src["url"])
        items = parse_nars(soup) if soup else []
        old_urls = {i["url"] for i in existing.get("sources", {}).get(src["id"], {}).get("items", [])}
        for item in items:
            item["is_new"] = bool(item["url"]) and item["url"] not in old_urls
        result["sources"][src["id"]] = {
            "name": src["name"], "org": src["org"],
            "list_url": src["url"], "items": items, "crawled_at": TODAY,
        }
        print(f"  → {len(items)}건")

    # ── 서울시 보도자료 ──
    print("\n크롤링: 서울특별시 - 보도자료")
    seoul_items = crawl_seoul("https://www.seoul.go.kr/news/news_report.do")
    old_urls = {i["url"] for i in existing.get("sources", {}).get("seoul_press", {}).get("items", [])}
    for item in seoul_items:
        item["is_new"] = bool(item["url"]) and item["url"] not in old_urls
    result["sources"]["seoul_press"] = {
        "name": "보도자료", "org": "서울특별시",
        "list_url": "https://www.seoul.go.kr/news/news_report.do",
        "items": seoul_items, "crawled_at": TODAY,
    }

    # ── 업무자료 ──
    print("\n크롤링: 서울 도시계획포털 - 업무자료")
    upmu_items = crawl_upmu()
    old_urls = {i["url"] for i in existing.get("sources", {}).get("upmu", {}).get("items", [])}
    for item in upmu_items:
        item["is_new"] = bool(item["url"]) and item["url"] not in old_urls
    result["sources"]["upmu"] = {
        "name": "업무자료 (법정계획/운영지침)", "org": "서울 도시계획포털",
        "list_url": "https://urban.seoul.go.kr/view/html/PMNU5020000001",
        "items": upmu_items, "crawled_at": TODAY,
    }

    # ── 결정고시 ──
    print("\n크롤링: 서울 도시계획포털 - 결정고시(안)")
    ntfc_items = crawl_ntfc()
    old_urls = {i["url"] for i in existing.get("sources", {}).get("ntfc", {}).get("items", [])}
    for item in ntfc_items:
        item["is_new"] = bool(item["url"]) and item["url"] not in old_urls
    result["sources"]["ntfc"] = {
        "name": "결정고시(안)", "org": "서울 도시계획포털",
        "list_url": "https://urban.seoul.go.kr/view/html/PMNU4030100001",
        "items": ntfc_items, "crawled_at": TODAY,
    }

    # ── 열람공고 ──
    print("\n크롤링: 서울 도시계획포털 - 열람공고(안)")
    wrtanc_data = crawl_wrtanc()
    old_wrtanc_urls = {i["url"] for i in existing.get("sources", {}).get("wrtanc", {}).get("all", [])}
    for key, items in wrtanc_data.items():
        for item in items:
            item["is_new"] = bool(item["url"]) and item["url"] not in old_wrtanc_urls
    result["sources"]["wrtanc"] = {
        "name": "열람공고(안)", "org": "서울 도시계획포털",
        "list_url": "https://urban.seoul.go.kr/view/html/PMNU4010100001?searchGubun=ing",
        "crawled_at": TODAY,
        "items": wrtanc_data.get("all", []),
        "by_gu": {k: v for k, v in wrtanc_data.items() if k != "all"},
        "all": wrtanc_data.get("all", []),
    }

    total_wrtanc = len(wrtanc_data.get("all", []))
    new_wrtanc = sum(1 for i in wrtanc_data.get("all", []) if i.get("is_new"))
    print(f"  → 전체 {total_wrtanc}건 / 신규 {new_wrtanc}건")

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(len(v.get("items", v.get("all", []))) for v in result["sources"].values())
    new_count = sum(
        sum(1 for i in v.get("items", v.get("all", [])) if i.get("is_new"))
        for v in result["sources"].values()
    )
    print(f"\n✅ 완료: 총 {total}건 / 신규 {new_count}건")


if __name__ == "__main__":
    main()
