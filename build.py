# -*- coding: utf-8 -*-
"""
KLCCL 정적 사이트 생성 스크립트

  python build.py            # docs/ 폴더에 사이트 전체를 만든다(GitHub Pages가 이 폴더를 게시)
  python build.py --one      # 미리보기용: 모든 쪽을 하나로 합친 docs_preview.html 도 만든다

새 번역을 올리는 법
  1. content/<저자>/<저작>/ko/NNN.txt 에 한국어 원고를 둔다(머리 #번호/#제목/#구절/#CO/#본문, --- , 본문 {CO n})
  2. 원문이 있으면 content/<저자>/<저작>/orig/NNN.txt 에 둔다(⟦n⟧ 쪽 표시)
  3. python build.py 를 실행하고, 바뀐 docs/ 를 GitHub에 올린다
  서가, 저자, 총서, 성경, 원전 지도, 진행 현황, 찾기 색인, 홈 숫자는 파일을 보고 자동으로 다시 계산된다.

새 저작을 더하는 법
  content/<저자>/<저작>/work.json 을 만든다(content/calvin/job-sermons/work.json 참고).
"""
import html
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

뿌리 = Path(__file__).resolve().parent
출력 = 뿌리 / "docs"
KST = timezone(timedelta(hours=9))
기준일 = datetime.now(KST).strftime("%Y-%m-%d")

SITE = json.loads((뿌리 / "site.json").read_text(encoding="utf-8"))
LIB = json.loads((뿌리 / "catalog" / "library.json").read_text(encoding="utf-8"))
CO = json.loads((뿌리 / "catalog" / "co.json").read_text(encoding="utf-8"))
BIBLE = json.loads((뿌리 / "catalog" / "bible.json").read_text(encoding="utf-8"))
# 개역한글판 본문: catalog/krv/<약칭>.json (구절 "장:절" -> 본문)
KRV = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (뿌리 / "catalog" / "krv").glob("*.json")}
# 다른 번역본 목록 (catalog/versions.json). VPL 파일은 책 순서가 66권 차례와 같으므로 순서로 맞춘다
VERSIONS = json.loads((뿌리 / "catalog" / "versions.json").read_text(encoding="utf-8"))["versions"]


def VPL읽기(경로: Path) -> dict:
    """'GEN 1:1 본문' 형식을 {책코드: {장: [[절, 본문], …]}} 로. ¶ 표시는 지운다"""
    순서, 책들 = [], {}
    for 줄 in 경로.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\S+) (\d+):(\d+) ?(.*)$", 줄)
        if not m:
            continue
        b, c, v, t = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).replace("¶", "").strip()
        if b not in 책들:
            순서.append(b)
            책들[b] = {}
        책들[b].setdefault(c, []).append([v, t])
    코드들 = [x["code"] for x in BIBLE["books"]]
    return {코드들[i]: 책들[b] for i, b in enumerate(순서[:66])}


def 구절목록(ref: str, 책: dict) -> list:
    """'15:35; 16:1–9' 또는 '16:22–17:5' 같은 표기를 ['15:35', '16:1', …] 로 푼다. 자료에 없는 절이 있으면 None"""
    결과 = []
    for 조각 in [x.strip() for x in ref.replace("—", "–").replace("-", "–").split(";") if x.strip()]:
        m = re.match(r"^(\d+):(\d+)(?:–(?:(\d+):)?(\d+))?$", 조각)
        if not m:
            return None
        c1, v1 = int(m.group(1)), int(m.group(2))
        c2 = int(m.group(3)) if m.group(3) else c1
        v2 = int(m.group(4)) if m.group(4) else v1
        for c in range(c1, c2 + 1):
            시작 = v1 if c == c1 else 1
            if c == c2:
                끝 = v2
            else:   # 장 끝까지: 자료에 있는 마지막 절
                끝 = max(int(k.split(":")[1]) for k in 책 if int(k.split(":")[0]) == c)
            for v in range(시작, 끝 + 1):
                결과.append(f"{c}:{v}")
    return 결과 if all(k in 책 for k in 결과) else None

상태이름 = {3: "원문 대역 연결", 2: "웹 게시(한국어)", 1: "번역 원고 완료", "0x": "원고 확보 필요", 0: "예정"}


def e(s) -> str:
    """HTML 이스케이프"""
    return html.escape(str(s), quote=True)


def 둥근따옴표(s: str) -> str:
    return re.sub(r'"(?=\S)', "“", s).replace('"', "”")


def 범위풀기(글: str) -> set:
    """'1-61,72-118' 같은 표기를 번호 집합으로"""
    결과 = set()
    for 조각 in filter(None, [x.strip() for x in (글 or "").split(",")]):
        if "-" in 조각:
            a, b = 조각.split("-")
            결과 |= set(range(int(a), int(b) + 1))
        else:
            결과.add(int(조각))
    return 결과


# ------------------------------------------------------------------
# 1. 원고 읽기
# ------------------------------------------------------------------
def 원고읽기(경로: Path) -> dict:
    글 = 경로.read_text(encoding="utf-8")
    머리, 몸 = 글.split("\n---\n", 1)
    정보 = {}
    for 줄 in 머리.splitlines():
        if 줄.startswith("#") and ":" in 줄:
            k, v = 줄[1:].split(":", 1)
            정보[k.strip()] = v.strip()
    각주 = []

    def 각주바꿈(m):
        각주.append(m.group(1))
        return f"⁣FN{len(각주)}⁣"

    몸 = re.sub(r"\[\^((?:[^\[\]]|\[[^\]]*\])*)\]", 각주바꿈, 몸)
    쪽별, 현재 = {}, None
    for 문단 in [p.strip() for p in re.split(r"\n\s*\n", 몸) if p.strip()]:
        안내 = 문단.startswith("!")
        상자 = 문단.startswith(">")
        문단 = 문단.lstrip("!>").strip()
        부분 = re.split(r"\{CO (\d+)\}", 문단)
        if 부분[0].strip():
            쪽별.setdefault(현재 or "intro", []).append({"t": 부분[0].strip(), "note": 안내, "box": 상자, "cont": True})
        for i in range(1, len(부분), 2):
            현재 = int(부분[i])
            if 부분[i + 1].strip():
                쪽별.setdefault(현재, []).append({"t": 부분[i + 1].strip(), "note": False, "box": False, "cont": False})
    if "intro" in 쪽별:
        첫 = min(k for k in 쪽별 if k != "intro")
        쪽별[첫] = 쪽별.pop("intro") + 쪽별[첫]
    _c = 정보.get("CO", "0:0")
    vol = int(_c.split(":")[0]) if ":" in _c else 0
    return {"no": int(정보["번호"]), "title": 정보.get("제목", ""), "ref": 정보.get("구절", ""),
            "co": 정보.get("CO", ""), "vol": vol, "box": 정보.get("본문", ""), "pages": 쪽별, "notes": 각주}


def 원문읽기(경로: Path) -> dict:
    if not 경로.exists():
        return {}
    글 = 경로.read_text(encoding="utf-8")
    return {int(m.group(1)): [p.strip() for p in m.group(2).strip().split("\n") if p.strip()]
            for m in re.finditer(r"⟦(\d+)⟧\n(.*?)(?=⟦\d+⟧|\Z)", 글, re.S)}


def 저작읽기() -> list:
    저작들 = []
    for wj in sorted((뿌리 / "content").glob("*/*/work.json")):
        w = json.loads(wj.read_text(encoding="utf-8"))
        폴더 = wj.parent
        w["units"] = {}
        for 파일 in sorted((폴더 / "ko").glob("*.txt")) if (폴더 / "ko").exists() else []:
            u = 원고읽기(파일)
            u["orig"] = 원문읽기(폴더 / "orig" / 파일.name)
            # 원문 첫 쪽 첫 문단이 성경 본문(절 번호로 시작)이면 본문 상자로 옮긴다
            u["origbox"] = ""
            if u["orig"]:
                첫 = min(u["orig"])
                if u["orig"][첫] and re.match(r"^\d+\.\s", u["orig"][첫][0]):
                    u["origbox"] = u["orig"][첫].pop(0)
            w["units"][u["no"]] = u
        오프 = 범위풀기(w.get("translated_offline", ""))
        빠짐 = 범위풀기(w.get("missing", ""))
        for v in w["volumes"]:
            라벨 = v.get("labels")
            v["items"] = []
            for i, n in enumerate(range(v["from"], v["to"] + 1)):
                if n in w["units"]:
                    s = 3 if w["units"][n]["orig"] else 2
                elif n in 빠짐:
                    s = "0x"
                elif n in 오프:
                    s = 1
                else:
                    s = 0
                v["items"].append({"no": n, "s": s, "short": 라벨[i] if 라벨 else str(n),
                                   "title": w["units"][n]["title"] if n in w["units"] else ""})
        w["author_dir"] = 폴더.parent.name
        저작들.append(w)
    return 저작들


WORKS = sorted(저작읽기(), key=lambda w: (w["series"], w["branch"], min(v["no"] for v in w["volumes"])))


def 집계(items) -> dict:
    c = {3: 0, 2: 0, 1: 0, "0x": 0, 0: 0}
    for x in items:
        c[x["s"]] += 1
    return c


def 모든항목():
    return [x for w in WORKS for v in w["volumes"] for x in v["items"]]




# ------------------------------------------------------------------
# 2. 공통 틀
#    위쪽 탭은 저자나 원전 하나에 묶이지 않게 도서관 전체 기준으로 나눈다.
#    서가(모든 저작) · 저자 · 총서 · 성경 · 원전 · 찾기 · 소개
# ------------------------------------------------------------------
메뉴 = [("", "홈", "home"), ("bible/", "성경", "bible"), ("expositions/", "주석·설교", "expositions"), ("books/", "도서", "books"),
       ("psalter/", "시편찬송", "psalter"), ("authors/", "저자", "authors"),
       ("search/", "찾기", "search"), ("about/", "소개", "about")]
도서하위 = [("books/", "전체 도서", "books"), ("series/", "총서", "series")]
소개하위 = [("about/", "도서관 소개", "about"), ("about/principles/", "원칙", "principles"), ("about/progress/", "진행 현황", "progress"),
        ("about/news/", "소식", "news"), ("about/contribute/", "참여와 오류 제보", "contribute")]
저자이름 = {a["id"]: a for a in LIB["authors"]}
갈래이름 = {g["id"]: g["name"] for g in LIB["genres"]}
시대이름 = {x["id"]: x for x in LIB["eras"]}
책코드 = {b["abbr"]: b for b in BIBLE["books"]}


def 틀(경로: str, 제목: str, 본문: str, 현재: str = "", 빵: list = None, 서가: str = "", 설명: str = "", 하위: str = "", 하위목록: list = None) -> str:
    """경로는 docs/ 기준 상대 경로(예: 'sources/co/index.html'). 링크는 모두 상대 경로로 만든다"""
    깊이 = 경로.count("/")
    R = "../" * 깊이
    nav = "".join(f'<a href="{(R + h) or "./"}"{" class=on" if k == 현재 else ""}>{t}</a>' for h, t, k in 메뉴)
    빵글 = ""
    if 빵:
        빵글 = '<div class="crumb">' + " › ".join(
            (f'<a href="{R}{h}">{e(t)}</a>' if h is not None else f"<b>{e(t)}</b>") for h, t in 빵) + "</div>"
    if 하위:
        본문 = ('<nav class="subnav">' + "".join(
            f'<a href="{R}{h}"{" class=on" if k == 하위 else ""}>{t}</a>' for h, t, k in (하위목록 or 소개하위)) + "</nav>") + 본문
    본문 = 본문.replace("{R}", R)
    서가 = 서가.replace("{R}", R)
    배치 = (f'<div class="layout"><aside id="shelf">{서가}</aside><main>{빵글}{본문}{바닥(R)}</main></div>' if 서가
          else f'<div class="layout single"><main>{빵글}<div class="page">{본문}</div>{바닥(R)}</main></div>')
    쪽제목 = f"{제목} · {SITE['name']} {SITE['full']}" if 제목 else f"{SITE['name']} {SITE['full']}"
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(쪽제목)}</title><meta name="description" content="{e(설명 or SITE['tagline'])}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&family=EB+Garamond:ital,wght@0,400;0,600;1,400&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<link rel="stylesheet" href="{R}assets/kccl.css"></head>
<body data-root="{R}">
<header class="top">
  {'<button class="btn menu-btn" id="menuBtn" aria-label="서가 열기">목차</button>' if 서가 else ''}
  <a class="brand" href="{R}">{e(SITE['name'])}<small>{e(SITE['full'])} · AI 초벌 번역판</small></a>
  <nav class="gnav">{nav}</nav>
  <div class="seg theme" role="group" aria-label="색 모드"><button class="btn" data-theme-set="light">라이트</button><button class="btn" data-theme-set="dark">다크</button><button class="btn" data-theme-set="reading">리딩</button></div>
</header>
{배치}
<div class="pop" id="pop"></div><div class="toast" id="toast"></div>
<script src="{R}assets/kccl.js"></script>
</body></html>
"""


def 바닥(R: str) -> str:
    return (f'<footer class="foot">{e(SITE["name"])} {e(SITE["full"])} · 번역문 CC0 1.0 · AI 초벌 번역판 · 신학 감수 전 · '
            f'<a href="{R}about/principles/">원칙</a> · <a href="{R}about/contribute/">오류 제보</a> · 기준일 {기준일}</footer>')


def 막대(items) -> str:
    c, n = 집계(items), max(len(items), 1)
    return (f'<div class="bar"><i class="s3" style="width:{c[3]/n*100:.2f}%"></i>'
            f'<i class="s2" style="width:{c[2]/n*100:.2f}%"></i><i class="s1" style="width:{c[1]/n*100:.2f}%"></i></div>')


def 요약(items) -> str:
    c = 집계(items)
    if not items:
        return "준비 중"
    return f"{c[1]+c[2]+c[3]}/{len(items)} 번역 · 웹 {c[2]+c[3]} · 대역 {c[3]}"


def 저작주소(w) -> str:
    return f"{w['author_dir']}/{w['id']}/"


def 권표(v) -> str:
    """권 표시: CO 권수에 28을 더한 CR(Corpus Reformatorum) 권수. CO 값이 없으면 저작 안의 권 번호"""
    co = v.get("co")
    return f"CR {int(co) + 28}" if isinstance(co, int) or str(co).isdigit() else f'{v["no"]}권'


def PDF링크(w, v, 꼴="btn") -> str:
    """권별 AI 초벌 번역판 PDF 내려받기 링크. work.json 의 volumes[].pdf 에 파일 이름을 적는다"""
    f = v.get("pdf")
    if not isinstance(f, str):
        return ""
    원본 = 뿌리 / "content" / w["author"] / w["id"] / "pdf" / f
    크기 = f"{원본.stat().st_size / 1048576:.1f}MB" if 원본.exists() else ""
    쪽 = f'{v["pdf_pages"]}쪽, ' if v.get("pdf_pages") else ""
    주소 = f'{{R}}{저작주소(w)}pdf/{f}'
    if 꼴 == "tag":
        return f' <a class="tag" href="{주소}" download>PDF</a>'
    if 꼴 == "mini":
        return f'<a class="dl mini" href="{주소}" download>{권표(v)} PDF 내려받기</a>'
    return (f'<p><a class="btn dl" href="{주소}" download>{권표(v)} PDF 내려받기</a> '
            f'<span class="mini">AI 초벌 번역판 · 신학 감수 전 · {쪽}{크기} · CC0</span></p>')


def 원전권(w, v) -> str:
    """권·저작의 원전 표시. CO 저작은 'CO n', 그 밖은 work.json 의 source_short(예: '1932년판')"""
    if w.get("source", "co") == "co":
        return f'CO {v["co"]}' if isinstance(v, dict) else "CO " + ", ".join(str(x) for x in w["co"])
    return w.get("source_short", "원서")


def 쪽앞뒤(w, u) -> tuple:
    """인용 표기 앞뒤: CO 저작은 ('CO 34:', ''), 그 밖은 ('원서 ', '쪽')"""
    if w.get("source", "co") == "co":
        return f'CO {u["vol"]}:', ""
    return w.get("page_prefix", "원서 "), "쪽"


def 쪽범위(w, u) -> str:
    """머리에 보일 원전 범위: 'CO 8:543–566' 또는 '원서 77–154쪽'"""
    if w.get("source", "co") == "co":
        return f'CO {u["co"]}'
    return f'{w.get("page_prefix", "원서 ")}{u["co"]}쪽'


def 고지(w) -> str:
    return ("AI로 옮긴 초벌 번역입니다. 신학 감수를 거치지 않았으니, 인용할 때는 원문("
            + ("CO 권:쪽" if w.get("source", "co") == "co" else "원서 쪽") + ")을 확인해 주십시오.")


def 단위주소(w, n) -> str:
    return f"{w['author_dir']}/{w['id']}/{n:03d}.html"


def 저작항목(w):
    return [x for v in w["volumes"] for x in v["items"]]


def 단위장들(w, u) -> list:
    """설교가 다루는 성경 장 목록 (책약칭, 장)"""
    책 = KRV.get(w.get("krv_book", ""), {}).get("verses", {})
    절 = 구절목록(u["ref"], 책) if 책 else None
    return sorted({(w["krv_book"], int(k.split(":")[0])) for k in 절}) if 절 else []


# ------------------------------------------------------------------
# 3. 쪽 만들기
# ------------------------------------------------------------------
쪽들 = {}   # 경로 -> HTML


def 홈():
    it = 모든항목()
    c = 집계(it)
    공개 = [(w, n) for w in WORKS for n in sorted(w["units"])]
    대역 = [(w, n) for w, n in 공개 if w["units"][n]["orig"]]
    시작 = 대역[0] if 대역 else (공개[0] if 공개 else None)
    시작단추 = (f'<a class="btn on" href="{{R}}{단위주소(*시작)}">대역 읽기 시작: 칼빈 「{e(시작[0]["title"])}」 제{시작[1]}편</a> '
            if 시작 else "")
    둘러보기 = [("bible/", "성경", "개역한글판 66권을 책처럼 펼쳐 읽습니다. 영어 번역본과 나란히 볼 수 있습니다."),
            ("expositions/", "주석·설교", "번역된 주석과 설교를 성경 책별로 찾아 읽습니다."),
            ("books/", "도서", "교리서, 신조, 서신, 경건 서적과 총서를 갈래·시대·원어로 골라 봅니다."),
            ("psalter/", "시편찬송", "한국어 제네바 시편가 150편의 악보와 가사, 개역한글판 시편 150편입니다."),
            ("authors/", "저자", "교부부터 종교개혁자, 청교도까지 저자별로 봅니다.")]
    카드 = "".join(f'<a class="card" href="{{R}}{h}"><h3>{t}</h3><p>{d}</p></a>' for h, t, d in 둘러보기)
    소식 = "".join(f"<tr><td>{e(d)}</td><td>{e(t)}</td></tr>" for d, t in LIB["news"][:4])
    co진행 = sum(1 for v in CO["volumes"] if CO진행(v["vol"]) > 0)
    본문 = f"""<div class="hero"><div class="en">{e(SITE['en'])}</div>
<h1>{e(SITE['name'])} {e(SITE['full'])}</h1><p class="lead">{e(SITE['tagline'])}</p>
<p>{시작단추}<a class="btn" href="{{R}}about/principles/">이 도서관의 원칙</a></p>
<div class="stats">
<div class="stat"><b>{len([a for a in LIB['authors'] if a['ready']])}</b><span>도서관에 오른 저자</span></div>
<div class="stat"><b>{c[1]+c[2]+c[3]}</b><span>번역을 마친 편</span></div>
<div class="stat"><b>{c[2]+c[3]}</b><span>웹에서 읽을 수 있는 편</span></div>
<div class="stat"><b>{co진행}/59</b><span>작업을 시작한 칼빈 전집 권</span></div></div></div>
<h2>둘러보기</h2><div class="cards">{카드}</div>
<h2>지금의 목표: 칼빈 전집 59권</h2>
<p>첫 목표는 19세기에 간행된 칼빈 전집(CO, 1863–1900) 59권 전체를 원문에서 한국어로 옮기는 것입니다. 번역에는 오랜 시간이 걸리므로, 마치는 대로 한 편씩 더합니다. 그다음에는 다른 종교개혁자와 교부, 청교도의 공유 저작물로 서가를 넓힙니다.</p>
<p><a class="btn" href="{{R}}about/progress/">진행 현황</a></p>
<h2>이 도서관이 지키는 세 가지</h2><div class="cards">
<div class="card"><h3>원문과 나란히</h3><p>모든 번역은 원문과 원전 쪽수(예: CO 34:1)로 맞대어 놓아, 누구나 원문을 확인할 수 있습니다.</p></div>
<div class="card"><h3>조건 없는 공개</h3><p>원전은 공유 저작물만, 번역문은 CC0 1.0으로 공개합니다. 복제, 배포, 수정, 출판 모두 자유입니다.</p></div>
<div class="card"><h3>투명한 초벌 번역</h3><p>AI로 초벌 번역했고 신학 감수 전입니다. 오류 제보를 받아 고치고, 고친 이력을 남깁니다.</p></div></div>
<h2>소식</h2><table class="t"><tr><th style="width:120px">날짜</th><th>내용</th></tr>{소식}</table>
<p><a href="{{R}}about/news/">소식 전체 보기</a></p>"""
    쪽들["index.html"] = 틀("index.html", "", 본문, "home")


def 서가쪽():
    """모든 저작을 한곳에서: 갈래·시대·원어 거르기 (앞으로 저자가 늘어도 그대로 쓴다)"""
    칸 = ""
    for w in WORKS:
        a = 저자이름[w["author"]]
        it = 저작항목(w)
        c = 집계(it)
        상태 = "web" if c[2] + c[3] else ("done" if c[1] else "plan")
        칸 += (f'<a class="card wk" href="{{R}}{저작주소(w)}" data-genre="{w.get("genre", "")}" data-era="{a["era"]}" '
              f'data-lang="{e(w.get("lang", ""))}" data-state="{상태}">'
              f'<div class="g">{e(a["name"])} · {e(갈래이름.get(w.get("genre"), ""))} · {e(w.get("lang", ""))}</div>'
              f'<h3>「{e(w["title"])}」</h3><p>{e(w["summary"])}</p>{막대(it)}<span class="mini">{요약(it)}</span></a>')
    def 칩(종류, 목록):
        return (f'<div class="chips" data-filter="{종류}"><button class="btn on" data-v="">전체</button>'
                + "".join(f'<button class="btn" data-v="{e(v)}">{e(t)}</button>' for v, t in 목록) + "</div>")
    원어들 = sorted({w.get("lang", "") for w in WORKS if w.get("lang")})
    본문 = (f'<h1>도서</h1><p class="lead">이 도서관에 오른 모든 저작입니다. 설교집과 주석, 교리서, 신조, 서신, 경건 서적을 갈래와 시대, 원어로 골라 볼 수 있습니다.</p>'
          f'<div class="filters"><span>갈래</span>{칩("genre", [(g["id"], g["name"]) for g in LIB["genres"]])}'
          f'<span>시대</span>{칩("era", [(x["id"], x["name"]) for x in LIB["eras"]])}'
          f'<span>원어</span>{칩("lang", [(x, x) for x in 원어들])}'
          f'<span>상태</span>{칩("state", [("web", "웹에서 읽기"), ("done", "번역 완료"), ("plan", "예정")])}</div>'
          f'<p class="mini" id="count"></p><div class="cards" id="works">{칸}</div>'
          f'<p class="mini" id="empty" hidden>조건에 맞는 저작이 아직 없습니다. 서가는 번역이 끝나는 대로 늘어납니다.</p>')
    쪽들["books/index.html"] = 틀("books/index.html", "도서", 본문, "books", [("", SITE["name"]), (None, "도서")], 하위="books", 하위목록=도서하위)


def 저자쪽():
    본문 = '<h1>저자</h1><p class="lead">공유 저작물로 확인된 저자를 시대 순으로 싣습니다. 아직 번역이 없는 저자는 예정으로 표시합니다.</p>'
    for 시대 in LIB["eras"]:
        여기 = [a for a in LIB["authors"] if a["era"] == 시대["id"]]
        if not 여기:
            continue
        본문 += f'<h2>{e(시대["name"])} <span class="mini">{e(시대["range"])}</span></h2><div class="cards">'
        for a in 여기:
            저작수 = len([w for w in WORKS if w["author"] == a["id"]])
            머리 = f'<h3>{e(a["name"])} <span class="mini">{e(a["life"])}</span></h3><p>{e(a["desc"])}</p>'
            if a["ready"]:
                본문 += f'<a class="card" href="{{R}}{a["id"]}/">{머리}<span class="mini">저작 {저작수}종</span></a>'
            else:
                본문 += f'<div class="card soon">{머리}</div>'
        본문 += "</div>"
    쪽들["authors/index.html"] = 틀("authors/index.html", "저자", 본문, "authors", [("", SITE["name"]), (None, "저자")])
    # 저자별 쪽
    for a in [x for x in LIB["authors"] if x["ready"]]:
        경로 = f'{a["id"]}/index.html'
        저작 = [w for w in WORKS if w["author"] == a["id"]]
        원전 = [s for s in LIB["sources"] if s["author"] == a["id"]]
        b = f'<h1>{e(a["name"])} <span class="mini">{e(a["life"])}</span></h1><p class="lead">{e(a["desc"])}</p>'
        for g in LIB["genres"]:
            여기 = [w for w in 저작 if w.get("genre") == g["id"]]
            if not 여기:
                continue
            b += f'<h2>{e(g["name"])}</h2><table class="t"><tr><th>저작</th><th style="width:90px">원전</th><th style="width:230px">진행</th></tr>'
            for w in 여기:
                it = 저작항목(w)
                b += (f'<tr><td><a href="{{R}}{저작주소(w)}"><b>「{e(w["title"])}」</b></a><br><span class="mini">{e(w["summary"])}</span></td>'
                      f'<td class="mini">{e(원전권(w, None))}</td><td>{막대(it)}<span class="mini">{요약(it)}</span></td></tr>')
            b += "</table>"
        쪽들[경로] = 틀(경로, a["name"], b, "authors", [("", SITE["name"]), ("authors/", "저자"), (None, a["name"])])


def CO진행(vol: int) -> int:
    """해당 CO 권에서 번역이 끝난 단위 수"""
    n = 0
    for w in WORKS:
        for v in w["volumes"]:
            if v["co"] == vol:
                c = 집계(v["items"])
                n += c[1] + c[2] + c[3]
    return n


def 원전쪽():
    b = ('<h1>원전</h1><p class="lead">번역의 저본이 되는 원전 전집입니다. 모든 번역은 이 전집의 권과 쪽수로 원문과 맞대어 있어, 인용과 대조가 쉽습니다.</p>'
         '<div class="box">인용 표기 읽는 법: <b>CO 34:3</b>은 칼빈 전집 제34권 3쪽입니다.</div><div class="cards">')
    for s in LIB["sources"]:
        권 = f", {s['vols']}권" if s.get("vols") else ""
        해 = ", " + e(s["years"]) if s["years"] else ""
        머리 = f'<h3>{e(s["name"])}</h3><p>{e(s["full"])}{해}{권}</p>'
        if s["ready"]:
            시작 = sum(1 for v in CO["volumes"] if CO진행(v["vol"]) > 0) if s["id"] == "co" else 0
            b += f'<a class="card" href="{{R}}sources/{s["id"]}/">{머리}<span class="mini">작업을 시작한 권 {시작}/{s["vols"]}</span></a>'
        else:
            b += f'<div class="card soon">{머리}<span class="mini">예정</span></div>'
    b += "</div>"
    쪽들["sources/index.html"] = 틀("sources/index.html", "원전", b, "sources", [("", SITE["name"]), (None, "원전")])
    CO지도()


def CO지도():
    갈래 = {b["id"]: b["name"] for s in LIB["series"] for b in s["branches"]}
    갈래["reference"] = "참고 자료"
    칸 = ""
    앞설명 = None
    for v in CO["volumes"]:
        설명 = v["note"] if v["note"] != 앞설명 else ""
        앞설명 = v["note"]
        관련 = [(w, vv) for w in WORKS for vv in w["volumes"] if vv["co"] == v["vol"]]
        진행 = ""
        if 관련:
            모두 = [x for _, vv in 관련 for x in vv["items"]]
            진행 = 막대(모두) + f'<span class="mini">{요약(모두)}</span>'
            진행 += "".join(f'<br><a href="{{R}}{저작주소(w)}">{e(vv["title"])}</a>' for w, vv in 관련)
        cls = "cv" + (" on" if 관련 else "") + (" ref" if v["branch"] == "reference" else "")
        칸 += (f'<div class="{cls}"><div class="g">{e(v["group"])} · {e(갈래.get(v["branch"], ""))}</div>'
              f'<div class="n">CO {v["vol"]}</div><div>{e(v["title"])}</div>'
              f'<div class="mini">{e(v["lang"])}{" · " + e(설명) if 설명 else ""}</div>{진행}</div>')
    본문 = f"""<h1>칼빈 전집(CO) 59권 지도</h1>
<p class="lead">CO는 <i>Ioannis Calvini Opera quae supersunt omnia</i>(현존하는 칼빈 저작 전집, 1863–1900)입니다. 칼빈 연구에서 표준으로 인용하는 판본이며 저작권이 없습니다. 이 도서관은 59권 전체를 옮기는 것을 첫 목표로 삼습니다.</p>
<p class="mini">금색 테두리는 작업을 시작한 권입니다. 23–57권의 권별 내용은 조사하면서 채웁니다.</p>
<div class="covol">{칸}</div>"""
    쪽들["sources/co/index.html"] = 틀("sources/co/index.html", "칼빈 전집(CO) 지도", 본문, "sources",
                                    [("", SITE["name"]), ("sources/", "원전"), (None, "칼빈 전집(CO)")])


def 성경쪽():
    """성경 66권: 개역한글판 본문 읽기 + 각 책·장을 다룬 저작 모음"""
    # 장별로 그 장을 다룬 설교·주석을 모은다
    장색인 = {}
    for w in WORKS:
        for n, u in w["units"].items():
            for 책, 장 in 단위장들(w, u):
                장색인.setdefault((책, 장), []).append((w, u))
    종류 = {"주석": "k-c", "설교": "k-s", "주석·설교": "k-cs", "확인 중": "k-q", "없음": ""}
    본문 = ('<h1>성경</h1><p class="lead">개역한글판(1961) 66권 전체를 읽을 수 있습니다. 책마다 이 도서관에 있는 설교와 주석을 함께 모읍니다.</p>'
          '<p><a class="btn on" href="{R}bible/read/">책으로 펼쳐 읽기</a></p>'
          '<div class="legend"><span>칼빈 전집에 남은 것:</span><span><i class="kind k-c">주석</i></span><span><i class="kind k-s">설교</i></span>'
          '<span><i class="kind k-cs">주석·설교</i></span><span><i class="kind k-q">확인 중</i></span><span><i class="kind">없음</i></span></div>')
    for 약 in ("구약", "신약"):
        칸 = ""
        for b in [x for x in BIBLE["books"] if x["testament"] == 약]:
            수 = len({id(u) for (책, _), l in 장색인.items() if 책 == b["abbr"] for _, u in l})
            칸 += (f'<a class="bk" href="{{R}}bible/{b["code"]}/"><b>{e(b["name"])}</b> <i class="kind {종류.get(b["kind"], "")}">칼빈 {e(b["kind"])}</i>'
                  f'{"<small>" + e(b["note"]) + "</small>" if b["note"] else ""}'
                  f'{"<small>이 도서관의 글 " + str(수) + "편</small>" if 수 else ""}</a>')
        본문 += f"<h2>{약}</h2><div class='bible'>{칸}</div>"
    본문 += f'<p class="mini">{e(BIBLE["note"])} 성경 본문은 저작재산권이 소멸한 『성경전서 개역한글판』입니다.</p>'
    # (예전 66권 목록 쪽은 쓰지 않는다. 성경 탭은 펼쳐 읽기 화면만 보인다)

    for b in BIBLE["books"]:
        책 = KRV.get(b["abbr"], {}).get("verses", {})
        장수 = max((int(k.split(":")[0]) for k in 책), default=0)
        글들 = [w for w in WORKS if b["abbr"] in w.get("bible", [])]
        h = f'<h1>{e(b["name"])}</h1><p class="lead">개역한글판 {장수}장. 칼빈 전집에 남은 것: {e(b["kind"])}{" (" + e(b["note"]) + ")" if b["note"] else ""}</p>'
        if 글들:
            h += "<h2>이 책을 다룬 저작</h2><ul>" + "".join(
                f'<li><a href="{{R}}{저작주소(w)}">{e(저자이름[w["author"]]["name"])}, 「{e(w["title"])}」</a> <span class="mini">{요약(저작항목(w))}</span></li>' for w in 글들) + "</ul>"
        h += '<h2>장</h2><div class="grid">' + "".join(
            f'<a class="cell{" s2" if (b["abbr"], c) in 장색인 else ""}" href="{{R}}bible/{b["code"]}/{c}.html" title="{e(b["name"])} {c}장">{c}</a>'
            for c in range(1, 장수 + 1)) + "</div>"
        if 장색인 and any(k[0] == b["abbr"] for k in 장색인):
            h += '<p class="mini">색이 칠해진 장은 이 도서관에 그 장을 다룬 글이 있습니다.</p>'
        경로 = f'bible/{b["code"]}/index.html'
        쪽들[경로] = 틀(경로, b["name"], h, "expositions", [("", SITE["name"]), ("expositions/", "주석·설교"), (None, b["name"])])
        for c in range(1, 장수 + 1):
            절들 = sorted((int(k.split(":")[1]), t) for k, t in 책.items() if int(k.split(":")[0]) == c)
            본 = "".join(f'<p class="v" id="v{v}"><sup class="vn">{v}</sup>{e(t)}</p>' for v, t in 절들)
            관련 = 장색인.get((b["abbr"], c), [])
            옆 = ""
            if 관련:
                옆 = '<h2>이 장을 다룬 글</h2><ul>' + "".join(
                    f'<li><a href="{{R}}{단위주소(w, u["no"])}">{e(저자이름[w["author"]]["name"])}, 「{e(w["title"])}」 제{u["no"]}{e(w["unit"])}</a> '
                    f'<span class="mini">({e(u["ref"])})</span></li>' for w, u in 관련) + "</ul>"
            앞뒤 = '<div class="pager">' + (
                f'<a href="{{R}}bible/{b["code"]}/{c-1}.html"><small>이전 장</small>{e(b["name"])} {c-1}장</a>' if c > 1 else '<span style="flex:1"></span>') + (
                f'<a class="next" href="{{R}}bible/{b["code"]}/{c+1}.html"><small>다음 장</small>{e(b["name"])} {c+1}장</a>' if c < 장수 else '<span style="flex:1"></span>') + "</div>"
            h = (f'<h1>{e(b["name"])} {c}장</h1><p class="mini">성경전서 개역한글판(1961) · <a href="{{R}}bible/read/#{b["code"]}/{c}">책으로 펼쳐 읽기</a></p>'
                 f'<div class="krvtext">{본}</div>{옆}{앞뒤}')
            경로 = f'bible/{b["code"]}/{c}.html'
            쪽들[경로] = 틀(경로, f'{b["name"]} {c}장', h, "expositions",
                          [("", SITE["name"]), ("expositions/", "주석·설교"), (f'bible/{b["code"]}/', b["name"]), (None, f"{c}장")],
                          설명=f'{b["name"]} {c}장 개역한글판 본문')


def 성경책쪽():
    """책 모양으로 성경 읽기: 본문은 data/krv/<코드>.json 을 불러와 펼친 두 쪽에 흘려 넣는다"""
    목록 = []
    for b in BIBLE["books"]:
        절 = KRV.get(b["abbr"], {}).get("verses", {})
        목록.append({"code": b["code"], "abbr": b["abbr"], "name": b["name"], "t": b["testament"],
                   "ch": max((int(k.split(":")[0]) for k in 절), default=1)})
    판목록 = "".join(f'<option value="{v["id"]}">{e(v["name"])}</option>' for v in VERSIONS)
    본문 = (f'<div class="reader-bar"><select id="verSel" aria-label="번역본">{판목록}</select>'
          f'<select id="parSel" aria-label="나란히 볼 번역본"><option value="">나란히 보기: 없음</option>{판목록}</select>'
          f'<select id="bkSel" aria-label="책"></select><select id="chSel" aria-label="장"></select>'
          f'<div class="seg"><button class="btn" id="fsMinus">가−</button><button class="btn" id="fsPlus">가+</button></div>'
          f'<select id="coverSel" aria-label="표지 색"></select><button class="btn" id="markBtn">책갈피로 가기</button>'
          f'<span class="mini">절을 누르면 책갈피, 키보드 ←→나 화면 밀기로 쪽을 넘깁니다.</span></div>'
          f'<div class="bookwrap"><div class="tabs ot" id="tabsOT"></div><div class="tabs nt" id="tabsNT"></div>'
          f'<button class="turn prev" id="prevBtn" aria-label="앞 쪽">‹</button><button class="turn next" id="nextBtn" aria-label="다음 쪽">›</button>'
          f'<div class="pages"><div class="runhead" id="runhead"></div><div id="viewport"><div id="flow"></div></div><div class="pageno" id="pageno"></div></div></div>'
          f'<script>window.KLCCL_BOOKLIST={json.dumps(목록, ensure_ascii=False)};window.KLCCL_VERSIONS={json.dumps(VERSIONS, ensure_ascii=False)};</script>'
          f'<script src="{{R}}assets/reader.js" defer></script>')
    for 경로 in ("bible/index.html", "bible/read/index.html"):   # 예전 주소(bible/read/)도 그대로 열리게
        h = 틀(경로, "성경", 본문, "bible")
        # 책 화면은 넓게 쓰도록 본문 여백 틀을 걷어 낸다
        h = h.replace('<div class="layout single"><main>', '<div class="layout single wide"><main>').replace('<div class="page">', '<div>', 1)
        쪽들[경로] = h


def 강해쪽():
    """주석·설교: 번역된 저작 카드 + 성경 책별 찾기(번역이 있는 책만 진하게)"""
    강해 = [w for w in WORKS if w.get("genre") in ("sermons", "commentaries")]
    카드 = "".join(
        f'<a class="card" href="{{R}}{저작주소(w)}"><h3>「{e(w["title"])}」</h3>'
        f'<p>{e(저자이름[w["author"]]["name"])} · {e(갈래이름.get(w["genre"], ""))}</p>'
        f'{막대(저작항목(w))}<span class="mini">{요약(저작항목(w))}</span></a>' for w in 강해)
    본문 = ('<h1>주석·설교</h1><p class="lead">번역된 주석과 설교입니다. 성경 책으로 찾으려면 아래에서 책을 고르십시오.</p>'
          f'<div class="cards">{카드}</div><h2>성경 책별로 찾기</h2>')
    for 약 in ("구약", "신약"):
        칸 = ""
        for b in [x for x in BIBLE["books"] if x["testament"] == 약]:
            있음 = any(b["abbr"] in w.get("bible", []) for w in 강해)
            칸 += (f'<a class="bkmini on" href="{{R}}bible/{b["code"]}/">{e(b["name"])}</a>' if 있음
                  else f'<span class="bkmini">{e(b["name"])}</span>')
        본문 += f'<h3 class="testament">{약}</h3><div class="bkminis">{칸}</div>'
    본문 += '<p class="mini">진한 책에 번역된 주석·설교가 있습니다. 번역이 늘면 차례로 진해집니다.</p>'
    쪽들["expositions/index.html"] = 틀("expositions/index.html", "주석·설교", 본문, "expositions", [("", SITE["name"]), (None, "주석·설교")])


PSALTER_DIR = 뿌리 / "content" / "psalter" / "genevan"
PSALTER = (json.loads((PSALTER_DIR / "psalter.json").read_text(encoding="utf-8"))["psalms"]
           if (PSALTER_DIR / "psalter.json").exists() else [])


def 절구성(글: str) -> dict:
    """'1절=1~3절, 2절=4~5절 앞' 같은 메모를 {가사 절: '시편 1~3절'} 로 푼다"""
    결과 = {}
    for 조각 in re.sub(r"\([^)]*\)", "", 글).split(","):
        m = re.match(r"\s*(\d+)절\s*=\s*(.+?)\s*$", 조각)
        if m:
            결과[int(m.group(1))] = m.group(2)
    return 결과


def 시편찬송쪽():
    """시편찬송: 한국어 제네바 시편가 150편(악보 PDF, MusicXML, 가사)과 개역한글 시편"""
    시편 = next(b for b in BIBLE["books"] if b["abbr"] == "시")
    칸 = "".join(f'<a class="cell" href="{{R}}bible/{시편["code"]}/{n}.html" title="시편 {n}편 (개역한글판)">{n}</a>' for n in range(1, 151))
    상태 = "공개(AI 초벌 편역 · 신학 감수 전)" if PSALTER else "예정"
    본문 = f"""<h1>시편찬송</h1><p class="lead">종교개혁 교회는 시편을 운율로 옮겨 회중이 함께 불렀습니다. 칼빈의 제네바 교회에서 완성된 「제네바 시편가」(1562)가 그 대표입니다.</p>
<h2>싣는 것</h2><table class="t"><tr><th style="width:190px">자료</th><th>내용</th><th style="width:150px">상태</th></tr>
<tr><td>한국어 제네바 시편가</td><td>제네바 곡조(1539–1562)와 클로드 구디멜의 4성부 화성(1564)에 개역한글판 시편을 운율에 맞게 편역한 가사를 붙인 150편. 곡마다 악보 PDF와 MusicXML(출력용·반주용)을 내려받을 수 있습니다</td><td>{상태}</td></tr>
<tr><td>제네바 시편가 원문</td><td>마로와 베자의 프랑스어 운율 시편(16세기, 공유 저작물)</td><td>예정</td></tr>
<tr><td>칼빈의 서문</td><td>시편가에 붙인 칼빈의 서문(1542·1543)</td><td>예정</td></tr>
<tr><td>시편 본문</td><td>개역한글판 시편 150편 (곡별 쪽과 성경 메뉴에서 읽기)</td><td>공개</td></tr></table>
<div class="box">오늘날 교회에서 쓰는 한국어 시편찬송가와 찬송가 가사·편곡은 대부분 저작권이 살아 있어 싣지 않습니다. 이 도서관은 16세기 원문과 곡조처럼 공유 저작물인 것만 싣고, 한국어 가사는 새로 옮겨 조건 없이 공개합니다. 선율과 화성은 genevanpsalter.com에 공개된 악보를 옮겼고, 한국어 가사와 편집 악보는 CC0로 공개합니다.</div>"""
    if PSALTER:
        격자 = "".join(f'<a class="cell" href="{{R}}psalter/{p["n"]:03d}.html" title="시편 {p["n"]}편 · {e(p["tune"])}">{p["n"]}</a>' for p in PSALTER)
        본문 += f"""<h2>한국어 제네바 시편가 150편</h2>
<p class="mini">편 번호를 누르면 악보와 가사가 열립니다. 가사는 개역한글판(1961) 시편을 곡조의 음절 수에 맞게 옮긴 AI 초벌 편역판이며 신학 감수 전입니다. 악보에는 빠르기와 도돌이표를 표시하지 않았으니 가사 줄 수만큼 절을 되풀이해 부릅니다.</p>
<div class="grid">{격자}</div>"""
    else:
        본문 += f"""<h2>시편 150편 (개역한글판)</h2><div class="grid">{칸}</div>"""
    쪽들["psalter/index.html"] = 틀("psalter/index.html", "시편찬송", 본문, "psalter", [("", SITE["name"]), (None, "시편찬송")])
    for i, p in enumerate(PSALTER):
        n = p["n"]
        구성 = 절구성(p.get("plan", ""))
        절들 = "".join(
            f'<div style="margin:0 0 14px"><b>{k}절</b>'
            + (f' <span class="mini">(시편 {e(구성[k])})</span>' if k in 구성 else "")
            + '<br>' + "<br>".join(e(x) for x in v) + "</div>"
            for k, v in enumerate(p["verses"], 1))
        쪽수 = len(list((PSALTER_DIR / "img").glob(f"ps{n:03d}-*.png")))
        악보 = "".join(f'<img src="img/ps{n:03d}-{k}.png" alt="시편 {n}편 악보 {k}쪽" loading="{"eager" if k == 1 else "lazy"}" '
                      f'style="width:100%;max-width:820px;display:block;margin:0 auto 12px;background:#fff;border:1px solid var(--line);border-radius:6px">'
                      for k in range(1, 쪽수 + 1))
        음원 = PSALTER_DIR / "mp3" / f"ps{n:03d}.mp3"
        반주 = (f'<button class="btn" onclick="var a=document.getElementById(\'acc\');if(a.paused){{a.play();this.textContent=\'반주 멈춤\'}}else{{a.pause();this.textContent=\'반주 재생\'}}">반주 재생</button>'
                f'<audio id="acc" preload="none" src="mp3/ps{n:03d}.mp3"></audio>') if 음원.exists() else \
               '<span class="btn" style="opacity:.45;cursor:default" title="반주 음원은 준비 중입니다">반주 재생(준비 중)</span>'
        앞 = f'<a class="btn" href="{n-1:03d}.html">← 시편 {n-1}편</a> ' if i > 0 else ""
        뒤 = f'<a class="btn" href="{n+1:03d}.html">시편 {n+1}편 →</a>' if i < len(PSALTER) - 1 else ""
        본문 = f"""<h1>시편 {n}편</h1>
<p class="lead">{e(p["tune"])} · {e(p["meter"])}</p>
<p class="mini">곡조: {e(p["music"])} · 화성: {e(p["harm"])} · 가사: 개역한글판 시편 {n}편 편역(AI 초벌 편역판 · 신학 감수 전) · {len(p["verses"])}절</p>
<p><a class="btn dl" href="pdf/ps{n:03d}.pdf">악보 PDF</a>
<a class="btn" href="xml/ps{n:03d}.musicxml" download>MusicXML(출력용)</a>
<a class="btn" href="xml/ps{n:03d}_accomp.musicxml" download>MusicXML(반주용, 전주·반복 포함)</a>
<a class="btn" href="{{R}}bible/{시편["code"]}/{n}.html">개역한글 시편 {n}편 읽기</a></p>
<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin:28px 0 14px;padding-bottom:8px"><h2 style="margin:0;border:0;padding:0">악보</h2>
<span style="display:flex;gap:6px;flex-wrap:wrap">{앞}<a class="btn" href="./">목록</a>{반주}{뒤}</span></div>{악보}
<h2>가사</h2><div style="font-family:var(--serif);font-size:17px;line-height:1.9">{절들}</div>
"""
        쪽들[f"psalter/{n:03d}.html"] = 틀(f"psalter/{n:03d}.html", f"시편 {n}편 · 한국어 제네바 시편가", 본문, "psalter",
                                       [("", SITE["name"]), ("psalter/", "시편찬송"), (None, f"시편 {n}편")],
                                       설명=f"한국어 제네바 시편가 시편 {n}편: {p['tune']} 곡조의 악보 PDF, MusicXML, 가사")


def 찾기쪽():
    """정적 사이트용 찾기: 저작·설교 제목·구절 색인(search.json)을 브라우저에서 거른다"""
    색인 = []
    for a in LIB["authors"]:
        if a["ready"]:
            색인.append({"t": a["name"], "s": "저자", "u": f'{a["id"]}/'})
    for w in WORKS:
        a = 저자이름[w["author"]]["name"]
        색인.append({"t": f'{a}, 「{w["title"]}」', "s": "저작", "u": 저작주소(w), "x": w["summary"]})
        for n, u in sorted(w["units"].items()):
            색인.append({"t": f'「{w["title"]}」 제{n}{w["unit"]} {u["title"]}', "s": f'{a} · {u["ref"]} · {쪽범위(w, u)}',
                       "u": 단위주소(w, n)})
    for b in BIBLE["books"]:
        색인.append({"t": b["name"], "s": "성경", "u": f'bible/{b["code"]}/', "x": b["abbr"]})
    책목록 = {b["abbr"]: b["code"] for b in BIBLE["books"]} | {b["name"]: b["code"] for b in BIBLE["books"]}
    본문 = (f'<h1>찾기</h1><p class="lead">저자, 저작, 설교 제목, 성경 구절로 찾습니다. 성경 구절은 "욥 16:2"나 "욥기 16"처럼 적으면 그 장으로 갑니다.</p>'
          f'<input class="search big" id="sq" type="search" placeholder="예: 욥 16:2, 위로자, 칼빈" autofocus>'
          f'<div id="sr" class="results"></div>'
          f'<p class="mini">지금은 제목과 구절 색인으로 찾습니다. 본문 전체 찾기는 번역이 늘어나면 더합니다.</p>'
          f'<script>window.KLCCL_SEARCH={json.dumps(색인, ensure_ascii=False)};window.KLCCL_BOOKS={json.dumps(책목록, ensure_ascii=False)};</script>')
    쪽들["search/index.html"] = 틀("search/index.html", "찾기", 본문, "search", [("", SITE["name"]), (None, "찾기")])


def 총서():
    본문 = '<h1>총서</h1><p class="lead">총서는 저자와 갈래별로 묶어 펴내는 번역 시리즈입니다. 권마다 진행 정도를 표시합니다.</p>'
    for s in LIB["series"]:
        본문 += f"<h2>{e(s['name'])}</h2><p>{e(s['desc'])}</p>"
        for b in s["branches"]:
            vols = [(w, v) for w in WORKS if w["series"] == s["id"] and w["branch"] == b["id"] for v in w["volumes"]]
            본문 += f'<h3 style="font-family:var(--serif);margin:18px 0 4px">갈래: {e(b["name"])}</h3><p class="mini">{e(b["note"])}</p>'
            if not vols:
                본문 += '<p class="mini">대상 선정 중입니다.</p>'
                continue
            줄 = "".join(
                f'<tr><td>{권표(v)[3:] if 권표(v).startswith("CR") else 권표(v)}</td><td><b><a href="{{R}}{저작주소(w)}">{e(v["title"])}</a></b><br>'
                f'<span class="mini">{v["from"]}–{v["to"]} ({len(v["items"])}{e(w["unit"])})</span>'
                f'{PDF링크(w, v, "tag")}</td><td class="mini">{e(원전권(w, v))}</td>'
                f'<td>{막대(v["items"])}<span class="mini">{요약(v["items"])}</span></td></tr>'
                for w, v in sorted(vols, key=lambda x: x[1]["no"]))
            본문 += f'<table class="t"><tr><th style="width:64px">CR</th><th>제목</th><th style="width:80px">저본</th><th style="width:230px">진행</th></tr>{줄}</table>'
    본문 += '<div class="card soon" style="margin-top:20px"><h3>다른 총서 (예정)</h3><p>교부, 종교개혁자, 청교도의 공유 저작물로 총서를 더합니다.</p></div>'
    쪽들["series/index.html"] = 틀("series/index.html", "총서", 본문, "books", [("", SITE["name"]), ("books/", "도서"), (None, "총서")], 하위="series", 하위목록=도서하위)


def 진행():
    it = 모든항목()
    c = 집계(it)
    범례 = "".join(f'<span><i class="cell s{k}"></i>{상태이름[k]} {c[k]}</span>' for k in (3, 2, 1, "0x", 0))
    본문 = f'<h1>진행 현황</h1><p class="lead">원고 파일에서 자동으로 만든 표입니다. 기준일 {기준일}.</p><div class="legend">{범례}</div>'
    for w in WORKS:
        for v in w["volumes"]:
            본문 += f'<h2>{e(v["title"])} <span class="mini">{e(원전권(w, v))}</span></h2>'
            본문 += f'{막대(v["items"])}<div class="mini">{요약(v["items"])}</div><div class="grid">'
            for x in v["items"]:
                제 = f'제{x["no"]}{w["unit"]} {x["title"]} · {상태이름[x["s"]]}'
                if x["s"] in (2, 3):
                    본문 += f'<a class="cell s{x["s"]}" href="{{R}}{단위주소(w, x["no"])}" title="{e(제)}">{e(x["short"])}</a>'
                else:
                    본문 += f'<span class="cell s{x["s"]}" title="{e(제)}">{e(x["short"])}</span>'
            본문 += "</div>"
    쪽들["about/progress/index.html"] = 틀("about/progress/index.html", "진행 현황", 본문, "about",
                                       [("", SITE["name"]), ("about/", "소개"), (None, "진행 현황")], 하위="progress")


def 저작쪽(w):
    경로 = 저작주소(w) + "index.html"
    a = 저자이름[w["author"]]
    본문 = f'<h1>{e(a["name"])}, 「{e(w["title"])}」</h1><p class="lead">{e(w["summary"])}</p>'
    for v in w["volumes"]:
        본문 += f'<h2>{권표(v)} 『{e(v["title"])}』 <span class="mini">{e(원전권(w, v))}</span></h2>'
        본문 += f'{막대(v["items"])}<div class="mini" style="margin-bottom:8px">{요약(v["items"])}</div>'
        본문 += PDF링크(w, v)
        공개 = [x for x in v["items"] if x["s"] in (2, 3)]
        if 공개:
            본문 += (f'<details class="units"><summary>편 목록 펼치기 <span class="mini">(공개 {len(공개)}{e(w["unit"])})</span></summary>'
                     '<table class="t"><tr><th style="width:80px">편</th><th>제목</th><th style="width:110px">상태</th></tr>') + "".join(
                f'<tr><td>제{x["no"]}{e(w["unit"])}</td><td><a href="{{R}}{단위주소(w, x["no"])}">{e(x["title"])}</a> ' +
                (f'<span class="mini">({e(w["units"][x["no"]]["ref"])})</span>' if w["units"][x["no"]]["ref"] else "") + '</td>' +
                f'<td><span class="tag">{"대역" if x["s"] == 3 else "한국어"}</span></td></tr>' for x in 공개) + "</table></details>"
        남음 = [x for x in v["items"] if x["s"] not in (2, 3)]
        if 남음:
            c = 집계(남음)
            본문 += (f'<p class="mini">웹 연결 대기 {c[1]}{e(w["unit"])}, 원고 확보 필요 {c["0x"]}{e(w["unit"])}, '
                    f'번역 예정 {c[0]}{e(w["unit"])}.' + "</p>")
    쪽들[경로] = 틀(경로, f'「{w["title"]}」', 본문, "books",
                  [("", SITE["name"]), ("books/", "도서"), (f'{a["id"]}/', a["name"]), (None, w["title"])])


def 서가(w, 현재번호: int) -> str:
    a = 저자이름[w["author"]]
    h = f'<div class="shelf"><h3>저자</h3><div class="series"><a href="{{R}}{a["id"]}/" style="text-decoration:none">{e(a["name"])} ({e(a["life"])})</a></div><h3>저작</h3>'
    h += f'<div class="series"><a href="{{R}}{저작주소(w)}" style="text-decoration:none">「{e(w["title"])}」</a></div>'
    for v in w["volumes"]:
        여기 = v["from"] <= 현재번호 <= v["to"]
        제목 = f'{권표(v)} 『{e(v["title"])}』 {v["from"]}–{v["to"]}'
        공개 = [x for x in v.get("items", []) if x["s"] in (2, 3)]
        if not 공개:
            # 공개된 편이 없는 권은 접을 것이 없으므로 제목만 둔다
            h += f'<div class="vol soon">{제목}</div>'
            continue
        # 권마다 접고 펼치는 토글. 지금 읽는 권만 펼쳐 둔다
        h += f'<details class="voltog"{" open" if 여기 else ""}><summary class="vol{" cur" if 여기 else ""}">{제목}</summary>'
        h += PDF링크(w, v, "mini")
        h += '<nav class="slist">'
        for x in 공개:
            h += (f'<a href="{{R}}{단위주소(w, x["no"])}"{" class=cur" if x["no"] == 현재번호 else ""}>제{x["no"]}{e(w["unit"])}'
                  f'{" <span class=tag>대역</span>" if x["s"] == 3 else ""}<span>{e(x["title"])}</span></a>')
        남 = len(v["items"]) - len(공개)
        if 남:
            h += f'<span class="off">그 밖 {남}{e(w["unit"])}은 준비 중</span>'
        h += "</nav></details>"
    return h + "</div>"


def 각주표시(s: str) -> str:
    return re.sub(r"⁣FN(\d+)⁣", lambda m: f'<sup class="fn" data-n="{m.group(1)}">{m.group(1)}</sup>', s)


def 읽기쪽(w, u):
    경로 = 단위주소(w, u["no"])
    a = 저자이름[w["author"]]
    원문있음 = bool(u["orig"])
    h = (f'<div class="tools"><div class="seg" role="group" aria-label="보기 방식">'
         f'<button class="btn" data-mode="both">대역</button><button class="btn" data-mode="ko">한국어</button>'
         f'<button class="btn" data-mode="fr">원문</button></div>'
         f'<div class="seg" role="group" aria-label="글자 크기"><button class="btn" data-fs="-1">가−</button><button class="btn" data-fs="1">가+</button></div>'
         f'<input class="search" id="q" type="search" placeholder="이 글에서 찾기 (한국어·원문)"><span class="hits" id="hits"></span>'
         f'<button class="btn" id="copyText">본문 복사</button></div>')
    h += (f'<article class="reader" id="reader" data-author="{e(a["name"])}" data-cite-title="{e(w["cite_title"])}" data-no="{u["no"]}" '
          f'data-unit="{e(w["unit"])}" data-vol="{u["vol"]}" data-cite-pre="{e(쪽앞뒤(w, u)[0])}" data-cite-post="{쪽앞뒤(w, u)[1]}" data-site="{e(SITE["name"])}">')
    h += (f'<div class="head"><div class="no">제{u["no"]}{e(w["unit"])}</div><div class="sub">{e(u["title"])}{" (" + e(u["ref"]) + ")" if u["ref"] else ""}</div>'
          f'<div class="co">{e(쪽범위(w, u))}</div></div>')
    책 = KRV.get(w.get("krv_book", ""), {}).get("verses", {})
    구절 = 구절목록(u["ref"], 책) if 책 else None
    칼빈본문 = (f'<div class="ko calvin"><span class="lbl">칼빈이 읽은 본문 · 프랑스어에서 옮김 (Claude 번역)</span>'
              f'{각주표시(e(둥근따옴표(u["box"])))}</div>')
    if not 구절 and not u["box"].strip():
        h += '<div class="verse">'
    elif 구절:
        개역 = " ".join(f'<sup class="vn">{k}</sup>{e(책[k])}' for k in 구절)
        h += (f'<div class="verse"><div class="vgrid"><div class="ko krv"><span class="lbl">성경 본문 · 개역한글판</span>{개역}</div>'
              f'{칼빈본문}</div>')
    else:
        h += f'<div class="verse">{칼빈본문}'
    h += ((f'<div class="fr frbox" lang="fr"><span class="lbl">{e(w["orig_label"])}</span>{e(u["origbox"])}</div>' if u["origbox"] else "") + "</div>")
    h += ('<div class="notice">' + 고지(w)
          + ("" if 원문있음 else " 이 글은 아직 원문 대역이 연결되지 않았습니다.") + "</div>")
    for idx, p in enumerate(sorted(u["pages"])):
        ko = "".join(
            f'<p class="{"note " if x["note"] else ""}{"cont" if x["cont"] else ""}">{각주표시(e(둥근따옴표(x["t"])))}</p>'
            for x in u["pages"][p])
        if 원문있음:
            fr = "".join(f'<p lang="fr">{e(t)}</p>' for t in u["orig"].get(p, []))
            오른쪽 = f'<div class="fr">{"<div class=lang>" + e(w["orig_label"]) + "</div>" if idx == 0 else ""}{fr}</div>'
        else:
            오른쪽 = '<div class="fr-missing">원문 대역은 준비 중입니다.</div>' if idx == 0 else "<div class=fr></div>"
        h += (f'<section class="row" id="p{p}"><div class="pg">{쪽앞뒤(w, u)[0]}{p}{쪽앞뒤(w, u)[1]}<button data-cite="{p}" title="인용 표기 복사">인용</button></div>'
              f'<div class="ko">{"<div class=lang>한국어 번역</div>" if idx == 0 else ""}{ko}</div>{오른쪽}</section>')
    if u["notes"]:
        h += '<div class="notes"><h4>각주</h4><ol>' + "".join(
            f'<li id="fn{k}">{e(둥근따옴표(n))}</li>' for k, n in enumerate(u["notes"], 1)) + "</ol></div>"
    장들 = 단위장들(w, u)
    if 장들:
        h += '<div class="notes"><h4>성경 본문 전체 보기</h4>' + " · ".join(
            f'<a href="{{R}}bible/{책코드[b]["code"]}/{c}.html">{e(책코드[b]["name"])} {c}장</a>' for b, c in 장들) + "</div>"
    번호들 = sorted(w["units"])
    i = 번호들.index(u["no"])
    앞 = w["units"][번호들[i - 1]] if i > 0 else None
    뒤 = w["units"][번호들[i + 1]] if i + 1 < len(번호들) else None
    h += '<div class="pager">' + (
        f'<a href="{{R}}{단위주소(w, 앞["no"])}"><small>이전</small>제{앞["no"]}{e(w["unit"])} {e(앞["title"])}</a>' if 앞 else '<span style="flex:1"></span>') + (
        f'<a class="next" href="{{R}}{단위주소(w, 뒤["no"])}"><small>다음</small>제{뒤["no"]}{e(w["unit"])} {e(뒤["title"])}</a>' if 뒤 else '<span style="flex:1"></span>') + "</div>"
    h += "</article>"
    강해 = w.get("genre") in ("sermons", "commentaries")
    빵 = [("", SITE["name"]), ("expositions/", "주석·설교") if 강해 else ("books/", "도서"), (f'{a["id"]}/', a["name"]), (저작주소(w), w["title"]), (None, f'제{u["no"]}{w["unit"]}')]
    쪽들[경로] = 틀(경로, f'{a["name"]} 「{w["title"]}」 제{u["no"]}{w["unit"]}', h, "expositions" if 강해 else "books", 빵, 서가(w, u["no"]),
                  설명=f'{a["name"]} 「{w["title"]}」 제{u["no"]}{w["unit"]} {u["title"]}' + (f'({u["ref"]})' if u["ref"] else "") + ' 한국어 번역과 원문 대역')


def 소개쪽들():
    빵 = lambda t: [("", SITE["name"]), ("about/", "소개"), (None, t)]
    소개 = f"""<h1>도서관 소개</h1><p class="lead">{e(SITE['name'])}({e(SITE['en'])})는 서양 기독교 고전을 한국어로 옮겨 무료로 공개하는 온라인 도서관입니다.</p>
<h2>왜 만드는가</h2><p>영어권에는 교부와 종교개혁자, 청교도의 저작을 무료로 읽을 수 있는 도서관이 오래전부터 있습니다. 한국어로는 그런 서고가 없어서, 원어를 모르는 목회자와 신학생, 성도가 원전에 닿기 어렵습니다. 이 도서관은 그 빈자리를 채우려 합니다.</p>
<h2>무엇이 다른가</h2><table class="t"><tr><th style="width:160px">특징</th><th>내용</th></tr>
<tr><td>기독교 고전 전문</td><td>교부, 종교개혁, 청교도 저작에 집중합니다.</td></tr>
<tr><td>원어 직접 번역</td><td>중역하지 않고 원문에서 옮깁니다.</td></tr>
<tr><td>학술 쪽수 인용</td><td>원전 전집의 쪽수로 원문과 번역을 맞대어, 논문과 설교에서 그대로 인용할 수 있습니다.</td></tr>
<tr><td>조건 없는 공개</td><td>번역문 CC0. 비영리 조건도 붙이지 않습니다.</td></tr></table>
<h2>도서관의 짜임</h2><table class="t"><tr><th style="width:160px">탭</th><th>내용</th></tr>
<tr><td>성경</td><td>개역한글판 66권과, 책·장마다 이 도서관의 설교와 주석을 함께 봅니다.</td></tr>
<tr><td>주석·설교</td><td>성경 66권 차례로 정리한 주석과 설교입니다.</td></tr>
<tr><td>도서</td><td>교리서, 신조, 서신, 경건 서적과 총서를 갈래, 시대, 원어로 골라 봅니다.</td></tr>
<tr><td>시편찬송</td><td>한국어 제네바 시편가 150편(악보 PDF·MusicXML·가사)과 개역한글판 시편 150편입니다.</td></tr>
<tr><td>저자</td><td>시대 순으로 정리한 저자와 저자별 저작입니다.</td></tr>
<tr><td>원전</td><td>번역의 저본인 원전 전집의 권별 지도입니다.</td></tr>
<tr><td>찾기</td><td>저자, 저작, 제목, 성경 구절로 찾습니다.</td></tr></table>
<h2>어떻게 운영하는가</h2><p>회원 가입, 광고, 후원 결제가 없는 정적 사이트입니다. 무료 호스팅에 파일만 올려 운영하므로 운영비가 들지 않습니다. 원고와 사이트 파일은 공개 저장소에 두어, 누구나 내려받아 보관하거나 다른 곳에 다시 올릴 수 있습니다.</p>
<h2>관계 밝힘</h2><p>이 도서관은 어떤 교단, 학교, 해외 도서관과도 소속 관계가 없는 개인의 비영리 작업입니다.</p>"""
    원칙 = """<h1>이 도서관의 원칙</h1><p class="lead">무엇을 싣고, 어떻게 옮기고, 어떤 조건으로 공개하는지 밝혀 둡니다.</p>
<h2>싣는 것</h2><dl class="def">
<dt>공유 저작물만</dt><dd>저자 사망 후 70년이 지났고, 원전 판본도 공유 저작물인 것만 싣습니다. 칼빈 저작은 칼빈 전집(Ioannis Calvini Opera, 1863–1900)과 16세기 초판을 저본으로 합니다.</dd>
<dt>싣지 않는 것</dt><dd>현대 비평판(Supplementa Calviniana, 새 전집 등), 저작권이 살아 있는 현대 번역, 다른 사이트가 덧붙인 소개글·표지·전자책 편집물은 쓰지 않습니다.</dd></dl>
<h2>옮기는 방식</h2><dl class="def">
<dt>원어에서 직접</dt><dd>영어 번역을 거치지 않고 원문(프랑스어, 라틴어 등)에서 바로 옮깁니다.</dd>
<dt>쪽 단위 대역</dt><dd>원문과 번역은 원전 쪽(예: CO 34:n) 단위로 맞대어 놓습니다. 쪽 표시 옆 「인용」을 누르면 인용 표기가 복사됩니다.</dd>
<dt>문체</dt><dd>설교는 합쇼체로 옮깁니다. 성경 본문은 저작재산권이 소멸한 『성경전서 개역한글판』(1961)으로 통일합니다.</dd>
<dt>설교 첫머리 본문 상자</dt><dd>개역한글판 본문과, 칼빈이 설교 때 읽은 프랑스어 성경 본문을 옮긴 문장을 나란히 둡니다. 칼빈은 자기가 읽은 본문의 낱말을 짚어 설교하므로 두 본문을 함께 보아야 설교가 잘 이해됩니다. 칼빈 본문의 번역은 Claude가 프랑스어에서 옮긴 것이며, 원문은 그 아래에 그대로 둡니다.</dd>
<dt>함께 싣는 성경 번역본</dt><dd>개역한글판 외에 제네바 성경(1599), 흠정역(KJV), World English Bible, Berean Standard Bible을 함께 싣습니다. 모두 저작권이 없는 퍼블릭 도메인 본문이며, 외국어 번역본은 대조용 참고 자료입니다. 외경(제2경전)은 싣지 않습니다.</dd>
<dt>AI 초벌 번역판</dt><dd>초벌 번역에 생성형 AI(Claude)를 썼고, 신학 전문가의 감수는 거치지 않았습니다. 그래서 모든 번역은 「AI 초벌 번역판 · 신학 감수 전」입니다. 인용할 때는 원문(CO 권:쪽)을 확인해 주십시오.</dd></dl>
<h2>이용 조건</h2><div class="box">번역문은 CC0 1.0 퍼블릭 도메인 기증으로 공개합니다. 누구나 허락 없이 복제, 배포, 수정, 출판할 수 있습니다. 출처를 밝혀 주시면 고맙지만 의무는 아닙니다.</div>
<h2>고침과 기록</h2><p>오류 제보는 <a href="{R}about/contribute/">참여와 오류 제보</a> 쪽의 방법으로 받습니다. 고친 내용은 판 번호와 함께 기록해, 어느 판을 인용했는지 알 수 있게 합니다.</p>"""
    gh, em = SITE["contact"].get("github"), SITE["contact"].get("email")
    제보 = f"""<h1>참여와 오류 제보</h1><p class="lead">오역, 빠진 문장, 어색한 표현, 성경 구절 오류를 알려 주십시오. 신학 지식이 없어도 이상하게 읽히는 곳이면 충분합니다.</p>
<h2>제보 방법</h2><table class="t"><tr><th style="width:160px">방법</th><th>안내</th></tr>
<tr><td>GitHub 이슈</td><td>{f'<a href="{e(gh)}/issues" target="_blank" rel="noopener">저장소 이슈 쪽</a>에 새 글을 남겨 주십시오.' if gh else '공개 저장소를 열면 이곳에 주소를 적습니다.'}</td></tr>
<tr><td>이메일</td><td>{e(em) if em else '운영자 주소를 정하면 이곳에 적습니다.'}</td></tr></table>
<h2>적어 주시면 좋은 것</h2><div class="box">저작: 칼빈 「욥기 설교」 제62편<br>쪽: CO 34:3 (쪽 표시 옆 「인용」 단추로 복사할 수 있습니다)<br>현재 번역: (문제가 되는 문장)<br>제안: (고친 문장, 있으면)<br>까닭: (원문 근거나 어색한 이유, 짧게)</div>
<h2>함께하기</h2><p>원문을 읽을 수 있는 분의 감수, 신학 용어 검토, 원전 판본 조사를 환영합니다. 참여하신 분의 이름은 원하시면 고친 이력에 남깁니다.</p>"""
    소식 = '<h1>소식</h1><table class="t"><tr><th style="width:120px">날짜</th><th>내용</th></tr>' + "".join(
        f"<tr><td>{e(d)}</td><td>{e(t)}</td></tr>" for d, t in LIB["news"]) + "</table>"
    쪽들["about/index.html"] = 틀("about/index.html", "소개", 소개, "about", 빵("소개"), 하위="about")
    쪽들["about/principles/index.html"] = 틀("about/principles/index.html", "원칙", 원칙, "about", 빵("원칙"), 하위="principles")
    쪽들["about/contribute/index.html"] = 틀("about/contribute/index.html", "참여와 오류 제보", 제보, "about", 빵("참여와 오류 제보"), 하위="contribute")
    쪽들["about/news/index.html"] = 틀("about/news/index.html", "소식", 소식, "about", 빵("소식"), 하위="news")
    b = SITE.get("base_url", "").rstrip("/")
    쪽들["404.html"] = 틀("404.html", "찾을 수 없음",
                         f'<h1>쪽을 찾을 수 없습니다</h1><p><a href="{b + "/" if b else "{R}"}">홈으로 가기</a> · <a href="{b + "/search/" if b else "{R}search/"}">찾기</a></p>')


# ------------------------------------------------------------------
# 4. 쓰기
# ------------------------------------------------------------------
def 쓰기():
    if 출력.exists():
        shutil.rmtree(출력)
    for 경로, 글 in 쪽들.items():
        f = 출력 / 경로
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(글, encoding="utf-8")
    shutil.copytree(뿌리 / "assets", 출력 / "assets")
    # 권별 PDF 복사: content/<저자>/<저작>/pdf/<파일> → docs/<저작주소>pdf/<파일>
    for w in WORKS:
        for v in w["volumes"]:
            if isinstance(v.get("pdf"), str):
                원본 = 뿌리 / "content" / w["author"] / w["id"] / "pdf" / v["pdf"]
                if 원본.exists():
                    (출력 / 저작주소(w) / "pdf").mkdir(parents=True, exist_ok=True)
                    shutil.copy2(원본, 출력 / 저작주소(w) / "pdf" / v["pdf"])
    # 한국어 제네바 시편가: content/psalter/genevan/{pdf,xml} → docs/psalter/{pdf,xml}
    for 하위 in ("pdf", "xml", "img", "mp3"):
        if (PSALTER_DIR / 하위).exists():
            shutil.copytree(PSALTER_DIR / 하위, 출력 / "psalter" / 하위)
    # 책 모양 읽기용 성경 본문: data/<번역본>/<책코드>.json = {"name", "chapters": [[[절, 본문], …], …]}
    for ver in VERSIONS:
        폴더 = 출력 / "data" / ver["id"]
        폴더.mkdir(parents=True, exist_ok=True)
        if ver["id"] == "krv":
            책별 = {}
            for b in BIBLE["books"]:
                장들 = {}
                for k, t in KRV.get(b["abbr"], {}).get("verses", {}).items():
                    c, v = map(int, k.split(":"))
                    장들.setdefault(c, []).append([v, t])
                책별[b["code"]] = {c: sorted(l) for c, l in 장들.items()}
        else:
            책별 = VPL읽기(뿌리 / "catalog" / "versions" / f'{ver["id"]}.vpl.txt')
        for b in BIBLE["books"]:
            장들 = 책별.get(b["code"], {})
            배열 = [장들.get(c, []) for c in range(1, max(장들, default=0) + 1)]
            (폴더 / f'{b["code"]}.json').write_text(
                json.dumps({"name": b["name"], "chapters": 배열}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (출력 / ".nojekyll").write_text("", encoding="utf-8")   # GitHub Pages가 파일을 가공하지 않게
    if SITE.get("domain"):   # 연결한 도메인을 GitHub Pages가 기억하도록
        (출력 / "CNAME").write_text(SITE["domain"] + "\n", encoding="utf-8")
    b = SITE.get("base_url", "").rstrip("/")
    (출력 / "robots.txt").write_text(f"User-agent: *\nAllow: /\n" + (f"Sitemap: {b}/sitemap.xml\n" if b else ""), encoding="utf-8")
    if b:
        주소들 = "".join(f"<url><loc>{b}/{p.replace('index.html', '')}</loc></url>" for p in 쪽들 if p != "404.html")
        (출력 / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{주소들}</urlset>',
            encoding="utf-8")


def 미리보기한장():
    """아티팩트 미리보기용: 모든 쪽을 한 파일에 넣고 주소(#경로)로 바꿔 보여 준다"""
    css = (뿌리 / "assets" / "kccl.css").read_text(encoding="utf-8")
    js = (뿌리 / "assets" / "kccl.js").read_text(encoding="utf-8")
    몸들 = {}
    for p, h in 쪽들.items():
        # 성경 장 쪽은 1,189개라 미리보기에는 욥기만 넣는다(실제 사이트에는 모두 들어감)
        if re.match(r"bible/[^/]+/\d+\.html$", p) and not p.startswith("bible/job/"):
            continue
        몸 = h[h.index("<body") :h.index('<script src=')]
        몸 = 몸[몸.index(">") + 1:]
        몸들[p] = 몸
    틀글 = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(SITE['name'])} {e(SITE['full'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&family=EB+Garamond:ital,wght@0,400;0,600;1,400&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>{css}</style></head><body data-root="#"><div id="root"></div>
<script>
const PAGES = {json.dumps(몸들, ensure_ascii=False).replace("</", "<\\/")};
const JS = {json.dumps(js, ensure_ascii=False).replace("</", "<\\/")};
// 상대 경로 링크를 미리보기 안의 주소로 바꾼다
function norm(base, href){{
  if (/^(https?:|mailto:|#)/.test(href)) return null;
  const parts = base.split('/'); parts.pop();
  for (const seg of href.split('/')) {{ if (seg === '..') parts.pop(); else if (seg !== '.') parts.push(seg); }}
  let p = parts.join('/'); if (p === '' || p.endsWith('/')) p += 'index.html';
  return p;
}}
function show(path){{
  if (!PAGES[path]) path = 'index.html';
  const root = document.getElementById('root'); root.innerHTML = PAGES[path];
  root.querySelectorAll('a[href]').forEach(a => {{ const n = norm(path, a.getAttribute('href')); if (n) a.setAttribute('href', '#' + n); }});
  root.querySelectorAll('script').forEach(old => {{ const n = document.createElement('script'); n.textContent = old.textContent; old.replaceWith(n); }});
  document.querySelectorAll('script[data-k]').forEach(s => s.remove());
  const s = document.createElement('script'); s.dataset.k = 1; s.textContent = JS; document.body.appendChild(s);
  window.scrollTo(0, 0);
}}
window.addEventListener('hashchange', () => show(location.hash.slice(1)));
show(location.hash.slice(1) || 'index.html');
</script></body></html>"""
    (뿌리 / "docs_preview.html").write_text(틀글, encoding="utf-8")


if __name__ == "__main__":
    홈(); 서가쪽(); 저자쪽(); 총서(); 성경쪽(); 강해쪽(); 성경책쪽(); 시편찬송쪽(); 찾기쪽(); 진행(); 소개쪽들()
    for w in WORKS:
        저작쪽(w)
        for n in sorted(w["units"]):
            읽기쪽(w, w["units"][n])
    쓰기()
    if "--one" in sys.argv:
        미리보기한장()
    공개 = sum(len(w["units"]) for w in WORKS)
    print(f"완료: 쪽 {len(쪽들)}개, 웹 공개 {공개}편, 출력 {출력}")
