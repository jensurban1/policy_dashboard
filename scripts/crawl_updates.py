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
SEOUL_DEPTS = [
    # 미래공간기획관
    "미래공간담당관", "공공개발담당관", "용산입체도시담당관", "도시활력담당관",
    # 균형발전본부
    "균형발전기획관", "균형발전정책과", "도시정비과", "동남권사업과", "동북권사업과", "서부권사업과", "광화문광장사업과",
    # 도시공간본부
    "도시공간기획관", "도시공간전략과", "도시계획과", "도시계획상임기획과", "도시재창조과",
    "신속통합기획과", "도시관리과", "시설계획과", "토지관리과",
    # 주택실
    "주택정책관", "건축기획관", "주택정책과", "임대주택과", "부동산정책개발센터",
    "공공주택과", "주거환경개선과", "건축기획과", "전략주택공급과", "공동주택과",
    "주거정비과", "재정비촉진과",
]

# 서울 25개 자치구 코드
SGG_LIST = [
    {"val": "11680", "txt": "강남구"},
    {"val": "11740", "txt": "강동구"},
    {"val": "11305", "txt": "강북구"},
    {"val": "11500", "txt": "강서구"},
    {"val": "11620", "txt": "관악구"},
    {"val": "11215", "txt": "광진구"},
    {"val": "11530", "txt": "구로구"},
    {"val": "11545", "txt": "금천구"},
    {"val": "11350", "txt": "노원구"},
    {"val": "11320", "txt": "도봉구"},
    {"val": "11230", "txt": "동대문구"},
    {"val": "11590", "txt": "동작구"},
    {"val": "11440", "txt": "마포구"},
    {"val": "11410", "txt": "서대문구"},
    {"val": "11650", "txt": "서초구"},
    {"val": "11200", "txt": "성동구"},
    {"val": "11290", "txt": "성북구"},
    {"val": "11710", "txt": "송파구"},
    {"val": "11470", "txt": "양천구"},
    {"val": "11560", "txt": "영등포구"},
    {"val": "11170", "txt": "용산구"},
    {"val": "11380", "txt": "은평구"},
    {"val": "11110", "txt": "종로구"},
    {"val": "11140", "txt": "중구"},
    {"val": "11260", "txt": "중랑구"},
]

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


def crawl_wrtanc():
    """
    서울 도시계획포털 열람공고 API 크롤링.
    전체 + 25개 자치구별로 진행중 공고를 수집해서 반환.
    반환 구조:
    {
      "all":   [{"title":..., "url":..., "date":..., "end_date":..., "gu":...}, ...],
      "11680": [...],  # 강남구
      ...
    }
    """
    API_URL = "https://urban.seoul.go.kr/wrtanc/getWrtancList.json"
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU4010100001"

    # 날짜 범위: 오늘 기준 6개월 전 ~ 6개월 후 (진행중이므로 넉넉하게)
    today = datetime.now(KST)
    bgn = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=180)).strftime("%Y-%m-%d")

    def fetch_gu(reading_area=""):
        payload = {
            "pageNo": 1,
            "pageSize": 50,
            "searchGubun": "ing",          # 진행중 고정
            "announceNo": "-",
            "title": "",
            "pubSiteCode": "",
            "readingArea": reading_area,   # "" = 전체, "11680" = 강남구 등
            "bgnDate": bgn,
            "endDate": end,
            "onOff": "ALL",
            "sido": "",
            "announceNo1": "",
            "sidoR": "",
            "siteCode": "",
            "noticeBgnDt": " ",
            "noticeEndDt": " ",
        }
        try:
            r = requests.post(
                API_URL,
                json=payload,
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("content") or data.get("list") or data.get("resultList") or []
        except Exception as e:
            print(f"  [ERROR] 열람공고 API ({reading_area or '전체'}): {e}")
            return []

    def parse_item(item, gu_name=""):
        """API 응답 아이템 → 공통 포맷 변환"""
        # 공고 URL: announceCode로 상세 페이지 링크
        announce_code = item.get("announceCode", "")
        proj_code = item.get("projCode", "")
        if announce_code:
            url = f"{DETAIL_BASE}?announceCode={announce_code}&projCode={proj_code}&searchGubun=ing"
        else:
            url = f"{DETAIL_BASE}?searchGubun=ing"

        # 공고명: projNm 또는 title 필드
        title = (
            item.get("projNm")
            or item.get("title")
            or item.get("announceTitle")
            or ""
        ).strip()

        # 날짜: 공고일
        date = (
            item.get("createDatetime", "")[:10]
            if item.get("createDatetime")
            else ""
        )

        # 의견제출 종료일 (D-day 표시용)
        end_date = (item.get("noticeEndDt") or "").strip()

        # 자치구명: dept.deptName 또는 siteNm
        if not gu_name:
            dept = item.get("dept") or {}
            gu_name = (
                dept.get("deptNm")
                or dept.get("deptName")
                or item.get("siteNm")
                or item.get("pubSiteNm")
                or ""
            ).strip()

        return {
            "title": title,
            "url": url,
            "date": date,
            "end_date": end_date,
            "gu": gu_name,
        }

    result = {}

    # 전체 수집
    print("  열람공고 전체 수집 중...")
    all_raw = fetch_gu("")
    result["all"] = [parse_item(i) for i in all_raw if i.get("projNm") or i.get("title")]
    print(f"    → 전체 {len(result['all'])}건")

    # 자치구별 수집
    for sgg in SGG_LIST:
        code = sgg["val"]
        name = sgg["txt"]
        raw = fetch_gu(code)
        items = [parse_item(i, gu_name=name) for i in raw if i.get("projNm") or i.get("title")]
        result[code] = items
        if items:
            print(f"    → {name} {len(items)}건")

    return result


def crawl_source(source):
    print(f"크롤링: {source['org']} - {source['name']}")
    t = source["type"]

    if t == "seoul":
        # 14일치 수집 — 페이지당 10건이므로 최대 10페이지, target=50으로 넉넉하게
        items = crawl_seoul(source["url"], max_pages=10, target=50)
        # 14일 이내 필터
        cutoff = (datetime.now(KST) - timedelta(days=14)).strftime("%Y-%m-%d")
        items = [i for i in items if i.get("date", "") >= cutoff]
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


def crawl_upmu():
    """
    서울 도시계획포털 업무자료(법정계획/운영지침)
    seoulboard API: listVO.listObject 배열 사용
    상세 URL: seoulboard.seoul.go.kr/front/detail.do?bbsNo=318&nttNo={nttNo}
    """
    DETAIL_BASE = "https://seoulboard.seoul.go.kr/front/detail.do?bbsNo=318&nttNo="
    try:
        r = requests.get(
            "https://seoulboard.seoul.go.kr/front/bbs.json",
            params={
                "bbsNo": "318",
                "curPage": "1",
                "cntPerPage": "15",
                "srchKey": "sj",
                "srchText": "",
                "srchBeginDt": "",
                "srchEndDt": "",
                "srchCtgry": "",
            },
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [ERROR] 업무자료 API: {e}")
        return []

    raw_list = (data.get("listVO") or {}).get("listObject") or []
    items = []
    for item in raw_list[:15]:
        title = (item.get("sj") or "").strip()
        dept  = (item.get("organDept") or "").strip()
        date  = (item.get("writngDe") or "")[:10]
        ntt_no = str(item.get("nttNo") or "")
        if not title:
            continue
        url = f"{DETAIL_BASE}{ntt_no}" if ntt_no else "https://urban.seoul.go.kr/view/html/PMNU5020000001"
        items.append({"title": title, "url": url, "date": date, "dept": dept})

    print(f"  → 업무자료 {len(items)}건")
    return items


def crawl_ntfc():
    """
    서울 도시계획포털 결정고시 API 크롤링
    POST /ntfc/getNtfcList.json
    """
    API_URL = "https://urban.seoul.go.kr/ntfc/getNtfcList.json"
    DETAIL_BASE = "https://urban.seoul.go.kr/view/html/PMNU4030100001"

    # 자치구코드 → 자치구명 매핑
    SGG_MAP = {s["val"]: s["txt"] for s in SGG_LIST}

    try:
        r = requests.post(
            API_URL,
            json={
                "pageNo": 1,
                "pageSize": 30,
                "keywordList": [""],
                "pubSiteCode": "",
                "organCode": "",
                "bgnDate": "",
                "endDate": "",
                "srchType": "title",
                "noticeCode": "",
            },
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [ERROR] 결정고시 API: {e}")
        return []

    items = []
    content = data.get("content", [])
    for item in content:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        notice_code = item.get("noticeCode", "")
        notice_no = item.get("noticeNo", "")
        site_code = item.get("siteCode", "")
        # siteCd 객체에서 자치구명 추출
        site_cd = item.get("siteCd") or {}
        gu_name = site_cd.get("siteName", "") or SGG_MAP.get(site_code, "")
        date = (item.get("noticeDate") or "")[:10]
        url = f"{DETAIL_BASE}?noticeCode={notice_code}" if notice_code else DETAIL_BASE
        items.append({
            "title": title,
            "url": url,
            "date": date,
            "gu": gu_name,
            "notice_no": notice_no,
        })

    print(f"  → 결정고시 {len(items)}건")
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

    # ── 기존 소스 크롤링 ──
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

    # ── 업무자료(법정계획/운영지침) 크롤링 ──
    print("\n크롤링: 서울 도시계획포털 - 업무자료(법정계획/운영지침)")
    upmu_items = crawl_upmu()
    old_upmu_urls = {i["url"] for i in existing.get("sources", {}).get("upmu", {}).get("items", [])}
    for item in upmu_items:
        item["is_new"] = bool(item["url"]) and item["url"] not in old_upmu_urls
    result["sources"]["upmu"] = {
        "name": "업무자료 (법정계획/운영지침)",
        "org": "서울 도시계획포털",
        "list_url": "https://urban.seoul.go.kr/view/html/PMNU5020000001",
        "items": upmu_items,
        "crawled_at": TODAY,
    }

    # ── 결정고시 크롤링 ──
    print("\n크롤링: 서울 도시계획포털 - 결정고시(안)")
    ntfc_items = crawl_ntfc()
    old_ntfc_urls = {i["url"] for i in existing.get("sources", {}).get("ntfc", {}).get("items", [])}
    for item in ntfc_items:
        item["is_new"] = bool(item["url"]) and item["url"] not in old_ntfc_urls
    result["sources"]["ntfc"] = {
        "name": "결정고시(안)",
        "org": "서울 도시계획포털",
        "list_url": "https://urban.seoul.go.kr/view/html/PMNU4030100001",
        "items": ntfc_items,
        "crawled_at": TODAY,
    }

    # ── 열람공고 크롤링 ──
    print("\n크롤링: 서울 도시계획포털 - 열람공고(안)")
    wrtanc_data = crawl_wrtanc()

    # is_new 체크: 기존 전체 목록의 url 집합과 비교
    old_wrtanc_urls = {
        i["url"]
        for i in existing.get("sources", {}).get("wrtanc", {}).get("all", [])
    }
    for key, items in wrtanc_data.items():
        for item in items:
            item["is_new"] = bool(item["url"]) and item["url"] not in old_wrtanc_urls

    result["sources"]["wrtanc"] = {
        "name": "열람공고(안)",
        "org": "서울 도시계획포털",
        "list_url": "https://urban.seoul.go.kr/view/html/PMNU4010100001?searchGubun=ing",
        "crawled_at": TODAY,
        "items": wrtanc_data.get("all", []),   # 전체 목록 (is_new 체크용)
        "by_gu": {k: v for k, v in wrtanc_data.items() if k != "all"},  # 자치구별
        "all": wrtanc_data.get("all", []),     # 전체 (카드에서 직접 접근)
    }

    total_wrtanc = len(wrtanc_data.get("all", []))
    new_wrtanc = sum(1 for i in wrtanc_data.get("all", []) if i.get("is_new"))
    print(f"  → 전체 {total_wrtanc}건 / 신규 {new_wrtanc}건")

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(
        len(v.get("items", v.get("all", [])))
        for v in result["sources"].values()
    )
    new_count = sum(
        sum(1 for i in v.get("items", v.get("all", [])) if i.get("is_new"))
        for v in result["sources"].values()
    )
    print(f"\n✅ 완료: 총 {total}건 / 신규 {new_count}건")


if __name__ == "__main__":
    main()
