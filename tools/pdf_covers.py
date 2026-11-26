# -*- coding: utf-8 -*-
"""
권별 PDF에 KLCCL 표지를 붙인다.

  1면  겉표지(남색 천 장정, 표지 시안 B)
  2면  공백
  3면  내표지(백지·금색 띠, 표지 시안 A)  ← 원래 1면(옛 표지)을 이것으로 바꾼다
  4면~ 원래 2면부터 그대로(차례 링크와 책갈피는 원래 쪽을 가리키므로 그대로 작동)

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
자료 = json.loads((뿌리 / "tools" / "pdf_covers.json").read_text(encoding="utf-8"))["covers"]
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
    큰 = min(제목크기(x, 48, 420) for x in c["title_b"])
    제목 = "<br>".join(e(x) for x in c["title_b"])
    부제 = "<br>".join(e(x) for x in c["sub"])
    return f"""<div class="pg serif" style="background:#1f2a44;padding:28px">
<div style="width:100%;height:100%;box-sizing:border-box;border:1px solid #c9a96a;padding:6px">
<div style="width:100%;height:100%;box-sizing:border-box;border:1px solid #6f6a5c;padding:40px 30px 34px;display:flex;flex-direction:column;align-items:center;text-align:center">
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


def 표지pdf(c, 출력: Path, 브라우저):
    """겉표지·내표지 두 쪽짜리 PDF"""
    글 = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{공통css}</style></head><body>{겉표지(c)}{내표지(c)}</body></html>'
    h = 출력.with_suffix(".html")
    h.write_text(글, encoding="utf-8")
    p = 브라우저.new_page()
    p.goto(h.as_uri())
    p.wait_for_timeout(300)
    p.pdf(path=str(출력), width="148mm", height="210mm", print_background=True)
    p.close()
    h.unlink()


def 붙이기(원본: Path, 표지: Path, 새것: Path) -> int:
    """1면 겉표지, 2면 공백, 3면 내표지(옛 1면을 대신), 그 뒤는 원래 2면부터"""
    pdf = pikepdf.open(원본)
    t = pikepdf.open(표지)
    상자 = pdf.pages[0].mediabox
    옛표지 = pdf.pages[0]
    pdf.pages.insert(0, t.pages[0])                                   # 겉표지
    빈쪽 = pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=상자, Resources=pikepdf.Dictionary()))
    pdf.pages.insert(1, 빈쪽)                                          # 공백
    pdf.pages.insert(2, t.pages[1])                                   # 내표지
    옛번호 = pdf.pages[3].obj.objgen
    pdf.pages.remove(pdf.pages[3])                                    # 옛 표지
    # 옛 표지를 가리키던 곳(이름 붙은 목적지 Doc-Start·cover.0·page.1, 문서 열 때 첫 화면)은 새 겉표지로 옮긴다
    새첫쪽 = pdf.pages[0].obj
    def 옮김(d):
        if isinstance(d, pikepdf.Dictionary):
            d = d.get("/D")
        if isinstance(d, pikepdf.Array) and len(d) and getattr(d[0], "objgen", None) == 옛번호:
            d[0] = 새첫쪽
    if "/Names" in pdf.Root and "/Dests" in pdf.Root.Names:
        for _, v in pikepdf.NameTree(pdf.Root.Names.Dests).items():
            옮김(v)
    if "/OpenAction" in pdf.Root:
        옮김(pdf.Root.OpenAction)
    for i in (0, 2):                                                  # 표지 쪽 크기를 본문과 같게
        pdf.pages[i].mediabox = 상자
    n = len(pdf.pages)
    pdf.save(새것)
    return n


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
        for i, c in enumerate(자료):
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
