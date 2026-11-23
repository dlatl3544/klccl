# KCCL 한국어 기독교 고전 도서관

저작권이 소멸한 기독교 고전을 원문과 한국어 번역으로 나란히 읽는 무료 공개 도서관의 원본 저장소입니다.
번역문은 CC0 1.0으로 공개합니다.

## 폴더 구조

| 폴더·파일 | 내용 |
|---|---|
| site.json | 사이트 이름, 소개 문구, 주소(base_url), 연락처. 이름이나 도메인이 바뀌면 여기만 고칩니다. |
| catalog/library.json | 저자, 총서와 갈래, 소식 |
| catalog/co.json | 칼빈 전집(CO) 1–59권 지도 |
| catalog/bible.json | 성경 66권별 주석·설교 대조 |
| content/저자/저작/work.json | 저작 정보(제목, 권 구성, CO 권, 오프라인 번역 범위) |
| content/저자/저작/ko/NNN.txt | 한국어 원고 |
| content/저자/저작/orig/NNN.txt | 원문(⟦n⟧ 쪽 표시) |
| assets/ | 공통 스타일과 스크립트 |
| build.py | 사이트 생성 스크립트 |
| docs/ | 생성된 사이트. GitHub Pages가 이 폴더를 게시합니다. 직접 고치지 않습니다. |

## 번역을 더할 때

1. 원고를 `content/calvin/job-sermons/ko/` 에 넣습니다(예: 072.txt).
2. 원문이 있으면 `content/calvin/job-sermons/orig/` 에 같은 이름으로 넣습니다.
3. `python build.py` 를 실행합니다.
4. 바뀐 내용을 GitHub에 올립니다.

홈 숫자, 총서 표, CO 지도, 성경별, 진행 현황은 원고 파일을 보고 자동으로 다시 계산됩니다.

## 새 저작을 더할 때

`content/calvin/<저작이름>/work.json` 을 만듭니다. `content/calvin/job-sermons/work.json` 을 본떠 쓰면 됩니다.

## 처음 공개하는 법 (GitHub Pages, 무료)

1. GitHub에 무료 계정을 만들고 새 공개 저장소(예: kccl)를 만듭니다.
2. 이 폴더 전체를 그 저장소에 올립니다.
3. 저장소 Settings → Pages → Branch 를 main, 폴더를 /docs 로 정하고 저장합니다.
4. 몇 분 뒤 https://계정이름.github.io/kccl/ 에서 사이트가 열립니다.
5. site.json 의 base_url 에 그 주소를 적고 다시 빌드하면 sitemap.xml 이 생겨 검색엔진에 잘 잡힙니다.

## 미리보기

- `python build.py --one` 을 실행하면 모든 쪽을 하나로 합친 docs_preview.html 도 만들어집니다.
- 실제 사이트처럼 보려면 docs 폴더에서 `python -m http.server` 를 실행하고 브라우저로 http://localhost:8000 을 엽니다.
