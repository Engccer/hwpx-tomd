# hwpx-tomd 패키지 개발·배포 계획

작성일: 2026-06-05(금)
상태: 계획 수립 완료, 구현 착수 전

## 0. 한 줄 정의

HWPX 파일을 외부 API 없이 로컬에서 Markdown/텍스트로 변환하는 가볍고 독립적인 Python 패키지(읽기 전용). 라이브러리 API와 CLI를 함께 제공한다.

## 1. 배경: 왜 이 패키지를 만드는가

### 출발점
`hwpx_edit.py`(현재 `tools/hwpx-automation/` 안, 976줄)의 `--to-md` 파서 엔진은 2026-06-05 실측 디버깅으로 세 가지 결함이 모두 수정되어, HWPX 텍스트 추출 완전성이 유료 Upstage 파서와 동급 또는 그 이상으로 검증되었다. 그 결과 이 엔진을 두 스킬이 함께 쓰게 되었다.

- `hwpx-automation` 스킬: HWPX 읽기·편집
- `docparse` 스킬: 문서 파싱(HWPX는 그동안 Upstage API로 처리했으나, 이제 무료·오프라인 로컬 추출 경로가 생김)

### 문제: self-contained 원칙과 DRY의 충돌
한 코드를 두 스킬이 쓰게 되면 두 가지 원칙이 충돌한다.

- self-contained: 각 스킬은 자기 폴더만으로 동작해야 한다(복제본이 있어야 함)
- DRY/단일 소스: 같은 코드가 여러 곳에 있으면 분기·관리 부담이 생긴다(복제본이 없어야 함)

### 선택한 해법: 독립 패키지(분기를 관리하는 게 아니라 제거)
파서 엔진을 별도 설치형 패키지로 추출하면 코드가 한 곳(패키지)에만 존재한다. 복제본 자체가 없으므로 분기가 물리적으로 불가능하고, 동기화 스크립트조차 필요 없다. 두 스킬은 이 패키지를 바라보는 두 소비자가 될 뿐이다.

추가로, 김헌용 교사는 학교·장교조 업무에서 HWPX를 매우 자주 다루므로 "스킬에 묶이지 않은 독립 변환 도구"의 실수요가 크고, 성능 고도화 후 대중 공개(PyPI, MIT) 가능성도 있다. `hwpx-automation`은 이미 공개 git repo(`github.com/Engccer/hwpx-automation`, MIT)이고 npm 패키지 배포 경험(`@dodo-planet/cli`, `@tobilu/qmd`)도 있어 배포 인프라 부담이 작다.

### 의사결정 기록 (검토했던 대안)
| 안 | 내용 | 채택 여부 | 사유 |
|----|------|----------|------|
| A. 벤더링 + sync 자동화 | 캐노니컬에서 docparse로 코드를 복제하고 sync 스크립트로 동기화 | 미채택 | 복제본이 존재해 sync가 필요. 분기 부담을 줄이지만 0은 아님 |
| B. 런타임 의존 + 폴백 | docparse가 실행 시 hwpx-automation 경로를 탐색해 호출, 없으면 Upstage | 미채택 | self-contained 약화(미설치 디바이스에서 로컬 파싱 불가) |
| **C. 독립 패키지** | 파서 엔진을 pip 설치형 패키지로 추출, 두 스킬이 의존 | **채택** | 분기를 완전 제거. 독립 활용·대중 공개 경로 확보 |

범위는 **(i) 읽기 전용**으로 확정했다. 편집 기능은 docparse가 쓰지 않고, 가벼운 단일 책임 도구로서 대중 공개 시 이해가 쉽기 때문이다.

## 2. 범위

### In scope (읽기 전용)
- HWPX → Markdown 변환 (본문 문단, 표, 글상자)
- HWPX → 평문 텍스트 추출
- 표를 `cellAddr`/`cellSpan` 기반 그리드로 정확히 배치(가로·세로 병합 보존)
- 병합 칸 채우기 옵션(`merge_fill`): 병합으로 덮인 칸을 시작 칸 값으로 채워 행 단위 파싱·LLM 입력에 적합(기본 off=GFM 정렬 보존)
- 글상자(drawText) 내부 본문을 reading-order로 수집
- `<hp:t>` tail 텍스트 보존(객관식 선택지 누락 방지)
- 변환 후 자가검증 3종: 단어 집합 recall + 글자 멀티셋 recall(`char_recall`, 반복·숫자·짧은 토큰 손실 감지) + 객관식 마커 보존 가드(①②③ 등이 줄면 임계값 무관 경고)
- 본문 이미지 개수 집계(`image_count`) + 이미지 존재 경고(이미지 내 텍스트 누락 가능성 고지, recall 맹점 보완)
- 암호화(AES) HWPX 자동 감지 후 명확한 예외/안내
- 라이브러리 API + CLI

### Out of scope (이번 패키지에서 제외)
- HWPX 편집(set-cell, find-replace, split-cell, delete-rows 등): `hwpx-automation` 스킬에 잔류
- HWP(구형 바이너리) 직접 처리: `hwpx-automation`의 `hwp2hwpx.bat`로 변환 후 입력
- 암호 해제(복호화): 한컴 COM 필요, 범위 밖(감지·안내까지만)
- 이미지 내 텍스트 OCR: 텍스트 추출 범위 밖(존재 경고까지만). 필요 시 Upstage 등 OCR 파서 병용
- 표의 구조화 데이터 반환(리스트/딕셔너리): 추후 검토(YAGNI)

## 3. 이식할 코드: hwpx_edit.py 파서 엔진

원본 경로: `C:/Users/pc/Windows-Projects/tools/hwpx-automation/hwpx_edit.py`

### 추출 대상 함수·상수 (읽기 전용 코어)
| 구분 | 항목 | 원본 위치(줄) |
|------|------|--------------|
| 상수 | `NS`(네임스페이스), `ENCRYPTION_HINT` | 24~32, 67~81 |
| 헬퍼 | `localname`, `t_full_text`, `is_encrypted_hwpx`, `get_output_path` | 221~243, 51~64, 35~48 |
| 표 접근 | `get_table_rows`, `get_row_cells`, `get_cell_addr`, `get_cell_span` | 211~218, 288~293, 274~285 |
| 셀 텍스트 | `get_cell_text`, `get_cell_paragraph_texts` | 246~271 |
| 렌더 | `render_cell_lines`, `render_table_md`, `render_block_lines`, `table_to_markdown` | 357~481, 328~354 |
| 엔트리 | `cmd_to_md` (→ 라이브러리 `to_markdown`/`convert`로 리네임·재설계) | 484~556 |

`cmd_info`, `cmd_set_cell` 등 편집 명령군(558~872줄)과 `main()` CLI(884줄~)는 이식하지 않는다.

### 이미 수정된 세 결함 (반드시 회귀 테스트로 보존)
| 결함 | 증상 | 수정 | 효과 |
|------|------|------|------|
| ① `<hp:t>` tail 손실 | `t_elem.text`만 읽어 내부 `<hp:tab>`/`<hp:lineBreak>`의 tail에 든 텍스트(객관식 선택지 ②③⑤ 등)를 잃음 | `t_full_text`가 `itertext`로 전체 수집, tab/lineBreak는 공백 치환 | 선택지 전부 보존 |
| ② 글상자(drawText) 본문 누락 | `cmd_to_md`가 최상위 p의 `run>t` 직속과 `.//tbl`만 수집해 글상자 내부 본문을 통째로 누락 | `render_block_lines`의 reading-order 재귀 순회 | Workbook류 recall 17~33% → 100% |
| ③ rowSpan/colSpan 미처리 | span을 `cellAddr`에서 잘못 읽어 항상 (1,1) 반환 → 모든 병합 무시, 표 정렬 붕괴 | `get_cell_span`이 별도 `<hp:cellSpan>`에서 읽고, `render_table_md`가 `cellAddr`/`cellSpan` 그리드 배치 | 표 정렬 복원 |

자가검증: 변환 후 원본 `<hp:t>` 단어 집합 대비 출력 recall을 계산하고 0.95 미만이면 경고(조용한 누락 방지). 단어 추출 정규식 `[A-Za-z]{3,}|[가-힣]{2,}`.

### 검증 데이터 (회귀 기준)
- 워크시트 5종(동아출판 윤정미 22개정, 2026 1학년 1학기 기말 워크시트) + 이질 5종(고사 원안·평가계획·체크리스트·채점기준표·읽기 안내문) 단어 recall 100%, 회귀 없음
- 암호화 배포본(고사 원안 일부, AES-256-CBC)은 파싱 불가가 정상이며 자동 감지로 명확히 안내됨
- 상세 보고서: `C:/Users/pc/Windows-Projects/docs/DocumentParse/HWPX_파서비교_2026-06-05/hwpx_edit_디버깅가능성_검토_2026-06-05.md`

## 4. 아키텍처: 라이브러리 + CLI 분리

현재 `hwpx_edit.py`는 파싱·CLI 출력·`sys.exit`가 한 함수에 엉켜 있다. 라이브러리화의 핵심 리팩토링은 다음 분리다.

- **core.py(순수 함수)**: 부작용 없이 값만 반환. 암호화는 `print`+`sys.exit`이 아니라 예외(`HwpxEncryptedError`)로, recall은 `print`가 아니라 반환 결과(dataclass)에 담는다.
- **cli.py(얇은 계층)**: argparse로 입력을 받아 core를 호출하고, 예외를 잡아 사용자 메시지·종료 코드로 변환하며, recall 경고를 stderr로 출력한다.

이 분리로 라이브러리 사용자는 깔끔한 반환값을 얻고, CLI 사용자는 기존과 같은 동작을 얻는다.

## 5. 공개 API 설계 (초안)

```python
from hwpx_tomd import to_markdown, convert, HwpxEncryptedError

# 1) 가장 간단: Markdown 문자열 반환
md: str = to_markdown("file.hwpx")               # cell_br=False 기본
md: str = to_markdown("file.hwpx", cell_br=True) # 셀 내부 문단을 <br>로 구분

# 2) 자가검증 결과까지 필요할 때: dataclass 반환
result = convert("file.hwpx")
# result.markdown : str
# result.recall   : float (원본 대비 단어 recall, 0.0~1.0)
# result.warnings : list[str] (recall<0.95 등)

# 3) 암호화 파일: 예외
try:
    to_markdown("encrypted.hwpx")
except HwpxEncryptedError as e:
    print(e)  # 복호화 안내 메시지 포함
```

CLI:
```bash
hwpx-tomd file.hwpx                 # file.md 생성 (또는 stdout 옵션)
hwpx-tomd file.hwpx -o out.md
hwpx-tomd file.hwpx --cell-br
hwpx-tomd file.hwpx --stdout        # 파이프용
```

## 6. 패키지 구조 (src layout)

```
hwpx-tomd/
├── pyproject.toml          # 빌드·메타데이터·[project.scripts] 엔트리
├── README.md               # 사용법·설치·예제 (공개 대비)
├── LICENSE                 # MIT
├── CLAUDE.md               # 작업 가이드 (이미 작성됨)
├── PLAN.md                 # 이 문서
├── src/
│   └── hwpx_tomd/
│       ├── __init__.py     # 공개 API export (to_markdown, convert, 예외, __version__)
│       ├── core.py         # 파서 엔진 (이식·라이브러리화)
│       ├── cli.py          # argparse CLI
│       └── _version.py     # 단일 버전 출처
└── tests/
    ├── conftest.py
    ├── data/               # 합성 HWPX 픽스처 + 기대 Markdown (골든)
    └── test_to_markdown.py
```

CLI 엔트리포인트는 `pyproject.toml`의 `[project.scripts]`에 `hwpx-tomd = "hwpx_tomd.cli:main"`으로 등록한다.

## 7. 의존성

- **lxml만 필요**: to-md 경로는 표준 라이브러리(`zipfile`, `os`, `sys`, `re`) + `lxml.etree`만 사용한다. `python-hwpx`에는 의존하지 않는다.
- 이점: `python-hwpx`가 도입한 `lxml<6` 핀 함정(과거 실측 사례)을 원천 회피한다. `pyproject.toml`에서 `lxml>=4.9`처럼 넉넉히 잡는다.
- Python 3.10+ 권장(dataclass·타입힌트). 개발 환경은 3.12.

## 8. 테스트 전략

- **골든 파일 테스트**: 입력 HWPX → 기대 Markdown 비교. 결함 ①②③ 각각을 재현하는 최소 픽스처를 포함(선택지 tail, 글상자, 병합 표).
- **recall 회귀 가드**: 각 픽스처 변환 결과의 recall ≥ 0.95 단언.
- **암호화 경로**: 암호화 HWPX 픽스처에서 `HwpxEncryptedError` 발생 단언.
- **테스트 데이터 주의(중요)**: 공개 repo가 될 수 있으므로 출판사 워크시트·학교 고사 원안 등 저작물·민감 문서는 테스트 픽스처에 넣지 않는다. 결함을 재현하는 **직접 제작한 합성 HWPX**만 `tests/data/`에 둔다. 출판사·학교 자료를 이용한 검증은 로컬에서만 수행한다.

## 9. 두 소비 스킬 마이그레이션

### hwpx-automation 스킬
- `hwpx_edit.py`의 to-md 함수군을 제거하고 `from hwpx_tomd import to_markdown` 호출로 교체.
- `--to-md` CLI 동작·출력 위치는 하위호환 유지(기존 사용자·다른 스킬이 의존).
- 편집 명령군은 그대로 잔류.
- 의존성에 `hwpx-tomd` 추가. 의존 방향은 단방향(hwpx-tomd는 hwpx-automation을 모름).

### docparse 스킬
- `parsers/hwpx_local_parse.py` 신규: 다른 `*_parse.py`와 동일한 인터페이스(`python hwpx_local_parse.py "<파일>"` → `_hwpxlocal.md`). 내부에서 `hwpx_tomd` 호출.
- `SKILL.md` HWPX 티어 갱신: "단순 텍스트 추출은 무료·오프라인 `hwpx_tomd` 우선, 시각적 배치 재현이 중요하거나 recall<95% 경고가 나는 문서는 Upstage." (현재도 안내 문구는 이 방향으로 정리되어 있으니 실제 파서 편입으로 확장.)

## 10. 배포 단계

1. **로컬 개발 설치**: `pip install -e .` (editable). 두 스킬이 이 패키지를 import.
2. **자체 검증**: 골든 테스트 통과 + 이질 5종 로컬 재현 + 두 스킬 회귀 없음 확인.
3. **공개 결정 시(고도화 후)**: README·LICENSE 정비 → TestPyPI 업로드·검증 → PyPI 정식 공개.
4. **멀티 디바이스 배포**: Mac·다른 Windows에 `pip install`. (스킬 파일은 junction/복제로 전파되지만, 패키지는 디바이스별 pip 설치가 필요함을 문서화.)

## 11. 버전 정책

- semver. `0.1.0`에서 시작.
- 버전 단일 출처는 `src/hwpx_tomd/_version.py`(또는 `pyproject.toml` dynamic).
- 패키지 버전을 올릴 때 의존하는 두 스킬을 점검(특히 공개 API 시그니처 변경 시).

## 12. 로드맵 (체크리스트)

- [x] 1. 패키지 이름 확정 + PyPI 가용성 확인 (`hwpx-tomd` 확정, PyPI 404=가용 확인. `hwpx2md`는 타인 점유)
- [x] 2. 스캐폴드: `pyproject.toml`(hatchling, PEP 639 license), src layout, `LICENSE`(MIT), `README.md`
- [x] 3. `core.py`: 함수 이식 + 라이브러리화(예외 `HwpxError`/`HwpxEncryptedError`/`HwpxParseError`, `ConversionResult` dataclass, print/sys.exit 제거)
- [x] 4. `cli.py`: argparse, 암호화·recall을 CLI 계층에서 출력(종료코드 0/1/2/3, `--stdout`/`--cell-br`/`-o`)
- [x] 5. 테스트: 합성 HWPX 픽스처 + 결함 ①②③ 회귀 가드 + recall 단언 + 암호화·파싱오류 예외 + CLI (현재 33개 통과; 6c·6d에서 8+8 증설)
- [x] 6. 로컬 editable 설치 + 검증 샘플 10종 재현 (원본 엔진 대비 전부 IDENTICAL·recall 100%, 암호화 1종 정상 실패)
- [x] 6b. Upstage 파싱본 대비 추가 5종 교차검증 (2026-06-06): 내용 동등(체크리스트 100% 일치), 표·객관식 마커는 패키지 우위(3학년 원안 마커 145 vs 131, Upstage가 ①③ 일부 누락), Upstage의 낮아 보이던 recall은 (a)HTML 태그 노이즈 (b)단어 분절 차이 (c)병합셀 반복 때문이며 실제 내용 손실 아님으로 규명. 유일한 격차는 이미지 내 텍스트(L5 BMP 제목)=OCR 영역. 암호화 1종(2학년 원안) 정상 차단.
- [x] 6c. 6b에서 도출한 개선 반영 (2026-06-06): (A)본문 이미지 개수 `ConversionResult.image_count` + 이미지 존재 경고로 self-recall 맹점 보완 (B)recall이 `<hp:t>` 텍스트 기준이라 이미지 내 텍스트를 못 잡는 한계를 README·docstring에 명시 (C)병합 칸 채우기 옵션 `merge_fill`(라이브러리·`--merge-fill` CLI) 추가. 회귀 테스트 8개 추가(16→25). 기본 출력은 무손상(byte-stable).
- [x] 6d. 나머지 미사용 쌍 전수 스윕 + 자가검증 강화 (2026-06-06): 미사용 HWPX-Upstage 쌍 29종을 전수 대조. **핵심 발견**: 원본 `<hp:t>` 대비 패키지 출력이 33종 전부 마커 Δ=0·글자 멀티셋 손실 0(=문자·마커 단위 완벽 보존). char_cov 하위권은 전부 Workbook이고 Upstage-only 단어가 죄다 이미지 캡션 어휘(image/placeholder/illustration…)→그래픽 손실이지 패키지 결함 아님. L5_Grammar Plus 마커 pkg 63<up 69도 원본이 정확히 63이라 Upstage 측 이미지 OCR+행 중복. 비-pic 시각객체 census 결과 OLE/수식/차트 0건, container·polygon은 순수 텍스트 문서에도 흔해 경고 확장 부적합으로 판정. **도출 개선**: (D)글자 멀티셋 recall `ConversionResult.char_recall`(단어 집합 recall이 못 보는 반복·숫자·짧은 토큰 손실 감지) (E)객관식 마커 보존 가드(①②③ 등이 출력에서 줄면 임계값 무관 정확 경고, 시험 무결성). 회귀 테스트 8개 추가(25→33). 실문서 33종에서 char_recall 전부 1.0·마커 경고 0건(오탐 없음). 기본 출력 무손상.
- [ ] 7. hwpx-automation 마이그레이션(to-md → 패키지 호출, 편집 잔류, 하위호환)
- [ ] 8. docparse 마이그레이션(`hwpx_local_parse.py` + `SKILL.md`)
- [ ] 9. (공개 결정 시) README·문서 완성 → TestPyPI → PyPI
- [ ] 10. 멀티 디바이스 배포 + 문서 동기화

## 13. 미결정 사항 (새 세션 초반에 확정)

- **패키지 이름**: `hwpx-tomd`(잠정, import명 `hwpx_tomd`). 후보: `hwpx2md`, `hwpx-reader`. PyPI 충돌 여부 확인 후 확정. `python-hwpx`(범용 읽기/쓰기 라이브러리)와 이름·기능이 구분되도록 "to markdown" 정체성을 살린다.
- **공개 시점**: 성능 고도화 후 대중 공개(현 단계는 로컬 개발·검증 우선).
- **표 구조화 API**: 표를 리스트/딕셔너리로 반환하는 API를 추가할지는 실수요 확인 후 결정.

## 14. 참조 경로

| 자료 | 경로 |
|------|------|
| 원본 파서 엔진 | `C:/Users/pc/Windows-Projects/tools/hwpx-automation/hwpx_edit.py` (상단 헬퍼 + 221~556줄) |
| 디버깅 보고서 | `C:/Users/pc/Windows-Projects/docs/DocumentParse/HWPX_파서비교_2026-06-05/hwpx_edit_디버깅가능성_검토_2026-06-05.md` |
| 변경 이력 | `C:/Users/pc/Windows-Projects/docs/DocumentParse/CHANGELOG.md` |
| 검증 샘플 | `C:/Users/pc/Windows-Projects/docs/DocumentParse/HWPX_파서비교_2026-06-05/` (워크시트·이질 5종) |
| 소비 스킬 1 | `C:/Users/pc/Windows-Projects/tools/hwpx-automation/SKILL.md` |
| 소비 스킬 2 | `C:/Users/pc/Windows-Projects/tools/docparse/SKILL.md` |
