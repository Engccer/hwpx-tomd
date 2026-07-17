# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고, 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

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

[0.2.0]: https://github.com/Engccer/hwpx-tomd/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Engccer/hwpx-tomd/releases/tag/v0.1.0
