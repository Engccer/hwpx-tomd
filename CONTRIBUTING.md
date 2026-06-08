# 기여 안내 (CONTRIBUTING)

`hwpx-tomd`는 HWPX를 로컬에서 Markdown으로 변환하는 **읽기 전용 엔진**입니다. 이 저장소(`github.com/Engccer/hwpx-tomd`)가 엔진의 **단일 진실 원천(SSoT)**이고, PyPI(`pip install hwpx-tomd`)는 그 빌드 산출물을 배포만 합니다. 따라서 엔진 개선·버그 신고·패치는 **모두 이 GitHub 저장소로** 모입니다(PyPI는 이슈·PR을 받지 못합니다).

## 이 엔진을 공유하는 두 소비자

이 패키지는 두 Claude Code 스킬이 같은 `core.py`를 호출해 씁니다. 변환 결함을 어느 쪽에서 발견하든 고치는 곳은 한 군데, 바로 이 엔진입니다.

- `hwpx-automation` 스킬: `hwpx_edit.py --to-md`가 `from hwpx_tomd import convert`를 호출.
- `docparse` 스킬: `parsers/hwpx_local_parse.py`가 동일 엔진을 호출(`_hwpxlocal.md` 출력).

"변환 정확도" 문제(파싱 누락, 표 정렬 붕괴, 객관식 마커 손실, tail 텍스트 손실 등)는 두 스킬의 래퍼가 아니라 **여기서** 고쳐야 양쪽에 동시에 반영됩니다. 편집·CLI 래퍼 고유의 함정은 각 스킬에 남깁니다.

## 역할에 따른 개선 경로

같은 결함이라도 누가 고치느냐에 따라 경로가 갈립니다.

| 역할 | 엔진 보유 형태 | 경로 |
|------|---------------|------|
| **유지보수자** (editable git 체크아웃 보유) | `pip install -e .` | 로컬에서 red-green 수정 → 버전 bump → `git push` → PyPI publish. editable이라 수정이 소비 스킬에 즉시 라이브 반영 |
| **다운스트림 사용자** (PyPI 설치) | `pip install hwpx-tomd` | site-packages를 직접 고치면 재설치 때 사라지고 upstream에도 안 남는다. **이슈를 열거나 PR을 보낸다**(아래 절차) |

다른 머신(예: 두 번째 작업 PC)에서 PyPI로만 설치해 쓰는 경우도 다운스트림과 동일합니다. 고친 뒤 push하고 그 머신에서는 `pip install -U hwpx-tomd`로 받습니다. 머신 간 동기화는 파일 복사가 아니라 GitHub pull/push로 합니다.

## 버그 신고 (수정 없이)

[이슈](https://github.com/Engccer/hwpx-tomd/issues)를 열고 다음을 첨부해 주세요.

1. **최소 재현 HWPX**: 결함을 재현하는 가장 작은 파일. 저작물·민감 문서는 올리지 말고(아래 "테스트 데이터 정책"), 구조만 남긴 합성 파일로 줄여 주세요. 첨부가 어려우면 문제 부분의 XML 조각(`Contents/section0.xml`)이라도.
2. **기대 출력 vs 실제 출력**: 변환 결과 Markdown에서 무엇이 빠지거나 어긋났는지.
3. **환경**: `hwpx-tomd` 버전(`python -c "import hwpx_tomd; print(hwpx_tomd.__version__)"`), Python·OS, `lxml` 버전.
4. 가능하면 `convert()`의 `result.recall`·`result.char_recall`·`result.warnings` 값.

## 패치 보내기 (PR)

이 엔진은 **회귀 테스트 우선(red-green)**으로 고칩니다. 검증되지 않은 변환 수정은 받지 않습니다.

1. 저장소를 fork 후 브랜치 생성.
2. **실패하는 회귀 테스트를 먼저 추가**: `tests/test_hwpx_tomd.py`에 결함을 드러내는 테스트를 넣고, 수정 전 빨간불(fail)을 확인합니다. 픽스처는 `tests/conftest.py`가 동적으로 만드는 **합성 HWPX**를 따릅니다(아래 정책).
3. `src/hwpx_tomd/core.py`를 고쳐 초록불(pass)로 만듭니다. 부작용 없는 순수 함수 원칙을 지킵니다(`print`/`sys.exit`는 `cli.py`에만).
4. 회귀 가드(객관식 마커 보존, 단어·글자 recall)와 기존 33개 테스트가 모두 통과하는지 확인합니다.
5. PR을 엽니다. **버전(`_version.py`) bump와 PyPI publish는 유지보수자가** 머지 후 진행하므로, 기여자는 버전을 올리지 않아도 됩니다.

## 개발 환경·테스트

```bash
# editable 설치 (테스트 의존 포함)
pip install -e ".[test]"
pytest

# 또는 uv
uv run --extra test pytest
```

`tests/conftest.py`가 픽스처 HWPX를 코드로 생성하므로 저장소에는 바이너리 샘플이 없습니다. CLI 동작 확인:

```bash
hwpx-tomd file.hwpx --stdout
```

## 테스트 데이터 정책 (중요)

이 저장소는 공개되어 있습니다. **출판사 워크시트·학교 고사 원안 등 저작물·개인정보 문서를 `tests/data/`나 이슈 첨부로 올리지 마세요.** 결함을 재현하는, 직접 만든 **합성 HWPX**만 픽스처·재현본으로 씁니다. 저작물·실무 문서로의 검증은 각자 로컬에서만 합니다.

## 범위 밖 요청

이 패키지는 **읽기 전용 변환**만 다룹니다. 다음은 설계상 받지 않습니다(README "범위" 참조).

- HWPX **편집**: `hwpx-automation` 스킬 소관.
- HWP(구형 바이너리) 직접 처리·암호 해제: 먼저 HWPX로 변환해 입력.
- **이미지 내 텍스트 OCR**: 텍스트 추출 범위 밖(필요 시 OCR 파서 병용). `recall`은 `<hp:t>` 텍스트 기준이라 이미지 속 글자는 분모에 없습니다.

## 라이선스

기여하신 내용은 저장소 라이선스 [MIT](LICENSE)로 배포됩니다.
