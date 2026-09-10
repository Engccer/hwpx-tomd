# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고, 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [0.3.0] - 2026-09-11

2023 교육부 정책연구 최종보고서·인사관리 안내서 2차 검수(2026-09-06)에서 드러난 구조 손실을 고쳤다.

### Added
- 캡션·본문의 자동 번호 필드(`<hp:autoNum num="3" numType="TABLE|PICTURE">`)를 글자로 푼다. 종전에는 필드를 건너뛰어 「<표 Ⅱ->」처럼 번호가 빠졌다(최종보고서 캡션 783개 중 237개 실측). 각주 번호(FOOTNOTE)는 종전대로 무시한다
- 1×1 래퍼 표의 유일한 내용이 표 하나면 안쪽 표를 그 자리에 렌더한다(표를 글상자처럼 감싼 직무 도식이 한 칸에 평탄화되던 문제)
- 텍스트 없는 셀의 화살표 선 도형(`<hp:line>` + ARROW 화살촉)을 방향에 따라 `→`·`↓`로 렌더한다(흐름표의 화살표 칸이 빈 칸이던 문제)
- `merge_fill="vertical"` / CLI `--merge-fill-vertical`: 세로 병합(rowSpan) 칸만 채우고 가로 병합(colSpan) 칸은 비운다(표 제목 행·유의사항 행이 열 수만큼 반복되지 않게)
- `prune_empty=True` / CLI `--prune-empty`: 전부 빈 행·열을 표에서 지운다(레이아웃용 빈 칸이 만든 5열 참고 박스·8열 흐름표)

### Changed
- 셀 안 중첩표는 평탄화하지 않고 바깥 표 바로 뒤에 별도 표로 낸다(0.2.2의 `<br>` 평탄화를 대체. 2열 책무 목록이 한 칸에 좌우 번갈아 눌리던 문제). 셀의 다른 텍스트는 그대로 남고, 승격·호이스팅된 표 자신의 캡션도 함께 렌더한다

## [0.2.2] - 2026-08-28

### Fixed
- 한 문단이 서식(charPr)마다 여러 `<hp:run>`으로 나뉠 때 run 경계마다 공백이 삽입되어 「내용은 파란색으로」가 「내용 은 파란색 으로」로 깨지던 문제. 최상위 문단·표 셀 양쪽 경로 모두 run 텍스트를 원문 그대로 이어 붙이고 공백 정규화만 한다(실측: 2023 교육부 정책연구 최종보고서 HWP의 델파이 조사지 안내문·강조 서식 문단)
- 표 셀 안의 중첩표를 평탄화할 때 모든 `<hp:t>`를 한 버퍼에 몰아넣어 셀·문단 경계가 사라지던 문제(「수업과 학습지도」「생활지도와」가 「학습지도생활지도와」로 접합). 중첩표도 문단 단위로 나눠 `--cell-br`이면 `<br>`, 아니면 공백으로 잇는다
- 표·그림 개체의 `<hp:caption>`(「<표 Ⅰ-1> …」「[그림 Ⅰ-1] …」)이 렌더되지 않아 캡션 272건이 통째로 빠지던 문제. `side="TOP"`이면 표 앞, 그 밖(BOTTOM 등)은 표 뒤에 캡션 줄을 낸다. 단어 recall은 목차에 같은 문구가 있으면 이 손실을 잡지 못했다(실측: 2023 교육부 정책연구 최종보고서)

## [0.2.1] - 2026-08-20

### Fixed
- hwp2hwpx 변환본의 section XML에 남은 XML 1.0 불법 제어문자(하이퍼링크 `Command` 값의 NUL 패딩 등)로 파싱이 중단되던 문제. 첫 파싱이 실패하면 해당 바이트만 제거하고 한 번 더 시도하며, 제거가 일어나면 경고를 남긴다. 탭·개행·복귀는 보존하고, 제거해도 파싱되지 않는 손상은 종전대로 `HwpxParseError` (#1)

## [0.2.0] - 2026-06-09

### Added
- 이미지 추출 기능: `convert(image_dir=...)`로 HWPX 내장 이미지(BinData)를 파일로 추출하고 매핑 JSON을 생성
- CLI 옵션 `--image-dir`, `--image-prefix`
- 본문 읽기 순서(reading order)에 맞춘 이미지 참조 삽입
- `ConversionResult`에 `extracted_images`, `image_map` 필드 추가
- WMF 등 변환 불가 포맷에 대한 경고

### Changed
- 이미지 추출 경로의 타입힌트 통일, 빈 디렉터리 가드 등 내부 정리

## [0.1.0] - 2026-06-08

### Added
- 최초 공개 릴리스 (PyPI `hwpx-tomd`, MIT)
- HWPX를 외부 API 없이 로컬에서 Markdown으로 변환하는 엔진: 글상자, `<hp:t>` tail, 표 `cellAddr`/`cellSpan` 병합 보존
- 자가검증 3종: 단어 recall, 글자 recall, 객관식 마커 가드
- 이미지 포함 문서에 대한 경고 출력
- 라이브러리 API(`to_markdown`, `convert`)와 CLI(`hwpx-tomd`)

[0.2.1]: https://github.com/Engccer/hwpx-tomd/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Engccer/hwpx-tomd/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Engccer/hwpx-tomd/releases/tag/v0.1.0
