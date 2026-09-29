"""외부뉴스: Google News RSS (키 불필요). 네이버 검색 API도 같은 형태로 붙일 수 있다."""
import html
import re
import urllib.parse
from email.utils import parsedate_to_datetime

from .http import get_bytes

NEG = ["사고", "붕괴", "영업정지", "행정처분", "적자", "손실", "소송", "과징금", "중대재해", "부실", "하향", "연체", "압수수색", "리콜"]
POS = ["수주", "흑자", "상향", "성장", "개선", "최대", "협약", "맞손", "출시"]


def classify(title):
    n = [w for w in NEG if w in title]
    if n:
        return "부정", n
    p = [w for w in POS if w in title]
    return ("긍정", p) if p else ("중립", [])


def search(query, limit=8):
    url = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko".format(urllib.parse.quote('"' + query + '"'))
    xml = get_bytes(url).decode("utf-8", "ignore")
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        t = html.unescape(re.search(r"<title>(.*?)</title>", block, re.S).group(1))
        link = re.search(r"<link>(.*?)</link>", block, re.S)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        src = re.search(r"<source[^>]*>(.*?)</source>", block, re.S)
        title = re.sub(r"\s+-\s+[^-]+$", "", t)
        tone, kw = classify(title)
        items.append({"title": title, "publisher": html.unescape(src.group(1)) if src else "",
                      "date": parsedate_to_datetime(pub.group(1)).strftime("%Y-%m-%d") if pub else "",
                      "url": link.group(1).strip() if link else "", "tone": tone, "keywords": kw})
    if not items:
        raise RuntimeError("뉴스 결과 없음")
    return items
