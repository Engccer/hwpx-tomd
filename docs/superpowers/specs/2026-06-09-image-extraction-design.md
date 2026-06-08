# hwpx-tomd 이미지 추출 기능 설계

작성일: 2026-06-09
상태: 설계 승인됨(구현 대기)
관련 문서: `PLAN.md`(로드맵), docparse `scripts/generate_alt_text.py`(alt 주입 워크플로우)
근거 비교: `docs/DocumentParse/03_파서비교평가/HWPX_파서비교_2026-06-09/`(hwpx-tomd vs python-hwpx)

## 1. 배경과 동기

hwpx-tomd는 현재 본문 이미지를 추출하지 않고 `count_images()`로 개수만 세어 경고한다. 2026-06-09 실문서 비교(영어과 교육과정 별책14)에서 python-hwpx `export_markdown(image_dir=...)`가 이미지를 파일로 추출하는 점이 명확한 차별점으로 확인됐다.

사용자 주 용도는 **OCR 파이프라인 입력**이다: 추출한 이미지를 docparse(Upstage/Gemini Vision)로 넘겨 그림 속 텍스트까지 확보한다. 따라서 hwpx-tomd는 이미지 추출 + reading-order 참조 삽입 + 매핑 JSON 생성까지만 책임지고, OCR 자체는 docparse가 받는다(hwpx-tomd의 무API·읽기전용·경량 철학 유지).

HWPX는 PDF보다 유리하다. PDF는 이미지가 페이지에 박혀 있어 페이지 렌더링(PyMuPDF)이 필요하지만, HWPX는 `BinData/`에 이미지 원본 파일이 그대로 들어 있어 추출 후 그 파일을 Vision에 직접 보낼 수 있다.

## 2. 목표 / 비목표

### 목표
- `convert`/`to_markdown`에 `image_dir`, `image_ref_prefix` 옵션 추가
- 본문 reading-order 정확한 위치에 `![image](prefix+파일명)` 참조 삽입
- `BinData` 이미지를 `image_dir`로 추출(중복 제거, 고유 파일만)
- docparse가 OCR 후 alt를 주입하기 쉬운 매핑 JSON 생성
- 하위호환: `image_dir` 미지정 시 현행 동작 100% 불변

### 비목표(out of scope)
- OCR/Vision 호출 자체(docparse 담당, hwpx-tomd는 무API 유지)
- WMF/EMF의 래스터 변환(추출만 하고 `ocr_eligible` 플래그로 표시)
- docparse 측 HWPX 전용 alt 생성 스크립트(별도 후속 작업, 6절 참조)
- 이미지 편집·원본 수정(읽기 전용 유지)

## 3. 설계 상세

### 3.1 API
```python
convert(filepath, *, cell_br=False, merge_fill=False,
        image_dir=None, image_ref_prefix="")
to_markdown(filepath, *, cell_br=False, merge_fill=False,
            image_dir=None, image_ref_prefix="")
```
- `image_dir=None`(기본): 현행 동작 그대로(이미지 생략 + 경고). 기존 33개 테스트와 두 소비 스킬(hwpx-automation `--to-md`, docparse `hwpx_local_parse.py`) 호출부 무영향.
- `image_dir` 지정: 해당 폴더로 이미지 추출 + 본문에 참조 삽입.
- `image_ref_prefix`: md 참조와 매핑 `file`에 붙는 경로 접두(예: `"img/"`). 기본 `""`. 실제 파일은 항상 `image_dir`에 평면 저장되며, prefix는 md가 이미지를 참조하는 상대경로 표기에만 쓰인다(예: prefix `"img/"`면 md는 `![image](img/image7.jpg)`, 실제 파일은 `image_dir/image7.jpg`).
- `ConversionResult`에 필드 추가:
  - `image_map: dict[str, dict]` (매핑 JSON 본체)
  - `extracted_images: int` (추출된 고유 파일 수)
- CLI(`cli.py`): `--image-dir PATH`, `--image-prefix STR` 추가. `--image-dir` 지정 시 매핑 JSON을 `<image_dir>/_image_map.json`으로도 저장.

### 3.2 데이터 흐름
1. zip을 한 번 열어 section roots를 파싱한다(기존 `_read_section_roots` 로직 재사용, zip 핸들만 공유하도록 조정).
2. `image_dir`가 지정된 경우:
   1. zip namelist에서 `BinData/{id}.*` stem 매칭으로 `binaryItemIDRef → BinData/파일경로` 매핑을 구성한다. (실측상 본문 `binaryItemIDRef="image1"`이 `BinData/image1.*`의 stem과 일치하므로 content.hpf 파싱은 불필요하다.)
   2. `render_block_lines`에 이미지 컨텍스트(매핑·prefix·수집 콜백)를 전달한다. `pic` 분기를 추가해 `<hc:img binaryItemIDRef="imageN">`을 읽어 그 위치에 `![image](prefix+파일명)`을 삽입하고, 사용된 ID를 수집한다.
   3. 본문에 실제 배치된(참조된) BinData만 `image_dir`로 추출한다. 같은 ID가 여러 번 참조되면 파일은 1회만 추출(고유 파일), 참조는 공유한다.
   4. 매핑 JSON을 구성한다.
3. `ConversionResult`에 markdown + image_map + extracted_images를 담아 반환한다.

### 3.3 매핑 JSON 포맷(docparse `inject()` 호환)
docparse의 `inject()`는 `{md참조문자열: {...}}` dict를 받아 정규식으로 치환한다. 이를 그대로 소비하도록 키를 md 참조 문자열로 둔다. 중복 이미지는 같은 alt를 공유하므로 **고유 이미지당 1항목**(키 충돌 없음, OCR 비용도 고유 수만큼으로 절감):
```json
{
  "![image](image7.jpg)": {
    "image_id": "image7",
    "file": "image7.jpg",
    "ext": "jpg",
    "ocr_eligible": true,
    "ko_alt": null
  }
}
```
- `ko_alt: null`은 docparse가 Gemini Vision으로 채울 자리.
- 본문 내 위치는 md 참조 자체가 표현하므로 JSON에는 고유 이미지 메타만 둔다.
- `image_ref_prefix`가 있으면 키와 `file`에 반영(예: `"![image](img/image7.jpg)"`, `file: "img/image7.jpg"`).

### 3.4 엣지케이스·에러
| 상황 | 처리 |
|------|------|
| `image_dir=None` | 현행(생략 + 경고). 하위호환 |
| WMF/EMF 등 벡터 | 추출은 하되 `ocr_eligible=false` + 경고("Vision/OCR 부적합, 변환 필요"). 이 문서의 29MB `image8.wmf`가 해당 |
| BinData 누락·깨짐 | 해당 참조를 md·image_map에서 완전히 생략(깨진 링크 없음). `_ImageCtx.ref_for`가 unknown id에 None을 반환하므로 렌더링 중 자연히 제외됨 |
| 같은 ID 중복 참조 | 파일 1회만 추출, 참조 공유 |
| stem 매칭(기본 경로) | content.hpf 파싱 없이 zip namelist stem 매칭이 PRIMARY 경로 |
| 암호화 HWPX | 기존 `HwpxEncryptedError` 그대로 |

`ocr_eligible` 판정: 확장자 기준 화이트리스트(jpg/jpeg/png/gif/bmp/tiff/webp = true, wmf/emf 등 = false).

### 3.5 자가검증(기존 정신 계승)
- 본문 이미지 참조 수 == `count_images()`(배치 인스턴스 수) 일치 확인. 불일치 시 경고.
- 경고문 보강: "본문 이미지 N개 배치(고유 M개) 추출 완료. 그림 속 텍스트는 OCR 필요."
- 텍스트 recall/char_recall/마커 가드는 이미지와 무관하므로 영향 없음(기존 유지).

## 4. 테스트 계획
테스트 데이터 주의: 공개 repo 가능성이 있으므로 저작물·민감 문서를 픽스처에 넣지 않는다. 이미지·중복참조를 담은 **직접 제작한 합성 HWPX**만 사용한다.

- **회귀(최우선)**: `image_dir=None`에서 기존 33개 테스트 전부 그대로 통과.
- **신규**:
  1. `image_dir` 지정 시 추출 파일 수 == 고유 이미지 수
  2. md 이미지 참조 수 == 배치 인스턴스 수(중복 포함)
  3. 매핑 JSON 구조·키(md 참조 문자열)·`ko_alt=null`
  4. WMF 픽스처 `ocr_eligible=false` + 경고
  5. 같은 ID 중복 참조 시 파일 1회 추출, 참조 공유
  6. 매니페스트 없는 합성본에서 stem 매칭 폴백
  7. `image_ref_prefix` 반영(키·file 경로)

## 5. 의존성·철학 영향
- 추가 의존성 0(zipfile 표준 + 이미 쓰는 lxml). lxml만 의존 유지.
- "읽기 전용"은 입력 HWPX 불변을 뜻하므로 유지된다(이미지 파일 출력은 markdown 출력과 동급의 산출이다).
- 무API 철학 유지(OCR은 docparse가 담당).

## 6. 향후(이 spec 범위 밖)
- **docparse HWPX alt 생성 경로**: 추출된 이미지 파일을 직접 Gemini Vision에 보내 한국어 alt를 생성하는 경로(PDF와 달리 페이지 렌더링 불필요). 기존 `generate_alt_text.py`를 확장하거나 HWPX 전용 스크립트 신설. 매핑 JSON(`_image_map.json`)을 입력으로 사용.
- **hwpx-automation 연계**: `hwpx_edit.py --to-md` 래퍼에 `--image-dir`를 전달하는 옵션(선택).
