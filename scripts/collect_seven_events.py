"""세븐일레븐 홈페이지의 행사 상품 목록(1+1, 2+1, 증정, 할인)을 받아 표로 만든다.

실행:
    python3 scripts/collect_seven_events.py            # 받아서 표로 만들기
    python3 scripts/collect_seven_events.py parse      # 이미 받은 원본에서 표만 다시 만들기

출처:  https://www.7-eleven.co.kr/product/presentList.asp  (robots.txt는 /product/ 를 막지 않는다. 2026-11-17 확인)
원본:  data/raw/seven-eleven/<받은 날>/tab<행사>_p<쪽>.html   (받은 그대로. 저장소에 올리지 않는다)
출력:  data/clean/seven_eleven_events_<받은 날>.csv

주의:
- 이 목록은 "지금 행사 중인 상품"이다. 행사가 없는 상품은 여기에 없다.
- 가격은 홈페이지에 적힌 정가다. 행사 적용 단가는 행사 종류로 따로 계산한다.
- 행사는 달마다 바뀐다. 파일 이름의 날짜가 확인한 날이다.
- 요청 사이에 1초씩 쉰다.
"""

import csv
import datetime
import html
import http.cookiejar
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.7-eleven.co.kr/product/"
TABS = {"1": "1+1", "2": "2+1", "3": "증정행사", "4": "할인행사"}
PAGE_SIZE = 10
MAX_PAGES = 400
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ITEM = re.compile(
    r"<ul class=\"tag_list_01\">(?P<tags>.*?)</ul>.*?<img src=\"(?P<img>[^\"]*)\".*?"
    r"class='name'[^>]*>(?P<name>.*?)</div>.*?class='price'[^>]*>\s*<span>(?P<price>[^<]*)</span>",
    re.S,
)
TAG = re.compile(r"<li[^>]*>(.*?)</li>", re.S)


def fetch(day: str) -> Path:
    raw_dir = ROOT / "data" / "raw" / "seven-eleven" / day
    raw_dir.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = [("User-Agent", USER_AGENT), ("Referer", BASE + "presentList.asp"), ("X-Requested-With", "XMLHttpRequest")]
    opener.open(BASE + "presentList.asp", timeout=30).read()
    for tab, label in TABS.items():
        seen = set()
        for page in range(1, MAX_PAGES + 1):
            body = urllib.parse.urlencode(
                {"intPageSize": PAGE_SIZE, "intCurrPage": page, "cateCd1": "", "cateCd2": "", "cateCd3": "", "pTab": tab}
            ).encode()
            text = opener.open(BASE + "listMoreAjax.asp", data=body, timeout=60).read().decode("utf-8", errors="replace")
            names = [m.group("name") for m in ITEM.finditer(text)]
            new = [n for n in names if n not in seen]
            if not new:
                break
            (raw_dir / f"tab{tab}_p{page:03d}.html").write_text(text, encoding="utf-8")
            seen.update(new)
            time.sleep(1)
        print(f"{label}: {len(seen)}건, {page - 1}쪽")
    return raw_dir


def parse(raw_dir: Path, day: str) -> None:
    rows = {}
    for path in sorted(raw_dir.glob("tab*_p*.html")):
        tab = path.name[3]
        for m in ITEM.finditer(path.read_text(encoding="utf-8")):
            name = html.unescape(m.group("name")).strip()
            tags = [html.unescape(t).strip() for t in TAG.findall(m.group("tags"))]
            price = re.sub(r"[^0-9]", "", m.group("price"))
            code = re.search(r"/product/(\d+)/(\d+)\.", m.group("img"))
            maker = name.split(")")[0] if ")" in name[:12] else ""
            size = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|l|L|g|kg|입|개|매)\b", name)
            rows[(tab, name)] = [
                TABS[tab], name, maker, int(price) if price else "", size.group(0) if size else "",
                "|".join(tags), (code.group(1) + code.group(2)) if code else "", m.group("img"), day,
            ]
    out = ROOT / "data" / "clean" / f"seven_eleven_events_{day}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["행사", "상품명", "이름 앞 표기(제조사·브랜드)", "정가(원)", "용량 표기", "꼬리표", "바코드(이미지 경로에서)", "이미지 경로", "확인한 날"])
        writer.writerows(rows.values())
    print(f"{len(rows):,}건 -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "parse":
        latest = sorted((ROOT / "data" / "raw" / "seven-eleven").iterdir())[-1]
        parse(latest, latest.name)
    else:
        today = datetime.date.today().isoformat()
        parse(fetch(today), today)
