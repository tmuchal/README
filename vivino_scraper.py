"""
Vivino Wine Slider Scraper
- Selenium 4, Chrome headless
- 슬라이더 left% → 1-5 스케일 변환
- 리뷰 수 및 아로마 멘션 추출
- 결과 vivino_sliders.csv 저장
"""

import csv
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ──────────────────────────────────────────────────────────
# 대상 URL 목록
# ──────────────────────────────────────────────────────────
URLS = [
    "https://www.vivino.com/en/varvaglione-papale-primitivo-di-manduria-primitivo-di-manduria/w/1506422",
    "https://www.vivino.com/en/chateau-de-saint-cosme-les-deux-albion-principaute-d-orange/w/35424",
    "https://www.vivino.com/en/gaston-burtin-extra-brut-champagne/w/12489584",
    "https://www.vivino.com/IT/en/it-la-sala-chianti-classico/w/2140869",
    "https://www.vivino.com/en/prototype-cabernet-sauvignon/w/5733636",
    "https://www.vivino.com/en/prototype-zinfandel/w/6172116",
    "https://www.vivino.com/en/prototype-chardonnay/w/7553744",
    "https://www.vivino.com/en/mahi-sauvignon-blanc/w/1112088",
    "https://www.vivino.com/en/mahi-pinot-noir/w/1112105",
    "https://www.vivino.com/en/terramater-magis-limited-reserve-carmenere/w/9597776",
    "https://www.vivino.com/en/terramater-magis-limited-reserve-cabernet-sauvignon/w/7247216",
    "https://www.vivino.com/en/us-vinum-cellars-us-cabernet-sauvignon/w/90074",
    "https://www.vivino.com/en/de-montfaucon-baron-louis-lirac-cotes-du-rhone/w/1117640",
    "https://www.vivino.com/en/nineteen-crimes-cabernet-sauvignon-victoria-red-wine-v/w/3736213",
    "https://www.vivino.com/en/bread-and-butter-chardonnay/w/1755251",
    "https://www.vivino.com/en/apothic-red-winemaker-s-blend/w/1130327",
    "https://www.vivino.com/en/delaunois-d-fils-la-royale-champagne-premier-cru/w/3952842",
]

OUTPUT_CSV = "vivino_sliders.csv"
PAGE_WAIT  = 3   # 페이지 로딩 후 대기 (초)
PAGE_GAP   = 2   # 페이지 간 간격 (초)


# ──────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────
def left_to_score(left_pct: float) -> float:
    """left% → 1-5 스케일 (소수점 둘째 자리)"""
    return round(1 + (left_pct / 100) * 4, 2)


def extract_left_pct(style: str) -> float | None:
    """'left: 62.5%' 형태 style 속성에서 숫자 추출"""
    m = re.search(r"left\s*:\s*([\d.]+)%", style)
    return float(m.group(1)) if m else None


def build_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    # ChromeDriver 경로를 명시할 경우: Service("/path/to/chromedriver")
    return webdriver.Chrome(options=opts)


# ──────────────────────────────────────────────────────────
# 페이지별 데이터 수집
# ──────────────────────────────────────────────────────────
def scrape_page(driver: webdriver.Chrome, url: str) -> dict:
    """단일 Vivino 와인 페이지에서 데이터를 수집해 dict로 반환"""
    driver.get(url)
    time.sleep(PAGE_WAIT)

    # ── 와인 이름 ──────────────────────────────────────────
    wine_name = ""
    try:
        wine_name = driver.find_element(
            By.CSS_SELECTOR, "h1.wine-name, h1[class*='wineName'], h1"
        ).text.strip()
    except Exception:
        # URL 마지막 경로에서 이름 추출 (fallback)
        wine_name = url.rstrip("/").split("/")[-3].replace("-", " ").title()

    # ── 슬라이더 indicator 추출 ────────────────────────────
    # Vivino: div.indicator (style="left: XX%") 가 슬라이더 내부에 위치
    # 슬라이더 행은 div[class*='tasteStructure'] 또는 유사 컨테이너 내부
    #
    # 슬라이더 레이블 순서: Body, Tannin, Sweetness, Acidity [, Fizziness]
    # data-testid 또는 aria-label 등을 활용해 매핑
    slider_map = {
        "body":      None,
        "tannin":    None,
        "sweetness": None,
        "acidity":   None,
        "fizziness": None,
    }

    # 방법 1: data-testid 속성 활용
    # <div data-testid="tasteStructure--body"> ... <div class="indicator" style="left: XX%">
    testid_keys = {
        "body":      ["body", "Body"],
        "tannin":    ["tannin", "Tannin"],
        "sweetness": ["sweetness", "Sweetness", "sweet"],
        "acidity":   ["acidity", "Acidity"],
        "fizziness": ["fizziness", "Fizziness", "fizzy"],
    }

    for key, testids in testid_keys.items():
        for tid in testids:
            try:
                container = driver.find_element(
                    By.CSS_SELECTOR,
                    f'[data-testid*="{tid}"], [data-testid*="{tid.lower()}"]',
                )
                indicator = container.find_element(
                    By.CSS_SELECTOR, '[class*="indicator"]'
                )
                style = indicator.get_attribute("style") or ""
                left = extract_left_pct(style)
                if left is not None:
                    slider_map[key] = left_to_score(left)
                    break
            except Exception:
                continue

    # 방법 2: 레이블 텍스트 → 인접 indicator 매핑 (fallback)
    if all(v is None for v in slider_map.values()):
        label_re = {
            "body":      re.compile(r"body|bold|light", re.I),
            "tannin":    re.compile(r"tannin|tannic|smooth", re.I),
            "sweetness": re.compile(r"sweet|dry", re.I),
            "acidity":   re.compile(r"acid|soft", re.I),
            "fizziness": re.compile(r"fizz|gentle|sparkl", re.I),
        }
        try:
            # 모든 indicator style 수집
            indicators = driver.find_elements(
                By.CSS_SELECTOR, '[class*="indicator"][style*="left"]'
            )
            for ind in indicators:
                style = ind.get_attribute("style") or ""
                left = extract_left_pct(style)
                if left is None:
                    continue
                # 부모 컨테이너 텍스트에서 슬라이더 종류 추론
                try:
                    row_text = ind.find_element(
                        By.XPATH, "./ancestor::*[3]"
                    ).text.lower()
                except Exception:
                    row_text = ""
                for key, pattern in label_re.items():
                    if slider_map[key] is None and pattern.search(row_text):
                        slider_map[key] = left_to_score(left)
                        break
        except Exception:
            pass

    # ── 리뷰 수 추출 ───────────────────────────────────────
    review_count = ""
    review_patterns = [
        r"based on ([\d,]+)\s+user reviews?",
        r"([\d,]+)\s+ratings?",
        r"([\d,]+)\s+reviews?",
    ]
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        for pat in review_patterns:
            m = re.search(pat, page_text, re.I)
            if m:
                review_count = m.group(1).replace(",", "")
                break
    except Exception:
        pass

    # ── 아로마 멘션 추출 ──────────────────────────────────
    # "207 mentions of black fruit" 형태
    aroma_mentions = []
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        matches = re.findall(r"(\d[\d,]*)\s+mentions?\s+of\s+([^\n,]+)", page_text, re.I)
        aroma_mentions = [f"{cnt} mentions of {desc.strip()}" for cnt, desc in matches[:5]]
    except Exception:
        pass

    return {
        "와인이름":    wine_name,
        "Body":       slider_map["body"],
        "Tannin":     slider_map["tannin"],
        "Sweetness":  slider_map["sweetness"],
        "Acidity":    slider_map["acidity"],
        "Fizziness":  slider_map["fizziness"],
        "리뷰수":     review_count,
        "아로마멘션":  " | ".join(aroma_mentions) if aroma_mentions else "",
    }


# ──────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────
def main():
    driver = build_driver()
    results = []

    try:
        for i, url in enumerate(URLS, 1):
            print(f"[{i:02d}/{len(URLS)}] {url.split('/')[-1]}", end=" ... ")
            try:
                data = scrape_page(driver, url)
                results.append(data)
                print(f"OK  Body={data['Body']}  Tannin={data['Tannin']}  "
                      f"Sweetness={data['Sweetness']}  Acidity={data['Acidity']}  "
                      f"Fizziness={data['Fizziness']}  리뷰={data['리뷰수']}")
            except Exception as e:
                print(f"ERROR: {e}")
                results.append({
                    "와인이름": url.split("/w/")[0].rstrip("/").split("/")[-1],
                    "Body": None, "Tannin": None, "Sweetness": None,
                    "Acidity": None, "Fizziness": None,
                    "리뷰수": "", "아로마멘션": f"ERROR: {e}",
                })

            if i < len(URLS):
                time.sleep(PAGE_GAP)

    finally:
        driver.quit()

    # ── CSV 저장 ───────────────────────────────────────────
    fieldnames = ["와인이름", "Body", "Tannin", "Sweetness", "Acidity", "Fizziness", "리뷰수", "아로마멘션"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✓ 저장 완료: {OUTPUT_CSV}  ({len(results)}행)")

    # ── 테이블 출력 ────────────────────────────────────────
    col_widths = [35, 5, 7, 10, 8, 10, 8, 50]
    headers    = ["와인이름", "Body", "Tannin", "Sweetness", "Acidity", "Fizziness", "리뷰수", "아로마멘션"]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    def fmt_row(row_vals):
        cells = []
        for val, w in zip(row_vals, col_widths):
            s = str(val) if val is not None else "-"
            cells.append(f" {s:<{w}} ")
        return "|" + "|".join(cells) + "|"

    print(sep)
    print(fmt_row(headers))
    print(sep)
    for r in results:
        print(fmt_row([
            r["와인이름"][:35],
            r["Body"], r["Tannin"], r["Sweetness"],
            r["Acidity"], r["Fizziness"],
            r["리뷰수"], str(r["아로마멘션"])[:50],
        ]))
    print(sep)


if __name__ == "__main__":
    main()
