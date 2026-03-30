"""
Vivino Taste Data Scraper
- 18개 와인 슬라이더 점수 + 아로마 데이터 추출
- vivino_taste_data.csv 저장
"""

import csv
import json
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ── 와인 목록 ────────────────────────────────────────────────────────────────
WINES = [
    ("w01", "개스톰버튼 엑스트라브륏",         "https://www.vivino.com/en/gaston-burtin-extra-brut-champagne/w/12489584"),
    ("w03", "생콤 레듀스 알비옹 루즈",          "https://www.vivino.com/en/chateau-de-saint-cosme-cotes-du-rhone-les-deux-albion/w/1173569"),
    ("w04", "몽푸콩 바롱 루이",                 "https://www.vivino.com/en/de-montfaucon-baron-louis-lirac-cotes-du-rhone/w/1117640"),
    ("w05", "몽푸콩 샤또네프 뒤 빠쁘",          "https://www.vivino.com/en/de-montfaucon-chateauneuf-du-pape/w/4821949"),
    ("w06", "라살라 끼안티 클라시코",            "https://www.vivino.com/en/it-la-sala-chianti-classico/w/2140869"),
    ("w07", "라살라 끼안티 클라시코 리제르바",   "https://www.vivino.com/en/it-la-sala-chianti-classico-riserva/w/2221646"),
    ("w08", "깜뽀 알베로",                      "https://www.vivino.com/en/it-la-sala-campo-all-albero/w/1195511"),
    ("w09", "파팔레 리네아 오로",               "https://www.vivino.com/en/varvaglione-papale-linea-oro-primitivo-di-manduria/w/1202838"),
    ("w11", "프로토타입 까베르네쇼비뇽",         "https://www.vivino.com/en/prototype-cabernet-sauvignon/w/5885528"),
    ("w12", "프로토타입 진판델",                "https://www.vivino.com/en/prototype-zinfandel/w/6172116"),
    ("w13", "프로토타입 샤르도네",              "https://www.vivino.com/en/prototype-chardonnay/w/6781547"),
    ("w14", "포웰앤썬 리버사이드 바로사 GSM",   "https://www.vivino.com/en/powell-son-riverside-grenache-mataro-shiraz/w/5394465"),
    ("w15", "포웰앤썬 에덴밸리 리슬링",         "https://www.vivino.com/en/powell-son-riesling/w/3854730"),
    ("w16", "마히 쇼비뇽 블랑",                "https://www.vivino.com/en/mahi-sauvignon-blanc/w/1112088"),
    ("w17", "마히 피노누아",                   "https://www.vivino.com/en/mahi-pinot-noir/w/1112105"),
    ("w18", "인비니티 쇼비뇽블랑",             "https://www.vivino.com/en/lawson-s-dry-hills-inviniti-sauvignon-blanc-marlborough/w/10100841"),
    ("w19", "마지스 까르미네르",               "https://www.vivino.com/en/terramater-magis-limited-reserve-carmenere/w/9597776"),
    ("w20", "마지스 까베르네쇼비뇽",           "https://www.vivino.com/en/terramater-magis-limited-reserve-cabernet-sauvignon/w/7247216"),
]

PAGE_WAIT = 5
PAGE_GAP  = 2
OUTPUT    = "vivino_taste_data.csv"
UA        = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── 드라이버 ─────────────────────────────────────────────────────────────────
def build_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-US,en")
    opts.add_argument(f"user-agent={UA}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    try:
        driver = webdriver.Chrome(options=opts)
    except Exception:
        svc = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=svc, options=opts)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return driver


# ── 쿠키 팝업 처리 ───────────────────────────────────────────────────────────
def dismiss_cookie_popup(driver: webdriver.Chrome):
    for text in ["Accept", "I agree", "I Accept", "Accept all", "Agree"]:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//button[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'{text.upper()}')]")
                )
            )
            btn.click()
            time.sleep(0.5)
            return
        except Exception:
            pass


# ── 슬라이더 파싱: left: XX% → 1–5 점수 ──────────────────────────────────────
LABEL_MAP = {
    "light":  "body",      "bold":    "body",
    "smooth": "tannin",    "tannic":  "tannin",
    "dry":    "sweetness", "sweet":   "sweetness",
    "soft":   "acidity",   "acidic":  "acidity",
    "gentle": "fizziness", "fizzy":   "fizziness",
}

def left_to_score(pct: float) -> float:
    return round(1 + (pct / 100.0) * 4, 2)


def parse_sliders_html(src: str) -> dict:
    """tasteCharacteristic 행 → {body, tannin, sweetness, acidity, fizziness}"""
    sliders = {}
    # 각 행: 왼쪽 레이블 … left:XX% … 오른쪽 레이블
    pattern = re.compile(
        r'class="[^"]*tasteCharacteristic[^"]*".*?'
        r'class="[^"]*property[^"]*">([^<]+)</[^>]+>.*?'
        r'left:\s*([\d.]+)%.*?'
        r'class="[^"]*property[^"]*">([^<]+)</',
        re.S,
    )
    for m in pattern.finditer(src):
        left_lbl  = m.group(1).strip().lower()
        left_pct  = float(m.group(2))
        right_lbl = m.group(3).strip().lower()
        key = LABEL_MAP.get(left_lbl) or LABEL_MAP.get(right_lbl)
        if key and key not in sliders:
            sliders[key] = left_to_score(left_pct)
    return sliders


def parse_sliders_indicator(driver: webdriver.Chrome) -> dict:
    """DOM에서 indicatorBar 요소의 style.left 직접 읽기 (HTML 파싱 실패 시 fallback)"""
    sliders = {}
    # 슬라이더 컨테이너 찾기
    rows = driver.find_elements(
        By.CSS_SELECTOR,
        "[class*='tasteCharacteristic'], [class*='taste-characteristic']",
    )
    for row in rows:
        try:
            indicator = row.find_element(
                By.CSS_SELECTOR,
                "[class*='indicatorBar'], [class*='indicator']",
            )
            style = indicator.get_attribute("style") or ""
            m = re.search(r'left:\s*([\d.]+)%', style)
            if not m:
                # style이 width만 있는 경우 child 확인
                children = row.find_elements(By.CSS_SELECTOR, "[style*='left']")
                for c in children:
                    s = c.get_attribute("style") or ""
                    m = re.search(r'left:\s*([\d.]+)%', s)
                    if m:
                        break
            if not m:
                continue
            left_pct = float(m.group(1))
            # 행의 레이블 텍스트
            labels = row.find_elements(By.CSS_SELECTOR, "[class*='property'], [class*='label']")
            lbls = [l.text.strip().lower() for l in labels if l.text.strip()]
            key = None
            for lbl in lbls:
                key = LABEL_MAP.get(lbl)
                if key:
                    break
            if key and key not in sliders:
                sliders[key] = left_to_score(left_pct)
        except Exception:
            continue
    return sliders


def parse_sliders_json(src: str) -> dict:
    """JSON baseline_structure fallback"""
    sliders = {}
    m = re.search(r'"baseline_structure"\s*:\s*(\{[^}]+\})', src)
    if not m:
        return sliders
    try:
        bs = json.loads(m.group(1))
    except json.JSONDecodeError:
        return sliders
    mapping = {
        "intensity": "body",
        "tannin":    "tannin",
        "sweetness": "sweetness",
        "acidity":   "acidity",
        "fizziness": "fizziness",
    }
    for jk, sk in mapping.items():
        val = bs.get(jk)
        if val is not None:
            sliders[sk] = round(float(val), 2)
    return sliders


# ── 아로마 파싱 ───────────────────────────────────────────────────────────────
def parse_aroma(body_text: str, src: str):
    """
    Returns:
        keywords  : "blackberry, cherry, plum" (개별 키워드)
        mentions  : "207 mentions of black fruit notes | ..." (카테고리)
    """
    # 카테고리 멘션
    mention_matches = re.findall(
        r'(\d[\d,]*)\s+mentions?\s+of\s+([^\n]{3,60})',
        body_text, re.I,
    )
    mentions_list = [f"{c.replace(',','')} mentions of {d.strip()}" for c, d in mention_matches[:8]]

    # 개별 아로마 키워드 (JSON에서 추출)
    keywords_set = []
    try:
        flavor_blocks = re.findall(
            r'"group_name"\s*:\s*"[^"]*".*?"stats"\s*:\s*\[.*?\]',
            src, re.S,
        )
        for block in flavor_blocks:
            names = re.findall(r'"name"\s*:\s*"([^"]+)"', block)
            for n in names:
                if n not in keywords_set:
                    keywords_set.append(n)
    except Exception:
        pass

    # JSON에서 못 찾으면 body_text에서 추출 시도
    if not keywords_set and mention_matches:
        # "What does this wine taste like?" 이후 단락에서 개별 단어 추출
        m_start = re.search(r'taste like\?', body_text, re.I)
        if m_start:
            taste_section = body_text[m_start.end():m_start.end() + 500]
            # 소문자, 공백 포함 짧은 구 (아로마 키워드 형태)
            words = re.findall(r'\b[a-z][a-z ]{2,20}[a-z]\b', taste_section)
            seen = set()
            for w in words:
                w = w.strip()
                if w not in seen and w not in ("mentions", "of", "notes", "based", "on", "user", "reviews"):
                    seen.add(w)
                    keywords_set.append(w)
                    if len(keywords_set) >= 12:
                        break

    return (
        ", ".join(keywords_set[:12]),
        " | ".join(mentions_list),
    )


# ── 평점 파싱 ─────────────────────────────────────────────────────────────────
def parse_rating(src: str, body_text: str):
    """평균 평점 (1~5 소수점)"""
    m = re.search(r'"average"\s*:\s*([\d.]+)', src)
    if m:
        try:
            return str(round(float(m.group(1)), 1))
        except ValueError:
            pass
    m = re.search(r'\b([1-5]\.[0-9])\b', body_text)
    return m.group(1) if m else ""


def parse_ratings_count(body_text: str, src: str):
    """총 ratings 수"""
    # JSON에서 먼저
    m = re.search(r'"ratings_count"\s*:\s*(\d+)', src)
    if m:
        return m.group(1)
    m = re.search(r'([\d,]+)\s+ratings?', body_text, re.I)
    return m.group(1).replace(",", "") if m else ""


# ── 페이지 스크래핑 ───────────────────────────────────────────────────────────
def scrape_one(driver: webdriver.Chrome, wid: str, name: str, url: str) -> dict:
    driver.get(url)
    dismiss_cookie_popup(driver)
    time.sleep(PAGE_WAIT)

    # 스크롤 (lazy-load 트리거)
    for pos in [400, 800, 1200, 800, 400]:
        driver.execute_script(f"window.scrollTo(0, {pos})")
        time.sleep(0.3)
    time.sleep(0.5)

    # Cloudflare 재시도
    src = driver.page_source
    if "Just a moment" in src or "cf-browser-verification" in src:
        print("    ⚠ Cloudflare — 12s 재시도")
        time.sleep(12)
        driver.get(url)
        time.sleep(PAGE_WAIT + 3)
        src = driver.page_source

    # 첫 번째 와인의 HTML을 디버그 파일로 저장
    if wid == WINES[0][0]:
        try:
            with open("debug_taste_p1.html", "w", encoding="utf-8") as dbg:
                dbg.write(src[:80000])
            print("    [debug] debug_taste_p1.html 저장됨")
        except Exception as e:
            print(f"    [debug] 저장 실패: {e}")

    body_text = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        pass

    # 페이지 상태 진단 출력
    title = driver.title
    body_len = len(body_text)
    src_len  = len(src)
    print(f"    title={title!r}  body_len={body_len}  src_len={src_len}")

    # 슬라이더: HTML 파싱 → DOM fallback → JSON fallback
    sliders = parse_sliders_html(src)
    method = "html"
    if not sliders:
        sliders = parse_sliders_indicator(driver)
        method = "dom"
    if not sliders:
        sliders = parse_sliders_json(src)
        method = "json"

    if sliders:
        print(f"    슬라이더 {len(sliders)}개 [{method}]: {sliders}")
    else:
        print("    ⚠ 슬라이더 없음")

    aroma_kw, aroma_mention = parse_aroma(body_text, src)
    rating        = parse_rating(src, body_text)
    ratings_count = parse_ratings_count(body_text, src)

    return {
        "id":             wid,
        "original_name":  name,
        "vivino_url":     url,
        "rating":         rating,
        "ratings_count":  ratings_count,
        "body":           sliders.get("body", ""),
        "tannin":         sliders.get("tannin", ""),
        "sweetness":      sliders.get("sweetness", ""),
        "acidity":        sliders.get("acidity", ""),
        "fizziness":      sliders.get("fizziness", ""),
        "aroma_keywords": aroma_kw,
        "aroma_mentions": aroma_mention,
    }


def scrape_with_retry(driver: webdriver.Chrome, wid: str, name: str, url: str) -> dict:
    for attempt in range(1, 3):
        try:
            result = scrape_one(driver, wid, name, url)
            return result
        except Exception as e:
            print(f"    attempt {attempt} error: {e}")
            if attempt < 2:
                time.sleep(5)
    # 모두 실패
    return {
        "id": wid, "original_name": name, "vivino_url": url,
        "rating": "FAILED", "ratings_count": "FAILED",
        "body": "FAILED", "tannin": "FAILED", "sweetness": "FAILED",
        "acidity": "FAILED", "fizziness": "FAILED",
        "aroma_keywords": "FAILED", "aroma_mentions": "FAILED",
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    driver = build_driver()
    results = []

    for i, (wid, name, url) in enumerate(WINES, 1):
        print(f"\n[{i:02d}/{len(WINES):02d}] {wid} {name}")
        row = scrape_with_retry(driver, wid, name, url)
        results.append(row)

        def fv(k): return f"{row[k]}" if row[k] != "" else "-"
        print(
            f"    rating={fv('rating')}  ratings={fv('ratings_count')}  "
            f"body={fv('body')}  tannin={fv('tannin')}  "
            f"sweet={fv('sweetness')}  acid={fv('acidity')}  fizz={fv('fizziness')}"
        )
        if row["aroma_mentions"]:
            print(f"    아로마: {row['aroma_mentions'][:80]}")

        if i < len(WINES):
            time.sleep(PAGE_GAP)

    driver.quit()

    # ── CSV 저장 ──────────────────────────────────────────────────────────────
    fieldnames = [
        "id", "original_name", "vivino_url",
        "rating", "ratings_count",
        "body", "tannin", "sweetness", "acidity", "fizziness",
        "aroma_keywords", "aroma_mentions",
    ]
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✓ {OUTPUT} 저장 완료 ({len(results)}행)\n")

    # ── 터미널 테이블 ─────────────────────────────────────────────────────────
    COL_W = [4, 20, 5, 8, 5, 5, 6, 6, 6]
    COLS  = ["id", "이름", "평점", "평점수", "Body", "Tannin", "Sweet", "Acid", "Fizz"]
    SEP   = "+" + "+".join("-" * (w + 2) for w in COL_W) + "+"

    def cell(val, w):
        s = str(val) if val not in (None, "") else "-"
        return f" {s:<{w}} "

    print(SEP)
    print("|" + "|".join(f" {c:<{w}} " for c, w in zip(COLS, COL_W)) + "|")
    print(SEP)
    for r in results:
        name_short = r["original_name"][:20]
        vals = [
            r["id"], name_short, r["rating"], r["ratings_count"],
            r["body"], r["tannin"], r["sweetness"], r["acidity"], r["fizziness"],
        ]
        print("|" + "|".join(cell(v, w) for v, w in zip(vals, COL_W)) + "|")
    print(SEP)

    # 아로마 요약
    print("\n아로마 멘션 (상위 3개):")
    for r in results:
        if r["aroma_mentions"] and r["aroma_mentions"] != "FAILED":
            top3 = " | ".join(r["aroma_mentions"].split(" | ")[:3])
            print(f"  [{r['id']}] {r['original_name'][:20]}: {top3[:80]}")

    # 실패 목록
    failed = [r for r in results if r["rating"] == "FAILED" or r["body"] == "FAILED"]
    if failed:
        print(f"\n⚠ 실패 ({len(failed)}개):")
        for r in failed:
            print(f"  {r['id']} {r['original_name']}")
    else:
        print("\n✓ 전체 성공")


if __name__ == "__main__":
    main()
