> 🤖 **이 파일은 자동 생성됩니다 — 직접 수정하지 마세요.**
> 정본은 `CLAUDE.md` 입니다. 내용을 바꾸려면 `CLAUDE.md` 를 수정한 뒤
> 프로젝트 루트에서 `python sync_agent_docs.py` 를 실행하세요.
> 이 파일을 직접 고치면 다음 동기화 때 경고와 함께 덮어쓰기 대상이 됩니다.

<!-- SYNC-BODY-START — 이 줄 아래 본문은 CLAUDE.md 와 100% 동일하게 자동 생성됨 -->
# CLAUDE.md

이 파일은 Claude Code(claude.ai/code)가 이 저장소에서 작업할 때 참고하는 가이드다.

## 프로젝트 개요

`hwpx-tomd`: HWPX 파일을 외부 API 없이 로컬에서 Markdown/텍스트로 변환하는 가볍고 독립적인 Python 패키지(읽기 전용). 라이브러리 API와 CLI를 함께 제공한다.

- 사용자 호칭: "헌용 쌤" (영어: "Hunyong")
- 작성자: 신명중 김헌용 교사(시각장애 중등 영어 교사, 장교조 위원장). 학교·장교조 업무에서 HWPX를 매우 자주 다룬다.
- 라이선스(예정): MIT

## 현재 상태: 코어 구현·검증 완료 + 두 스킬 마이그레이션 완료

패키지 코어가 구현·검증되었고(2026-06-05), 첫 git 커밋과 두 소비 스킬 통합까지 마쳤다(2026-06-06). 배경·설계·로드맵 상세는 [`PLAN.md`](PLAN.md) 참조.

- **완료**: 이름 확정(`hwpx-tomd`, PyPI 가용 확인), src layout 스캐폴드, `core.py`(엔진 이식·라이브러리화), `cli.py`, 테스트 33개(결함 ①②③ 회귀 가드 + recall + 암호화 + 파싱 오류 + CLI + 이미지 경고 + merge_fill + char_recall + 마커 가드), editable 설치, 검증 샘플 10종이 원본 엔진 출력과 글자 단위 동일(IDENTICAL)·recall 100% 확인. 표가 많은 문서까지 동일하여 python-hwpx 표 로직 차용은 불필요로 결론.
- **Upstage 교차검증(2026-06-06)**: 추가 5종(고사 원안·교육과정·평가계획·체크리스트)을 Upstage 파싱본과 정밀 대조. 내용 동등(체크리스트 100% 일치), 표·객관식 마커는 패키지 우위, 유일한 격차는 이미지 내 텍스트(OCR 영역). 이를 바탕으로 세 개선 반영: (A) `ConversionResult.image_count` + 이미지 존재 경고(self-recall 맹점 보완), (B) recall이 `<hp:t>` 텍스트 기준이라는 한계 문서화, (C) 병합 칸 채우기 옵션 `merge_fill`(라이브러리·`--merge-fill`).
- **전수 스윕 + 자가검증 강화(2026-06-06)**: 나머지 미사용 쌍 29종을 전수 대조. 원본 `<hp:t>` 대비 33종 전부 마커 Δ=0·글자 멀티셋 손실 0(=문자·마커 단위 완벽 보존)으로 패키지에 텍스트 결함 없음을 입증. Upstage 대비 낮아 보이는 char 커버리지는 전부 이미지 캡션(그래픽 손실, OCR 영역). 비-pic 시각객체 census 결과 OLE/수식/차트 0건이고 container·polygon은 순수 텍스트 문서에도 흔해 이미지 경고 확장은 오탐 위험으로 기각. 대신 자가검증 메트릭의 맹점을 보강: (D) `ConversionResult.char_recall`(글자 멀티셋 recall; 단어 집합 recall이 못 보는 반복·숫자·짧은 토큰 손실 감지), (E) 객관식 마커 보존 가드(①②③ 등이 출력에서 줄면 임계값 무관 정확 경고). 실문서 33종 char_recall 전부 1.0·마커 경고 0건(오탐 없음).
- **첫 커밋(2026-06-06)**: `109399e feat: hwpx-tomd 0.1.0 초기 구현`. 13파일/1850줄. `.gitignore`가 `*.hwp`/`*.hwpx` 차단, 저작물 파일 미포함 확인.
- **hwpx-automation 마이그레이션 완료(2026-06-06, 로드맵 7)**: `hwpx_edit.py`가 to-md 전용 렌더 함수군 8개를 제거하고 `cmd_to_md`를 `from hwpx_tomd import convert` 호출 래퍼로 교체(편집 명령 잔류). 출력 byte-IDENTICAL 검증, `--merge-fill` 추가. 변환 엔진이 이제 이 패키지에만 존재(분기 제거).
- **docparse 마이그레이션 완료(2026-06-06, 로드맵 8)**: `parsers/hwpx_local_parse.py`(출력 `_hwpxlocal.md`)가 이 패키지를 호출. HWPX 티어가 hwpx_local 우선 + Upstage 폴백으로 전환.
- **대기**: 공개(9, TestPyPI/PyPI), 멀티 디바이스 배포(10).
- 의존성은 `lxml`만 요구하며 설치 환경의 lxml 6.x와 정상 동작(`python-hwpx`의 `lxml<6` 핀 회피 확인).
- 사전 조사 결론: PyPI의 기존 패키지(hwpx2md, python-hwpx, hwp2md, pyhwpxlib 등) 중 세 결함을 동시에 해결하는 것이 없어 자체 엔진 추출이 정답으로 재확인됨.

## 왜 만드는가 (요약)

`hwpx_edit.py`(현재 `tools/hwpx-automation/`)의 `--to-md` 파서 엔진이 2026-06-05 디버깅으로 세 결함(① `<hp:t>` tail 손실 ② 글상자 본문 누락 ③ 표 병합 무시)이 모두 수정되어 텍스트 완전성이 유료 Upstage 파서와 동급이 되었다. 이 엔진을 `hwpx-automation`과 `docparse` 두 스킬이 함께 쓰게 되면서, "복제하면 분기, 복제 안 하면 self-contained 위배"라는 충돌이 생겼다. 해법은 **엔진을 독립 패키지로 추출**하는 것이다. 코드가 한 곳에만 존재하므로 분기가 물리적으로 불가능하고, 두 스킬은 이 패키지의 소비자가 된다. 상세 의사결정 기록은 PLAN.md 1절.

## 범위

- **In scope(읽기 전용)**: HWPX → Markdown/텍스트, 표 그리드 배치(`cellAddr`/`cellSpan`), 글상자 reading-order 수집, tail 보존, recall 자가검증, 암호화 감지·안내, 라이브러리 + CLI
- **Out of scope**: HWPX 편집(hwpx-automation 잔류), HWP 바이너리 직접 처리, 암호 해제, 표 구조화 데이터 반환(추후)

## 아키텍처 핵심

원본 `hwpx_edit.py`는 파싱·CLI 출력·`sys.exit`가 한 함수에 엉켜 있다. 라이브러리화의 핵심은 분리다.

- `src/hwpx_tomd/core.py`: 부작용 없는 순수 함수. 암호화는 예외(`HwpxEncryptedError`), recall은 반환 dataclass에 담는다(`print`/`sys.exit` 금지).
- `src/hwpx_tomd/cli.py`: argparse 얇은 계층. core 호출 + 예외→메시지·종료코드 변환 + recall 경고를 stderr 출력.

공개 API 초안:
```python
from hwpx_tomd import to_markdown, convert, HwpxEncryptedError
md = to_markdown("file.hwpx", cell_br=False)   # str
result = convert("file.hwpx")                   # .markdown / .recall / .warnings
```

## 의존성

- **lxml만 필요** (to-md 경로는 표준 라이브러리 + `lxml.etree`만 사용). `python-hwpx`에 의존하지 않으므로 그 패키지의 `lxml<6` 핀 함정을 회피한다.
- Python 3.10+ (개발 3.12).

## 이식 원본·참조 경로

| 자료 | 경로 |
|------|------|
| 원본 파서 엔진(이식 대상) | `C:/Users/pc/Windows-Projects/tools/hwpx-automation/hwpx_edit.py` (상단 헬퍼 + 221~556줄) |
| 디버깅 보고서(결함·검증 상세) | `C:/Users/pc/Windows-Projects/docs/DocumentParse/HWPX_파서비교_2026-06-05/hwpx_edit_디버깅가능성_검토_2026-06-05.md` |
| 검증 샘플(워크시트·이질 5종) | `C:/Users/pc/Windows-Projects/docs/DocumentParse/HWPX_파서비교_2026-06-05/` |
| 소비 스킬 1 | `C:/Users/pc/Windows-Projects/tools/hwpx-automation/SKILL.md` |
| 소비 스킬 2 | `C:/Users/pc/Windows-Projects/tools/docparse/SKILL.md` |

이식할 함수 목록과 줄 위치는 PLAN.md 3절 표를 참조.

## 개발 명령어

```bash
# editable 설치 (테스트 의존 포함)
pip install -e ".[test]"

# 테스트
pytest

# CLI 실행
hwpx-tomd file.hwpx
hwpx-tomd file.hwpx -o out.md --cell-br
```

## 테스트 데이터 주의 (중요)

공개 repo가 될 수 있으므로 **출판사 워크시트·학교 고사 원안 등 저작물·민감 문서를 `tests/data/`에 넣지 않는다.** 결함 ①②③을 재현하는 직접 제작한 합성 HWPX만 픽스처로 둔다. 출판사·학교 자료 검증은 로컬에서만.

## 글로벌 작업 규칙 (반드시 준수)

이 컴퓨터의 모든 작업에 적용되는 사용자 전역 규칙(`~/.claude/CLAUDE.md`)이다.

- **문서에 em dash(—)·en dash(–) 금지.** 콜론(:), 괄호, 물결표(~), 가운뎃점(·)으로 대체.
- **날짜에 요일 병기 시 반드시 검증.** 추론 금지. `python -c "import datetime; print(datetime.date(2026,6,5).strftime('%A'))"` 또는 PowerShell `(Get-Date "2026-06-05").DayOfWeek`. 매핑 Mon=월 Tue=화 Wed=수 Thu=목 Fri=금 Sat=토 Sun=일.
- **작업 완료 시 TTS 요약**을 `C:/Users/pc/.claude/tts-summary.txt`에 Write 도구로 작성(한국어, 직접 서술체).
- **커밋·push는 사용자가 요청할 때만.** 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- 코드 작성 시 최신 문서 확인(Context7/chub 등). 학습 데이터에 의존하지 않는다.

## 관련 스킬

| 작업 | 스킬 |
|------|------|
| HWP→HWPX 변환(입력 준비), HWPX 편집 | `/hwpx-automation` |
| 문서 파싱(PDF·스캔·교차검증) | `/docparse` |
