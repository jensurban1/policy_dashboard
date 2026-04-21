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

# ════════════════════════════════════════
# 헤더 강화: 실제 Chrome이 보내는 풀세트
# ════════════════════════════════════════
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def api_headers(referer):
    """JSON API 호출용 헤더 (Referer/Origin/XMLHttpRequest 추가)"""
    h = {**HEADERS}
    h["Accept"] = "application/json, text/plain, */*"
    h["Sec-Fetch-Dest"] = "empty"
    h["Sec-Fetch-Mode"] = "cors"
    h["Sec-Fetch-Site"] = "same-origin"
    h["Referer"] = referer
    parts = referer.split("/", 3)
    h["Origin"] = parts[0] + "//" + parts[2]
    h["X-Requested-With"] = "XMLHttpRequest"
    return h


def _normalize_date(s: str) -> str:
    """다양한 날짜 형식을 YYYY-MM-DD로 통일. 실패 시 빈 문자열."""
    if not s:
        return ""
    s = s.strip()
    m = re.search(r"(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


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
    from playwright.sync_api import sync_playwright

    KRIHS_SOURCES = [
        {"id": "krihs_brief",   "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103050000&pub_kind=BR_1", "type": "board"},
        {"id": "krihs_working", "url": "https://www.krihs.re.kr/krihsLibraryReport/briefList.es?mid=a10103090000&pub_kind=WKP",  "type": "board"},
        {"id": "krihs_article", "url": "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1", "type": "table"},
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
    items = []
    lis = page.query_selector_all("div.board_list li")
    for li in lis[:10]:
        try:
            title_el = li.query_selector("strong.title")
            title = title_el.inner_text().strip() if title_el else ""
            if not title:
                continue

            date_el = li.query_selector("span.date")
            date_raw = date_el.inner_text().strip() if date_el else ""
            date = re.sub(r"발행일\s*", "", date_raw).strip()

            a_el = li.query_selector("a")
            href = a_el.get_attribute("href") if a_el else ""
            m = re.search(r"'[a-z]+-(\d+)'", href)
            if m:
                list_no = m.group(1)
                mid_m = re.search(r"mid=([a-z0-9]+)", page.url)
                mid = mid_m.group(1) if mid_m else "a10103050000"
                url = f"https://www.krihs.re.kr/gallery.es?mid={mid}&bid=0022&act=view&list_no={list_no}"
            else:
                url = page.url

            items.append({"title": title, "url": url, "date": date})
        except Exception:
            continue
    return items


def _parse_krihs_table(page):
    items = []
    rows = page.query_selector_all("table tbody tr")
    for row in rows[:15]:
        try:
            tds = row.query_selector_all("td")
            if len(tds) < 2:
                continue

            title = tds[0].inner_text().strip()
            if not title or len(title) < 3:
                continue

            vol = tds[1].inner_text().strip() if len(tds) > 1 else ""

            a_el = row.query_selector("a.btn_line")
            url = "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1"
            if a_el:
                href = a_el.get_attribute("href") or ""
                m = re.search(r"'a-(\d+)'", href)
                if m:
                    list_no = m.group(1)
                    url = f"https://www.krihs.re.kr/gallery.es?mid=a10103010000&bid=0025&act=view&list_no={list_no}"

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
    content = soup.select_one("#content")
    if not content:
        return items

    for a in content.select("a[href]")[:50]:
        href = a.get("href", "")
        m = re.search(r"view\('(\d+)'\)", href)
        if not m:
            continue
        ntt_id = m.group(1)
        title = a.get_text(strip=True)
        if len(title) < 5:
            continue
        url = f"https://www.nars.go.kr/report/view.do?nttId={ntt_id}"
        li = a.find_parent("li")
        date = ""
        if li:
            d = re.search(r"(\d{4}\.\d{2}\.\d{2})", li.get_text())
            if d:
                date = d.group(1).replace(".", "-")
        items.append({"title": title, "url": url, "date": date})
        if len(items) >= 10:
            break
    return items


# ════════════════════════════════════════
# 서울시 보도자료 (헤더 강화 + 세션)
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
    sess = requests.Session()
    # 메인 페이지 한 번 방문해서 쿠키 획득
    try:
        sess.get("https://www.seoul.go.kr/main/index.jsp", headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"  [WARN] 서울시 메인 방문 실패 (무시하고 진행): {e}")

    for page in range(1, max_pages + 1):
        url = f"{base_url}?curPage={page}&bbsNo=158"
        print(f"  서울시 {page}페이지...")
        try:
            r = sess.get(url, headers={**HEADERS, "Referer": base_url}, timeout=15)
            print(f"    status={r.status_code}, len={len(r.text)}")  # 진단
            r.raise_for_status()
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"  [ERROR] 서울시 {page}페이지: {e}")
            break

        page_items = parse_seoul_page(soup)
        # 날짜 정규화 (안전장치)
        for it in page_items:
            it["date"] = _normalize_date(it.get("date", ""))
        items.extend(page_items)
        if len(items) >= target:
            break

    cutoff = (datetime.now(KST) - timedelta(days=14)).strftime("%Y-%m-%d")
    # 날짜 비어있으면 살려둠 (페이지 형식 변경 대비)
    filtered = [i for i in items[:target] if (not i.get("date")) or i["date"] >= cutoff]
    print(f"  → 서울시 보도자료 최종 {len(filtered)}건 (raw {len(items)}건)")
    return filtered


# ════════════════════════════════════════
# 서울 도시계획포털 - 업무자료 (헤더 강화 + 세션)
# ════════════════════════════════════════

def crawl_upmu():
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU5020600001?subTit=%EC%97%85%EB%AC%B4%EC%9E%90%EB%A3%8C&type=1&brdSeq="
    REFERER = "https://urban.seoul.go.kr/view/html/PMNU5020000001"

    sess = requests.Session()
    try:
        sess.get(REFERER, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"  [WARN] 업무자료 페이지 방문 실패 (무시하고 진행): {e}")

    try:
        r = sess.get(
            "https://seoulboard.seoul.go.kr/front/bbs.json",
            params={"bbsNo": "318", "curPage": "1", "cntPerPage": "15",
                    "srchKey": "sj", "srchText": "", "srchBeginDt": "",
                    "srchEndDt": "", "srchCtgry": ""},
            headers=api_headers(REFERER),
            timeout=20,
        )
        print(f"  업무자료 응답: status={r.status_code}, len={len(r.text)}")  # 진단
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


# ════════════════════════════════════════
# 서울 도시계획포털 - 결정고시 (헤더 강화 + 세션)
# ════════════════════════════════════════

def crawl_ntfc():
    API_URL = "https://urban.seoul.go.kr/ntfc/getNtfcList.json"
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU4030100001"
    REFERER = DETAIL_BASE
    SGG_MAP = {s["val"]: s["txt"] for s in SGG_LIST}

    sess = requests.Session()
    try:
        sess.get(REFERER, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"  [WARN] 결정고시 페이지 방문 실패 (무시하고 진행): {e}")

    try:
        r = sess.post(
            API_URL,
            json={"pageNo": 1, "pageSize": 30, "keywordList": [""],
                  "pubSiteCode": "", "organCode": "", "bgnDate": "",
                  "endDate": "", "srchType": "title", "noticeCode": ""},
            headers={**api_headers(REFERER), "Content-Type": "application/json"},
            timeout=20,
        )
        print(f"  결정고시 응답: status={r.status_code}, len={len(r.text)}")  # 진단
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


# ════════════════════════════════════════
# 서울 도시계획포털 - 열람공고 (헤더 강화 + 세션)
# ════════════════════════════════════════

def crawl_wrtanc():
    API_URL = "https://urban.seoul.go.kr/wrtanc/getWrtancList.json"
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU4010100001"
    REFERER = "https://urban.seoul.go.kr/view/html/PMNU4010100001?searchGubun=ing"
    today = datetime.now(KST)
    bgn = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=180)).strftime("%Y-%m-%d")

    sess = requests.Session()
    try:
        sess.get(REFERER, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"  [WARN] 열람공고 페이지 방문 실패 (무시하고 진행): {e}")

    def fetch_gu(reading_area=""):
        payload = {
            "pageNo": 1, "pageSize": 50, "searchGubun": "ing",
            "announceNo": "-", "title": "", "pubSiteCode": "",
            "readingArea": reading_area, "bgnDate": bgn, "endDate": end,
            "onOff": "ALL", "sido": "", "announceNo1": "", "sidoR": "",
            "siteCode": "", "noticeBgnDt": " ", "noticeEndDt": " ",
        }
        try:
            r = sess.post(
                API_URL, json=payload,
                headers={**api_headers(REFERER), "Content-Type": "application/json"},
                timeout=20,
            )
            print(f"  열람공고 ({reading_area or '전체'}): status={r.status_code}, len={len(r.text)}")  # 진단
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
