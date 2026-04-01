"""
Apify Vivino Wine Data Scraper - 테스트 (와인 1개)
대상: Prototype Zinfandel (Vivino ID: 6172116)
확인 사항:
  1. APIFY_API_TOKEN 환경변수 인식
  2. Actor 호출 성공 (status: SUCCEEDED)
  3. 응답에 taste_profile 객체 존재
  4. body, tannins, sweetness, acidity, flavor_notes 필드 존재
  5. 수치가 1~5 스케일
  6. 배치 처리 가능한 응답 구조
"""

import json
import os
import sys

# ── 1. 토큰 확인 ─────────────────────────────────────────────────────────────
token = os.environ.get("APIFY_API_TOKEN", "")
if not token:
    print("❌ [1] APIFY_API_TOKEN 환경변수 없음")
    sys.exit(1)
print(f"✅ [1] APIFY_API_TOKEN 인식됨 (길이: {len(token)})")

from apify_client import ApifyClient

client = ApifyClient(token)

run_input = {
    "wineUrls": ["https://www.vivino.com/en/prototype-zinfandel/w/6172116"],
    "includeTasteProfile": True,
    "includeReviews": False,
    "maxResultsPerSearch": 1,
    "countryCode": "KR",
    "currencyCode": "KRW",
}

# ── 2. Actor 실행 ─────────────────────────────────────────────────────────────
print("\nApify Actor 실행 중... (mrbridge/vivino-wine-data-scraper)")
try:
    run = client.actor("mrbridge/vivino-wine-data-scraper").call(run_input=run_input)
except Exception as e:
    print(f"❌ [2] Actor 호출 실패: {e}")
    sys.exit(1)

status = run.get("status", "UNKNOWN")
if status == "SUCCEEDED":
    print(f"✅ [2] Actor 실행 성공 (status: {status})")
else:
    print(f"❌ [2] Actor 실행 실패 (status: {status})")
    print(f"     run info: {json.dumps(run, indent=2, ensure_ascii=False)}")
    sys.exit(1)

# ── 3~6. 응답 데이터 확인 ────────────────────────────────────────────────────
items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
print(f"\n응답 아이템 수: {len(items)}")

if not items:
    print("❌ [3] 응답 데이터 없음")
    sys.exit(1)

item = items[0]
print("\n── 원본 응답 JSON ──────────────────────────────────────────────")
print(json.dumps(item, indent=2, ensure_ascii=False))
print("────────────────────────────────────────────────────────────\n")

# 결과 파일 저장
with open("apify_test_result.json", "w", encoding="utf-8") as f:
    json.dump(items, f, indent=2, ensure_ascii=False)
print("결과 저장: apify_test_result.json\n")

# ── 검증 ─────────────────────────────────────────────────────────────────────
results = {}

# [3] taste_profile 존재 여부
taste = item.get("taste_profile") or item.get("tasteProfile") or item.get("tasteStructure") or {}
# 중첩 구조 탐색
if not taste:
    for key in item:
        val = item[key]
        if isinstance(val, dict) and any(k in val for k in ("body", "tannin", "tannins", "acidity", "sweetness")):
            taste = val
            break

results["[3] taste_profile 존재"] = bool(taste)
if taste:
    print(f"✅ [3] taste_profile 발견: {list(taste.keys())}")
else:
    print(f"❌ [3] taste_profile 없음 (최상위 키: {list(item.keys())})")

# [4] 필수 필드 존재
required = ["body", "tannin", "sweetness", "acidity"]
aliases = {
    "body":      ["body", "intensity"],
    "tannin":    ["tannin", "tannins"],
    "sweetness": ["sweetness", "sweet"],
    "acidity":   ["acidity", "acid"],
}
found_fields = {}
if taste:
    for field, alts in aliases.items():
        for alt in alts:
            if alt in taste:
                found_fields[field] = (alt, taste[alt])
                break

missing = [f for f in required if f not in found_fields]
results["[4] 필수 필드 존재"] = len(missing) == 0
if not missing:
    print(f"✅ [4] 필수 필드 모두 존재: {found_fields}")
else:
    print(f"❌ [4] 누락 필드: {missing}  /  발견: {found_fields}")

# flavor_notes
flavor = taste.get("flavor_notes") or taste.get("flavorNotes") or item.get("flavor_notes") or item.get("flavors") or []
results["[4] flavor_notes 존재"] = bool(flavor)
print(f"{'✅' if flavor else '⚠ '} [4] flavor_notes: {str(flavor)[:120]}")

# [5] 수치 1~5 스케일
in_range = {}
for field, (alt, val) in found_fields.items():
    try:
        v = float(val)
        in_range[field] = 1.0 <= v <= 5.0
    except (TypeError, ValueError):
        in_range[field] = False

results["[5] 수치 1~5 스케일"] = all(in_range.values()) if in_range else False
if results["[5] 수치 1~5 스케일"]:
    vals = {f: round(float(found_fields[f][1]), 2) for f in found_fields}
    print(f"✅ [5] 수치 범위 정상: {vals}")
else:
    print(f"❌ [5] 범위 이상: {in_range}  /  raw: {found_fields}")

# [6] 배치 구조
has_wine_id  = "id" in item or "wine_id" in item or "wineId" in item
has_wine_name = "name" in item or "wine_name" in item or "wineName" in item
results["[6] 배치 구조"] = has_wine_id or has_wine_name
print(f"{'✅' if results['[6] 배치 구조'] else '❌'} [6] 배치 구조 (id/name 존재): "
      f"keys={[k for k in item.keys() if 'id' in k.lower() or 'name' in k.lower()]}")

# ── 최종 요약 ─────────────────────────────────────────────────────────────────
print("\n══ 테스트 결과 요약 ═══════════════════════════════════════════")
all_pass = True
for check, passed in results.items():
    icon = "✅" if passed else "❌"
    print(f"  {icon} {check}")
    if not passed:
        all_pass = False

if all_pass:
    print("\n🎉 테스트 통과. 18개 우선 실행 후 500개 이상 확장 준비 완료")
else:
    print("\n⚠️  일부 항목 실패. 위 내용 확인 후 재시도 필요")
    sys.exit(1)
