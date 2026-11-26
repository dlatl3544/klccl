# -*- coding: utf-8 -*-
"""
권별 PDF에 KLCCL 표지를 붙인다.

  1면  겉표지(천 장정 꼴, 바탕색은 저자별: 칼빈 남색, 스킬더 포도주색)
  2면  공백
  3면  내표지(백지·금색 띠)  ← 조판본의 1면(옛 표지)을 이것으로 바꾼다
  4면~ 조판본 2면부터 그대로(차례 링크와 책갈피는 원래 쪽을 가리키므로 그대로 작동)
  끝   공백 · 펴낸 곳 정보 · 공백 · 뒷표지(겉표지와 같은 색)

이미 KLCCL 표지가 붙은 PDF에 다시 돌리면, 전에 붙인 쪽을 떼고 새로 붙인다.

  python tools/pdf_covers.py              # tools/pdf_covers.json 의 모든 권
  python tools/pdf_covers.py --check      # 표지만 covers_preview.pdf 로 만들어 본다

필요한 것: playwright(chromium), pikepdf, 글꼴 Noto Serif/Sans CJK KR(시스템),
EB Garamond(선택: 환경변수 EB_GARAMOND_DIR 에 woff2 폴더. 없으면 명조 글꼴로 대신)
새 PDF 파일 이름 앞머리는 한국 시각 yymmddhhmm_ 으로 바꾸고, work.json 의 pdf, pdf_pages 도 고친다.
"""
import glob
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pikepdf
from playwright.sync_api import sync_playwright

뿌리 = Path(__file__).resolve().parent.parent
설정 = json.loads((뿌리 / "tools" / "pdf_covers.json").read_text(encoding="utf-8"))
자료 = 설정["covers"]
저자색 = 설정["authors"]
KST = timezone(timedelta(hours=9))
e = lambda s: html.escape(str(s), quote=True)

EB = os.environ.get("EB_GARAMOND_DIR", "")
글꼴 = ""
if EB and Path(EB).exists():
    for 굵기, 꼴, 파일 in ((400, "normal", "eb-garamond-latin-400-normal.woff2"), (400, "italic", "eb-garamond-latin-400-italic.woff2"),
                         (500, "normal", "eb-garamond-latin-500-normal.woff2")):
        글꼴 += f"@font-face{{font-family:'EB Garamond';font-weight:{굵기};font-style:{꼴};src:url('file://{EB}/{파일}') format('woff2')}}\n"

공통css = 글꼴 + """
@page{size:148mm 210mm;margin:0}
html,body{margin:0;padding:0;word-break:keep-all}
.pg{width:148mm;height:210mm;overflow:hidden;page-break-after:always;box-sizing:border-box;position:relative}
.serif{font-family:'Noto Serif CJK KR','Noto Serif KR',serif}
.sans{font-family:'Noto Sans CJK KR','Noto Sans KR',sans-serif}
.lat{font-family:'EB Garamond','Noto Serif CJK KR',serif}
"""


def 제목크기(t: str, 기본: int, 폭: int) -> int:
    """한 줄 제목이 폭 안에 들도록 글자 크기를 줄인다(한글 한 자 ≈ 1em, 빈칸 ≈ 0.3em)"""
    너비 = sum(0.3 if c == " " else (0.62 if c.isascii() else 1.0) for c in t)
    return int(min(기본, 폭 / max(너비, 1)))


def 겉표지(c) -> str:
    색 = 저자색[c["author_id"]]
    큰 = min(제목크기(x, 48, 420) for x in c["title_b"])
    제목 = "<br>".join(e(x) for x in c["title_b"])
    부제 = "<br>".join(e(x) for x in c["sub"])
    return f"""<div class="pg serif" style="background:{색["bg"]};padding:28px">
<div style="width:100%;height:100%;box-sizing:border-box;border:1px solid #c9a96a;padding:6px">
<div style="width:100%;height:100%;box-sizing:border-box;border:1px solid {색["line"]};padding:40px 30px 34px;display:flex;flex-direction:column;align-items:center;text-align:center">
<div class="sans" style="font-size:12px;letter-spacing:.2em;color:#d8c08e">{e(c["series"])}</div>
<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center">
<div class="lat" style="font-size:15px;letter-spacing:.24em;color:#d8c08e">{e(c["badge_b"])}</div>
<div style="width:56px;height:1px;background:#c9a96a;margin:22px 0 26px"></div>
<div style="font-size:{큰}px;font-weight:700;color:#f3ead8;letter-spacing:-.02em;line-height:1.25">{제목}</div>
<div style="margin-top:18px;font-size:{16 if len(c["sub"]) > 1 else 17}px;line-height:1.6;color:#e2d8c4">{부제}</div>
<div style="width:56px;height:1px;background:#c9a96a;margin:26px 0 22px"></div>
<div class="lat" style="font-style:italic;font-size:16px;color:#cfc6b4">{e(c["latin"])}</div>
<div style="margin-top:26px;font-size:15px;color:#f3ead8">{e(c["author"])}</div>
<div class="sans" style="margin-top:10px;font-size:12px;color:#d8c08e;letter-spacing:.04em">AI 초벌 번역판 · 신학 감수 전</div>
</div>
<div style="display:flex;flex-direction:column;align-items:center;gap:6px">
<div style="font-size:22px;font-weight:700;letter-spacing:.34em;padding-left:.34em;color:#e5cd97">KLCCL</div>
<div class="sans" style="font-size:11px;color:#bdb4a2;letter-spacing:.06em">한국어 기독교 고전 도서관 · klccl.org</div>
</div></div></div></div>"""


def 내표지(c) -> str:
    큰 = 제목크기(c["title"], 46, 440)
    부제 = "<br>".join(e(x) for x in c["sub"])
    return f"""<div class="pg serif" style="background:#fffdf8;padding:56px 52px 44px;display:flex;flex-direction:column;align-items:center;color:#2b2620">
<div class="sans" style="font-size:12px;letter-spacing:.18em;color:#7a6a52">{e(c["series"])}</div>
<div style="width:100%;margin-top:14px;border-top:1px solid #a67c3d;border-bottom:1px solid #a67c3d;height:3px"></div>
<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center">
<div style="background:#a67c3d;color:#fffdf8;font-size:13px;letter-spacing:.06em;padding:7px 16px">{e(c["badge"])}</div>
<div style="margin-top:30px;font-size:{큰}px;font-weight:700;letter-spacing:-.02em;line-height:1.25">{e(c["title"])}</div>
<div style="margin-top:14px;font-size:{16 if len(c["sub"]) > 1 else 17}px;line-height:1.6;color:#4a4036">{부제}</div>
<div class="lat" style="margin-top:22px;font-style:italic;font-size:16px;color:#6b5f52">{e(c["latin"])}</div>
<div style="margin-top:30px;font-size:15px">{e(c["author"])}</div>
<div class="sans" style="margin-top:10px;font-size:12px;color:#8a6430;letter-spacing:.04em">AI 초벌 번역판 · 신학 감수 전</div>
</div>
<div style="width:100%;font-size:10.5px;line-height:1.6;color:#6b5f52;text-align:center;margin-bottom:16px">저본 · {e(c["source"])}</div>
<div style="width:100%;border-top:1px solid #e6ddcc;padding-top:18px;display:flex;flex-direction:column;align-items:center;gap:6px">
<div style="font-size:24px;font-weight:700;letter-spacing:.32em;padding-left:.32em">KLCCL</div>
<div class="sans" style="font-size:11px;color:#7a6a52;letter-spacing:.06em">한국어 기독교 고전 도서관 · klccl.org</div>
</div></div>"""


def 판권(c, 펴낸날: str) -> str:
    """펴낸 곳 정보 쪽(판권면). 아래쪽에 모아 둔다"""
    줄 = [("총서", c["series"]), ("지은이", 저자색[c["author_id"]]["name"]),
         ("옮김", "AI 초벌 번역(Claude) · 신학 감수 전"), ("저본", c["source"]),
         ("펴낸 날", f"{펴낸날} (이 판)"), ("펴낸 곳", "KLCCL 한국어 기독교 고전 도서관"),
         ("누리집", "https://klccl.org"), ("오류 제보", "klccl.org@gmail.com"),
         ("이용 조건", "번역문은 CC0 1.0 퍼블릭 도메인으로 공개합니다. 누구나 허락 없이 복제, 배포, 수정, 출판할 수 있습니다.")]
    표 = "".join(f'<tr><td style="width:64px;vertical-align:top;padding:4px 10px 4px 0;color:#7a6a52;white-space:nowrap">{e(k)}</td>'
                f'<td style="vertical-align:top;padding:4px 0;color:#2b2620">{e(v)}</td></tr>' for k, v in 줄)
    부제 = " · ".join(c["sub"])
    return f"""<div class="pg serif" style="background:#fffdf8;padding:60px 56px 56px;display:flex;flex-direction:column;justify-content:flex-end">
<div style="font-size:17px;font-weight:700;color:#2b2620">{e(c["title"])}</div>
<div style="margin-top:4px;font-size:12.5px;color:#4a4036">{e(부제)}</div>
<div style="margin:16px 0 12px;border-top:1px solid #a67c3d;border-bottom:1px solid #a67c3d;height:3px"></div>
<table style="border-collapse:collapse;font-size:11.5px;line-height:1.6">{표}</table>
<div style="margin-top:16px;border-top:1px solid #e6ddcc;padding-top:14px;display:flex;justify-content:space-between;align-items:baseline">
<span style="font-size:16px;font-weight:700;letter-spacing:.3em">KLCCL</span>
<span class="sans" style="font-size:10.5px;color:#7a6a52">AI 초벌 번역판 · 신학 감수 전</span></div>
</div>"""


def 뒷표지(c) -> str:
    색 = 저자색[c["author_id"]]
    return f"""<div class="pg serif" style="background:{색["bg"]};padding:28px">
<div style="width:100%;height:100%;box-sizing:border-box;border:1px solid #c9a96a;padding:6px">
<div style="width:100%;height:100%;box-sizing:border-box;border:1px solid {색["line"]};padding:48px 40px 34px;display:flex;flex-direction:column;align-items:center;text-align:center">
<div class="sans" style="font-size:12px;letter-spacing:.2em;color:#d8c08e">{e(c["series"])}</div>
<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center">
<div style="font-size:20px;font-weight:700;color:#f3ead8">{e(c["title"])}</div>
<div style="width:56px;height:1px;background:#c9a96a;margin:20px 0 22px"></div>
<div style="font-size:14px;line-height:1.95;color:#e9e0cd;text-align:left;max-width:360px">{e(c["blurb"])}</div>
<div style="width:56px;height:1px;background:#c9a96a;margin:24px 0 18px"></div>
<div class="sans" style="font-size:11.5px;line-height:1.8;color:#d8c08e">AI 초벌 번역판 · 신학 감수 전<br>번역문 CC0 1.0 · 누구나 조건 없이 쓸 수 있습니다</div>
</div>
<div style="display:flex;flex-direction:column;align-items:center;gap:6px">
<div style="font-size:22px;font-weight:700;letter-spacing:.34em;padding-left:.34em;color:#e5cd97">KLCCL</div>
<div class="sans" style="font-size:11px;color:#c9bfae;letter-spacing:.06em">한국어 기독교 고전 도서관 · klccl.org</div>
</div></div></div></div>"""


def 표지pdf(c, 출력: Path, 브라우저):
    """겉표지·내표지·판권·뒷표지 네 쪽짜리 PDF"""
    펴낸날 = datetime.now(KST).strftime("%Y년 %-m월 %-d일")
    글 = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{공통css}</style></head><body>'
          f'{겉표지(c)}{내표지(c)}{판권(c, 펴낸날)}{뒷표지(c)}</body></html>')
    h = 출력.with_suffix(".html")
    h.write_text(글, encoding="utf-8")
    p = 브라우저.new_page()
    p.goto(h.as_uri())
    p.wait_for_timeout(300)
    p.pdf(path=str(출력), width="148mm", height="210mm", print_background=True)
    p.close()
    h.unlink()


표시 = pikepdf.Name("/KLCCLPage")   # 이 도구가 붙인 쪽에 다는 표시(다시 돌릴 때 떼어 내려고)


def 붙이기(원본: Path, 표지: Path, 새것: Path) -> int:
    """앞: 겉표지·공백·내표지 / 뒤: 공백·판권·공백·뒷표지"""
    pdf = pikepdf.open(원본)
    t = pikepdf.open(표지)
    # 1) 떼어 낼 쪽: 전에 이 도구가 붙인 쪽(표시가 있는 쪽). 표시가 없으면 조판본의 1면(옛 표지).
    #    2026-11-26 첫 판은 표시 없이 앞 세 쪽(겉표지·공백·내표지)만 붙였으므로, 1면에 KLCCL 글자가 있고 3면에도 있으면 그 세 쪽을 뗀다.
    떼기 = [i for i, pg in enumerate(pdf.pages) if 표시 in pg.obj]
    if not 떼기:
        떼기 = [0, 1, 2] if 옛판(원본) else [0]
    상자 = pdf.pages[max(떼기) + 1 if max(떼기) + 1 < len(pdf.pages) else 0].mediabox
    없앨번호 = {pdf.pages[i].obj.objgen for i in 떼기}
    for i in sorted(떼기, reverse=True):
        del pdf.pages[i]

    def 빈쪽():
        return pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=상자, Resources=pikepdf.Dictionary()))

    앞 = [t.pages[0], 빈쪽(), t.pages[1]]
    for i, pg in enumerate(앞):
        pdf.pages.insert(i, pg)
    for pg in (빈쪽(), t.pages[2], 빈쪽(), t.pages[3]):
        pdf.pages.append(pg)
    n = len(pdf.pages)
    for i in (0, 1, 2, n - 4, n - 3, n - 2, n - 1):
        pdf.pages[i].mediabox = 상자
        pdf.pages[i].obj[표시] = True
    # 2) 떼어 낸 쪽을 가리키던 목적지(Doc-Start, cover.0, page.1)와 문서 열기 동작은 새 겉표지로
    새첫쪽 = pdf.pages[0].obj

    def 옮김(d):
        if isinstance(d, pikepdf.Dictionary):
            d = d.get("/D")
        if isinstance(d, pikepdf.Array) and len(d) and getattr(d[0], "objgen", None) in 없앨번호:
            d[0] = 새첫쪽
    if "/Names" in pdf.Root and "/Dests" in pdf.Root.Names:
        for _, v in pikepdf.NameTree(pdf.Root.Names.Dests).items():
            옮김(v)
    if "/OpenAction" in pdf.Root:
        옮김(pdf.Root.OpenAction)
    pdf.save(새것)
    return n


def 옛판(원본: Path) -> bool:
    """표시 없이 앞 세 쪽만 붙였던 첫 판인가: 1면과 3면 글에 KLCCL이 있으면 그렇다"""
    import subprocess
    글 = lambda k: subprocess.run(["pdftotext", "-f", str(k), "-l", str(k), str(원본), "-"], capture_output=True, text=True).stdout
    return "KLCCL" in 글(1) and "KLCCL" in 글(3)


def 시각() -> str:
    return datetime.now(KST).strftime("%y%m%d%H%M")


def main():
    판 = 시각()
    작업 = Path("/tmp/klccl_covers")
    작업.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        if "--check" in sys.argv:
            모두 = pikepdf.new()
            for i, c in enumerate(자료):
                f = 작업 / f"c{i}.pdf"
                표지pdf(c, f, b)
                모두.pages.extend(pikepdf.open(f).pages)
            모두.save(뿌리 / "covers_preview.pdf")
            print("covers_preview.pdf")
            return
        골라 = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
        for i, c in enumerate(자료):
            # --only 글자: pdf 경로에 그 글자가 있는 항목만 처리
            if 골라 and 골라 not in c["pdf"]:
                continue
            찾음 = glob.glob(str(뿌리 / c["pdf"]))
            assert len(찾음) == 1, (c["pdf"], 찾음)
            원본 = Path(찾음[0])
            f = 작업 / f"c{i}.pdf"
            표지pdf(c, f, b)
            새이름 = re.sub(r"^\d{10}_", 판 + "_", 원본.name)
            새것 = 원본.with_name(새이름)
            n = 붙이기(원본, f, 작업 / 새이름)
            # 같은 PDF를 쓰는 다른 저작 폴더(예: 욥기 3권과 히스기야·이사야 합본)에도 같은 파일을 둔다
            폴더들 = [원본.parent] + ([뿌리 / c["also"]] if c.get("also") else [])
            for 폴더 in 폴더들:
                옛 = 폴더 / 원본.name
                (폴더 / 새이름).write_bytes((작업 / 새이름).read_bytes())
                if 옛.exists() and 옛.name != 새이름:
                    옛.unlink()
                wj = 폴더.parent / "work.json"
                글 = wj.read_text(encoding="utf-8")
                w = json.loads(글)
                for v in w["volumes"]:
                    if v.get("pdf") == 원본.name:
                        글 = 글.replace(f'"{원본.name}"', f'"{새이름}"')
                        글 = re.sub(rf'("pdf": "{re.escape(새이름)}",\s*"pdf_pages": )\d+', rf"\g<1>{n}", 글)
                wj.write_text(글, encoding="utf-8")
            print(f"{새이름}: {n}쪽")
        b.close()


if __name__ == "__main__":
    main()
