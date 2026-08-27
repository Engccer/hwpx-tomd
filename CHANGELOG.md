# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고, 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [0.2.2] - 2026-08-28

### Fixed
- 한 문단이 서식(charPr)마다 여러 `<hp:run>`으로 나뉠 때 run 경계마다 공백이 삽입되어 「내용은 파란색으로」가 「내용 은 파란색 으로」로 깨지던 문제. 최상위 문단·표 셀 양쪽 경로 모두 run 텍스트를 원문 그대로 이어 붙이고 공백 정규화만 한다(실측: 2023 교육부 정책연구 최종보고서 HWP의 델파이 조사지 안내문·강조 서식 문단)
- 표 셀 안의 중첩표를 평탄화할 때 모든 `<hp:t>`를 한 버퍼에 몰아넣어 셀·문단 경계가 사라지던 문제(「수업과 학습지도」「생활지도와」가 「학습지도생활지도와」로 접합). 중첩표도 문단 단위로 나눠 `--cell-br`이면 `<br>`, 아니면 공백으로 잇는다

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
