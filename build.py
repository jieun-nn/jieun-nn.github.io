#!/usr/bin/env python3
"""징니 블로그 허브 생성기.

네이버 블로그 RSS를 읽어 글마다 '새로 쓴 요약 + 원문 링크' 페이지를 만든다.
- 원문 본문/사진은 복사하지 않는다 (요약은 data/summaries.json 에서만 가져옴)
- 각 페이지는 canonical 로 네이버 원문(m.blog)을 가리킨다
- 출력: index.html, p/<글번호>/index.html, og/<글번호>.png, sitemap.xml, robots.txt
"""
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
SITE = CONFIG["site_url"].rstrip("/")
BLOG_ID = CONFIG["blog_id"]
RSS_URL = f"https://rss.blog.naver.com/{BLOG_ID}.xml"

# 카테고리 색 (제목 카드·배지). 없는 카테고리는 기본색.
PALETTE = {
    "예술/전시/공연": "#2F6B4F",
    "맛집여행": "#B5562E",
    "맛집모아": "#B5562E",
    "카페여행": "#8A6A3B",
    "일상/뷰티": "#A2486B",
    "공부": "#3B5A8A",
    "콜로소 디자인 강의": "#2D3E73",
    "미술/디자인 작업": "#2D3E73",
    "활동/프로젝트 기록": "#4A4F8C",
    "PM 부트캠프 2기": "#4A4F8C",
    "대원미디어 서포터즈": "#6B5A2E",
}
DEFAULT_COLOR = "#3F4A54"


def esc(s):
    return html.escape(s or "", quote=True)


# ---------------------------------------------------------------- data
def fetch_rss():
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0 (jingni-hub)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def field(item, tag):
    m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.S)
    return html.unescape(m.group(1).strip()) if m else ""


def parse_rss(xml):
    posts = {}
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        m = re.search(r"/(\d{9,})", field(item, "link"))
        if not m:
            continue
        pid = m.group(1)
        dt = parsedate_to_datetime(field(item, "pubDate"))
        tags = [t.strip() for t in field(item, "tag").split(",") if t.strip()]
        # 본문(description)은 일부러 저장하지 않는다 → 원문 복제 방지
        posts[pid] = {
            "id": pid,
            "title": field(item, "title"),
            "category": field(item, "category") or "기타",
            "tags": tags,
            "date": dt.isoformat(),
        }
    return posts


def load_posts(offline=False):
    """RSS 는 최근 50개만 주므로, 지난 글은 data/posts.json 에 누적 보관한다."""
    archive_path = DATA / "posts.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {}
    if not offline:
        fresh = parse_rss(fetch_rss())
        archive.update(fresh)
        archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return sorted(archive.values(), key=lambda p: p["date"], reverse=True)


# ---------------------------------------------------------------- og card
FONT_CANDIDATES = [
    os.environ.get("HUB_FONT", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]


def find_font():
    for f in FONT_CANDIDATES:
        if f and Path(f).exists():
            return f
    return None


def wrap(draw, text, font, width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > width and cur:
            # 가능하면 공백에서 끊기
            cut = cur.rfind(" ")
            if cut > len(cur) * 0.6:
                lines.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def make_card(post, out):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    font_path = find_font()
    if not font_path:
        return False
    color = PALETTE.get(post["category"], DEFAULT_COLOR)
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(img)
    f_small = ImageFont.truetype(font_path, 34)
    f_title = ImageFont.truetype(font_path, 62)
    pad = 84
    d.text((pad, pad), post["category"], font=f_small, fill="#FFFFFFCC")
    lines = wrap(d, post["title"], f_title, W - pad * 2)
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1][:-1] + "…"
    y = pad + 90
    for ln in lines:
        d.text((pad, y), ln, font=f_title, fill="#FFFFFF")
        y += 84
    d.line([(pad, H - pad - 56), (W - pad, H - pad - 56)], fill="#FFFFFF55", width=2)
    d.text((pad, H - pad - 34), "징니 블로그 · jingni_blog", font=f_small, fill="#FFFFFF")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return True


# ---------------------------------------------------------------- html
CSS = """
:root{--bg:#FAF8F4;--fg:#1F2328;--muted:#6B6F76;--line:#E6E1D8;--card:#FFFFFF}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--fg:#E8E6E1;--muted:#9A9DA3;--line:#2A2C30;--card:#1C1D20}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;word-break:keep-all}
a{color:inherit}
.wrap{max-width:760px;margin:0 auto;padding:40px 16px 80px}
header.site{margin-bottom:36px}
header.site a{text-decoration:none}
header.site h1{font-size:28px;margin:0 0 6px}
header.site p{margin:0;color:var(--muted)}
.badge{display:inline-block;font-size:13px;padding:2px 10px;border-radius:99px;color:#fff;margin-right:8px}
.date{font-size:13px;color:var(--muted)}
ul.list{list-style:none;padding:0;margin:0}
ul.list li{padding:18px 0;border-top:1px solid var(--line)}
ul.list a.t{display:block;font-weight:600;font-size:17px;text-decoration:none;margin-top:6px}
ul.list a.t:hover{text-decoration:underline}
.cats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px}
.cats a{font-size:14px;text-decoration:none;padding:4px 12px;border:1px solid var(--line);border-radius:99px;background:var(--card)}
h2.cat{font-size:19px;margin:40px 0 4px}
article h1{font-size:26px;line-height:1.4;margin:12px 0 20px}
article .card{width:100%;height:auto;border-radius:12px;display:block;margin:0 0 24px}
article .summary{font-size:17px;margin:0 0 28px}
.cta{display:inline-block;padding:14px 22px;border-radius:10px;background:var(--fg);color:var(--bg);text-decoration:none;font-weight:600}
.tags{margin:28px 0 0;color:var(--muted);font-size:14px}
.source{margin-top:32px;padding-top:16px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
footer{margin-top:56px;font-size:13px;color:var(--muted)}
"""


def head(title, desc, canonical, og_image=None, extra=""):
    verify = CONFIG.get("google_site_verification")
    meta_verify = f'<meta name="google-site-verification" content="{esc(verify)}">' if verify else ""
    naver_verify = CONFIG.get("naver_site_verification")
    meta_naver = f'<meta name="naver-site-verification" content="{esc(naver_verify)}">' if naver_verify else ""
    og = f'<meta property="og:image" content="{esc(og_image)}">' if og_image else ""
    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
{meta_verify}{meta_naver}
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
{og}
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" href="{RSS_URL}" title="징니 블로그 RSS">
<style>{CSS}</style>
{extra}
</head><body><div class="wrap">"""


def site_header():
    return f"""<header class="site"><a href="{SITE}/"><h1>징니 블로그 아카이브</h1></a>
<p>전시·맛집·카페·디자인 이야기를 쓰는 <a href="https://m.blog.naver.com/{BLOG_ID}">네이버 블로그 '징니 블로그'</a>의 글 목록과 요약입니다.</p></header>"""


FOOTER = f"""<footer>각 글의 전문과 사진은 <a href="https://m.blog.naver.com/{BLOG_ID}">징니 블로그(네이버)</a> 원문에서 볼 수 있습니다.</footer></div></body></html>"""


def fmt_date(iso):
    d = datetime.fromisoformat(iso)
    return f"{d.year}. {d.month}. {d.day}."


def origin_url(pid):
    return f"https://m.blog.naver.com/{BLOG_ID}/{pid}"


def summary_for(post, summaries):
    s = summaries.get(post["id"])
    if s:
        return s
    # 요약이 아직 없는 새 글: 원문 문장을 쓰지 않고 제목/카테고리로만 안내
    return f"징니 블로그 '{post['category']}' 카테고리에 올라온 글입니다. 사진과 자세한 내용은 원문에서 확인할 수 있습니다."


def render_post(post, summaries, has_card):
    pid = post["id"]
    color = PALETTE.get(post["category"], DEFAULT_COLOR)
    summary = summary_for(post, summaries)
    origin = origin_url(pid)
    card_url = f"{SITE}/og/{pid}.png" if has_card else None
    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"],
        "description": summary,
        "datePublished": post["date"],
        "inLanguage": "ko",
        "author": {"@type": "Person", "name": "징니", "url": f"https://m.blog.naver.com/{BLOG_ID}"},
        "isBasedOn": origin,
        "mainEntityOfPage": origin,
        "url": f"{SITE}/p/{pid}/",
        "keywords": ", ".join(post["tags"][:15]),
    }
    if card_url:
        ld["image"] = card_url
    extra = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    tags = " ".join(f"#{esc(t)}" for t in post["tags"][:12])
    card = f'<img class="card" src="{SITE}/og/{pid}.png" width="1200" height="630" alt="{esc(post["title"])}">' if has_card else ""
    body = f"""{site_header()}
<article>
<span class="badge" style="background:{color}">{esc(post['category'])}</span><span class="date">{fmt_date(post['date'])}</span>
<h1>{esc(post['title'])}</h1>
{card}
<p class="summary">{esc(summary)}</p>
<a class="cta" href="{origin}" rel="noopener">원문 전체 보기 (네이버 블로그) →</a>
<p class="tags">{tags}</p>
<p class="source">이 페이지는 징니 블로그 원문을 요약한 안내 페이지입니다. 원문: <a href="{origin}">{origin}</a></p>
</article>
{FOOTER}"""
    return head(f"{post['title']} | 징니 블로그", summary, origin, card_url, extra) + body


def render_index(posts, summaries):
    cats = {}
    for p in posts:
        cats.setdefault(p["category"], []).append(p)
    cat_order = sorted(cats, key=lambda c: cats[c][0]["date"], reverse=True)
    nav = "".join(f'<a href="#c{i}">{esc(c)} ({len(cats[c])})</a>' for i, c in enumerate(cat_order))
    sections = []
    for i, c in enumerate(cat_order):
        color = PALETTE.get(c, DEFAULT_COLOR)
        items = "".join(
            f'<li><span class="date">{fmt_date(p["date"])}</span>'
            f'<a class="t" href="{SITE}/p/{p["id"]}/">{esc(p["title"])}</a></li>'
            for p in cats[c]
        )
        sections.append(f'<h2 class="cat" id="c{i}"><span class="badge" style="background:{color}">&nbsp;</span>{esc(c)}</h2><ul class="list">{items}</ul>')
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "징니 블로그 아카이브",
        "url": f"{SITE}/",
        "about": f"https://m.blog.naver.com/{BLOG_ID}",
    }
    extra = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    desc = "네이버 블로그 '징니 블로그'의 전시 관람기, 맛집·카페 후기, 디자인 강의 후기 글 목록과 요약."
    body = f"""{site_header()}<nav class="cats">{nav}</nav>{''.join(sections)}{FOOTER}"""
    return head("징니 블로그 아카이브 | 전시·맛집·카페·디자인 후기", desc, f"{SITE}/", None, extra) + body


def render_sitemap(posts):
    now = datetime.now(timezone.utc).date().isoformat()
    urls = [f"<url><loc>{SITE}/</loc><lastmod>{now}</lastmod></url>"]
    for p in posts:
        urls.append(f"<url><loc>{SITE}/p/{p['id']}/</loc><lastmod>{p['date'][:10]}</lastmod></url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


def main():
    offline = "--offline" in sys.argv
    out = ROOT / CONFIG.get("out_dir", ".")
    posts = load_posts(offline)
    summaries = json.loads((DATA / "summaries.json").read_text(encoding="utf-8"))
    missing = [p["id"] for p in posts if p["id"] not in summaries]

    cards = 0
    for p in posts:
        card_path = out / "og" / f"{p['id']}.png"
        has = card_path.exists() or make_card(p, card_path)
        cards += has
        page = out / "p" / p["id"] / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(render_post(p, summaries, has), encoding="utf-8")

    (out / "index.html").write_text(render_index(posts, summaries), encoding="utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(posts), encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    print(f"posts={len(posts)} cards={cards} missing_summaries={len(missing)}")
    if missing:
        print("요약이 없는 글:", ", ".join(missing))


if __name__ == "__main__":
    main()
