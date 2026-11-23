# -*- coding: utf-8 -*-
"""
개역한글판 전체 본문 CSV를 사이트용 책별 파일(catalog/krv/<약칭>.json)로 나누는 스크립트

  python tools/krv_from_csv.py 개역한글판.csv

CSV 열: book, book2(책 이름), chapter, name, content(한 장 전체. 줄마다 "절번호 본문"), URL
"""
import csv
import json
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

뿌리 = Path(__file__).resolve().parent.parent
목록 = json.loads((뿌리 / "catalog" / "bible.json").read_text(encoding="utf-8"))["books"]
약칭 = {b["name"]: b["abbr"] for b in 목록}
약칭["예레미야애가"] = "애"   # CSV는 붙여 쓴 이름을 쓴다


def main(경로: str):
    책들 = OrderedDict()
    with open(경로, encoding="utf-8-sig", newline="") as f:
        for 행 in csv.DictReader(f):
            이름, 장 = 행["book2"].strip(), int(행["chapter"])
            for 줄 in 행["content"].splitlines():
                m = re.match(r"^(\d+)\s+(.*)$", 줄.strip())
                if m:
                    책들.setdefault(이름, {})[f"{장}:{int(m.group(1))}"] = m.group(2).strip()
    # 절 번호가 비는 장이 있는지 점검
    for 이름, 절들 in 책들.items():
        장별 = defaultdict(list)
        for k in 절들:
            c, v = map(int, k.split(":"))
            장별[c].append(v)
        for c, l in 장별.items():
            if sorted(l) != list(range(1, max(l) + 1)):
                print(f"경고: {이름} {c}장 절 번호가 비어 있음")
    폴더 = 뿌리 / "catalog" / "krv"
    폴더.mkdir(parents=True, exist_ok=True)
    for 이름, 절들 in 책들.items():
        a = 약칭[이름]
        (폴더 / f"{a}.json").write_text(json.dumps(
            {"book": 이름, "abbr": a, "version": "성경전서 개역한글판(1961)",
             "note": "저작재산권 소멸(대한성서공회 공지: 2011.12.31).", "verses": 절들},
            ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(책들)}권, {sum(len(v) for v in 책들.values())}절 저장")


if __name__ == "__main__":
    main(sys.argv[1])
