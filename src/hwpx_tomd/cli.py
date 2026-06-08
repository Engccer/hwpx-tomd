"""hwpx_tomd.cli - argparse 기반 얇은 CLI 계층.

:mod:`hwpx_tomd.core`를 호출하고, 예외를 사용자 메시지·종료 코드로 변환하며,
recall·마커·이미지 경고를 stderr로 출력한다. 파싱 로직은 일절 들어 있지 않다.

종료 코드:
    0  성공
    1  일반 오류(HwpxParseError 등)
    2  잘못된 인자/파일 없음
    3  암호화된 HWPX(HwpxEncryptedError)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._version import __version__
from .core import HwpxEncryptedError, HwpxError, convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hwpx-tomd",
        description="HWPX 파일을 Markdown으로 변환합니다 (외부 API 불필요, 로컬·읽기 전용).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  hwpx-tomd doc.hwpx                  # doc.md 생성\n"
            "  hwpx-tomd doc.hwpx -o out.md        # 출력 경로 지정\n"
            "  hwpx-tomd doc.hwpx --stdout         # 표준출력 (파이프용)\n"
            "  hwpx-tomd doc.hwpx --cell-br        # 표 셀 내부 문단을 <br>로 구분\n"
            "  hwpx-tomd doc.hwpx --merge-fill     # 표 병합 칸을 같은 값으로 채움\n"
        ),
    )
    parser.add_argument("file", help="입력 HWPX 파일 경로")
    parser.add_argument(
        "-o",
        "--output",
        help="출력 .md 경로 (기본: 입력과 같은 위치의 <이름>.md)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="파일로 저장하지 않고 표준출력으로 결과를 보냄 (파이프용)",
    )
    parser.add_argument(
        "--cell-br",
        action="store_true",
        help="표 셀 내부 문단을 <br>로 구분 (긴 지문이 셀 안에 있는 고사지·보고서에 권장)",
    )
    parser.add_argument(
        "--merge-fill",
        action="store_true",
        help="표 병합(rowSpan/colSpan)으로 덮인 칸을 빈 칸 대신 같은 값으로 채움 "
        "(행 단위 파싱·LLM 입력용; 기본은 GFM 열 정렬 보존)",
    )
    parser.add_argument(
        "--image-dir",
        help="본문 이미지를 추출할 폴더. 지정 시 md에 ![image](...) 참조와 "
        "<image-dir>/_image_map.json(매핑) 생성. 미지정 시 이미지 생략(현행)",
    )
    parser.add_argument(
        "--image-prefix",
        default="",
        help="md 이미지 참조 경로 접두(예: img/). 파일은 --image-dir에 평면 저장",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="진행/recall 정보 메시지를 억제 (경고는 유지)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    in_path = Path(args.file)
    if not in_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {in_path}", file=sys.stderr)
        return 2

    try:
        result = convert(
            in_path,
            cell_br=args.cell_br,
            merge_fill=args.merge_fill,
            image_dir=args.image_dir,
            image_ref_prefix=args.image_prefix,
        )
    except HwpxEncryptedError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 3
    except HwpxError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    # --stdout 모드에서는 Markdown만 표준출력으로 내보내고, 그 외 정보 메시지는
    # 파이프 오염을 막기 위해 stderr로 보낸다.
    info_stream = sys.stderr if args.stdout else sys.stdout

    if args.stdout:
        sys.stdout.write(result.markdown)
        if not result.markdown.endswith("\n"):
            sys.stdout.write("\n")
    else:
        out_path = Path(args.output) if args.output else in_path.with_suffix(".md")
        out_path.write_text(result.markdown, encoding="utf-8")
        if not args.quiet:
            print(f"변환 완료: {out_path}", file=info_stream)
            print(f"크기: {len(result.markdown)} 글자", file=info_stream)

    if not args.quiet and not result.warnings:
        print(
            f"자가검증 recall: 단어 {result.recall:.1%} · 글자 {result.char_recall:.1%}",
            file=info_stream,
        )

    if args.image_dir and result.image_map:
        import json
        from pathlib import Path as _P
        map_path = _P(args.image_dir) / "_image_map.json"
        map_path.write_text(
            json.dumps(result.image_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not args.quiet:
            print(
                f"이미지 {result.extracted_images}개 추출 → {args.image_dir} "
                f"(매핑: {map_path})",
                file=info_stream,
            )

    for warning in result.warnings:
        print(f"경고: {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
