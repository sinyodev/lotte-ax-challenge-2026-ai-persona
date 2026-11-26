"""CU 홈페이지의 음료 상품 전체 목록을 받아 표로 만든다. 행사가 없는 상품도 들어 있다.

실행:
    python3 scripts/collect_cu_drinks.py          # 받아서 표로 만들기
    python3 scripts/collect_cu_drinks.py parse    # 이미 받은 원본에서 표만 다시 만들기

출처:  https://cu.bgfretail.com/product/product.do?category=product&depth2=4&depth3=6  (음료, 분류 코드 60)
       robots.txt는 없다(404, 2026-11-17 확인).
원본:  data/raw/cu/<받은 날>/drink_p<쪽>.html   (받은 그대로. 저장소에 올리지 않는다)
출력:  data/clean/cu_drinks_<받은 날>.csv

왜 CU인가: 세븐일레븐 홈페이지는 행사 상품만 보여준다. 행사가 없는 상품의 편의점 정가를 얻으려고 CU 목록을 쓴다.
주의: CU의 정가와 행사다. 세븐일레븐과 다를 수 있으므로 판매조건의 판매처를 "CU"로 적는다.
"""

import csv
import datetime
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://cu.bgfretail.com/product/productAjax.do"
REFERER = "https://cu.bgfretail.com/product/product.do?category=product&depth2=4&depth3=6"
CATEGORY = "60"
MAX_PAGES = 200
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ITEM = re.compile(
    r"class=\"name\" onclick=\"view\((?P<id>\d+)\);\"><p>(?P<name>.*?)</p>.*?class=\"price\"><strong>(?P<price>[^<]*)</strong>"
    r".*?<div class=\"badge\">(?P<badge>.*?)</div>\s*<div class=\"tag\">(?P<tag>.*?)</div>",
    re.S,
)
SPAN = re.compile(r"<span[^>]*>(.*?)</span>", re.S)


def clean(fragment: str) -> str:
    fragment = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
    return "|".join(html.unescape(re.sub(r"<[^>]+>", "", s)).strip() for s in SPAN.findall(fragment) if s.strip())


def fetch(day: str) -> Path:
    raw_dir = ROOT / "data" / "raw" / "cu" / day
    raw_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        body = urllib.parse.urlencode({
            "pageIndex": page, "searchMainCategory": CATEGORY, "searchSubCategory": "", "listType": "0",
            "searchCondition": "setA", "searchUseYn": "", "gdIdx": "0", "codeParent": CATEGORY,
            "user_id": "", "search2": "", "searchKeyword": "",
        }).encode()
        request = urllib.request.Request(URL, data=body, headers={"User-Agent": USER_AGENT, "Referer": REFERER})
        text = urllib.request.urlopen(request, timeout=60).read().decode("utf-8", errors="replace")
        ids = [m.group("id") for m in ITEM.finditer(text)]
        new = [i for i in ids if i not in seen]
        if not new:
            break
        (raw_dir / f"drink_p{page:03d}.html").write_text(text, encoding="utf-8")
        seen.update(new)
        time.sleep(1)
    print(f"음료 {len(seen)}건, {page - 1}쪽")
    return raw_dir


def parse(raw_dir: Path, day: str) -> None:
    rows = {}
    for path in sorted(raw_dir.glob("drink_p*.html")):
        for m in ITEM.finditer(path.read_text(encoding="utf-8")):
            name = html.unescape(m.group("name")).strip()
            price = re.sub(r"[^0-9]", "", m.group("price"))
            size = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|l|L|g|kg|입|개|매)\b", name)
            rows[m.group("id")] = [
                name, name.split(")")[0] if ")" in name[:12] else "", int(price) if price else "",
                size.group(0) if size else "", clean(m.group("badge")), clean(m.group("tag")), m.group("id"), day,
            ]
    out = ROOT / "data" / "clean" / f"cu_drinks_{day}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["상품명", "이름 앞 표기(제조사·브랜드)", "정가(원)", "용량 표기", "행사", "꼬리표", "CU 상품 번호", "확인한 날"])
        writer.writerows(rows.values())
    print(f"{len(rows):,}건 -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "parse":
        latest = sorted((ROOT / "data" / "raw" / "cu").iterdir())[-1]
        parse(latest, latest.name)
    else:
        today = datetime.date.today().isoformat()
        parse(fetch(today), today)
