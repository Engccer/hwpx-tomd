"""hwpx_tomd.core - HWPX를 Markdown으로 변환하는 순수 파서 엔진.

이 모듈은 부작용이 없다. 파일을 쓰거나 ``print``/``sys.exit``를 호출하지
않으며, 값(문자열, :class:`ConversionResult`)만 반환하고 오류는 예외로 알린다.
CLI 출력·종료 코드 변환은 :mod:`hwpx_tomd.cli`가 담당한다.

엔진은 2026-06-05 실측 디버깅으로 확인·수정된 세 결함을 모두 처리한다.
이 결함들은 회귀가 잦으므로 각 함수 주석에 근거를 남겨 둔다.

  1. ``<hp:t>`` tail 손실: ``t_elem.text``만 읽으면 내부 ``<hp:tab>``/
     ``<hp:lineBreak>`` 뒤 tail 텍스트(객관식 선택지 등)를 잃는다.
     :func:`t_full_text`가 ``itertext``로 전체를 수집한다.
  2. 글상자(drawText) 본문 누락: 최상위 문단의 직속 run/t와 표만 보면
     글상자 내부 본문을 통째로 누락한다. :func:`render_block_lines`가
     reading order로 재귀 순회한다.
  3. 표 병합(rowSpan/colSpan) 무시: span은 ``cellAddr``가 아니라 별도
     ``<hp:cellSpan>``에 있다. :func:`get_cell_span`이 올바른 위치에서 읽고
     :func:`render_table_md`가 ``cellAddr``/``cellSpan`` 그리드로 배치한다.
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from lxml import etree

__all__ = [
    "NS",
    "ENCRYPTION_HINT",
    "RECALL_WARN_THRESHOLD",
    "HwpxError",
    "HwpxEncryptedError",
    "HwpxParseError",
    "ConversionResult",
    "convert",
    "to_markdown",
]

PathLike = Union[str, Path]


# HWPX(OWPML) 네임스페이스
NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}

ENCRYPTION_HINT = (
    "이 HWPX 파일은 암호화되어 있습니다 (AES-256-CBC).\n"
    "XML 직접 파싱으로 처리할 수 없으므로 한컴 COM으로 암호를 먼저 제거해야 합니다.\n"
    "\n"
    "해결: 한컴오피스가 설치된 Windows에서 아래 스크립트로 복호화하세요.\n"
    "  hwp = win32.gencache.EnsureDispatch('HWPFrame.HwpObject')\n"
    "  hwp.Open(abs_in, 'HWPX', 'password:<비밀번호>')\n"
    "  act = hwp.CreateAction('FilePasswordChange')\n"
    "  pset = act.CreateSet(); act.GetDefault(pset)\n"
    "  pset.SetItem('String', ''); pset.SetItem('Ask', 0)\n"
    "  pset.SetItem('ReadString', ''); pset.SetItem('WriteString', '')\n"
    "  pset.SetItem('RWAsk', 0); act.Execute(pset)\n"
    "  hwp.SaveAs(abs_out, 'HWPX', ''); hwp.Quit()"
)

# 변환 후 원본 대비 단어 recall이 이 값 미만이면 경고한다(조용한 누락 방지).
RECALL_WARN_THRESHOLD = 0.95

# 단어 경계 추출: 영문 3글자 이상 또는 한글 2글자 이상.
_WORD_RE = re.compile(r"[A-Za-z]{3,}|[가-힣]{2,}")

# 내용 글자(한글·영문·숫자) 단위. 단어 recall(_WORD_RE)은 집합 기준이라 같은
# 단어의 반복 손실을 못 보고 1~2글자·숫자도 세지 않는다. 글자 멀티셋 recall은
# 이 맹점(반복·숫자·짧은 토큰 손실)까지 잡아낸다.
_CHAR_RE = re.compile(r"[가-힣A-Za-z0-9]")

# '둘러싸인 영숫자' 유니코드 블록(U+2460~U+24FF): ①②③ 같은 객관식 선택지
# 마커가 여기 속한다. 단어 recall이 세지 않는 시험 핵심 토큰이므로, 원본
# ``<hp:t>``에 있던 마커가 출력에서 하나라도 줄면(표 병합·중첩 렌더링 사고 등)
# 임계값과 무관하게 정확히 경고한다. 33개 실문서에서 손실 0으로 오탐 없음 확인.
_MARKER_RE = re.compile(r"[①-⓿]")


class HwpxError(Exception):
    """hwpx_tomd가 발생시키는 모든 오류의 기반 클래스."""


class HwpxEncryptedError(HwpxError):
    """HWPX가 암호화되어 있어 XML 직접 파싱이 불가능할 때 발생.

    메시지에 한컴 COM 복호화 안내(:data:`ENCRYPTION_HINT`)가 포함된다.
    """


class HwpxParseError(HwpxError):
    """HWPX가 올바른 zip이 아니거나 section XML을 찾을 수 없을 때 발생."""


@dataclass
class ConversionResult:
    """:func:`convert`의 반환값.

    Attributes:
        markdown: 변환된 Markdown 문자열.
        recall: 원본 ``<hp:t>`` 단어 집합 대비 출력 단어 recall(0.0~1.0).
            추출 가능한 단어가 없는 빈 문서는 1.0으로 본다.

            한계(중요): 이 값은 **section XML의 텍스트(``<hp:t>``) 기준**이다.
            따라서 그림(``<hp:pic>``) 안에 그래픽으로 박힌 텍스트(출판사 제목·
            도표·캡션 등)는 애초에 분모에 없어 recall이 1.0이어도 누락될 수
            있다. 이미지 내 텍스트는 OCR 영역이라 본 패키지(텍스트 추출)의
            범위를 벗어난다. 이 맹점은 :attr:`image_count`(>0이면 경고)로 보완한다.

            또 하나의 한계: 단어 **집합** 기준이라 같은 단어의 반복 손실이나
            숫자·1~2글자 토큰 손실을 못 본다. 이 맹점은 :attr:`char_recall`이
            보완한다.
        char_recall: 원본 ``<hp:t>`` 글자(한글·영문·숫자) **멀티셋** 대비 출력
            글자 recall(0.0~1.0). :attr:`recall`(단어 집합)이 구조적으로 못 보는
            손실(같은 단어 반복 누락, 숫자·짧은 토큰 누락)을 잡아내는 더 엄격한
            지표다. 출력이 원본 글자를 모두 포함하면 1.0. 빈 문서는 1.0.
        warnings: 단어/글자 recall이 임계값 미만이거나, 객관식 선택지 마커가
            누락되었거나, 본문에 이미지가 있을 때 등 사용자에게 알릴 경고 목록.
        image_count: 본문에 배치된 그림(``<hp:pic>``) 개수. >0이면 이미지 내
            텍스트가 누락되었을 수 있음을 알리는 경고가 :attr:`warnings`에 담긴다.
        extracted_images: image_dir 지정 시 실제 추출된 고유 이미지 파일 수(미지정 0).
        image_map: docparse inject() 호환 매핑. 키는 md 참조 문자열,
            값은 {image_id, file, ext, ocr_eligible, ko_alt}. 미지정 시 빈 dict.
    """

    markdown: str
    recall: float
    warnings: list[str] = field(default_factory=list)
    image_count: int = 0
    char_recall: float = 1.0
    extracted_images: int = 0
    image_map: dict = field(default_factory=dict)


def localname(tag: str) -> str:
    """네임스페이스를 제거한 태그 로컬명을 반환."""
    return tag.split("}")[-1] if "}" in tag else tag


def t_full_text(t_elem) -> str:
    """``<hp:t>``의 전체 텍스트를 추출한다.

    핵심(결함 1): ``t_elem.text``만 읽으면 ``<hp:t>`` 내부의 ``<hp:tab>``/
    ``<hp:lineBreak>`` 등 자식 요소의 tail 텍스트를 통째로 잃는다(객관식 선택지
    ②③⑤가 tab.tail에 들어 있는 경우 등). ``itertext``로 전체를 모으되 tab/
    lineBreak는 공백으로 치환해 단어 경계를 보존한다.
    """
    parts = [t_elem.text or ""]
    for child in t_elem:
        if localname(child.tag) in ("tab", "lineBreak", "br"):
            parts.append(" ")
        else:
            parts.append("".join(child.itertext()))
        parts.append(child.tail or "")
    return "".join(parts)


def is_encrypted_hwpx(filepath: PathLike) -> bool:
    """HWPX가 AES 등으로 암호화되어 있는지 확인.

    ``META-INF/manifest.xml``의 encryption-data 존재 여부로 판단한다.
    암호화된 경우 ``Contents/section0.xml``이 암호문이라 XML 파싱이 실패한다.
    """
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            if "META-INF/manifest.xml" not in zf.namelist():
                return False
            manifest = zf.read("META-INF/manifest.xml")
            return b"encryption-data" in manifest
    except (zipfile.BadZipFile, KeyError, OSError):
        return False


def get_table_rows(table):
    """표에서 행(``hp:tr``) 목록을 반환."""
    return table.findall("hp:tr", NS)


def get_row_cells(row):
    """행에서 셀(``hp:tc``) 목록을 반환."""
    return row.findall("hp:tc", NS)


def get_cell_addr(cell):
    """셀의 ``cellAddr``에서 (colAddr, rowAddr) 논리 위치를 추출. 없으면 (None, None)."""
    addr = cell.find("hp:cellAddr", NS)
    if addr is None:
        return None, None
    return int(addr.get("colAddr", "0")), int(addr.get("rowAddr", "0"))


def get_cell_span(cell):
    """셀의 (rowSpan, colSpan)을 추출.

    주의(결함 3): span은 ``cellAddr``가 아니라 별도 ``<hp:cellSpan>`` 요소에
    있다. ``cellAddr``에는 colAddr/rowAddr(논리 위치)만 있다. ``cellAddr``에서
    span을 읽으면 항상 (1,1)을 반환해 모든 병합이 무시되고 표 정렬이 깨진다.
    """
    span = cell.find("hp:cellSpan", NS)
    if span is None:
        return 1, 1
    return int(span.get("rowSpan", "1")), int(span.get("colSpan", "1"))


def render_cell_lines(cell) -> list[str]:
    """표 셀 안의 텍스트를 문단별 라인 리스트로 추출(reading order 근사).

    중첩표(셀 안의 표)와 글상자(drawText)까지 진입하고 tail 텍스트를 보존한다.
    중첩표는 구조를 평탄화하여 텍스트만 인라인 수집한다.
    """
    lines: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            s = " ".join(" ".join(x for x in buf if x).split())
            if s:
                lines.append(s)
            buf.clear()

    def rec(node):
        for child in node:
            tag = localname(child.tag)
            if tag == "p":
                flush()
                rec(child)
                flush()
            elif tag == "t":
                buf.append(t_full_text(child))
            elif tag == "tbl":
                for t in child.iter():
                    if localname(t.tag) == "t":
                        buf.append(t_full_text(t))
            else:
                rec(child)

    rec(cell)
    flush()
    return lines


def table_to_markdown(
    rows_data: list[list[tuple[str, int]]], merge_fill: bool = False
) -> str:
    """행 순차 표 데이터([(텍스트, colSpan), ...])를 Markdown 표로 변환(폴백 경로).

    ``merge_fill=True``이면 가로 병합(colSpan)으로 덮인 칸을 빈 칸 대신 같은
    값으로 채운다(행 단위로 자족적인 표가 필요한 다운스트림용). 폴백 경로에는
    행 위치 정보가 없어 세로 병합(rowSpan)은 채우지 못한다.
    """
    if not rows_data:
        return ""

    max_cols = max(sum(cs for _, cs in row) for row in rows_data)
    if max_cols == 0:
        return ""

    lines = []
    for row_idx, row in enumerate(rows_data):
        expanded: list[str] = []
        for text, col_span in row:
            expanded.append(text)
            for _ in range(col_span - 1):
                expanded.append(text if merge_fill else "")
        while len(expanded) < max_cols:
            expanded.append("")

        lines.append("| " + " | ".join(expanded[:max_cols]) + " |")
        if row_idx == 0:
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")

    return "\n".join(lines)


def render_table_md(tbl, cell_br: bool = False, merge_fill: bool = False) -> str:
    """표를 Markdown으로 변환한다.

    ``cellAddr``(colAddr/rowAddr) + ``cellSpan``(rowSpan/colSpan) 기반으로 셀을
    정확한 그리드 위치에 배치한다(결함 3 해결). 세로·가로 병합이 있어도 병합으로
    덮인 칸을 빈 칸으로 남겨 열 정렬을 유지한다(GFM은 병합 자체를 표현하지 못하므로
    텍스트는 시작 칸에 두고 나머지는 빈 칸으로 둔다). ``cellAddr``가 없으면 행 순차
    방식으로 폴백한다. 셀 텍스트는 :func:`render_cell_lines`로 추출한다
    (tail·글상자·중첩표 포함).

    ``merge_fill=True``이면 병합으로 덮인 칸을 빈 칸 대신 시작 칸과 같은 값으로
    채운다. 정보량은 같지만 모든 행이 자족적이 되어 LLM 입력·행 단위 파싱에
    유리하다(기본값 False는 GFM 정렬 보존을 우선). Upstage가 병합값을 스팬된 모든
    칸에 복제하는 동작과 동등해진다.
    """
    sep = "<br>" if cell_br else " "

    def cell_text(cell):
        return sep.join(render_cell_lines(cell)).replace("|", "\\|")

    cells = []
    max_r = max_c = 0
    use_grid = True
    for row in get_table_rows(tbl):
        for cell in get_row_cells(row):
            col, r = get_cell_addr(cell)
            if col is None or r is None:
                use_grid = False
                break
            rs, cs = get_cell_span(cell)
            cells.append((r, col, rs, cs, cell_text(cell)))
            max_r = max(max_r, r + rs)
            max_c = max(max_c, col + cs)
        if not use_grid:
            break

    # 폴백: 위치 정보가 없으면 행 순차 방식(colSpan만 펼침)
    if not use_grid or max_r == 0 or max_c == 0:
        rows_data = []
        for row in get_table_rows(tbl):
            row_data = []
            for cell in get_row_cells(row):
                _, col_span = get_cell_span(cell)
                row_data.append((cell_text(cell), col_span))
            rows_data.append(row_data)
        return table_to_markdown(rows_data, merge_fill=merge_fill)

    grid = [["" for _ in range(max_c)] for _ in range(max_r)]
    # 1단계: 시작 칸(anchor)에 값을 둔다(항상 정확).
    for (r, col, rs, cs, text) in cells:
        if 0 <= r < max_r and 0 <= col < max_c:
            grid[r][col] = text  # 병합으로 덮인 칸은 '' 유지 -> 정렬 보존
    # 2단계: merge_fill이면 병합으로 덮인 빈 칸을 시작 칸 값으로 채운다.
    if merge_fill:
        for (r, col, rs, cs, text) in cells:
            for dr in range(rs):
                for dc in range(cs):
                    rr, cc = r + dr, col + dc
                    if (dr or dc) and 0 <= rr < max_r and 0 <= cc < max_c \
                            and grid[rr][cc] == "":
                        grid[rr][cc] = text

    lines = []
    for ri in range(max_r):
        lines.append("| " + " | ".join(grid[ri]) + " |")
        if ri == 0:
            lines.append("| " + " | ".join(["---"] * max_c) + " |")
    return "\n".join(lines)


def render_block_lines(
    para, cell_br: bool = False, merge_fill: bool = False
) -> list[str]:
    """최상위 문단을 reading order로 순회하며 라인 리스트를 생성한다.

    핵심(결함 2): 글상자(drawText) 내부 문단까지 진입하고 표는 Markdown으로
    렌더한다. 기존 구현은 최상위 p의 run>t 직속과 ``.//tbl``만 보아 글상자 내부
    본문을 통째로 누락했다(Workbook류 recall 17~33% -> 100%로 개선). 표 서브트리는
    재방문하지 않아 본문/표 텍스트 중복을 막는다.

    ``merge_fill``은 표 병합 칸 채우기 옵션으로 :func:`render_table_md`에 전달된다.
    """
    lines: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            s = " ".join(" ".join(x for x in buf if x).split())
            if s:
                lines.append(s)
            buf.clear()

    def rec(node):
        for child in node:
            tag = localname(child.tag)
            if tag == "tbl":
                flush()
                md = render_table_md(child, cell_br=cell_br, merge_fill=merge_fill)
                if md:
                    lines.append("")
                    lines.append(md)
                    lines.append("")
            elif tag == "p":
                flush()
                rec(child)
                flush()
            elif tag == "t":
                buf.append(t_full_text(child))
            else:
                rec(child)

    rec(para)
    flush()
    return lines


def _words(s: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(s)}


def _char_counts(s: str) -> "Counter[str]":
    """내용 글자(한글·영문·숫자) 멀티셋."""
    return Counter(_CHAR_RE.findall(s))


def _marker_counts(s: str) -> "Counter[str]":
    """둘러싸인 영숫자 마커(①②③ 등) 멀티셋."""
    return Counter(_MARKER_RE.findall(s))


def _multiset_recall(src: "Counter[str]", out: "Counter[str]") -> float:
    """``src`` 멀티셋이 ``out``에 얼마나 보존됐는지(0.0~1.0). src가 비면 1.0.

    matched = Σ min(src[c], out[c]); recall = matched / Σ src[c]. 즉 같은 글자가
    원본에 n번, 출력에 m번이면 min(n, m)만 보존으로 친다(반복 손실 감지).
    """
    total = sum(src.values())
    if not total:
        return 1.0
    matched = sum(min(n, out.get(c, 0)) for c, n in src.items())
    return matched / total


def count_images(roots) -> int:
    """section root들에서 본문에 배치된 그림(``<hp:pic>``) 개수를 센다.

    그림 안에 그래픽으로 박힌 텍스트(출판사 제목·도표·캡션 등)는 XML에 없어
    텍스트 추출로는 얻을 수 없다. self-recall은 ``<hp:t>`` 텍스트 기준이라 이
    누락을 감지하지 못하므로(맹점), 이미지 존재 자체를 세어 경고에 활용한다.
    배치되지 않은(참조 없는) BinData가 아니라 실제 본문에 놓인 그림만 센다.
    """
    return sum(
        1
        for root in roots
        for el in root.iter()
        if localname(el.tag) == "pic"
    )


def _read_section_roots(filepath: PathLike) -> list:
    """HWPX zip에서 ``Contents/sectionN.xml``들을 파싱해 root 리스트를 반환.

    Raises:
        HwpxEncryptedError: 파일이 암호화되어 있을 때.
        HwpxParseError: 올바른 zip이 아니거나 section XML이 없을 때.
    """
    if is_encrypted_hwpx(filepath):
        raise HwpxEncryptedError(ENCRYPTION_HINT)

    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            section_files = sorted(
                n
                for n in zf.namelist()
                if "section" in n.lower() and n.endswith(".xml") and "Contents/" in n
            )
            if not section_files:
                raise HwpxParseError(
                    "section XML 파일을 찾을 수 없습니다 (Contents/sectionN.xml). "
                    "올바른 HWPX 파일인지 확인하세요."
                )
            roots = []
            for sf in section_files:
                try:
                    roots.append(etree.fromstring(zf.read(sf)))
                except etree.XMLSyntaxError as exc:
                    # zip은 정상이나 내부 section XML이 손상된 경우. lxml 예외가
                    # 그대로 새어 나가지 않도록 HwpxParseError로 감싼다(모든 파싱
                    # 실패는 HwpxError 한 계층으로 잡힌다는 계약 유지).
                    raise HwpxParseError(
                        f"section XML 파싱에 실패했습니다 ({sf}): {exc}"
                    ) from exc
            return roots
    except zipfile.BadZipFile as exc:
        raise HwpxParseError(
            f"올바른 HWPX(zip) 파일이 아닙니다: {filepath}"
        ) from exc


def _render_roots(
    roots, cell_br: bool, merge_fill: bool = False
) -> tuple[str, set[str], str]:
    """section root들을 (Markdown 문자열, 원본 단어 집합, 원본 ``<hp:t>`` 텍스트)로 변환.

    세 번째 반환값(원본 텍스트)은 글자 멀티셋 recall과 마커 보존 가드 계산용이다.
    """
    all_lines: list[str] = []
    gt_words: set[str] = set()
    src_parts: list[str] = []
    for root in roots:
        for t in root.iter():
            if localname(t.tag) == "t":
                txt = t_full_text(t)
                gt_words |= _words(txt)
                src_parts.append(txt)
        for child in root:
            if localname(child.tag) == "p":
                all_lines += render_block_lines(
                    child, cell_br=cell_br, merge_fill=merge_fill
                )

    # 연속 빈 줄 정리
    cleaned: list[str] = []
    prev_blank = False
    for line in all_lines:
        if line.strip() == "":
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False

    return "\n".join(cleaned), gt_words, " ".join(src_parts)


def convert(
    filepath: PathLike,
    *,
    cell_br: bool = False,
    merge_fill: bool = False,
    recall_threshold: float = RECALL_WARN_THRESHOLD,
) -> ConversionResult:
    """HWPX를 Markdown으로 변환하고 자가검증 결과를 함께 반환한다.

    reading order 재귀 순회로 글상자(drawText) 내부 본문까지 수집하고
    ``<hp:t>`` 내부 tail 텍스트(객관식 선택지 등)를 보존한다. 표는 Markdown으로
    변환하며 표 서브트리는 재방문하지 않는다. 변환 후 세 가지 자가검증을 수행한다:
    단어 집합 recall, 글자 멀티셋 recall(:attr:`ConversionResult.char_recall`),
    그리고 객관식 마커 보존 가드. 앞 둘은 ``recall_threshold`` 미만이면 경고를,
    마커 가드는 마커가 하나라도 줄면(임계값 무관) 경고를 결과에 담는다.

    recall의 한계: 단어/글자 recall은 ``<hp:t>`` 텍스트 기준이라 그림
    (``<hp:pic>``) 안에 그래픽으로 박힌 텍스트는 감지하지 못한다(맹점). 이를
    보완하려고 본문 이미지 개수를 :attr:`ConversionResult.image_count`로 반환하고,
    이미지가 있으면 경고를 추가한다(이미지 내 텍스트는 OCR 영역이므로 본 패키지
    범위 밖). 또한 단어 집합 recall은 반복·숫자·짧은 토큰 손실을 못 보는데, 이는
    글자 멀티셋 recall(:attr:`ConversionResult.char_recall`)과 마커 가드가 메운다.

    Args:
        filepath: HWPX 파일 경로(str 또는 Path).
        cell_br: True이면 표 셀 내부 문단을 ``<br>``로 구분한다(긴 지문이 셀 안에
            있는 고사지·보고서에 권장).
        merge_fill: True이면 표 병합(rowSpan/colSpan)으로 덮인 칸을 빈 칸 대신
            시작 칸과 같은 값으로 채운다. 정보량은 같지만 모든 행이 자족적이 되어
            LLM 입력·행 단위 파싱에 유리하다(기본 False는 GFM 열 정렬 보존을 우선).
        recall_threshold: 이 값 미만이면 경고를 추가한다.

    Returns:
        :class:`ConversionResult` (markdown, recall, warnings, image_count,
        char_recall).

    Raises:
        HwpxEncryptedError: 파일이 암호화되어 있을 때.
        HwpxParseError: 올바른 HWPX zip이 아니거나 section XML이 없을 때.
    """
    roots = _read_section_roots(filepath)
    markdown, gt_words, src_text = _render_roots(
        roots, cell_br=cell_br, merge_fill=merge_fill
    )
    image_count = count_images(roots)

    warnings: list[str] = []
    if gt_words:
        out_words = _words(markdown)
        recall = len(gt_words & out_words) / len(gt_words)
        if recall < recall_threshold:
            missing = sorted(gt_words - out_words)[:20]
            warnings.append(
                f"원본 단어 recall {recall:.1%} (<{recall_threshold:.0%}): "
                f"일부 텍스트가 누락되었을 수 있습니다. 누락 의심 단어: {missing}"
            )
    else:
        # 추출 가능한 단어가 없는 문서(빈 문서 등)는 누락이 없으므로 1.0으로 본다.
        recall = 1.0

    # 글자 멀티셋 recall: 단어 집합 recall이 못 보는 반복·숫자·짧은 토큰 손실 감지.
    char_recall = _multiset_recall(_char_counts(src_text), _char_counts(markdown))
    if char_recall < recall_threshold:
        warnings.append(
            f"문자 recall {char_recall:.1%} (<{recall_threshold:.0%}): 반복 텍스트나 "
            "숫자·기호가 일부 누락되었을 수 있습니다(단어 recall이 못 보는 "
            "멀티셋·짧은 토큰 손실)."
        )

    # 마커 보존 가드: 원본<hp:t>에 있던 객관식 선택지 마커(①②③ 등)가 출력에서
    # 줄면 임계값과 무관하게 정확히 경고한다. 시험 문항 무결성에 치명적이며 단어/
    # 글자 recall로는 큰 문서에서 한두 개 손실이 임계값에 안 걸려 묻힐 수 있다.
    lost_markers = _marker_counts(src_text) - _marker_counts(markdown)
    if lost_markers:
        detail = " ".join(f"{m}×{n}" for m, n in sorted(lost_markers.items()))
        warnings.append(
            f"객관식 선택지 마커가 렌더링 중 누락되었습니다: {detail}. "
            "표 셀 병합·중첩 구조에서 마커가 빠졌을 수 있으니 확인하세요."
        )

    if image_count:
        warnings.append(
            f"본문에 이미지 {image_count}개가 있습니다. 이미지 안의 텍스트"
            "(제목·도표·캡션 등)는 추출되지 않으므로, 그래픽에 글자가 있으면 "
            "누락될 수 있습니다(self-recall은 XML 텍스트 기준이라 이를 감지하지 못함)."
        )

    return ConversionResult(
        markdown=markdown,
        recall=recall,
        warnings=warnings,
        image_count=image_count,
        char_recall=char_recall,
    )


def to_markdown(
    filepath: PathLike, *, cell_br: bool = False, merge_fill: bool = False
) -> str:
    """HWPX를 Markdown 문자열로 변환한다(가장 간단한 진입점).

    자가검증 recall이나 경고, 이미지 개수가 필요하면 :func:`convert`를 사용한다.

    Args:
        filepath: HWPX 파일 경로(str 또는 Path).
        cell_br: True이면 표 셀 내부 문단을 ``<br>``로 구분한다.
        merge_fill: True이면 표 병합 칸을 시작 칸 값으로 채운다(:func:`convert` 참조).

    Raises:
        HwpxEncryptedError: 파일이 암호화되어 있을 때.
        HwpxParseError: 올바른 HWPX zip이 아니거나 section XML이 없을 때.
    """
    return convert(filepath, cell_br=cell_br, merge_fill=merge_fill).markdown
