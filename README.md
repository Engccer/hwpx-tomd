# hwpx-tomd

HWPX(한컴오피스 한글) 문서를 외부 API 없이 **로컬에서 Markdown/텍스트로 변환**하는 가볍고 독립적인 Python 패키지입니다. 읽기 전용이며 `lxml`에만 의존합니다.

문서 파싱 서비스(Upstage 등)에 보내지 않고, 인터넷 연결 없이, 무료로 HWPX 본문을 추출합니다. 텍스트 완전성은 유료 파서와 동급 수준으로 검증되었습니다.

## 특징

- **본문·표·글상자**를 모두 추출: 글상자(drawText) 내부 본문을 reading order로 수집합니다.
- **표 병합 보존**: `cellAddr`/`cellSpan` 그리드 기반으로 가로·세로 병합을 정확히 배치합니다.
- **tail 텍스트 보존**: `<hp:t>` 내부 `<hp:tab>`/`<hp:lineBreak>` 뒤에 오는 텍스트(객관식 선택지 ②③⑤ 등)를 잃지 않습니다.
- **자가검증 recall**: 변환 후 원본 대비 **단어 recall**과 **글자 멀티셋 recall**을 함께 계산해 조용한 누락을 경고합니다(글자 recall은 반복·숫자·짧은 토큰 손실까지 잡습니다).
- **객관식 마커 보존 가드**: ①②③ 같은 선택지 마커가 렌더링 중 하나라도 빠지면 임계값과 무관하게 경고합니다(시험 문항 무결성).
- **이미지 존재 경고**: 본문에 그림이 있으면 그 개수를 알리고, 그래픽에 박힌 텍스트가 누락될 수 있음을 경고합니다.
- **병합 칸 채우기 옵션**: `merge_fill=True`로 병합 셀 값을 모든 칸에 채워 행 단위 파싱·LLM 입력에 맞춥니다.
- **암호화 감지**: AES 암호화 HWPX를 자동 감지하고 복호화 방법을 안내합니다.
- **가벼운 의존성**: `lxml`만 필요합니다(`python-hwpx`에 의존하지 않아 `lxml<6` 핀 충돌을 피합니다).

## 설치

```bash
pip install hwpx-tomd
```

로컬 개발:

```bash
pip install -e .
```

## 라이브러리 사용법

```python
from hwpx_tomd import to_markdown, convert, HwpxEncryptedError

# 1) 가장 간단: Markdown 문자열
md = to_markdown("file.hwpx")
md = to_markdown("file.hwpx", cell_br=True)     # 셀 내부 문단을 <br>로 구분
md = to_markdown("file.hwpx", merge_fill=True)  # 병합 칸을 같은 값으로 채움

# 2) 자가검증 결과까지: ConversionResult
result = convert("file.hwpx")
print(result.markdown)      # str
print(result.recall)        # float (단어 집합 recall, 0.0~1.0)
print(result.char_recall)   # float (글자 멀티셋 recall, 0.0~1.0; 더 엄격)
print(result.warnings)      # list[str]
print(result.image_count)   # int (본문 이미지 개수)

# 3) 암호화 파일: 예외
try:
    to_markdown("encrypted.hwpx")
except HwpxEncryptedError as e:
    print(e)   # 복호화 안내 포함
```

### recall의 한계 (꼭 읽어 주세요)

`recall`은 **section XML의 텍스트(`<hp:t>`) 기준**입니다. 그림(`<hp:pic>`) 안에 그래픽으로 박힌 텍스트(출판사 제목 이미지, 도표 캡션 등)는 애초에 분모에 없으므로, **recall이 1.0이어도 이미지 속 글자는 누락될 수 있습니다.** 이미지 내 텍스트는 OCR 영역이라 본 패키지(텍스트 추출)의 범위를 벗어납니다.

이 맹점을 보완하기 위해 `convert()`는 본문 이미지 개수를 `result.image_count`로 반환하고, 이미지가 있으면 `result.warnings`에 안내를 추가합니다. 이미지 속 텍스트까지 필요하면 OCR 기반 파서(Upstage 등)를 함께 쓰세요.

### 단어 recall vs 글자 recall vs 마커 가드

`recall`(단어 집합)은 같은 단어의 **반복 손실**이나 **숫자·1~2글자 토큰 손실**을 구조적으로 보지 못합니다(집합이라 한 번만 세고, 짧은 토큰은 단어 정규식이 거릅니다). 이를 `char_recall`(한글·영문·숫자 **글자 멀티셋** recall)이 보완합니다. 출력이 원본 글자를 모두 포함하면 1.0이고, 반복·숫자가 빠지면 1.0 미만으로 떨어집니다.

객관식 선택지 마커(①②③ 등 둘러싸인 영숫자)는 시험 문항에서 치명적이라 별도 **마커 보존 가드**가 있습니다. 원본 `<hp:t>`에 있던 마커가 출력에서 하나라도 줄면, recall 임계값과 무관하게 어떤 마커가 몇 개 빠졌는지 경고합니다. 큰 문서에서 마커 한두 개 손실은 recall 임계값에 안 걸려 묻히기 쉬운데, 이 가드는 정확 비교라 그런 누락도 잡습니다. (실측: 실제 시험·교육과정 문서 33종에서 두 recall 모두 1.0, 마커 손실 0건으로 오탐이 없음을 확인했습니다.)

### `merge_fill` 옵션

기본값(`merge_fill=False`)은 표 병합으로 덮인 칸을 빈 칸으로 두어 GFM 열 정렬을 보존합니다. `merge_fill=True`이면 병합 시작 칸의 값을 덮인 칸에도 채워, 모든 행이 자족적이 됩니다(정보량은 동일). 교육과정·평가계획처럼 머리 셀이 세로로 길게 병합된 표를 **행 단위로 읽거나 LLM에 입력**할 때 유용합니다.

## CLI 사용법

```bash
hwpx-tomd file.hwpx              # file.md 생성
hwpx-tomd file.hwpx -o out.md    # 출력 경로 지정
hwpx-tomd file.hwpx --stdout     # 표준출력 (파이프용)
hwpx-tomd file.hwpx --cell-br    # 표 셀 내부 문단을 <br>로 구분
hwpx-tomd file.hwpx --merge-fill # 표 병합 칸을 같은 값으로 채움
```

종료 코드: `0` 성공, `1` 일반 오류, `2` 잘못된 인자/파일 없음, `3` 암호화된 HWPX.

## 범위

- **In scope (읽기 전용)**: HWPX → Markdown/텍스트, 표 그리드 배치, 병합 칸 채우기 옵션, 글상자 수집, tail 보존, 자가검증(단어 recall · 글자 멀티셋 recall · 마커 보존 가드), 이미지 존재 경고, 암호화 감지·안내.
- **Out of scope**: HWPX 편집, HWP(구형 바이너리) 직접 처리, 암호 해제, **이미지 내 텍스트 OCR**, 표의 구조화 데이터 반환(추후 검토).

HWP(구형 바이너리)는 먼저 HWPX로 변환한 뒤 입력하세요. HWPX 편집이 필요하면 별도 도구를 사용하세요.

## 라이선스

[MIT](LICENSE) © 2026 Hunyong Kim (김헌용)
