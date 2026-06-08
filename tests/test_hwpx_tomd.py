"""hwpx_tomd 회귀 테스트.

세 결함(① tail 손실, ② 글상자 본문 누락, ③ 표 병합 무시)을 재현하는 합성
HWPX로 보존 여부를 단언하고, recall 자가검증·암호화 예외·파싱 오류·CLI 동작을
검증한다. 이 결함들은 회귀가 잦으므로 가드를 명시적으로 둔다.
"""

import zipfile

import pytest

from hwpx_tomd import (
    ConversionResult,
    HwpxEncryptedError,
    HwpxParseError,
    convert,
    to_markdown,
)
from hwpx_tomd.cli import main
from hwpx_tomd.core import (
    count_images,
    _char_counts,
    _marker_counts,
    _multiset_recall,
)


# --------------------------------------------------------------------------
# section0.xml 본문 조각 빌더
# --------------------------------------------------------------------------
def p(text):
    """하나의 <hp:t>를 가진 최상위 문단."""
    return f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"


def tc(col, row, text, *, colspan=1, rowspan=1):
    """cellAddr/cellSpan과 본문을 가진 표 셀."""
    return (
        "<hp:tc>"
        f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
        f'<hp:cellSpan colSpan="{colspan}" rowSpan="{rowspan}"/>'
        "<hp:subList>"
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
        "</hp:subList>"
        "</hp:tc>"
    )


# 결함 ①: <hp:t> 내부 tab/lineBreak 뒤 tail에 객관식 선택지가 들어 있다.
TAIL_P = (
    "<hp:p><hp:run>"
    "<hp:t>① 사과<hp:tab/>② 바나나<hp:lineBreak/>③ 포도</hp:t>"
    "</hp:run></hp:p>"
)

# 결함 ②: 도형(rect) 안 drawText의 subList에 본문이 들어 있다.
DRAWTEXT_P = (
    "<hp:p><hp:run>"
    "<hp:rect>"
    "<hp:drawText><hp:subList>"
    "<hp:p><hp:run><hp:t>글상자 안의 비밀 문장</hp:t></hp:run></hp:p>"
    "</hp:subList></hp:drawText>"
    "</hp:rect>"
    "</hp:run></hp:p>"
)

# 결함 ③: 첫 행이 colSpan=2로 병합된 2x2 표.
MERGED_TABLE = (
    "<hp:p><hp:run><hp:tbl>"
    "<hp:tr>" + tc(0, 0, "헤더", colspan=2) + "</hp:tr>"
    "<hp:tr>" + tc(0, 1, "에이") + tc(1, 1, "비이") + "</hp:tr>"
    "</hp:tbl></hp:run></hp:p>"
)

# 첫 열이 rowSpan=2로 세로 병합된 2x2 표(merge_fill 세로 병합 검증용).
ROWSPAN_TABLE = (
    "<hp:p><hp:run><hp:tbl>"
    "<hp:tr>" + tc(0, 0, "좌", rowspan=2) + tc(1, 0, "우상") + "</hp:tr>"
    "<hp:tr>" + tc(1, 1, "우하") + "</hp:tr>"
    "</hp:tbl></hp:run></hp:p>"
)

# 본문에 그림(hp:pic)이 박힌 문단. 이미지 안 텍스트는 XML에 없다(OCR 영역).
PIC_P = (
    "<hp:p><hp:run>"
    '<hp:pic><hp:img binaryItemIDRef="image1"/></hp:pic>'
    "</hp:run></hp:p>"
)

# 마커 가드 검증용: 최상위 <hp:run>(p로 감싸지 않음)에 객관식 마커가 있다.
# 렌더러는 최상위 <hp:p> 자식만 순회하므로 이 마커는 출력에서 빠진다. 즉 원본
# <hp:t>에는 있고(src 집계됨) 출력에는 없는 상황 = 렌더링 누락 = 가드가 발동.
ORPHAN_MARKER_RUN = (
    "<hp:run><hp:t>① 사과 ② 바나나 ③ 포도</hp:t></hp:run>"
)


# 셀 내부에 두 문단을 가진 단일 셀 표(cell_br 검증용).
MULTILINE_CELL_TABLE = (
    "<hp:p><hp:run><hp:tbl>"
    "<hp:tr>"
    "<hp:tc>"
    '<hp:cellAddr colAddr="0" rowAddr="0"/>'
    '<hp:cellSpan colSpan="1" rowSpan="1"/>'
    "<hp:subList>"
    "<hp:p><hp:run><hp:t>첫째 문단</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>둘째 문단</hp:t></hp:run></hp:p>"
    "</hp:subList>"
    "</hp:tc>"
    "</hp:tr>"
    "</hp:tbl></hp:run></hp:p>"
)


# --------------------------------------------------------------------------
# 결함 회귀 가드
# --------------------------------------------------------------------------
def test_defect1_tail_text_preserved(make_hwpx):
    """결함 ①: tab/lineBreak tail의 객관식 선택지가 보존되어야 한다."""
    md = to_markdown(make_hwpx(TAIL_P))
    assert "① 사과 ② 바나나 ③ 포도" in md
    assert "바나나" in md  # tab.tail
    assert "포도" in md  # lineBreak.tail


def test_defect2_drawtext_body_collected(make_hwpx):
    """결함 ②: 글상자(drawText) 내부 본문이 수집되어야 한다."""
    md = to_markdown(make_hwpx(DRAWTEXT_P))
    assert "글상자 안의 비밀 문장" in md


def test_defect3_merged_table_grid(make_hwpx):
    """결함 ③: 병합 셀이 그리드에 정확히 배치되고 열 정렬이 유지되어야 한다."""
    md = to_markdown(make_hwpx(MERGED_TABLE))
    table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert table_lines[0] == "| 헤더 |  |"  # colSpan=2 -> 덮인 칸은 빈 칸
    assert table_lines[1] == "| --- | --- |"
    assert table_lines[2] == "| 에이 | 비이 |"


# --------------------------------------------------------------------------
# 공개 API
# --------------------------------------------------------------------------
def test_convert_returns_dataclass(make_hwpx):
    result = convert(make_hwpx(p("간단한 문장 하나")))
    assert isinstance(result, ConversionResult)
    assert isinstance(result.markdown, str)
    assert "간단한 문장 하나" in result.markdown


def test_recall_full_on_clean_doc(make_hwpx):
    """결함이 모두 잡힌 문서는 recall 1.0, 경고 없음이어야 한다."""
    body = TAIL_P + DRAWTEXT_P + MERGED_TABLE + p("추가 본문 문단입니다")
    result = convert(make_hwpx(body))
    assert result.recall == 1.0
    assert result.warnings == []


def test_recall_empty_doc(make_hwpx):
    """추출 단어가 없는 문서는 recall 1.0으로 본다(누락 없음)."""
    result = convert(make_hwpx(""))
    assert result.recall == 1.0
    assert result.warnings == []


def test_cell_br_option(make_hwpx):
    path = make_hwpx(MULTILINE_CELL_TABLE)
    assert "첫째 문단 둘째 문단" in to_markdown(path)
    assert "첫째 문단<br>둘째 문단" in to_markdown(path, cell_br=True)


def test_accepts_str_and_path(make_hwpx):
    path = make_hwpx(p("경로 타입 테스트"))
    assert to_markdown(path) == to_markdown(str(path))


# --------------------------------------------------------------------------
# 신규: 이미지 존재 경고 (self-recall의 맹점 보완)
# --------------------------------------------------------------------------
def test_image_count_and_warning(make_hwpx):
    """본문에 그림이 있으면 image_count가 잡히고 경고가 추가되어야 한다.
    이미지 안 텍스트는 XML에 없어 self-recall은 1.0이지만(맹점), 경고로 알린다."""
    result = convert(make_hwpx(p("본문 텍스트") + PIC_P))
    assert result.image_count == 1
    assert result.recall == 1.0  # 텍스트 누락은 없음
    assert any("이미지" in w for w in result.warnings)


def test_multiple_images_counted(make_hwpx):
    result = convert(make_hwpx(PIC_P + p("사이 본문") + PIC_P))
    assert result.image_count == 2
    assert count_images  # 헬퍼가 공개되어 있음


def test_no_image_no_warning(make_hwpx):
    """그림이 없으면 image_count=0, 이미지 경고도 없어야 한다(오탐 방지)."""
    result = convert(make_hwpx(p("그림 없는 깨끗한 문서")))
    assert result.image_count == 0
    assert not any("이미지" in w for w in result.warnings)


def test_cli_image_warning_to_stderr(make_hwpx, capsys):
    code = main([str(make_hwpx(p("본문") + PIC_P)), "--stdout"])
    assert code == 0
    assert "이미지" in capsys.readouterr().err


# --------------------------------------------------------------------------
# 신규: merge_fill (병합 칸 채우기 옵션)
# --------------------------------------------------------------------------
def test_merge_fill_colspan(make_hwpx):
    """가로 병합(colSpan=2): 기본은 빈 칸, merge_fill이면 시작 칸 값으로 채움."""
    path = make_hwpx(MERGED_TABLE)
    default = [ln for ln in to_markdown(path).splitlines() if ln.startswith("|")]
    filled = [ln for ln in to_markdown(path, merge_fill=True).splitlines()
              if ln.startswith("|")]
    assert default[0] == "| 헤더 |  |"          # 기본: 덮인 칸 빈 칸
    assert filled[0] == "| 헤더 | 헤더 |"        # merge_fill: 같은 값
    assert filled[2] == "| 에이 | 비이 |"        # 비병합 행은 그대로


def test_merge_fill_rowspan(make_hwpx):
    """세로 병합(rowSpan=2): merge_fill이면 아래 칸도 시작 칸 값으로 채움."""
    path = make_hwpx(ROWSPAN_TABLE)
    default = [ln for ln in to_markdown(path).splitlines() if ln.startswith("|")]
    filled = [ln for ln in to_markdown(path, merge_fill=True).splitlines()
              if ln.startswith("|")]
    assert default[0] == "| 좌 | 우상 |"
    assert default[2] == "|  | 우하 |"           # 기본: 덮인 칸 빈 칸
    assert filled[2] == "| 좌 | 우하 |"          # merge_fill: 위 값 채움


def test_merge_fill_recall_unaffected(make_hwpx):
    """merge_fill은 값 반복일 뿐이라 recall(집합 기반)에 영향이 없어야 한다."""
    body = MERGED_TABLE + ROWSPAN_TABLE
    assert convert(make_hwpx(body), merge_fill=True).recall == 1.0


def test_cli_merge_fill(make_hwpx, capsys):
    code = main([str(make_hwpx(MERGED_TABLE)), "--stdout", "--merge-fill"])
    assert code == 0
    assert "| 헤더 | 헤더 |" in capsys.readouterr().out


# --------------------------------------------------------------------------
# 신규: char_recall (글자 멀티셋 recall: 단어 집합 recall의 맹점 보완)
# --------------------------------------------------------------------------
def test_multiset_recall_math():
    """멀티셋 recall: matched = Σ min(src, out) / Σ src. 반복 손실을 감지한다."""
    assert _multiset_recall(_char_counts("가가"), _char_counts("가")) == 0.5
    assert _multiset_recall(_char_counts("가가a1"), _char_counts("y 가 가 a 1")) == 1.0
    assert _multiset_recall(_char_counts(""), _char_counts("무엇이든")) == 1.0  # 빈 src


def test_char_counts_only_content_chars():
    """글자 멀티셋은 한글·영문·숫자만 센다(공백·기호·마커 제외)."""
    assert dict(_char_counts("가 나!a1 ②")) == {"가": 1, "나": 1, "a": 1, "1": 1}


def test_char_recall_full_on_clean_doc(make_hwpx):
    """결함이 모두 잡힌 문서는 char_recall도 1.0이어야 한다(반복·숫자 손실 없음)."""
    body = TAIL_P + DRAWTEXT_P + MERGED_TABLE + p("추가 본문 12345 반복 반복")
    result = convert(make_hwpx(body))
    assert result.char_recall == 1.0
    assert result.recall == 1.0
    assert result.warnings == []


def test_char_recall_field_default(make_hwpx):
    """char_recall 필드가 결과에 존재하고 기본 문서에서 1.0이어야 한다."""
    result = convert(make_hwpx(p("간단한 본문")))
    assert hasattr(result, "char_recall")
    assert result.char_recall == 1.0


# --------------------------------------------------------------------------
# 신규: 마커 보존 가드 (①②③ 등 객관식 선택지가 렌더링 중 누락되면 경고)
# --------------------------------------------------------------------------
def test_marker_counts_enclosed_alphanumerics():
    """둘러싸인 영숫자 블록(U+2460~U+24FF) 마커만 멀티셋으로 센다."""
    assert dict(_marker_counts("① a ② ② ③ 가나1")) == {"①": 1, "②": 2, "③": 1}


def test_marker_guard_no_false_positive(make_hwpx):
    """정상 보존되는 문서(tail의 ①②③)는 마커 경고가 없어야 한다(오탐 방지)."""
    result = convert(make_hwpx(TAIL_P))
    assert "① 사과 ② 바나나 ③ 포도" in result.markdown
    assert not any("마커" in w for w in result.warnings)
    assert result.char_recall == 1.0


def test_marker_guard_fires_on_loss(make_hwpx):
    """원본<hp:t>에 있던 마커가 출력에서 빠지면 임계값과 무관하게 경고한다."""
    result = convert(make_hwpx(p("정상 본문") + ORPHAN_MARKER_RUN))
    # 마커가 출력에서 사라졌으므로 마커 경고가 떠야 한다.
    assert any("마커" in w for w in result.warnings)
    # 손실된 마커 ①②③이 경고 문구에 적시되어야 한다.
    marker_warn = next(w for w in result.warnings if "마커" in w)
    assert "①" in marker_warn and "②" in marker_warn and "③" in marker_warn
    # 멀티셋 char_recall도 1.0 미만으로 손실을 반영한다.
    assert result.char_recall < 1.0


def test_cli_marker_warning_to_stderr(make_hwpx, capsys):
    code = main([str(make_hwpx(p("본문") + ORPHAN_MARKER_RUN)), "--stdout"])
    assert code == 0
    assert "마커" in capsys.readouterr().err


# --------------------------------------------------------------------------
# 오류 경로
# --------------------------------------------------------------------------
def test_encrypted_raises(make_hwpx):
    path = make_hwpx(p("암호화된 내용"), encrypted=True)
    with pytest.raises(HwpxEncryptedError):
        to_markdown(path)


def test_no_section_raises(tmp_path):
    path = tmp_path / "nosection.hwpx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
    with pytest.raises(HwpxParseError):
        to_markdown(path)


def test_bad_zip_raises(tmp_path):
    path = tmp_path / "bad.hwpx"
    path.write_bytes(b"this is not a zip file")
    with pytest.raises(HwpxParseError):
        to_markdown(path)


def test_broken_section_xml_raises(tmp_path):
    """zip은 정상이나 section XML이 손상된 경우 lxml 예외가 아니라
    HwpxParseError로 감싸져야 한다(모든 파싱 실패는 HwpxError 한 계층)."""
    path = tmp_path / "broken.hwpx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", "<hs:sec><hp:p><unclosed")
    with pytest.raises(HwpxParseError):
        to_markdown(path)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def test_cli_writes_md_file(make_hwpx):
    path = make_hwpx(p("CLI 파일 출력 문장"))
    code = main([str(path)])
    assert code == 0
    out_md = path.with_suffix(".md")
    assert out_md.exists()
    assert "CLI 파일 출력 문장" in out_md.read_text(encoding="utf-8")


def test_cli_output_option(make_hwpx, tmp_path):
    path = make_hwpx(p("출력 경로 지정"))
    target = tmp_path / "custom.md"
    code = main([str(path), "-o", str(target)])
    assert code == 0
    assert target.exists()
    assert "출력 경로 지정" in target.read_text(encoding="utf-8")


def test_cli_stdout(make_hwpx, capsys):
    path = make_hwpx(p("표준출력 문장"))
    code = main([str(path), "--stdout"])
    assert code == 0
    assert "표준출력 문장" in capsys.readouterr().out


def test_cli_missing_file(tmp_path):
    code = main([str(tmp_path / "does_not_exist.hwpx")])
    assert code == 2


def test_cli_encrypted_exit_code(make_hwpx, capsys):
    path = make_hwpx(p("내용"), encrypted=True)
    code = main([str(path)])
    assert code == 3
    assert "암호화" in capsys.readouterr().err


# --------------------------------------------------------------------------
# 이미지 추출
# --------------------------------------------------------------------------
def test_image_dir_none_keeps_current_behavior(make_hwpx):
    """image_dir 미지정 시 현행 동작 불변: 참조 없음, 추출 0, 맵 빈 dict, 경고 카운트 유지."""
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"JPEGDATA"})
    result = convert(src)
    assert "![image]" not in result.markdown
    assert result.extracted_images == 0
    assert result.image_map == {}
    assert result.image_count == 1  # 경고용 pic 카운트는 그대로


def test_bindata_files_stem_match(make_hwpx):
    from hwpx_tomd.core import _bindata_files
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"x", "image8.wmf": b"y"})
    import zipfile
    with zipfile.ZipFile(src) as zf:
        m = _bindata_files(zf)
    assert m["image1"] == "BinData/image1.jpg"
    assert m["image8"] == "BinData/image8.wmf"


def test_ocr_eligible():
    from hwpx_tomd.core import _ocr_eligible
    assert _ocr_eligible("jpg") is True
    assert _ocr_eligible("PNG") is True
    assert _ocr_eligible("wmf") is False
    assert _ocr_eligible("") is False


def test_image_ref_inserted_reading_order(make_hwpx):
    """_render_roots에 image_ctx를 주면 pic 위치에 참조가 삽입된다."""
    import zipfile
    from hwpx_tomd.core import (
        _read_section_roots, _render_roots, _bindata_files, _ImageCtx,
    )
    src = make_hwpx(p("앞 문단") + PIC_P + p("뒤 문단"),
                    bindata={"image1.jpg": b"x"})
    roots = _read_section_roots(src)
    with zipfile.ZipFile(src) as zf:
        id_to_file = _bindata_files(zf)
    ctx = _ImageCtx(id_to_file, "img/")
    md, _, _ = _render_roots(roots, cell_br=False, image_ctx=ctx)
    assert "![image](img/image1.jpg)" in md
    assert ctx.used == {"image1": "image1.jpg"}
    assert md.index("앞 문단") < md.index("![image]") < md.index("뒤 문단")


def test_image_extracted_and_mapped(make_hwpx, tmp_path):
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"JPEGDATA"})
    out = tmp_path / "imgs"
    result = convert(src, image_dir=str(out))
    assert (out / "image1.jpg").read_bytes() == b"JPEGDATA"
    assert result.extracted_images == 1
    assert "![image](image1.jpg)" in result.markdown
    assert result.image_map == {
        "![image](image1.jpg)": {
            "image_id": "image1", "file": "image1.jpg", "ext": "jpg",
            "ocr_eligible": True, "ko_alt": None,
        }
    }


def test_image_prefix_applied(make_hwpx, tmp_path):
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"x"})
    result = convert(src, image_dir=str(tmp_path / "i"), image_ref_prefix="img/")
    assert "![image](img/image1.jpg)" in result.markdown
    assert result.image_map["![image](img/image1.jpg)"]["file"] == "img/image1.jpg"


def test_duplicate_image_extracted_once(make_hwpx, tmp_path):
    src = make_hwpx(PIC_P + PIC_P, bindata={"image1.jpg": b"x"})
    result = convert(src, image_dir=str(tmp_path / "i"))
    assert result.markdown.count("![image](image1.jpg)") == 2  # 참조 2회
    assert result.extracted_images == 1                          # 파일 1개
    assert len(result.image_map) == 1


def test_wmf_not_ocr_eligible(make_hwpx, tmp_path):
    body = '<hp:p><hp:run><hp:pic><hp:img binaryItemIDRef="image8"/></hp:pic></hp:run></hp:p>'
    src = make_hwpx(body, bindata={"image8.wmf": b"x"})
    result = convert(src, image_dir=str(tmp_path / "i"))
    assert result.image_map["![image](image8.wmf)"]["ocr_eligible"] is False


def test_image_warning_mentions_extracted(make_hwpx, tmp_path):
    src = make_hwpx(PIC_P + PIC_P, bindata={"image1.jpg": b"x"})
    result = convert(src, image_dir=str(tmp_path / "i"))
    joined = " ".join(result.warnings)
    assert "추출" in joined and "OCR" in joined  # 추출 완료 + OCR 필요 안내


def test_image_warning_unchanged_without_dir(make_hwpx):
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"x"})
    result = convert(src)
    assert any("이미지 1개" in w for w in result.warnings)


def test_to_markdown_passes_image_dir(make_hwpx, tmp_path):
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"x"})
    md = to_markdown(src, image_dir=str(tmp_path / "i"))
    assert "![image](image1.jpg)" in md
    assert (tmp_path / "i" / "image1.jpg").exists()


def test_cli_image_dir_writes_map(make_hwpx, tmp_path):
    import json
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"x"})
    out = tmp_path / "imgs"
    rc = main([str(src), "--stdout", "--image-dir", str(out), "--image-prefix", "img/"])
    assert rc == 0
    assert (out / "image1.jpg").exists()
    m = json.loads((out / "_image_map.json").read_text(encoding="utf-8"))
    assert "![image](img/image1.jpg)" in m


def test_wmf_warning_text(make_hwpx, tmp_path):
    body = '<hp:p><hp:run><hp:pic><hp:img binaryItemIDRef="image8"/></hp:pic></hp:run></hp:p>'
    src = make_hwpx(body, bindata={"image8.wmf": b"x"})
    result = convert(src, image_dir=str(tmp_path / "i"))
    joined = " ".join(result.warnings)
    assert "비래스터" in joined and "OCR/Vision 부적합" in joined
