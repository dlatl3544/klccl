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
# 영문판(/en/) 화면용 영어 자료. 한국어 자료에 덧씌우고, 없는 값은 한국어 그대로 둔다
EN = json.loads((뿌리 / "catalog" / "en.json").read_text(encoding="utf-8"))
LANG = "ko"   # 지금 만드는 쪽의 화면 언어: "ko"(사이트 뿌리) 또는 "en"(docs/en/)


def T(ko: str, en: str) -> str:
    """화면 글: 한국어판이면 앞의 것, 영문판이면 뒤의 것"""
    return en if LANG == "en" else ko


def 영(s):
    """자료 값(언어 이름, 성경 갈래, CO 권 제목 등)을 영문판에서 영어로. 대조표에 없으면 그대로"""
    return EN["terms"].get(s, s) if LANG == "en" and isinstance(s, str) else s


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
    # 여는 따옴표: 글 첫머리나 빈칸·여는 괄호 뒤에 오고 바로 글자가 붙는 것, 또는 말줄임(…) 앞.
    # 나머지는 닫는 따옴표로 본다("아멘"이라는, "…하였다"(창 1:1) 처럼 뒤에 글자가 붙어도 닫는 따옴표).
    s = re.sub(r'(?:(?<=^)|(?<=[\s(\[{}“‘—·]))"(?=\S)|"(?=…)', "“", s, flags=re.M)
    return s.replace('"', "”")


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
로마 = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def 쪽값(s: str) -> int:
    """쪽 표시를 정렬용 정수로. 로마 숫자 쪽(머리말 V, VI 등)은 본문 쪽보다 앞에 오도록 -1000+값"""
    if s.isdigit():
        return int(s)
    n = 0
    for i, c in enumerate(s):
        v = 로마[c]
        n += -v if i + 1 < len(s) and 로마[s[i + 1]] > v else v
    return -1000 + n


def 쪽글(p: int) -> str:
    """정렬용 정수를 다시 쪽 표시 글로(로마 숫자 쪽 복원)"""
    if p >= 0:
        return str(p)
    n, 글 = p + 1000, ""
    for v, c in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            글, n = 글 + c, n - v
    return 글


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
        부분 = re.split(r"\{CO (\d+|[IVXLC]+)\}", 문단)
        if 부분[0].strip():
            쪽별.setdefault(현재 or "intro", []).append({"t": 부분[0].strip(), "note": 안내, "box": 상자, "cont": True})
        for i in range(1, len(부분), 2):
            현재 = 쪽값(부분[i])
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
    return {쪽값(m.group(1)): [p.strip() for p in m.group(2).strip().split("\n") if p.strip()]
            for m in re.finditer(r"⟦(\d+|[IVXLC]+)⟧\n(.*?)(?=⟦(?:\d+|[IVXLC]+)⟧|\Z)", 글, re.S)}


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
#    홈 · 성경 · 신조 · 도서(전체 도서, 주석·설교, 총서) · 시편찬송 · 저자 · 찾기 · 소개
# ------------------------------------------------------------------
메뉴 = [("", "홈", "home"), ("bible/", "성경", "bible"), ("creeds/", "신조", "creeds"), ("books/", "도서", "books"),
       ("psalter/", "시편찬송", "psalter"), ("authors/", "저자", "authors"),
       ("search/", "찾기", "search"), ("about/", "소개", "about")]
도서하위 = [("books/", "전체 도서", "books"), ("expositions/", "주석·설교", "expositions"), ("series/", "총서", "series")]
소개하위 = [("about/", "도서관 소개", "about"), ("about/principles/", "원칙", "principles"), ("about/progress/", "진행 현황", "progress"),
        ("about/news/", "소식", "news"), ("about/contribute/", "참여와 오류 제보", "contribute")]
저자이름 = {a["id"]: a for a in LIB["authors"]}
갈래이름 = {g["id"]: g["name"] for g in LIB["genres"]}
시대이름 = {x["id"]: x for x in LIB["eras"]}
책코드 = {b["abbr"]: b for b in BIBLE["books"]}
원자료 = {"SITE": SITE, "LIB": LIB, "CO": CO, "BIBLE": BIBLE, "WORKS": WORKS, "VERSIONS": VERSIONS}


def 저작영(w) -> dict:
    """저작 하나를 영문판 화면용으로 복사한다. 편 원고(제목, 본문)는 한국어 그대로 둔다"""
    x = EN["works"].get(f'{w["author_dir"]}/{w["id"]}', {})
    w2 = dict(w)
    for k in ("title", "cite_title", "summary", "orig_label", "unit", "source_short", "page_prefix"):
        if k in x:
            w2[k] = x[k]
    w2["units_word"] = x.get("units", "parts")
    w2["lang"] = 영(w.get("lang", ""))
    w2["volumes"] = [dict(v, title=x.get("volumes", {}).get(str(v["no"]), v["title"])) for v in w["volumes"]]
    return w2


def 언어설정(lang: str):
    """화면 언어를 바꾸고, 그 언어로 자료(사이트·저자·총서·성경·CO·저작)와 메뉴를 다시 짠다"""
    global LANG, SITE, LIB, CO, BIBLE, WORKS, VERSIONS, 저자이름, 갈래이름, 시대이름, 책코드, 메뉴, 도서하위, 소개하위, 상태이름
    LANG = lang
    o = 원자료
    if lang == "ko":
        SITE, LIB, CO, BIBLE, WORKS, VERSIONS = o["SITE"], o["LIB"], o["CO"], o["BIBLE"], o["WORKS"], o["VERSIONS"]
        메뉴 = [("", "홈", "home"), ("bible/", "성경", "bible"), ("creeds/", "신조", "creeds"), ("books/", "도서", "books"),
              ("psalter/", "시편찬송", "psalter"), ("authors/", "저자", "authors"),
              ("search/", "찾기", "search"), ("about/", "소개", "about")]
        도서하위 = [("books/", "전체 도서", "books"), ("expositions/", "주석·설교", "expositions"), ("series/", "총서", "series")]
        소개하위 = [("about/", "도서관 소개", "about"), ("about/principles/", "원칙", "principles"), ("about/progress/", "진행 현황", "progress"),
                ("about/news/", "소식", "news"), ("about/contribute/", "참여와 오류 제보", "contribute")]
        상태이름 = {3: "원문 대역 연결", 2: "웹 게시(한국어)", 1: "번역 원고 완료", "0x": "원고 확보 필요", 0: "예정"}
    else:
        s = EN["site"]
        SITE = dict(o["SITE"], full=s["full"], tagline=s["tagline"])
        L = o["LIB"]
        def 덧(d, k, 표):   # 사전 d 를 복사하고 표[d[k]] 의 값을 덧씌운다
            return dict(d, **표.get(d[k], {}))
        LIB = {
            "authors": [dict(덧(a, "id", EN["authors"]), lang=영(a.get("lang", ""))) for a in L["authors"]],
            "eras": [덧(x, "id", EN["eras"]) for x in L["eras"]],
            "genres": [dict(g, name=EN["genres"].get(g["id"], g["name"])) for g in L["genres"]],
            "series": [dict(sr, name=EN["series"].get(sr["id"], {}).get("name", sr["name"]),
                            desc=EN["series"].get(sr["id"], {}).get("desc", sr["desc"]),
                            branches=[덧(b, "id", EN["series"].get(sr["id"], {}).get("branches", {})) for b in sr["branches"]])
                       for sr in L["series"]],
            "news": [[d, EN["news"].get(t, t)] for d, t in L["news"]],
            "sources": [덧(x, "id", EN["sources"]) for x in L["sources"]],
        }
        CO = dict(o["CO"], volumes=[dict(v, group=영(v["group"]), title=영(v["title"]), lang=영(v["lang"]), note=영(v["note"]))
                                    for v in o["CO"]["volumes"]])
        BIBLE = dict(o["BIBLE"], note=영(o["BIBLE"]["note"]),
                     books=[dict(b, name=EN["bible_books"].get(b["code"], b["name"]), kind_ko=b["kind"], kind=영(b["kind"]),
                                 note=영(b["note"])) for b in o["BIBLE"]["books"]])
        WORKS = [저작영(w) for w in o["WORKS"]]
        VERSIONS = [dict(v, **EN["versions"].get(v["id"], {})) for v in o["VERSIONS"]]
        메뉴 = [("", "Home", "home"), ("bible/", "Bible", "bible"), ("creeds/", "Creeds", "creeds"),
              ("books/", "Books", "books"), ("psalter/", "Psalter", "psalter"), ("authors/", "Authors", "authors"),
              ("search/", "Search", "search"), ("about/", "About", "about")]
        도서하위 = [("books/", "All books", "books"), ("expositions/", "Commentaries & Sermons", "expositions"), ("series/", "Series", "series")]
        소개하위 = [("about/", "About the library", "about"), ("about/principles/", "Principles", "principles"),
                ("about/progress/", "Progress", "progress"), ("about/news/", "News", "news"),
                ("about/contribute/", "Contribute & report errors", "contribute")]
        상태이름 = {3: "Parallel original linked", 2: "On the web (Korean)", 1: "Translation draft done", "0x": "Source text needed", 0: "Planned"}
    저자이름 = {a["id"]: a for a in LIB["authors"]}
    갈래이름 = {g["id"]: g["name"] for g in LIB["genres"]}
    시대이름 = {x["id"]: x for x in LIB["eras"]}
    책코드 = {b["abbr"]: b for b in BIBLE["books"]}


def 제(n, w) -> str:
    """편 이름: '제62편' / 'Sermon 62'. work.json 의 names(예: 0 → 머리말)가 있으면 그 이름, 단위가 '§'이면 '§ 12'"""
    이름 = w.get("names", {}).get(str(n))
    if 이름:
        return T(이름[0], 이름[1]) if isinstance(이름, list) else 이름
    if w["unit"] == "§":
        return f"§ {n}"
    return T(f'제{n}{w["unit"]}', f'{w["unit"]} {n}')


def 편수(k, w) -> str:
    """편 수: '61편' / '61 sermons'"""
    if w["unit"] == "§":
        return T(f"{k}개 절", f'{k} section{"" if k == 1 else "s"}')
    return T(f'{k}{w["unit"]}', f'{k} {w["unit"].lower() if k == 1 else w.get("units_word", "parts")}')


def 장이름(이름, c) -> str:
    """'욥기 3장' / 'Job 3'"""
    return T(f"{이름} {c}장", f"{이름} {c}")


def 틀(경로: str, 제목: str, 본문: str, 현재: str = "", 빵: list = None, 서가: str = "", 설명: str = "", 하위: str = "", 하위목록: list = None) -> str:
    """경로는 언어별 사이트 뿌리 기준 상대 경로(예: 'sources/co/index.html'). 링크는 모두 상대 경로로 만든다.
    {R}: 같은 언어 사이트의 뿌리(영문판은 docs/en/), {A}: 공용 자료(assets, data, PDF, 악보)가 있는 docs/ 뿌리"""
    깊이 = 경로.count("/")
    R = "../" * 깊이
    A = R + ("../" if LANG == "en" else "")
    nav = "".join(f'<a href="{(R + h) or "./"}"{" class=on" if k == 현재 else ""}>{t}</a>' for h, t, k in 메뉴)
    빵글 = ""
    if 빵:
        빵글 = '<div class="crumb">' + " › ".join(
            (f'<a href="{R}{h}">{e(t)}</a>' if h is not None else f"<b>{e(t)}</b>") for h, t in 빵) + "</div>"
    if 하위:
        본문 = ('<nav class="subnav">' + "".join(
            f'<a href="{R}{h}"{" class=on" if k == 하위 else ""}>{t}</a>' for h, t, k in (하위목록 or 소개하위)) + "</nav>") + 본문
    본문 = 본문.replace("{R}", R).replace("{A}", A)
    서가 = 서가.replace("{R}", R).replace("{A}", A)
    배치 = (f'<div class="layout"><aside id="shelf">{서가}</aside><main>{빵글}{본문}{바닥(R)}</main></div>' if 서가
          else f'<div class="layout single"><main>{빵글}<div class="page">{본문}</div>{바닥(R)}</main></div>')
    쪽제목 = f"{제목} · {SITE['name']} {SITE['full']}" if 제목 else f"{SITE['name']} {SITE['full']}"
    # 언어 전환: 한국어판 쪽과 영문판(en/) 쪽은 경로가 1:1로 맞는다
    p = 경로[:-len("index.html")] if 경로.endswith("index.html") else 경로
    if 경로 == "404.html":   # 404 쪽은 어느 주소에서나 열리므로 절대 주소로
        b0 = SITE.get("base_url", "").rstrip("/")
        한주소, 영주소 = b0 + "/", b0 + "/en/"
    elif LANG == "en":
        한주소, 영주소 = A + p, (R + p) or "./"
    else:
        한주소, 영주소 = (R + p) or "./", R + "en/" + p
    언어단추 = (f'<div class="seg lang" role="group" aria-label="Language / 언어">'
             f'<a class="btn{" on" if LANG == "ko" else ""}" href="{한주소}" hreflang="ko" lang="ko">KOREAN</a>'
             f'<a class="btn{" on" if LANG == "en" else ""}" href="{영주소}" hreflang="en" lang="en">ENGLISH</a></div>')
    b = SITE.get("base_url", "").rstrip("/")
    대체 = (f'<link rel="alternate" hreflang="ko" href="{b}/{p}"><link rel="alternate" hreflang="en" href="{b}/en/{p}">'
          if b and 경로 != "404.html" else "")
    return f"""<!DOCTYPE html>
<html lang="{T('ko', 'en')}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(쪽제목)}</title><meta name="description" content="{e(설명 or SITE['tagline'])}">{대체}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&family=EB+Garamond:ital,wght@0,400;0,600;1,400&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<link rel="icon" href="{A}assets/icons/favicon.ico" sizes="48x48"><link rel="icon" type="image/png" sizes="32x32" href="{A}assets/icons/favicon-32x32.png"><link rel="icon" type="image/png" sizes="16x16" href="{A}assets/icons/favicon-16x16.png">
<link rel="apple-touch-icon" href="{A}assets/icons/apple-touch-icon.png"><link rel="manifest" href="{A}assets/icons/site.webmanifest"><meta name="theme-color" content="#13402b">
<link rel="stylesheet" href="{A}assets/kccl.css"></head>
<body data-root="{R}" data-assets="{A}">
<header class="top">
  {f'<button class="btn menu-btn" id="menuBtn" aria-label="{T("서가 열기", "Open shelf")}">{T("목차", "Contents")}</button>' if 서가 else ''}
  <a class="brand" href="{R or './'}">{e(SITE['name'])}<small>{e(SITE['full'])} · {T('AI 번역판', 'AI translation')}</small></a>
  <nav class="gnav">{nav}</nav>
  <div class="seg theme" role="group" aria-label="{T('색 모드', 'Color mode')}"><button class="btn" data-theme-set="light">{T('라이트', 'Light')}</button><button class="btn" data-theme-set="dark">{T('다크', 'Dark')}</button><button class="btn" data-theme-set="reading">{T('리딩', 'Reading')}</button></div>
  {언어단추}
</header>
{배치}
<div class="pop" id="pop"></div><div class="toast" id="toast"></div>
<script src="{A}assets/kccl.js"></script>
</body></html>
"""


def 바닥(R: str) -> str:
    return T(f'<footer class="foot">{e(SITE["name"])} {e(SITE["full"])} · 번역문 CC0 1.0 · AI 초벌 번역판 · 신학 감수 전 · '
             f'<a href="{R}about/principles/">원칙</a> · <a href="{R}about/contribute/">오류 제보</a> · 기준일 {기준일}</footer>',
             f'<footer class="foot">{e(SITE["name"])} {e(SITE["full"])} · Translations CC0 1.0 · AI draft translation · not yet theologically reviewed · '
             f'<a href="{R}about/principles/">Principles</a> · <a href="{R}about/contribute/">Report errors</a> · As of {기준일}</footer>')


def 막대(items) -> str:
    c, n = 집계(items), max(len(items), 1)
    return (f'<div class="bar"><i class="s3" style="width:{c[3]/n*100:.2f}%"></i>'
            f'<i class="s2" style="width:{c[2]/n*100:.2f}%"></i><i class="s1" style="width:{c[1]/n*100:.2f}%"></i></div>')


def 요약(items) -> str:
    c = 집계(items)
    if not items:
        return T("준비 중", "In preparation")
    return T(f"{c[1]+c[2]+c[3]}/{len(items)} 번역 · 웹 {c[2]+c[3]} · 대역 {c[3]}",
             f"{c[1]+c[2]+c[3]}/{len(items)} translated · web {c[2]+c[3]} · parallel {c[3]}")


def 저작주소(w) -> str:
    return f"{w['author_dir']}/{w['id']}/"


def 권표(v) -> str:
    """권 표시: CO 권수에 28을 더한 CR(Corpus Reformatorum) 권수. CO 값이 없으면 저작 안의 권 번호"""
    co = v.get("co")
    return f"CR {int(co) + 28}" if isinstance(co, int) or str(co).isdigit() else T(f'{v["no"]}권', f'Vol. {v["no"]}')


def PDF링크(w, v, 꼴="btn") -> str:
    """권별 AI 초벌 번역판 PDF 내려받기 링크. work.json 의 volumes[].pdf 에 파일 이름을 적는다"""
    f = v.get("pdf")
    if not isinstance(f, str):
        return ""
    원본 = 뿌리 / "content" / w["author"] / w["id"] / "pdf" / f
    크기 = f"{원본.stat().st_size / 1048576:.1f}MB" if 원본.exists() else ""
    쪽 = T(f'{v["pdf_pages"]}쪽, ', f'{v["pdf_pages"]:,} pages, ') if v.get("pdf_pages") else ""
    주소 = f'{{A}}{저작주소(w)}pdf/{f}'
    if 꼴 == "tag":
        return f' <a class="tag" href="{주소}" download>PDF</a>'
    if 꼴 == "mini":
        return f'<a class="dl mini" href="{주소}" download>{권표(v)} {T("PDF 내려받기", "PDF download")}</a>'
    return (f'<p><a class="btn dl" href="{주소}" download>{권표(v)} {T("PDF 내려받기", "PDF download (Korean)")}</a> '
            f'<span class="mini">{T("AI 초벌 번역판 · 신학 감수 전", "AI draft translation · not yet theologically reviewed")} · {쪽}{크기} · CC0</span></p>')


def 원전권(w, v) -> str:
    """권·저작의 원전 표시. CO 저작은 'CO n', 그 밖은 work.json 의 source_short(예: '1932년판')"""
    if w.get("source", "co") == "co":
        return f'CO {v["co"]}' if isinstance(v, dict) else "CO " + ", ".join(str(x) for x in w["co"])
    return w.get("source_short", T("원서", "Original"))


def 쪽앞뒤(w, u) -> tuple:
    """인용 표기 앞뒤: CO 저작은 ('CO 34:', ''), 그 밖은 ('원서 ', '쪽')"""
    if w.get("source", "co") == "co":
        return f'CO {u["vol"]}:', ""
    if "page_suffix" in w:   # 신조처럼 쪽이 아니라 조항 단위로 맞대는 저작: '제3항' / '§3'
        return T(w.get("page_prefix", ""), w.get("page_prefix_en", "§")), T(w["page_suffix"], "")
    return w.get("page_prefix", T("원서 ", "p. ")), T("쪽", "")


def 쪽범위(w, u) -> str:
    """머리에 보일 원전 범위: 'CO 8:543–566' 또는 '원서 77–154쪽'"""
    if w.get("source", "co") == "co":
        return f'CO {u["co"]}'
    if "range_prefix" in w:   # 예: 'Schaff 2:57–58'
        return f'{w["range_prefix"]}{u["co"]}'
    return T(f'{w.get("page_prefix", "원서 ")}{u["co"]}쪽', f'pp. {u["co"]}')


def 고지(w) -> str:
    co = w.get("source", "co") == "co"
    return T("AI로 옮긴 초벌 번역입니다. 신학 감수를 거치지 않았으니, 인용할 때는 원문("
             + ("CO 권:쪽" if co else w.get("check_label", "원서 쪽")) + ")을 확인해 주십시오.",
             "This is a draft translation made with AI and has not been theologically reviewed. When quoting, please check the original ("
             + ("CO volume:page" if co else ("the original text and the page of the source edition" if "check_label" in w else "page of the original edition")) + ").")


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


def 공개신조문서수() -> int:
    """신조 탭 문서 목록에서 공개된 편(링크가 걸리는 문서)의 수. 신조쪽()의 '있음' 판정과 같은 기준"""
    저작별 = {f'{w["author_dir"]}/{w["id"]}': w for w in WORKS}
    목록 = json.loads((뿌리 / "catalog" / "creeds.json").read_text(encoding="utf-8"))["groups"]
    return sum(1 for g in 목록 for x in g["items"]
               if (w := 저작별.get(x.get("work", ""))) is not None and x.get("no") in w["units"])


def 홈():
    it = 모든항목()
    c = 집계(it)
    # 웹에 공개된 도서 권수: 공개된 편(웹 또는 대역)이 하나라도 있는 권
    공개권 = sum(1 for w in WORKS if w.get("genre") != "catechisms" for v in w["volumes"] if any(x["s"] in (2, 3) for x in v["items"]))
    # 웹에 공개된 시편찬송 곡수: 나눠 부르는 시편은 부분마다 한 곡(장)으로 센다(시편 150편 → 186장)
    공개시편 = sum(len(x["parts"]) if x.get("parts") else 1 for x in PSALTER if x.get("verses"))
    # 웹에 공개된 신조 편수 (신조는 도서 권수에 넣지 않고 따로 센다)
    # 본문 파일(장·조항) 수가 아니라 신조 탭 「실을 문서」 목록(catalog/creeds.json)의 문서 단위로 센다.
    # 고대 교회 신경처럼 한 저작에 여러 문서가 묶이면 문서마다 하나로 세고,
    # 제2 스위스 신앙고백처럼 한 문서가 여러 파일로 나뉘어도 하나로 센다.
    공개신조 = 공개신조문서수()
    둘러보기 = [("bible/", T("성경", "Bible"), T("개역한글판 66권을 책처럼 펼쳐 읽습니다. 영어 번역본과 나란히 볼 수 있습니다.",
                                             "Read all 66 books of the Korean Revised Version laid open like a book, side by side with English translations.")),
            ("creeds/", T("신조", "Creeds"), T("신경과 신앙고백, 요리문답을 원문과 나란히 읽습니다.",
                                             "Read the creeds, confessions, and catechisms side by side with the original.")),
            ("books/", T("도서", "Books"), T("주석과 설교, 교리서, 서신, 경건 서적과 총서를 갈래·시대·원어로 골라 보고, 주석·설교는 성경 책별로 찾습니다.",
                                           "Browse commentaries, sermons, doctrinal works, letters, devotional books, and series by genre, era, and original language, and find commentaries and sermons by book of the Bible.")),
            ("psalter/", T("시편찬송", "Psalter"), T("한국어 제네바 시편가 186장(시편 150편)의 악보와 가사, 개역한글판 시편 150편입니다.",
                                                 "Scores and lyrics of the 186 tunes (150 psalms) of the Korean Genevan Psalter, and the 150 psalms of the Korean Revised Version.")),
            ("authors/", T("저자", "Authors"), T("교부부터 종교개혁자, 청교도까지 저자별로 봅니다.",
                                               "Browse by author, from the Church Fathers to the Reformers and the Puritans."))]
    카드 = "".join(f'<a class="card" href="{{R}}{h}"><h3>{t}</h3><p>{d}</p></a>' for h, t, d in 둘러보기)
    소식 = "".join(f"<tr><td>{e(d)}</td><td>{e(t)}</td></tr>" for d, t in LIB["news"][:4])
    if LANG == "en":
        본문 = f"""<div class="hero"><div class="en">{e(SITE['name'])}</div>
<div class="hero-title"><h1>{e(SITE['full'])}</h1><a class="btn" href="{{R}}about/principles/">Principles of this library</a></div>
<p class="lead">{e(SITE['tagline'])}</p>
<div class="stats">
<div class="stat"><b>{len([a for a in LIB['authors'] if a['ready']])}</b><span>authors in the library</span></div>
<div class="stat"><b>{공개권}</b><span>volumes published on the web</span></div>
<div class="stat"><b>{공개신조}</b><span>creeds published on the web</span></div>
<div class="stat"><b>{공개시편}</b><span>psalter tunes published on the web</span></div></div></div>
<div class="box">The English pages are for finding your way around the library. The translations themselves, the PDFs, and the psalter lyrics are in Korean, shown next to the original Latin, French, or Dutch text.</div>
<h2>Explore</h2><div class="cards">{카드}</div>
<h2>The current goal: the 59 volumes of Calvin's works</h2>
<p>The first goal is to translate all 59 volumes of Calvin's collected works (CO, 1863–1900), published in the nineteenth century, from the original languages into Korean. Since this will take a long time, each part is added as soon as it is finished. After that, the shelves will grow with public-domain works of other Reformers, the Church Fathers, and the Puritans.</p>
<p><a class="btn" href="{{R}}about/progress/">Progress</a></p>
<h2>Three commitments of this library</h2><div class="cards">
<div class="card"><h3>Side by side with the original</h3><p>Every translation is aligned with the original and its page in the source edition (e.g. CO 34:1), so anyone can check the original text.</p></div>
<div class="card"><h3>Open without conditions</h3><p>Only public-domain sources are used, and the translations are released under CC0 1.0. Copying, distributing, modifying, and publishing are all free.</p></div>
<div class="card"><h3>A transparent draft translation</h3><p>The draft translation was made with AI and has not yet been theologically reviewed. Error reports are received and corrected, and the corrections are recorded.</p></div></div>
<h2>News</h2><table class="t"><tr><th style="width:120px">Date</th><th>Item</th></tr>{소식}</table>
<p><a href="{{R}}about/news/">All news</a></p>"""
        쪽들["index.html"] = 틀("index.html", "", 본문, "home")
        return
    본문 = f"""<div class="hero"><div class="en">{e(SITE['en'])}</div>
<div class="hero-title"><h1>{e(SITE['name'])} {e(SITE['full'])}</h1><a class="btn" href="{{R}}about/principles/">이 도서관의 원칙</a></div>
<p class="lead">{e(SITE['tagline'])}</p>
<div class="stats">
<div class="stat"><b>{len([a for a in LIB['authors'] if a['ready']])}</b><span>도서관에 오른 저자</span></div>
<div class="stat"><b>{공개권}</b><span>웹에 공개된 도서 권수</span></div>
<div class="stat"><b>{공개신조}</b><span>웹에 공개된 신조 편수</span></div>
<div class="stat"><b>{공개시편}</b><span>웹에 공개된 시편찬송 곡수</span></div></div></div>
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
    """신조를 뺀 모든 저작: 갈래·시대·원어 거르기 (신조는 신조 탭에만 둔다)"""
    칸 = ""
    도서들 = [w for w in WORKS if w.get("genre") != "catechisms"]
    for w in 도서들:
        a = 저자이름[w["author"]]
        it = 저작항목(w)
        c = 집계(it)
        상태 = "web" if c[2] + c[3] else ("done" if c[1] else "plan")
        제목 = T(f'「{e(w["title"])}」', f'<i>{e(w["title"])}</i>')
        칸 += (f'<a class="card wk" href="{{R}}{저작주소(w)}" data-genre="{w.get("genre", "")}" data-era="{a["era"]}" '
              f'data-lang="{e(w.get("lang", ""))}" data-state="{상태}">'
              f'<div class="g">{e(a["name"])} · {e(갈래이름.get(w.get("genre"), ""))} · {e(w.get("lang", ""))}</div>'
              f'<h3>{제목}</h3><p>{e(w["summary"])}</p>{막대(it)}<span class="mini">{요약(it)}</span></a>')
    def 칩(종류, 목록):
        return (f'<div class="chips" data-filter="{종류}"><button class="btn on" data-v="">{T("전체", "All")}</button>'
                + "".join(f'<button class="btn" data-v="{e(v)}">{e(t)}</button>' for v, t in 목록) + "</div>")
    원어들 = sorted({w.get("lang", "") for w in 도서들 if w.get("lang")})
    본문 = (T('<h1>도서</h1><p class="lead">이 도서관에 오른 저작입니다(신조는 신조 탭에 따로 둡니다). 설교집과 주석, 교리서, 서신, 경건 서적을 갈래와 시대, 원어로 골라 볼 수 있습니다. 주석과 설교를 성경 책별로 찾으려면 위의 「주석·설교」를 누르십시오.</p>',
              '<h1>Books</h1><p class="lead">The works in this library (the creeds are kept separately under Creeds). Sermons, commentaries, doctrinal works, letters, and devotional books can be filtered by genre, era, and original language. The translations are in Korean. To find commentaries and sermons by book of the Bible, choose "Commentaries &amp; Sermons" above.</p>')
          + f'<div class="filters"><span>{T("갈래", "Genre")}</span>{칩("genre", [(g["id"], g["name"]) for g in LIB["genres"] if g["id"] != "catechisms"])}'
          f'<span>{T("시대", "Era")}</span>{칩("era", [(x["id"], x["name"]) for x in LIB["eras"]])}'
          f'<span>{T("원어", "Language")}</span>{칩("lang", [(x, x) for x in 원어들])}'
          f'<span>{T("상태", "Status")}</span>{칩("state", [("web", T("웹에서 읽기", "Read on the web")), ("done", T("번역 완료", "Translated")), ("plan", T("예정", "Planned"))])}</div>'
          f'<p class="mini" id="count"></p><div class="cards" id="works">{칸}</div>'
          f'<p class="mini" id="empty" hidden>{T("조건에 맞는 저작이 아직 없습니다. 서가는 번역이 끝나는 대로 늘어납니다.", "No works match these filters yet. The shelves grow as translations are finished.")}</p>')
    쪽들["books/index.html"] = 틀("books/index.html", T("도서", "Books"), 본문, "books", [("", SITE["name"]), (None, T("도서", "Books"))], 하위="books", 하위목록=도서하위)


def 저자쪽():
    본문 = T('<h1>저자</h1><p class="lead">공유 저작물로 확인된 저자를 시대 순으로 싣습니다. 아직 번역이 없는 저자는 예정으로 표시합니다.</p>',
            '<h1>Authors</h1><p class="lead">Authors whose works are confirmed to be in the public domain, in chronological order. Authors with no translations yet are marked as planned.</p>')
    for 시대 in LIB["eras"]:
        여기 = [a for a in LIB["authors"] if a["era"] == 시대["id"]]
        if not 여기:
            continue
        본문 += f'<h2>{e(시대["name"])} <span class="mini">{e(시대["range"])}</span></h2><div class="cards">'
        for a in 여기:
            저작수 = len([w for w in WORKS if w["author"] == a["id"]])
            머리 = f'<h3>{e(a["name"])} <span class="mini">{e(a["life"])}</span></h3><p>{e(a["desc"])}</p>'
            if a["ready"]:
                본문 += f'<a class="card" href="{{R}}{a["id"]}/">{머리}<span class="mini">{T(f"저작 {저작수}종", f"{저작수} work" + ("" if 저작수 == 1 else "s"))}</span></a>'
            else:
                본문 += f'<div class="card soon">{머리}</div>'
        본문 += "</div>"
    쪽들["authors/index.html"] = 틀("authors/index.html", T("저자", "Authors"), 본문, "authors", [("", SITE["name"]), (None, T("저자", "Authors"))])
    # 저자별 쪽
    for a in [x for x in LIB["authors"] if x["ready"]]:
        경로 = f'{a["id"]}/index.html'
        저작 = [w for w in WORKS if w["author"] == a["id"]]
        b = f'<h1>{e(a["name"])} <span class="mini">{e(a["life"])}</span></h1><p class="lead">{e(a["desc"])}</p>'
        for g in LIB["genres"]:
            여기 = [w for w in 저작 if w.get("genre") == g["id"]]
            if not 여기:
                continue
            b += (f'<h2>{e(g["name"])}</h2><table class="t"><tr><th>{T("저작", "Work")}</th><th style="width:90px">{T("원전", "Source")}</th>'
                  f'<th style="width:230px">{T("진행", "Progress")}</th></tr>')
            for w in 여기:
                it = 저작항목(w)
                제목 = T("「" + e(w["title"]) + "」", e(w["title"]))
                b += (f'<tr><td><a href="{{R}}{저작주소(w)}"><b>{제목}</b></a><br><span class="mini">{e(w["summary"])}</span></td>'
                      f'<td class="mini">{e(원전권(w, None))}</td><td>{막대(it)}<span class="mini">{요약(it)}</span></td></tr>')
            b += "</table>"
        쪽들[경로] = 틀(경로, a["name"], b, "authors", [("", SITE["name"]), ("authors/", T("저자", "Authors")), (None, a["name"])])


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
    # (예전 66권 목록 쪽은 쓰지 않는다. 성경 탭은 펼쳐 읽기 화면만 보인다)

    for b in BIBLE["books"]:
        책 = KRV.get(b["abbr"], {}).get("verses", {})
        장수 = max((int(k.split(":")[0]) for k in 책), default=0)
        글들 = [w for w in WORKS if b["abbr"] in w.get("bible", [])]
        남은것 = e(b["kind"]) + (" (" + e(b["note"]) + ")" if b["note"] else "")
        h = (f'<h1>{e(b["name"])}</h1><p class="lead">'
             + T(f'개역한글판 {장수}장. 칼빈 전집에 남은 것: {남은것}',
                 f'{장수} chapters in the Korean Revised Version. In Calvin\'s collected works: {남은것}') + '</p>')
        if 글들:
            h += f'<h2>{T("이 책을 다룬 저작", "Works on this book")}</h2><ul>' + "".join(
                f'<li><a href="{{R}}{저작주소(w)}">{e(저자이름[w["author"]]["name"])}, {T("「" + e(w["title"]) + "」", "<i>" + e(w["title"]) + "</i>")}</a> '
                f'<span class="mini">{요약(저작항목(w))}</span></li>' for w in 글들) + "</ul>"
        h += f'<h2>{T("장", "Chapters")}</h2><div class="grid">' + "".join(
            f'<a class="cell{" s2" if (b["abbr"], c) in 장색인 else ""}" href="{{R}}bible/{b["code"]}/{c}.html" title="{e(장이름(b["name"], c))}">{c}</a>'
            for c in range(1, 장수 + 1)) + "</div>"
        if 장색인 and any(k[0] == b["abbr"] for k in 장색인):
            h += f'<p class="mini">{T("색이 칠해진 장은 이 도서관에 그 장을 다룬 글이 있습니다.", "Shaded chapters are treated in works in this library.")}</p>'
        경로 = f'bible/{b["code"]}/index.html'
        쪽들[경로] = 틀(경로, b["name"], h, "books", [("", SITE["name"]), ("books/", T("도서", "Books")), ("expositions/", T("주석·설교", "Commentaries & Sermons")), (None, b["name"])])
        for c in range(1, 장수 + 1):
            절들 = sorted((int(k.split(":")[1]), t) for k, t in 책.items() if int(k.split(":")[0]) == c)
            본 = "".join(f'<p class="v" id="v{v}"><sup class="vn">{v}</sup>{e(t)}</p>' for v, t in 절들)
            관련 = 장색인.get((b["abbr"], c), [])
            옆 = ""
            if 관련:
                옆 = f'<h2>{T("이 장을 다룬 글", "Works on this chapter")}</h2><ul>' + "".join(
                    f'<li><a href="{{R}}{단위주소(w, u["no"])}">{e(저자이름[w["author"]]["name"])}, '
                    f'{T("「" + e(w["title"]) + "」", "<i>" + e(w["title"]) + "</i>,")} {e(제(u["no"], w))}</a> '
                    f'<span class="mini">({e(u["ref"])})</span></li>' for w, u in 관련) + "</ul>"
            앞뒤 = '<div class="pager">' + (
                f'<a href="{{R}}bible/{b["code"]}/{c-1}.html"><small>{T("이전 장", "Previous chapter")}</small>{e(장이름(b["name"], c - 1))}</a>' if c > 1 else '<span style="flex:1"></span>') + (
                f'<a class="next" href="{{R}}bible/{b["code"]}/{c+1}.html"><small>{T("다음 장", "Next chapter")}</small>{e(장이름(b["name"], c + 1))}</a>' if c < 장수 else '<span style="flex:1"></span>') + "</div>"
            h = (f'<h1>{e(장이름(b["name"], c))}</h1><p class="mini">{T("성경전서 개역한글판(1961)", "Korean Revised Version (1961), in Korean")} · '
                 f'<a href="{{R}}bible/read/#{b["code"]}/{c}">{T("책으로 펼쳐 읽기", "Open in the book reader")}</a></p>'
                 f'<div class="krvtext" lang="ko">{본}</div>{옆}{앞뒤}')
            경로 = f'bible/{b["code"]}/{c}.html'
            쪽들[경로] = 틀(경로, 장이름(b["name"], c), h, "books",
                          [("", SITE["name"]), ("books/", T("도서", "Books")), ("expositions/", T("주석·설교", "Commentaries & Sermons")), (f'bible/{b["code"]}/', b["name"]), (None, T(f"{c}장", f"Chapter {c}"))],
                          설명=T(f'{b["name"]} {c}장 개역한글판 본문', f'{b["name"]} {c}, Korean Revised Version text'))


def 성경책쪽():
    """책 모양으로 성경 읽기: 본문은 data/krv/<코드>.json 을 불러와 펼친 두 쪽에 흘려 넣는다"""
    목록 = []
    for b in BIBLE["books"]:
        절 = KRV.get(b["abbr"], {}).get("verses", {})
        목록.append({"code": b["code"], "abbr": T(b["abbr"], b["code"].title()), "name": b["name"], "t": b["testament"],
                   "ch": max((int(k.split(":")[0]) for k in 절), default=1)})
    판목록 = "".join(f'<option value="{v["id"]}">{e(v["name"])}</option>' for v in VERSIONS)
    본문 = (f'<div class="reader-bar"><select id="verSel" aria-label="{T("번역본", "Version")}">{판목록}</select>'
          f'<select id="parSel" aria-label="{T("나란히 볼 번역본", "Parallel version")}"><option value="">{T("나란히 보기: 없음", "Parallel: none")}</option>{판목록}</select>'
          f'<select id="bkSel" aria-label="{T("책", "Book")}"></select><select id="chSel" aria-label="{T("장", "Chapter")}"></select>'
          f'<div class="seg"><button class="btn" id="fsMinus">{T("가−", "A−")}</button><button class="btn" id="fsPlus">{T("가+", "A+")}</button></div>'
          f'<select id="coverSel" aria-label="{T("표지 색", "Cover color")}"></select><button class="btn" id="markBtn">{T("책갈피로 가기", "Go to bookmark")}</button>'
          f'<span class="mini">{T("절을 누르면 책갈피, 키보드 ←→나 화면 밀기로 쪽을 넘깁니다.", "Click a verse to bookmark it; turn pages with the ← → keys or by swiping.")}</span></div>'
          f'<div class="bookwrap"><div class="tabs ot" id="tabsOT"></div><div class="tabs nt" id="tabsNT"></div>'
          f'<button class="turn prev" id="prevBtn" aria-label="{T("앞 쪽", "Previous page")}">‹</button><button class="turn next" id="nextBtn" aria-label="{T("다음 쪽", "Next page")}">›</button>'
          f'<div class="pages"><div class="runhead" id="runhead"></div><div id="viewport"><div id="flow"></div></div><div class="pageno" id="pageno"></div></div></div>'
          f'<script>window.KLCCL_BOOKLIST={json.dumps(목록, ensure_ascii=False)};window.KLCCL_VERSIONS={json.dumps(VERSIONS, ensure_ascii=False)};'
          + ("window.KLCCL_DEFAULT_PAR='kjv';" if LANG == "en" else "") +
          f'</script><script src="{{A}}assets/reader.js" defer></script>')
    for 경로 in ("bible/index.html", "bible/read/index.html"):   # 예전 주소(bible/read/)도 그대로 열리게
        h = 틀(경로, T("성경", "Bible"), 본문, "bible")
        # 책 화면은 넓게 쓰도록 본문 여백 틀을 걷어 낸다
        h = h.replace('<div class="layout single"><main>', '<div class="layout single wide"><main>').replace('<div class="page">', '<div>', 1)
        쪽들[경로] = h


def 강해쪽():
    """주석·설교: 번역된 저작 카드 + 성경 책별 찾기(번역이 있는 책만 진하게)"""
    강해 = [w for w in WORKS if w.get("genre") in ("sermons", "commentaries")]
    카드 = "".join(
        f'<a class="card" href="{{R}}{저작주소(w)}"><h3>{T("「" + e(w["title"]) + "」", "<i>" + e(w["title"]) + "</i>")}</h3>'
        f'<p>{e(저자이름[w["author"]]["name"])} · {e(갈래이름.get(w["genre"], ""))}</p>'
        f'{막대(저작항목(w))}<span class="mini">{요약(저작항목(w))}</span></a>' for w in 강해)
    본문 = (T('<h1>주석·설교</h1><p class="lead">번역된 주석과 설교입니다. 성경 책으로 찾으려면 아래에서 책을 고르십시오.</p>',
              '<h1>Commentaries &amp; Sermons</h1><p class="lead">The translated commentaries and sermons (in Korean, with the original). To find them by book of the Bible, choose a book below.</p>')
          + f'<div class="cards">{카드}</div><h2>{T("성경 책별로 찾기", "Find by book of the Bible")}</h2>')
    for 약 in ("구약", "신약"):
        칸 = ""
        for b in [x for x in BIBLE["books"] if x["testament"] == 약]:
            있음 = any(b["abbr"] in w.get("bible", []) for w in 강해)
            칸 += (f'<a class="bkmini on" href="{{R}}bible/{b["code"]}/">{e(b["name"])}</a>' if 있음
                  else f'<span class="bkmini">{e(b["name"])}</span>')
        본문 += f'<h3 class="testament">{T(약, "Old Testament" if 약 == "구약" else "New Testament")}</h3><div class="bkminis">{칸}</div>'
    본문 += f'<p class="mini">{T("진한 책에 번역된 주석·설교가 있습니다. 번역이 늘면 차례로 진해집니다.", "Highlighted books have translated commentaries or sermons. More will be highlighted as translations are added.")}</p>'
    쪽들["expositions/index.html"] = 틀("expositions/index.html", T("주석·설교", "Commentaries & Sermons"), 본문, "books",
                                     [("", SITE["name"]), ("books/", T("도서", "Books")), (None, T("주석·설교", "Commentaries & Sermons"))],
                                     하위="expositions", 하위목록=도서하위)


def 신조쪽():
    """신조: 공개된 신조 저작 카드 + catalog/creeds.json 의 실을 문서 목록(공개된 편은 링크, 나머지는 예정)"""
    글들 = [w for w in WORKS if w.get("genre") == "catechisms"]
    카드 = "".join(
        f'<a class="card" href="{{R}}{저작주소(w)}"><h3>{T("「" + e(w["title"]) + "」", "<i>" + e(w["title"]) + "</i>")}</h3>'
        f'<p>{e(w["summary"])}</p>'
        f'{막대(저작항목(w))}<span class="mini">{요약(저작항목(w))}</span></a>' for w in 글들)
    본문 = T('<h1>신조</h1><p class="lead">교회가 고백해 온 신경과 신앙고백, 요리문답입니다. 공유 저작물 판본의 원문과 AI 번역을 조항 단위로 나란히 놓아, 누구나 원문을 확인할 수 있게 합니다. 번역문은 CC0입니다.</p>',
             '<h1>Creeds</h1><p class="lead">The creeds, confessions, and catechisms the church has confessed. The AI translation is set article by article beside the original text from public-domain editions, so that anyone can check the original. The translations are released under CC0.</p>')
    if 카드:
        본문 += f'<div class="cards">{카드}</div>'
    저작별 = {f'{w["author_dir"]}/{w["id"]}': w for w in WORKS}
    목록 = json.loads((뿌리 / "catalog" / "creeds.json").read_text(encoding="utf-8"))["groups"]
    본문 += f'<h2>{T("실을 문서", "Documents in this collection")}</h2>'
    for g in 목록:
        줄 = ""
        for x in g["items"]:
            w = 저작별.get(x.get("work", ""))
            있음 = w is not None and x.get("no") in w["units"]
            이름 = T(x["title"], x.get("en", x["title"]))
            제목칸 = f'<a href="{{R}}{단위주소(w, x["no"])}">{e(이름)}</a>' if 있음 else e(이름)
            상태 = (f'<span class="tag">{T("대역", "Parallel")}</span>' if 있음 and w["units"][x["no"]]["orig"]
                  else (f'<span class="tag">{T("한국어", "Korean")}</span>' if 있음 else f'<span class="mini">{T("예정", "Planned")}</span>'))
            줄 += f'<tr><td>{제목칸}</td><td>{e(T(x["year"], x.get("en_year", x["year"])))}</td><td>{e(T(x["lang"], x.get("en_lang", x["lang"])))}</td><td>{e(T(x["source"], x.get("en_source", x["source"])))}</td><td>{상태}</td></tr>'
        본문 += (f'<h3>{e(T(g["name"], g.get("en", g["name"])))}</h3><table class="t"><tr><th>{T("문서", "Document")}</th><th style="width:110px">{T("연도", "Year")}</th>'
                 f'<th style="width:150px">{T("원어", "Language")}</th><th style="width:170px">{T("저본", "Source edition")}</th><th style="width:70px">{T("상태", "Status")}</th></tr>{줄}</table>')
    본문 += T('<p class="mini">저본은 Schaff, <i>The Creeds of Christendom</i>(1877, 1919년 4판), Niemeyer, <i>Collectio confessionum</i>(1840), Müller, <i>Die Bekenntnisschriften der reformierten Kirche</i>(1903), 칼빈 전집(CO), 멜란히톤 전집(CR), 웨스트민스터 문서 초판처럼 저작권이 소멸한 판본만 씁니다. 저작권이 있는 기존 한국어 번역은 참고하지 않고 원문에서 새로 옮깁니다.</p>',
              '<p class="mini">Only public-domain editions are used: Schaff, <i>The Creeds of Christendom</i> (1877; 4th ed. 1919), Niemeyer, <i>Collectio confessionum</i> (1840), Müller, <i>Die Bekenntnisschriften der reformierten Kirche</i> (1903), Calvin\'s collected works (CO), Melanchthon\'s collected works (CR), and the first editions of the Westminster documents. Existing Korean translations under copyright are not consulted; everything is translated afresh from the original.</p>')
    쪽들["creeds/index.html"] = 틀("creeds/index.html", T("신조", "Creeds"), 본문, "creeds",
                                [("", SITE["name"]), (None, T("신조", "Creeds"))],
                                설명=T("신경과 신앙고백, 요리문답을 원문과 한국어 번역으로 나란히 읽습니다.", "Creeds, confessions, and catechisms in Korean translation side by side with the original."))


PSALTER_DIR = 뿌리 / "content" / "psalter" / "genevan"
PSALTER = (json.loads((PSALTER_DIR / "psalter.json").read_text(encoding="utf-8"))["psalms"]
           if (PSALTER_DIR / "psalter.json").exists() else [])


def 절구성(글: str) -> dict:
    """'1절=1~3절, 2절=4~5절 앞' 같은 메모를 {가사 절: '시편 1~3절'} 로 푼다"""
    결과 = {}
    # '1(성경 1~3), 2(4~6)' 또는 '1절(성경 1~3), 2절(4~6)' 꼴
    괄호 = re.findall(r"(?:^|[,=]\s*)(\d+)절?\s*\((?:성경\s*)?([^)]*)\)", 글)
    if len(괄호) >= 2:
        return {int(k): v.strip() + "절" for k, v in 괄호}
    for 조각 in re.sub(r"\([^)]*\)", "", 글).split(","):
        m = re.match(r"\s*(\d+)절\s*=\s*(.+?)\s*$", 조각)
        if m:
            결과[int(m.group(1))] = m.group(2)
    return 결과


def 시편찬송쪽():
    """시편찬송: 한국어 제네바 시편가 186장(악보 PDF, MusicXML, 가사)과 개역한글 시편"""
    시편 = next(b for b in BIBLE["books"] if b["abbr"] == "시")
    칸 = "".join(f'<a class="cell" href="{{R}}bible/{시편["code"]}/{n}.html" title="{T(f"시편 {n}편 (개역한글판)", f"Psalm {n} (Korean Revised Version)")}">{n}</a>' for n in range(1, 151))
    상태 = T("공개(AI 초벌 편역 · 신학 감수 전)", "Published (AI draft adaptation · not yet theologically reviewed)") if PSALTER else T("예정", "Planned")
    if LANG == "en":
        본문 = """<h1>Psalter</h1><p class="lead">The churches of the Reformation put the psalms into meter so that the whole congregation could sing them together. The Genevan Psalter (1562), completed in Calvin's church in Geneva, is the foremost example.</p>"""
        싣는것 = f"""<h2>Contents</h2><table class="t"><tr><th style="width:190px">Material</th><th>Description</th><th style="width:150px">Status</th></tr>
<tr><td>Korean Genevan Psalter</td><td>All 150 psalms: the Genevan tunes (1539–1562) with Claude Goudimel's four-part harmonizations (1564), set to Korean lyrics adapted in meter from the psalms of the Korean Revised Version. A score PDF and MusicXML files (for printing and for accompaniment) can be downloaded for every tune</td><td>{상태}</td></tr>
<tr><td>Original Genevan Psalter</td><td>The French metrical psalms of Marot and Beza (16th century, public domain)</td><td>Planned</td></tr>
<tr><td>Calvin's preface</td><td>Calvin's preface to the psalter (1542, 1543)</td><td>Planned</td></tr>
<tr><td>Psalm texts</td><td>The 150 psalms of the Korean Revised Version (read from each tune page or from the Bible menu)</td><td>Published</td></tr></table>
<div class="box">Most Korean psalm and hymn lyrics and arrangements used in churches today are still under copyright, so they are not included. This library includes only public-domain material such as the sixteenth-century texts and tunes, and newly translates the Korean lyrics and releases them without conditions. The melodies and harmonies were transcribed from the scores published at genevanpsalter.com; the Korean lyrics and the edited scores are released under CC0.</div>"""
    else:
        본문 = f"""<h1>시편찬송</h1><p class="lead">종교개혁 교회는 시편을 운율로 옮겨 회중이 함께 불렀습니다. 칼빈의 제네바 교회에서 완성된 「제네바 시편가」(1562)가 그 대표입니다.</p>"""
        싣는것 = f"""<h2>싣는 것</h2><table class="t"><tr><th style="width:190px">자료</th><th>내용</th><th style="width:150px">상태</th></tr>
<tr><td>한국어 제네바 시편가</td><td>제네바 곡조(1539–1562)와 클로드 구디멜의 4성부 화성(1564)에 개역한글판 시편을 운율에 맞게 편역한 가사를 붙인 186장(시편 150편). 곡마다 악보 PDF와 MusicXML(출력용·반주용)을 내려받을 수 있습니다</td><td>{상태}</td></tr>
<tr><td>제네바 시편가 원문</td><td>마로와 베자의 프랑스어 운율 시편(16세기, 공유 저작물)</td><td>예정</td></tr>
<tr><td>칼빈의 서문</td><td>시편가에 붙인 칼빈의 서문(1542·1543)</td><td>예정</td></tr>
<tr><td>시편 본문</td><td>개역한글판 시편 150편 (곡별 쪽과 성경 메뉴에서 읽기)</td><td>공개</td></tr></table>
<div class="box">오늘날 교회에서 쓰는 한국어 시편찬송가와 찬송가 가사·편곡은 대부분 저작권이 살아 있어 싣지 않습니다. 이 도서관은 16세기 원문과 곡조처럼 공유 저작물인 것만 싣고, 한국어 가사는 새로 옮겨 조건 없이 공개합니다. 선율과 화성은 genevanpsalter.com에 공개된 악보를 옮겼고, 한국어 가사와 편집 악보는 CC0로 공개합니다.</div>"""
    # 곡 목록: 긴 시편은 뜻의 단락에 따라 A, B, C … 여러 곡으로 나눈다(psalter.json 의 parts)
    곡들 = []
    for p in PSALTER:
        if p.get("parts"):
            for q in p["parts"]:
                곡들.append({"p": p, "id": q["id"], "이름": T(f'시편 {p["n"]}편 {q["label"]}', f'Psalm {p["n"]}{q["label"]}'), "표": f'{p["n"]}{q["label"]}',
                           "시작": q["start"], "절": p["verses"][q["start"]:q["start"] + q["count"]], "형제": p["parts"]})
        else:
            곡들.append({"p": p, "id": f'{p["n"]:03d}', "이름": T(f'시편 {p["n"]}편', f'Psalm {p["n"]}'), "표": str(p["n"]),
                       "시작": 0, "절": p["verses"], "형제": None})
    if PSALTER:
        격자 = "".join(f'<a class="cell" href="{{R}}psalter/{g["id"]}.html" title="{g["이름"]} · {e(g["p"]["tune"])}">{g["표"]}</a>' for g in 곡들)
        본문 += T(f"""<h2>한국어 제네바 시편가 186장 (시편 150편)</h2>
<p class="mini">번호를 누르면 악보와 가사가 열립니다. 절이 많은 긴 시편은 뜻의 단락을 따라 A, B, C …로 나누어 한 곡씩 실었습니다. 가사는 개역한글판(1961) 시편을 곡조의 음절 수에 맞게 옮긴 AI 초벌 편역판이며 신학 감수 전입니다. 악보에는 빠르기와 도돌이표를 표시하지 않았으니 가사 줄 수만큼 절을 되풀이해 부릅니다.</p>
<div class="grid">{격자}</div>""", f"""<h2>Korean Genevan Psalter, 186 tunes (150 psalms)</h2>
<p class="mini">Click a number to open the score and lyrics. Long psalms with many stanzas are divided into tunes A, B, C … following their sense units. The Korean lyrics are an AI draft adaptation of the psalms of the Korean Revised Version (1961), fitted to the syllable counts of the tunes, and have not yet been theologically reviewed. The scores show no tempo or repeat signs; repeat the tune for as many stanzas as there are lines of lyrics.</p>
<div class="grid">{격자}</div>""")
    else:
        본문 += f"""<h2>{T("시편 150편 (개역한글판)", "The 150 Psalms (Korean Revised Version)")}</h2><div class="grid">{칸}</div>"""
    본문 += 싣는것
    쪽들["psalter/index.html"] = 틀("psalter/index.html", T("시편찬송", "Psalter"), 본문, "psalter", [("", SITE["name"]), (None, T("시편찬송", "Psalter"))])
    for i, g in enumerate(곡들):
        p, gid, n = g["p"], g["id"], g["p"]["n"]
        구성 = 절구성(p.get("plan", ""))
        절들 = "".join(
            f'<div style="margin:0 0 14px"><b>{T(f"{k}절", f"Stanza {k}")}</b>'
            + (f' <span class="mini">({T("시편 ", "Ps. ")}{e(구성[k + g["시작"]])})</span>' if k + g["시작"] in 구성 else "")
            + '<br>' + "<br>".join(e(x) for x in v) + "</div>"
            for k, v in enumerate(g["절"], 1))
        쪽수 = len(list((PSALTER_DIR / "img").glob(f"ps{gid}-*.png")))
        악보 = "".join(f'<img src="{{A}}psalter/img/ps{gid}-{k}.png" alt="{g["이름"]} {T("악보", "score, page")} {k}{T("쪽", "")}" loading="{"eager" if k == 1 else "lazy"}" '
                      f'style="width:100%;max-width:820px;display:block;margin:0 auto 12px;background:#fff;border:1px solid var(--line);border-radius:6px">'
                      for k in range(1, 쪽수 + 1))
        음원 = PSALTER_DIR / "mp3" / f"ps{gid}.mp3"
        재생, 멈춤 = T("반주 재생", "Play accompaniment"), T("반주 멈춤", "Stop accompaniment")
        반주 = (f'<button class="btn" onclick="var a=document.getElementById(\'acc\');if(a.paused){{a.play();this.textContent=\'{멈춤}\'}}else{{a.pause();this.textContent=\'{재생}\'}}">{재생}</button>'
                f'<audio id="acc" preload="none" src="{{A}}psalter/mp3/ps{gid}.mp3"></audio>') if 음원.exists() else \
               f'<span class="btn" style="opacity:.45;cursor:default" title="{T("반주 음원은 준비 중입니다", "The accompaniment audio is in preparation")}">{T("반주 재생(준비 중)", "Accompaniment (in preparation)")}</span>'
        앞 = f'<a class="btn" href="{곡들[i-1]["id"]}.html">← {곡들[i-1]["이름"]}</a> ' if i > 0 else ""
        뒤 = f'<a class="btn" href="{곡들[i+1]["id"]}.html">{곡들[i+1]["이름"]} →</a>' if i < len(곡들) - 1 else ""
        나눔 = ""
        if g["형제"]:
            단추들 = " ".join((f'<b>{q["label"]}</b>' if q["id"] == gid else f'<a href="{q["id"]}.html">{q["label"]}</a>') for q in g["형제"])
            처음, 끝 = g["시작"] + 1, g["시작"] + len(g["절"])
            나눔 = T(f'<p class="mini">시편 {n}편은 {len(g["형제"])}곡으로 나누어 실었습니다: {단추들} · 이 곡은 시편 {n}편 가사의 {처음}~{끝}번째 절입니다.</p>',
                     f'<p class="mini">Psalm {n} is divided into {len(g["형제"])} tunes: {단추들} · This tune contains stanzas {처음}–{끝} of the Psalm {n} lyrics.</p>')
        if LANG == "en":
            소개 = (f'<p class="lead">{e(p["tune"])} · {e(p["meter"])}</p>'
                  + (f'<p class="mini">English title: {e(re.sub(r"(?<![A-Za-z])L(?![A-Za-z])", "LORD", p["title_en"]))}</p>' if p.get("title_en") else "")
                  + f'<p class="mini">Tune: {e(p["music"])} · Harmony: {e(p["harm"])} · Lyrics: Korean adaptation of Psalm {n} from the Korean Revised Version '
                  f'(AI draft adaptation · not yet theologically reviewed) · {len(g["절"])} stanza{"" if len(g["절"]) == 1 else "s"}</p>')
        else:
            소개 = (f'<p class="lead">{e(p["tune"])} · {e(p["meter"])}</p>'
                  f'<p class="mini">곡조: {e(p["music"])} · 화성: {e(p["harm"])} · 가사: 개역한글판 시편 {n}편 편역(AI 초벌 편역판 · 신학 감수 전) · {len(g["절"])}절</p>')
        본문 = f"""<h1>{g["이름"]}</h1>
{소개}{나눔}
<p><a class="btn dl" href="{{A}}psalter/pdf/ps{gid}.pdf">{T("악보 PDF", "Score PDF")}</a>
<a class="btn" href="{{A}}psalter/xml/ps{gid}.musicxml" download>{T("MusicXML(출력용)", "MusicXML (for printing)")}</a>
<a class="btn" href="{{A}}psalter/xml/ps{gid}_accomp.musicxml" download>{T("MusicXML(반주용, 전주·반복 포함)", "MusicXML (for accompaniment, with prelude and repeats)")}</a>
<a class="btn" href="{{R}}bible/{시편["code"]}/{n}.html">{T(f"개역한글 시편 {n}편 읽기", f"Read Psalm {n} (Korean Revised Version)")}</a></p>
<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin:28px 0 14px;padding-bottom:8px"><h2 style="margin:0;border:0;padding:0">{T("악보", "Score")}</h2>
<span style="display:flex;gap:6px;flex-wrap:wrap">{앞}<a class="btn" href="./">{T("목록", "List")}</a>{반주}{뒤}</span></div>{악보}
<h2>{T("가사", "Lyrics (Korean)")}</h2><div lang="ko" style="font-family:var(--serif);font-size:17px;line-height:1.9">{절들}</div>
"""
        쪽들[f"psalter/{gid}.html"] = 틀(f"psalter/{gid}.html", T(f'{g["이름"]} · 한국어 제네바 시편가', f'{g["이름"]} · Korean Genevan Psalter'), 본문, "psalter",
                                      [("", SITE["name"]), ("psalter/", T("시편찬송", "Psalter")), (None, g["이름"])],
                                      설명=T(f'한국어 제네바 시편가 {g["이름"]}: {p["tune"]} 곡조의 악보 PDF, MusicXML, 가사',
                                            f'Korean Genevan Psalter, {g["이름"]}: score PDF, MusicXML, and Korean lyrics for the tune {p["tune"]}'))
    # 나누기 전 주소(예: psalter/119.html)는 첫 곡으로 넘긴다
    for p in PSALTER:
        if p.get("parts"):
            첫, 표, 라 = p["parts"][0]["id"], p["n"], p["parts"][0]["label"]
            제목 = T(f"시편 {표}편", f"Psalm {표}")
            이동 = T(f"시편 {표}편 {라}로 이동", f"Go to Psalm {표}{라}")
            쪽들[f'psalter/{표:03d}.html'] = (f'<!DOCTYPE html><html lang="{T("ko", "en")}"><head><meta charset="utf-8">'
                f'<meta http-equiv="refresh" content="0; url={첫}.html"><link rel="canonical" href="{첫}.html"><title>{제목}</title></head>'
                f'<body><a href="{첫}.html">{이동}</a></body></html>')


def 찾기쪽():
    """정적 사이트용 찾기: 저작·설교 제목·구절 색인(search.json)을 브라우저에서 거른다"""
    색인 = []
    for a in LIB["authors"]:
        if a["ready"]:
            색인.append({"t": a["name"], "s": T("저자", "Author"), "u": f'{a["id"]}/'})
    for w in WORKS:
        a = 저자이름[w["author"]]["name"]
        색인.append({"t": T(f'{a}, 「{w["title"]}」', f'{a}, {w["title"]}'), "s": T("저작", "Work"), "u": 저작주소(w), "x": w["summary"]})
        for n, u in sorted(w["units"].items()):
            색인.append({"t": T(f'「{w["title"]}」 {제(n, w)} {u["title"]}', f'{w["title"]}, {제(n, w)}: {u["title"]}'),
                       "s": f'{a} · {u["ref"]} · {쪽범위(w, u)}', "u": 단위주소(w, n)})
    for b in BIBLE["books"]:
        색인.append({"t": b["name"], "s": T("성경", "Bible"), "u": f'bible/{b["code"]}/', "x": b["abbr"] + " " + 원자료["BIBLE"]["books"][BIBLE["books"].index(b)]["name"]})
    # 구절 바로 가기용 책 이름표: 한국어 약칭·이름은 늘 받고, 영문판은 영어 이름과 코드(예: job, 1sa)도 받는다
    책목록 = {b["abbr"]: b["code"] for b in 원자료["BIBLE"]["books"]} | {b["name"]: b["code"] for b in 원자료["BIBLE"]["books"]}
    if LANG == "en":
        for b in BIBLE["books"]:
            책목록[b["name"].lower()] = b["code"]
            책목록[b["code"]] = b["code"]
            책목록[b["name"].lower().replace(" ", "")] = b["code"]
            책목록[b["name"][:3].lower()] = 책목록.get(b["name"][:3].lower(), b["code"])
    본문 = (T('<h1>찾기</h1><p class="lead">저자, 저작, 설교 제목, 성경 구절로 찾습니다. 성경 구절은 "욥 16:2"나 "욥기 16"처럼 적으면 그 장으로 갑니다.</p>',
              '<h1>Search</h1><p class="lead">Search by author, work, title, or Bible reference. Type a reference such as "Job 16:2" or "Psalms 23" to go to that chapter. Titles of individual sermons and parts are in Korean.</p>')
          + f'<input class="search big" id="sq" type="search" placeholder="{T("예: 욥 16:2, 위로자, 칼빈", "e.g. Job 16:2, Calvin, Institutes")}" autofocus>'
          f'<div id="sr" class="results"></div>'
          f'<p class="mini">{T("지금은 제목과 구절 색인으로 찾습니다. 본문 전체 찾기는 번역이 늘어나면 더합니다.", "For now the search covers titles and references. Full-text search will be added as the translations grow.")}</p>'
          f'<script>window.KLCCL_SEARCH={json.dumps(색인, ensure_ascii=False)};window.KLCCL_BOOKS={json.dumps(책목록, ensure_ascii=False)};</script>')
    쪽들["search/index.html"] = 틀("search/index.html", T("찾기", "Search"), 본문, "search", [("", SITE["name"]), (None, T("찾기", "Search"))])


def 총서():
    본문 = T('<h1>총서</h1><p class="lead">총서는 저자와 갈래별로 묶어 펴내는 번역 시리즈입니다. 권마다 진행 정도를 표시합니다.</p>',
            '<h1>Series</h1><p class="lead">The series are translation collections published by author and branch. Progress is shown for each volume.</p>')
    for s in [x for x in LIB["series"] if x["id"] != "creeds"]:   # 신조는 신조 탭에만
        본문 += f"<h2>{e(s['name'])}</h2><p>{e(s['desc'])}</p>"
        for b in s["branches"]:
            vols = [(w, v) for w in WORKS if w["series"] == s["id"] and w["branch"] == b["id"] for v in w["volumes"]]
            본문 += f'<h3 style="font-family:var(--serif);margin:18px 0 4px">{T("갈래", "Branch")}: {e(b["name"])}</h3><p class="mini">{e(b["note"])}</p>'
            if not vols:
                본문 += f'<p class="mini">{T("대상 선정 중입니다.", "Works are being selected.")}</p>'
                continue
            줄 = "".join(
                f'<tr><td>{권표(v)[3:] if 권표(v).startswith("CR") else 권표(v)}</td><td><b><a href="{{R}}{저작주소(w)}">{e(v["title"])}</a></b><br>'
                f'<span class="mini">{v["from"]}–{v["to"]} ({e(편수(len(v["items"]), w))})</span>'
                f'{PDF링크(w, v, "tag")}</td><td class="mini">{e(원전권(w, v))}</td>'
                f'<td>{막대(v["items"])}<span class="mini">{요약(v["items"])}</span></td></tr>'
                for w, v in sorted(vols, key=lambda x: x[1]["no"]))
            본문 += (f'<table class="t"><tr><th style="width:64px">CR</th><th>{T("제목", "Title")}</th><th style="width:80px">{T("저본", "Source")}</th>'
                     f'<th style="width:230px">{T("진행", "Progress")}</th></tr>{줄}</table>')
    본문 += T('<div class="card soon" style="margin-top:20px"><h3>다른 총서 (예정)</h3><p>교부, 종교개혁자, 청교도의 공유 저작물로 총서를 더합니다.</p></div>',
             '<div class="card soon" style="margin-top:20px"><h3>Other series (planned)</h3><p>Series will be added with public-domain works of the Church Fathers, the Reformers, and the Puritans.</p></div>')
    쪽들["series/index.html"] = 틀("series/index.html", T("총서", "Series"), 본문, "books",
                                [("", SITE["name"]), ("books/", T("도서", "Books")), (None, T("총서", "Series"))], 하위="series", 하위목록=도서하위)


def 진행():
    it = 모든항목()
    c = 집계(it)
    범례 = "".join(f'<span><i class="cell s{k}"></i>{상태이름[k]} {c[k]}</span>' for k in (3, 2, 1, "0x", 0))
    본문 = (T(f'<h1>진행 현황</h1><p class="lead">원고 파일에서 자동으로 만든 표입니다. 기준일 {기준일}.</p>',
              f'<h1>Progress</h1><p class="lead">This table is generated automatically from the manuscript files. As of {기준일}.</p>')
          + f'<div class="legend">{범례}</div>')
    for w in WORKS:
        for v in w["volumes"]:
            본문 += f'<h2>{e(v["title"])} <span class="mini">{e(원전권(w, v))}</span></h2>'
            본문 += f'{막대(v["items"])}<div class="mini">{요약(v["items"])}</div><div class="grid">'
            for x in v["items"]:
                제목 = f'{제(x["no"], w)} {x["title"]} · {상태이름[x["s"]]}'
                if x["s"] in (2, 3):
                    본문 += f'<a class="cell s{x["s"]}" href="{{R}}{단위주소(w, x["no"])}" title="{e(제목)}">{e(x["short"])}</a>'
                else:
                    본문 += f'<span class="cell s{x["s"]}" title="{e(제목)}">{e(x["short"])}</span>'
            본문 += "</div>"
    쪽들["about/progress/index.html"] = 틀("about/progress/index.html", T("진행 현황", "Progress"), 본문, "about",
                                       [("", SITE["name"]), ("about/", T("소개", "About")), (None, T("진행 현황", "Progress"))], 하위="progress")


def 저작쪽(w):
    경로 = 저작주소(w) + "index.html"
    a = 저자이름[w["author"]]
    제목 = T("「" + e(w["title"]) + "」", "<i>" + e(w["title"]) + "</i>")
    본문 = f'<h1>{e(a["name"])}, {제목}</h1><p class="lead">{e(w["summary"])}</p>'
    if LANG == "en":
        본문 += '<p class="mini">The texts below are Korean translations, shown side by side with the original.</p>'
    for v in w["volumes"]:
        본문 += f'<h2>{권표(v)} {T("『" + e(v["title"]) + "』", "<i>" + e(v["title"]) + "</i>")} <span class="mini">{e(원전권(w, v))}</span></h2>'
        본문 += f'{막대(v["items"])}<div class="mini" style="margin-bottom:8px">{요약(v["items"])}</div>'
        본문 += PDF링크(w, v)
        공개 = [x for x in v["items"] if x["s"] in (2, 3)]
        if 공개:
            본문 += (f'<details class="units"><summary>{T("편 목록 펼치기", "Show list of parts")} <span class="mini">({T("공개", "published:")} {e(편수(len(공개), w))})</span></summary>'
                     f'<table class="t"><tr><th style="width:80px">{T("편", "No.")}</th><th>{T("제목", "Title (Korean)")}</th><th style="width:110px">{T("상태", "Status")}</th></tr>') + "".join(
                f'<tr><td>{e(제(x["no"], w))}</td><td><a href="{{R}}{단위주소(w, x["no"])}" lang="ko">{e(x["title"])}</a> ' +
                (f'<span class="mini">({e(w["units"][x["no"]]["ref"])})</span>' if w["units"][x["no"]]["ref"] else "") + '</td>' +
                f'<td><span class="tag">{T("대역", "Parallel") if x["s"] == 3 else T("한국어", "Korean")}</span></td></tr>' for x in 공개) + "</table></details>"
        남음 = [x for x in v["items"] if x["s"] not in (2, 3)]
        if 남음:
            c = 집계(남음)
            본문 += T(f'<p class="mini">웹 연결 대기 {편수(c[1], w)}, 원고 확보 필요 {편수(c["0x"], w)}, 번역 예정 {편수(c[0], w)}.</p>',
                     f'<p class="mini">Awaiting web publication: {c[1]}; source text needed: {c["0x"]}; translation planned: {c[0]}.</p>')
    신조 = w.get("genre") == "catechisms"
    쪽들[경로] = 틀(경로, T(f'「{w["title"]}」', w["title"]), 본문, "creeds" if 신조 else "books",
                  [("", SITE["name"]), ("creeds/", T("신조", "Creeds")) if 신조 else ("books/", T("도서", "Books")),
                   (f'{a["id"]}/', a["name"]), (None, w["title"])])


def 서가(w, 현재번호: int) -> str:
    a = 저자이름[w["author"]]
    h = (f'<div class="shelf"><h3>{T("저자", "Author")}</h3><div class="series"><a href="{{R}}{a["id"]}/" style="text-decoration:none">{e(a["name"])} ({e(a["life"])})</a></div>'
         f'<h3>{T("저작", "Work")}</h3>')
    h += f'<div class="series"><a href="{{R}}{저작주소(w)}" style="text-decoration:none">{T("「" + e(w["title"]) + "」", e(w["title"]))}</a></div>'
    for v in w["volumes"]:
        여기 = v["from"] <= 현재번호 <= v["to"]
        제목 = f'{권표(v)} {T("『" + e(v["title"]) + "』", e(v["title"]))} {v["from"]}–{v["to"]}'
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
            h += (f'<a href="{{R}}{단위주소(w, x["no"])}"{" class=cur" if x["no"] == 현재번호 else ""}>{e(제(x["no"], w))}'
                  f'{" <span class=tag>" + T("대역", "Parallel") + "</span>" if x["s"] == 3 else ""}<span lang="ko">{e(x["title"])}</span></a>')
        남 = len(v["items"]) - len(공개)
        if 남:
            h += f'<span class="off">{T(f"그 밖 {편수(남, w)}은 준비 중", f"{남} more in preparation")}</span>'
        h += "</nav></details>"
    return h + "</div>"


def 각주표시(s: str) -> str:
    return re.sub(r"⁣FN(\d+)⁣", lambda m: f'<sup class="fn" data-n="{m.group(1)}">{m.group(1)}</sup>', s)


def 읽기쪽(w, u):
    경로 = 단위주소(w, u["no"])
    a = 저자이름[w["author"]]
    원문있음 = bool(u["orig"])
    h = (f'<div class="tools"><div class="seg" role="group" aria-label="{T("보기 방식", "View")}">'
         f'<button class="btn" data-mode="both">{T("대역", "Parallel")}</button><button class="btn" data-mode="ko">{T("한국어", "Korean")}</button>'
         f'<button class="btn" data-mode="fr">{T("원문", "Original")}</button></div>'
         f'<div class="seg" role="group" aria-label="{T("글자 크기", "Text size")}"><button class="btn" data-fs="-1">{T("가−", "A−")}</button><button class="btn" data-fs="1">{T("가+", "A+")}</button></div>'
         f'<input class="search" id="q" type="search" placeholder="{T("이 글에서 찾기 (한국어·원문)", "Find in this text (Korean or original)")}"><span class="hits" id="hits"></span>'
         f'<button class="btn" id="copyText">{T("본문 복사", "Copy Korean text")}</button></div>')
    h += (f'<article class="reader" id="reader" data-author="{e(a["name"])}" data-cite-title="{e(w["cite_title"])}" data-no="{u["no"]}" '
          f'data-unit="{e(w["unit"])}" data-label="{e(제(u["no"], w))}" data-vol="{u["vol"]}" data-cite-pre="{e(쪽앞뒤(w, u)[0])}" data-cite-post="{쪽앞뒤(w, u)[1]}" data-site="{e(SITE["name"])}">')
    h += (f'<div class="head"><div class="no">{e(제(u["no"], w))}</div><div class="sub" lang="ko">{e(u["title"])}{" (" + e(u["ref"]) + ")" if u["ref"] else ""}</div>'
          f'<div class="co">{e(쪽범위(w, u))}</div></div>')
    책 = KRV.get(w.get("krv_book", ""), {}).get("verses", {})
    구절 = 구절목록(u["ref"], 책) if 책 else None
    칼빈본문 = (f'<div class="ko calvin"><span class="lbl">{T("칼빈이 읽은 본문 · 프랑스어에서 옮김 (Claude 번역)", "The text Calvin read · translated into Korean from the French (by Claude)")}</span>'
              f'{각주표시(e(둥근따옴표(u["box"])))}</div>')
    if not 구절 and not u["box"].strip():
        # 본문 상자가 없는 글(신조 등)은 빈 상자를 숨긴다
        h += '<div class="verse">' if u["origbox"] else '<div class="verse" style="display:none">'
    elif 구절:
        개역 = " ".join(f'<sup class="vn">{k}</sup>{e(책[k])}' for k in 구절)
        h += (f'<div class="verse"><div class="vgrid"><div class="ko krv"><span class="lbl">{T("성경 본문 · 개역한글판", "Bible text · Korean Revised Version")}</span>{개역}</div>'
              f'{칼빈본문}</div>')
    else:
        h += f'<div class="verse">{칼빈본문}'
    h += ((f'<div class="fr frbox" lang="fr"><span class="lbl">{e(w["orig_label"])}</span>{e(u["origbox"])}</div>' if u["origbox"] else "") + "</div>")
    h += ('<div class="notice">' + 고지(w)
          + ("" if 원문있음 else T(" 이 글은 아직 원문 대역이 연결되지 않았습니다.", " The parallel original text has not yet been linked for this text.")) + "</div>")
    for idx, p in enumerate(sorted(u["pages"])):
        ko = "".join(
            f'<p class="{"note " if x["note"] else ""}{"cont" if x["cont"] else ""}">{각주표시(e(둥근따옴표(x["t"])))}</p>'
            for x in u["pages"][p])
        if 원문있음:
            fr = "".join(f'<p lang="fr">{e(t)}</p>' for t in u["orig"].get(p, []))
            오른쪽 = f'<div class="fr">{"<div class=lang>" + e(w["orig_label"]) + "</div>" if idx == 0 else ""}{fr}</div>'
        else:
            오른쪽 = f'<div class="fr-missing">{T("원문 대역은 준비 중입니다.", "The parallel original text is in preparation.")}</div>' if idx == 0 else "<div class=fr></div>"
        h += (f'<section class="row" id="p{쪽글(p)}"><div class="pg">{쪽앞뒤(w, u)[0]}{쪽글(p)}{쪽앞뒤(w, u)[1]}<button data-cite="{쪽글(p)}" title="{T("인용 표기 복사", "Copy citation")}">{T("인용", "Cite")}</button></div>'
              f'<div class="ko" lang="ko">{"<div class=lang>" + T("한국어 번역", "Korean translation") + "</div>" if idx == 0 else ""}{ko}</div>{오른쪽}</section>')
    if u["notes"]:
        h += f'<div class="notes" lang="ko"><h4>{T("각주", "Notes")}</h4><ol>' + "".join(
            f'<li id="fn{k}">{e(둥근따옴표(n))}</li>' for k, n in enumerate(u["notes"], 1)) + "</ol></div>"
    장들 = 단위장들(w, u)
    if 장들:
        h += f'<div class="notes"><h4>{T("성경 본문 전체 보기", "Full Bible text")}</h4>' + " · ".join(
            f'<a href="{{R}}bible/{책코드[b]["code"]}/{c}.html">{e(장이름(책코드[b]["name"], c))}</a>' for b, c in 장들) + "</div>"
    번호들 = sorted(w["units"])
    i = 번호들.index(u["no"])
    앞 = w["units"][번호들[i - 1]] if i > 0 else None
    뒤 = w["units"][번호들[i + 1]] if i + 1 < len(번호들) else None
    h += '<div class="pager">' + (
        f'<a href="{{R}}{단위주소(w, 앞["no"])}"><small>{T("이전", "Previous")}</small>{e(제(앞["no"], w))} {e(앞["title"])}</a>' if 앞 else '<span style="flex:1"></span>') + (
        f'<a class="next" href="{{R}}{단위주소(w, 뒤["no"])}"><small>{T("다음", "Next")}</small>{e(제(뒤["no"], w))} {e(뒤["title"])}</a>' if 뒤 else '<span style="flex:1"></span>') + "</div>"
    h += "</article>"
    강해 = w.get("genre") in ("sermons", "commentaries")
    빵 = [("", SITE["name"]), ("creeds/", T("신조", "Creeds")) if w.get("genre") == "catechisms" else ("books/", T("도서", "Books"))] + ([("expositions/", T("주석·설교", "Commentaries & Sermons"))] if 강해 else []) + [
         (f'{a["id"]}/', a["name"]), (저작주소(w), w["title"]), (None, 제(u["no"], w))]
    쪽제목 = T(f'{a["name"]} 「{w["title"]}」 {제(u["no"], w)}', f'{a["name"]}, {w["title"]}, {제(u["no"], w)}')
    쪽들[경로] = 틀(경로, 쪽제목, h, "creeds" if w.get("genre") == "catechisms" else "books", 빵, 서가(w, u["no"]),
                  설명=T(f'{쪽제목} {u["title"]}' + (f'({u["ref"]})' if u["ref"] else "") + ' 한국어 번역과 원문 대역',
                        f'{쪽제목}' + (f' ({u["ref"]})' if u["ref"] else "") + ': Korean translation side by side with the original'))


def 소개쪽들():
    if LANG == "en":
        소개쪽들_영()
        return
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
<tr><td>신조</td><td>신경과 신앙고백, 요리문답입니다.</td></tr>
<tr><td>도서</td><td>이 도서관의 모든 저작입니다. 주석과 설교, 교리서, 서신, 경건 서적과 총서를 갈래, 시대, 원어로 골라 보고, 주석·설교는 성경 66권 차례로도 찾습니다.</td></tr>
<tr><td>시편찬송</td><td>한국어 제네바 시편가 186장(악보 PDF·MusicXML·가사)과 개역한글판 시편 150편입니다.</td></tr>
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
{f'<tr><td>GitHub 이슈</td><td><a href="{e(gh)}/issues" target="_blank" rel="noopener">저장소 이슈 쪽</a>에 새 글을 남겨 주십시오.</td></tr>' if gh else ''}
<tr><td>이메일</td><td>{f'<a href="mailto:{e(em)}">{e(em)}</a> 으로 보내 주십시오.' if em else '운영자 주소를 정하면 이곳에 적습니다.'}</td></tr></table>
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


def 소개쪽들_영():
    """소개 쪽 영문판"""
    빵 = lambda t: [("", SITE["name"]), ("about/", "About"), (None, t)]
    소개 = f"""<h1>About the library</h1><p class="lead">{e(SITE['name'])} ({e(SITE['full'])}) is an online library that translates Western Christian classics into Korean and makes them freely available.</p>
<h2>Why we are building it</h2><p>English readers have long had libraries where the works of the Church Fathers, the Reformers, and the Puritans can be read for free. There has been no such collection in Korean, so pastors, theological students, and church members who do not read the original languages find it hard to reach the primary sources. This library seeks to fill that gap.</p>
<h2>What makes it different</h2><table class="t"><tr><th style="width:160px">Feature</th><th>Description</th></tr>
<tr><td>Christian classics only</td><td>The library concentrates on patristic, Reformation, and Puritan works.</td></tr>
<tr><td>Direct translation</td><td>Works are translated from the original languages, not through an intermediate translation.</td></tr>
<tr><td>Scholarly page citations</td><td>The original and the translation are aligned by the page numbers of the standard edition, so they can be cited directly in papers and sermons.</td></tr>
<tr><td>Open without conditions</td><td>Translations are CC0. Not even a non-commercial condition is attached.</td></tr></table>
<h2>How the library is organized</h2><table class="t"><tr><th style="width:160px">Tab</th><th>Contents</th></tr>
<tr><td>Bible</td><td>The 66 books of the Korean Revised Version, with this library's sermons and commentaries for each book and chapter.</td></tr>
<tr><td>Creeds</td><td>The creeds, confessions, and catechisms.</td></tr>
<tr><td>Books</td><td>All the works in the library. Commentaries, sermons, doctrinal works, letters, devotional books, and series, filtered by genre, era, and original language; commentaries and sermons can also be found by the 66 books of the Bible.</td></tr>
<tr><td>Psalter</td><td>The 150 psalms of the Korean Genevan Psalter (score PDFs, MusicXML, lyrics) and the 150 psalms of the Korean Revised Version.</td></tr>
<tr><td>Authors</td><td>Authors in chronological order, with their works.</td></tr>
<tr><td>Search</td><td>Search by author, work, title, and Bible reference.</td></tr></table>
<h2>Languages</h2><p>The library is a Korean library: the translations, the PDFs, and the psalter lyrics are in Korean, alongside the original Latin, French, or Dutch. These English pages translate the menus, descriptions, and guides so that readers who do not read Korean can find their way around and locate the original texts.</p>
<h2>How it is run</h2><p>It is a static site with no sign-up, no advertising, and no donation payments. It runs simply by placing files on free hosting, so there are no operating costs. The manuscripts and site files are kept in a public repository, so anyone can download and keep them or republish them elsewhere.</p>
<h2>Affiliation</h2><p>This library is a private, non-profit project with no affiliation to any denomination, school, or foreign library.</p>"""
    원칙 = """<h1>Principles of this library</h1><p class="lead">What we include, how we translate, and on what terms we publish.</p>
<h2>What we include</h2><dl class="def">
<dt>Public domain only</dt><dd>Only works whose authors died more than 70 years ago, in editions that are themselves in the public domain, are included. Calvin's works are translated from Calvin's collected works (Ioannis Calvini Opera, 1863–1900) and sixteenth-century first editions.</dd>
<dt>What we do not use</dt><dd>Modern critical editions (Supplementa Calviniana, new collected editions, etc.), modern translations still under copyright, and introductions, covers, or e-book editions added by other sites are not used.</dd></dl>
<h2>How we translate</h2><dl class="def">
<dt>Directly from the original</dt><dd>Works are translated directly from the original (French, Latin, etc.), not through an English translation.</dd>
<dt>Page-by-page parallel text</dt><dd>The original and the translation are aligned page by page in the source edition (e.g. CO 34:n). Click "Cite" next to a page marker to copy a citation.</dd>
<dt>Style</dt><dd>Sermons are rendered in the formal Korean polite style. Bible quotations follow the Korean Revised Version (1961), whose copyright has expired.</dd>
<dt>The Scripture box at the start of a sermon</dt><dd>The Korean Revised Version text is set beside a translation of the French Bible text Calvin read when preaching. Since Calvin preaches by working through the words of the text he read, the two are best read together. The translation of Calvin's text is by Claude from the French, and the original is kept below it.</dd>
<dt>Bible versions included</dt><dd>Besides the Korean Revised Version, the Geneva Bible (1599), the King James Version, the World English Bible, and the Berean Standard Bible are included. All are public-domain texts, and the foreign-language versions are reference material for comparison. The Apocrypha (deuterocanonical books) are not included.</dd>
<dt>AI draft translation</dt><dd>Generative AI (Claude) was used for the draft translation, and it has not been reviewed by theological experts. Every translation is therefore marked "AI draft translation · not yet theologically reviewed." When quoting, please check the original (CO volume:page).</dd></dl>
<h2>Terms of use</h2><div class="box">The translations are released as a CC0 1.0 public-domain dedication. Anyone may copy, distribute, modify, and publish them without permission. Crediting the source is appreciated but not required.</div>
<h2>Corrections and records</h2><p>Error reports are received as described on the <a href="{R}about/contribute/">Contribute &amp; report errors</a> page. Corrections are recorded with edition numbers so that it is clear which edition was cited.</p>"""
    gh, em = SITE["contact"].get("github"), SITE["contact"].get("email")
    제보 = f"""<h1>Contribute &amp; report errors</h1><p class="lead">Please let us know about mistranslations, omitted sentences, awkward expressions, or wrong Bible references. You do not need theological training; a place that reads oddly is enough.</p>
<h2>How to report</h2><table class="t"><tr><th style="width:160px">Method</th><th>Details</th></tr>
{f'<tr><td>GitHub issues</td><td>Please open a new issue on the <a href="{e(gh)}/issues" target="_blank" rel="noopener">repository issues page</a>.</td></tr>' if gh else ''}
<tr><td>Email</td><td>{f'Please write to <a href="mailto:{e(em)}">{e(em)}</a>.' if em else 'The address will be given here once it is set.'}</td></tr></table>
<h2>Helpful details</h2><div class="box">Work: Calvin, Sermons on Job, Sermon 62<br>Page: CO 34:3 (copy it with the "Cite" button next to the page marker)<br>Current translation: (the sentence in question)<br>Suggestion: (a corrected sentence, if you have one)<br>Reason: (the basis in the original or why it reads oddly, briefly)</div>
<p>Reports may be written in English or Korean.</p>
<h2>Join in</h2><p>Reviews by readers of the original languages, checks of theological terminology, and research on source editions are all welcome. If you wish, your name will be recorded in the correction history.</p>"""
    소식 = '<h1>News</h1><table class="t"><tr><th style="width:120px">Date</th><th>Item</th></tr>' + "".join(
        f"<tr><td>{e(d)}</td><td>{e(t)}</td></tr>" for d, t in LIB["news"]) + "</table>"
    쪽들["about/index.html"] = 틀("about/index.html", "About", 소개, "about", 빵("About the library"), 하위="about")
    쪽들["about/principles/index.html"] = 틀("about/principles/index.html", "Principles", 원칙, "about", 빵("Principles"), 하위="principles")
    쪽들["about/contribute/index.html"] = 틀("about/contribute/index.html", "Contribute & report errors", 제보, "about", 빵("Contribute & report errors"), 하위="contribute")
    쪽들["about/news/index.html"] = 틀("about/news/index.html", "News", 소식, "about", 빵("News"), 하위="news")


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
    # 파비콘: 브라우저가 기본으로 찾는 /favicon.ico 자리에도 둔다
    shutil.copy2(뿌리 / "assets" / "icons" / "favicon.ico", 출력 / "favicon.ico")
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


def 모든쪽():
    홈(); 서가쪽(); 저자쪽(); 총서(); 성경쪽(); 강해쪽(); 신조쪽(); 성경책쪽(); 시편찬송쪽(); 찾기쪽(); 진행(); 소개쪽들()
    for w in WORKS:
        저작쪽(w)
        for n in sorted(w["units"]):
            읽기쪽(w, w["units"][n])


if __name__ == "__main__":
    # 1) 한국어판: docs/ 뿌리
    언어설정("ko")
    모든쪽()
    if "--one" in sys.argv:
        미리보기한장()
    한국어쪽 = dict(쪽들)
    # 2) 영문판: docs/en/. 화면 글(메뉴, 안내, 표제)만 영어이고, 번역 원고·PDF·악보·성경 자료는 한국어판과 같은 파일을 함께 쓴다
    쪽들.clear()
    언어설정("en")
    모든쪽()
    영문쪽 = {"en/" + k: v for k, v in 쪽들.items()}
    쪽들.clear()
    쪽들.update(한국어쪽)
    쪽들.update(영문쪽)
    언어설정("ko")
    쓰기()
    공개 = sum(len(w["units"]) for w in WORKS)
    print(f"완료: 쪽 {len(쪽들)}개(한국어 {len(한국어쪽)}, 영어 {len(영문쪽)}), 웹 공개 {공개}편, 출력 {출력}")
