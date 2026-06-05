"""hwpx_tomd - HWPX를 외부 API 없이 로컬에서 Markdown으로 변환하는 읽기 전용 패키지.

기본 사용법::

    from hwpx_tomd import to_markdown, convert

    md = to_markdown("file.hwpx")                  # Markdown 문자열
    md = to_markdown("file.hwpx", merge_fill=True) # 표 병합 칸을 같은 값으로 채움
    result = convert("file.hwpx", cell_br=True)
    # result: .markdown / .recall(단어) / .char_recall(글자 멀티셋) /
    #         .warnings / .image_count
"""

from ._version import __version__
from .core import (
    ConversionResult,
    HwpxEncryptedError,
    HwpxError,
    HwpxParseError,
    convert,
    to_markdown,
)

__all__ = [
    "__version__",
    "to_markdown",
    "convert",
    "ConversionResult",
    "HwpxError",
    "HwpxEncryptedError",
    "HwpxParseError",
]
