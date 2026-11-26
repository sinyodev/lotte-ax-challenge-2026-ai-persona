"""공식 원문과 RSS에 붙은 보도 요약·사진만 읽는다."""

import re
from xml.etree import ElementTree as ET

from lxml import etree, html

from . import sites
from .stories import reference

STORIES_PER_NEWSROOM = 3
MAX_SUMMARY_WORDS = 20
MAX_SUMMARY_CHARS = 150
CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"
MEDIA = "{http://search.yahoo.com/mrss/}"

# 발행 날짜나 시제를 바꾸지 않고 기사 서술의 끝맺음만 뉴스레터에 맞춘다.
NEWS_ENDINGS = {
    "선보인다": "선보여요", "나선다": "나서요", "팔린다": "팔려요", "밝혔다": "밝혔어요",
    "했다": "했어요", "됐다": "됐어요", "한다": "해요", "된다": "돼요", "있다": "있어요",
}


def newsletter_copy(row: dict) -> dict:
    if not row.get("id", "").startswith("news-") or not row.get("summary"):
        return row
    title = row["title"].rstrip("! ")
    # 인용한 홍보 문구 다음에 독립된 기사 제목이 있으면 그 제목을 쓴다.
    title = re.sub(r'^“[^”]+”\s+(?=[가-힣A-Z0-9]+(?: [가-힣A-Z0-9]+)?,)', "", title)
    if "! " in title and "출시" in title.rsplit("! ", 1)[1]:
        title = title.rsplit("! ", 1)[1]
    summary = row["summary"]
    for ending, spoken in NEWS_ENDINGS.items():
        if summary.rstrip(".").endswith(ending):
            summary = summary.rstrip(".")[:-len(ending)] + spoken + "."
            break
    return {**row, "title": title, "summary": summary}

ARTICLE_SELECTORS = {
    "bgf": ("//div[@class='contents_detail']/div[@class='title']/h1", "//div[@class='detail_inner']"),
    "lotte": ("//div[@class='titArea']/p[@class='tit']", "//div[@class='conTxt']"),
    "shinsegae": ("//meta[@property='og:title']/@content", "//div[@class='post-contents']"),
}


def _text(node) -> str:
    return " ".join(node.text_content().split())


def _same_headline(candidate: str, title: str) -> bool:
    normalized = "".join(c.casefold() for c in candidate if c.isalnum())
    headline = "".join(c.casefold() for c in title if c.isalnum())
    return bool(headline) and (normalized == headline or normalized.startswith(headline))


def _summary(values, title: str) -> str | None:
    for value in values:
        value = " ".join(value.split())
        if not value or value.startswith(("-", "▶", "※", "[사진", "사진=", "사진 :", "©", "The post ")):
            continue
        # 인용부호와 서식을 걷었을 때 제목과 같은 문장을 걸러낸다.
        for sentence in re.split(r"(?<=[.!?])\s+", value):
            if len(sentence) < 12 or _same_headline(sentence, title):
                continue
            words = sentence.split()
            if len(words) <= MAX_SUMMARY_WORDS and len(sentence) <= MAX_SUMMARY_CHARS:
                return sentence
            excerpt = " ".join(words[:MAX_SUMMARY_WORDS])
            if len(excerpt) > MAX_SUMMARY_CHARS:
                excerpt = excerpt[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0]
            return excerpt.rstrip(",. …") + "…"
    return None


def _html_fragment(value: str):
    if value.strip():
        try:
            fragment = html.fragment_fromstring(value, create_parent=True)
        except etree.ParserError:
            return None
        for node in fragment.xpath(".//script|.//style"):
            node.drop_tree()
        return fragment
    return None


def _photos(root):
    for node in root.xpath(".//img"):
        dimensions = (node.get("width", ""), node.get("height", ""))
        if any(value.isdecimal() and int(value) < 120 for value in dimensions):
            continue
        for name in ("src", "data-src", "data-original"):
            value = node.get(name)
            if value:
                yield value, node.get("alt")


def _add_media(row: dict, summary: str | None, photos) -> dict:
    if summary:
        row["summary"] = summary
        row["sources"] = [reference(row["publisher"], row["date"], summary, row["url"])]
    if not row["image"]:
        for url, alt in photos:
            image = sites.press_photo(row["url"], url)
            if image:
                row.update(image=image, alt=" ".join(alt.split()) if alt else None, photoCredit=row["publisher"])
                break
    return row


def from_article(row: dict, payload: bytes, site: str) -> dict:
    doc = html.fromstring(payload.decode("utf-8-sig"))
    title_xpath, body_xpath = ARTICLE_SELECTORS[site]
    body = doc.xpath(body_xpath)
    if not body:
        return row
    headline = doc.xpath(title_xpath)
    if headline and site != "shinsegae":
        title = _text(headline[0])
        if title:
            row.update(title=title, keyword=title, sources=[reference(row["publisher"], row["date"], title, row["url"])])
    sections = body[0]
    description = doc.xpath("//meta[@property='og:description']/@content") if site == "shinsegae" else []
    paragraphs = [_text(node) for node in sections.xpath(".//p")]
    summary = row["summary"] or _summary([*paragraphs, *description], row["title"])
    photos = list(_photos(sections))
    if site == "shinsegae":
        og_alt = next(iter(doc.xpath("//meta[@property='og:image:alt']/@content")), None)
        photos.extend((url, og_alt) for url in doc.xpath("//meta[@property='og:image']/@content"))
    return _add_media(row, summary, photos)


def from_rss(row: dict, item: ET.Element) -> dict:
    description = _html_fragment(item.findtext("description") or "")
    content = _html_fragment(item.findtext(CONTENT_ENCODED) or "")
    paragraphs = [_text(node) for node in content.xpath(".//p")] if content is not None else []
    if description is not None:
        paragraphs.append(_text(description))
    photos = list(_photos(content)) if content is not None else []
    for node in [*item.findall(MEDIA + "content"), *item.findall(MEDIA + "thumbnail")]:
        if node.get("url"):
            photos.append((node.get("url"), None))
    return _add_media(row, _summary(paragraphs, row["title"]), photos)
