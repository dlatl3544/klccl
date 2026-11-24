# 권별 PDF 표지에 "CR nn (CO nn)" 네모 상자를 덧찍는다
# 사용: python3 pdf_cr_box.py 원본.pdf 출력.pdf <CO 권수>
import subprocess, sys, tempfile
from pathlib import Path
from pypdf import PdfReader, PdfWriter

원본, 출력, co = sys.argv[1], sys.argv[2], int(sys.argv[3])
표시 = f"CR {co + 28} (CO {co})"
r = PdfReader(원본)
w_pt = float(r.pages[0].mediabox.width); h_pt = float(r.pages[0].mediabox.height)
# 표지 제목 위(위에서 175pt 지점)에 가운데 맞춰 상자를 놓는다
tex = rf"""\documentclass{{article}}
\usepackage[paperwidth={w_pt}bp,paperheight={h_pt}bp,margin=0pt]{{geometry}}
\usepackage{{fontspec}}\setmainfont{{Noto Serif CJK KR}}
\usepackage{{tikz}}\pagestyle{{empty}}
\begin{{document}}\begin{{tikzpicture}}[remember picture,overlay]
\node[draw=black!80,line width=0.6pt,inner xsep=9pt,inner ysep=5pt,font=\fontsize{{11}}{{13}}\selectfont]
  at ([yshift=-175bp]current page.north) {{{표시}}};
\end{{tikzpicture}}\end{{document}}"""
with tempfile.TemporaryDirectory() as d:
    Path(d, "o.tex").write_text(tex, encoding="utf-8")
    for _ in range(2):
        subprocess.run(["xelatex", "-interaction=nonstopmode", "o.tex"], cwd=d, capture_output=True, check=True)
    덧 = PdfReader(Path(d, "o.pdf")).pages[0]
    wr = PdfWriter(clone_from=r)
    wr.pages[0].merge_page(덧)
    wr.write(출력)
print("완료:", 출력, 표시)
