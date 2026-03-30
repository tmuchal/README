"""
Vivino Wine Slider Scraper
- Selenium 4 + Chrome headless
- 슬라이더 left: XX% → 1-5 점수 변환
- 리뷰 수, 아로마 멘션 추출
- 리다이렉트 URL 추적
- vivino_sliders.csv 저장
"""

import csv
import json
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ── 와인 목록 ────────────────────────────────────────────────────────────────
# (이름, URL, 종류)  종류: "red" | "white" | "sparkling"
WINES = [
    ("Varvaglione Papale Primitivo di Manduria",
     "https://www.vivino.com/en/varvaglione-papale-primitivo-di-manduria-primitivo-di-manduria/w/1506422",
     "red"),
    ("Chateau de Saint Cosme Cotes du Rhone Les Deux Albion",
     "https://www.vivino.com/en/chateau-de-saint-cosme-cotes-du-rhone-les-deux-albion/w/1173569",
     "red"),
    ("Gaston Burtin Extra Brut Champagne",
     "https://www.vivino.com/en/gaston-burtin-extra-brut-champagne/w/12489584",
     "sparkling"),
    ("La Sala Chianti Classico",
     "https://www.vivino.com/IT/en/it-la-sala-chianti-classico/w/2140869",
     "red"),
    ("Prototype Cabernet Sauvignon",
     "https://www.vivino.com/en/prototype-cabernet-sauvignon/w/5885528",
     "red"),
    ("Prototype Zinfandel",
     "https://www.vivino.com/en/prototype-zinfandel/w/6172116",
     "red"),
    ("Prototype Chardonnay",
     "https://www.vivino.com/en/prototype-chardonnay/w/6781547",
     "white"),
    ("Mahi Sauvignon Blanc",
     "https://www.vivino.com/en/mahi-sauvignon-blanc/w/1112088",
     "white"),
    ("Mahi Pinot Noir",
     "https://www.vivino.com/en/mahi-pinot-noir/w/1112105",
     "red"),
    ("Terramater Magis Limited Reserve Carmenere",
     "https://www.vivino.com/en/terramater-magis-limited-reserve-carmenere/w/9597776",
     "red"),
    ("Terramater Magis Limited Reserve Cabernet Sauvignon",
     "https://www.vivino.com/en/terramater-magis-limited-reserve-cabernet-sauvignon/w/7247216",
     "red"),
    ("Vinum Cellars Cabernet Sauvignon",
     "https://www.vivino.com/en/us-vinum-cellars-us-cabernet-sauvignon/w/90074",
     "red"),
    ("De Montfaucon Baron Louis Lirac Cotes du Rhone",
     "https://www.vivino.com/en/de-montfaucon-baron-louis-lirac-cotes-du-rhone/w/1117640",
     "red"),
    ("19 Crimes Cabernet Sauvignon",
     "https://www.vivino.com/en/nineteen-crimes-cabernet-sauvignon-victoria-red-wine-v/w/3736213",
     "red"),
    ("Bread and Butter Chardonnay",
     "https://www.vivino.com/en/bread-and-butter-chardonnay/w/1755251",
     "white"),
    ("Apothic Red",
     "https://www.vivino.com/en/apothic-red-winemaker-s-blend/w/1130327",
     "red"),
    ("Delaunois d Fils La Royale Champagne Premier Cru",
     "https://www.vivino.com/en/delaunois-d-fils-la-royale-champagne-premier-cru/w/3952842",
     "sparkling"),
]

# 종류별 슬라이더 레이블 집합
SLIDER_LABELS = {
    "red":      {"body", "tannin", "sweetness", "acidity"},
    "white":    {"body", "sweetness", "acidity"},
    "sparkling":{"body", "acidity", "fizziness"},
}

# HTML 레이블 텍스트 → 슬라이더 키 매핑
LABEL_MAP = {
    "light":  "body",      "bold":    "body",
    "smooth": "tannin",    "tannic":  "tannin",
    "dry":    "sweetness", "sweet":   "sweetness",
    "soft":   "acidity",   "acidic":  "acidity",
    "gentle": "fizziness", "fizzy":   "fizziness",
}

PAGE_WAIT = 5   # 페이지 로딩 후 대기(초)
PAGE_GAP  = 2   # 페이지 간 간격(초)
OUTPUT    = "vivino_sliders.csv"


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def left_to_score(pct: float) -> float:
    return round(1 + (pct / 100.0) * 4, 2)


def build_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-US,en")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Selenium 4.6+ Service 자동 관리 (webdriver-manager fallback)
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


def parse_sliders_html(src: str) -> dict:
    """
    HTML에서 tasteCharacteristic 행을 찾아 left: XX% 값 추출.
    <tr class="...tasteCharacteristic...">
      <td><div class="...property...">Light</div></td>
      <td ...><... style="width: X%; left: Y%;"></td>
      <td><div class="...property...">Bold</div></td>
    </tr>
    """
    sliders = {}
    pattern = re.compile(
        r'class="[^"]*tasteCharacteristic[^"]*".*?'
        r'class="[^"]*property[^"]*">([^<]+)</div>.*?'
        r'left:\s*([\d.]+)%.*?'
        r'class="[^"]*property[^"]*">([^<]+)</div>',
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


def parse_sliders_json(src: str) -> dict:
    """
    페이지 내 JSON baseline_structure 에서 값 추출 (fallback).
    {"intensity":X,"tannin":X,"sweetness":X,"acidity":X,"fizziness":X}
    """
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


def scrape_page(driver: webdriver.Chrome, name: str, url: str, wine_type: str) -> dict:
    expected_keys = SLIDER_LABELS[wine_type]

    driver.get(url)
    time.sleep(PAGE_WAIT)

    # 스크롤로 지연 로딩 트리거
    for pos in [400, 800, 1200, 800]:
        driver.execute_script(f"window.scrollTo(0, {pos})")
        time.sleep(0.4)
    time.sleep(0.5)

    final_url = driver.current_url
    src = driver.page_source

    # Cloudflare 차단 감지 → 재시도
    if "Just a moment" in src or "cf-browser-verification" in src:
        print("  ⚠ Cloudflare 감지 — 10초 후 재시도")
        time.sleep(10)
        driver.get(url)
        time.sleep(PAGE_WAIT + 2)
        final_url = driver.current_url
        src = driver.page_source

    # 와인 이름
    try:
        wine_name = driver.find_element(
            By.CSS_SELECTOR,
            "h1[class*='wineName'], h1[class*='wine'], h1",
        ).text.strip().replace("\n", " ")
    except Exception:
        wine_name = name

    # 슬라이더: HTML 우선, JSON fallback
    sliders = parse_sliders_html(src)
    used_fallback = False
    if not sliders:
        sliders = parse_sliders_json(src)
        used_fallback = bool(sliders)

    # 슬라이더가 아예 없으면 데이터 없음
    has_data = bool(sliders)

    # 종류에 맞지 않는 키 제거 (e.g. white 와인의 tannin)
    for k in list(sliders.keys()):
        if k not in expected_keys:
            del sliders[k]

    # 리뷰 수: 전체 평점 수 ("X ratings") 우선, fallback: "based on X user reviews"
    review_count = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        # 총 평점 수 (와인 점수 옆에 표시, 예: "24,962 ratings")
        m = re.search(r'([\d,]+)\s+ratings?', body_text, re.I)
        if m:
            review_count = m.group(1).replace(",", "")
        else:
            # fallback: 슬라이더 투표자 수 ("based on X user reviews")
            m = re.search(r'based on ([\d,]+)\s+user reviews?', body_text, re.I)
            if m:
                review_count = m.group(1).replace(",", "")
    except Exception:
        pass

    # 아로마 멘션
    aroma_list = []
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        matches = re.findall(
            r'(\d[\d,]*)\s+mentions?\s+of\s+([^\n,\.]{3,40})',
            body_text, re.I,
        )
        aroma_list = [f"{c} mentions of {d.strip()}" for c, d in matches[:5]]
    except Exception:
        pass

    note = ""
    if not has_data:
        note = "데이터 없음"
    elif used_fallback:
        note = "JSON fallback"

    return {
        "와인이름":   wine_name,
        "Body":      sliders.get("body"),
        "Tannin":    sliders.get("tannin"),
        "Sweetness": sliders.get("sweetness"),
        "Acidity":   sliders.get("acidity"),
        "Fizziness": sliders.get("fizziness"),
        "리뷰수":    review_count,
        "아로마멘션": " | ".join(aroma_list),
        "원래URL":   url,
        "최종URL":   final_url,
        "_note":     note,
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    driver = build_driver()
    results = []

    for i, (name, url, wine_type) in enumerate(WINES, 1):
        print(f"\n[{i:02d}/17] {name}  ({wine_type})")
        try:
            data = scrape_page(driver, name, url, wine_type)
            results.append(data)

            def v(x): return f"{x:.2f}" if x is not None else "  -  "
            redirect = " ← 리다이렉트" if data["원래URL"] != data["최종URL"] else ""
            note     = f"  [{data['_note']}]" if data["_note"] else ""
            print(
                f"  Body={v(data['Body'])}  Tannin={v(data['Tannin'])}  "
                f"Sweet={v(data['Sweetness'])}  Acid={v(data['Acidity'])}  "
                f"Fizz={v(data['Fizziness'])}  Reviews={data['리뷰수']}"
                f"{redirect}{note}"
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "와인이름": name, "Body": None, "Tannin": None,
                "Sweetness": None, "Acidity": None, "Fizziness": None,
                "리뷰수": "", "아로마멘션": f"ERROR: {e}",
                "원래URL": url, "최종URL": "", "_note": "에러 스킵",
            })

        if i < len(WINES):
            time.sleep(PAGE_GAP)

    driver.quit()

    # ── CSV 저장 ──────────────────────────────────────────────────────────────
    fieldnames = [
        "와인이름", "Body", "Tannin", "Sweetness", "Acidity", "Fizziness",
        "리뷰수", "아로마멘션", "원래URL", "최종URL",
    ]
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✓ {OUTPUT} 저장 완료 ({len(results)}행)\n")

    # ── 터미널 테이블 출력 ────────────────────────────────────────────────────
    COL_W = [42, 5, 6, 6, 6, 6, 7]
    COLS  = ["와인이름", "Body", "Tannin", "Sweet", "Acid", "Fizz", "리뷰수"]
    SEP   = "+" + "+".join("-" * (w + 2) for w in COL_W) + "+"

    def cell(val, w):
        s = f"{val:.2f}" if isinstance(val, float) else (str(val) if val else "-")
        return f" {s:<{w}} "

    def hdr_cell(txt, w):
        return f" {txt:<{w}} "

    print(SEP)
    print("|" + "|".join(hdr_cell(c, w) for c, w in zip(COLS, COL_W)) + "|")
    print(SEP)
    for r in results:
        vals = [
            r["와인이름"].replace("\n", " ")[:42],
            r["Body"], r["Tannin"], r["Sweetness"],
            r["Acidity"], r["Fizziness"], r["리뷰수"],
        ]
        print("|" + "|".join(cell(v, w) for v, w in zip(vals, COL_W)) + "|")
    print(SEP)

    print("\n아로마 멘션:")
    for r in results:
        a = r["아로마멘션"]
        if a and not a.startswith("ERROR"):
            print(f"  {r['와인이름'].replace(chr(10),' ')[:35]}: {a[:90]}")

    print("\n리다이렉트 발생:")
    redirected = [r for r in results if r["원래URL"] != r["최종URL"]]
    if redirected:
        for r in redirected:
            print(f"  {r['와인이름'].replace(chr(10),' ')[:35]}")
            print(f"    원래: {r['원래URL']}")
            print(f"    최종: {r['최종URL']}")
    else:
        print("  없음")

    print("\n데이터 없음:")
    no_data = [r for r in results if r.get("_note") == "데이터 없음"]
    if no_data:
        for r in no_data:
            print(f"  {r['와인이름'].replace(chr(10),' ')}")
    else:
        print("  없음")


if __name__ == "__main__":
    main()
