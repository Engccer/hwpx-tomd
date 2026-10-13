"""외부 패키지 없는 실행과 두 XML 파서의 결과 계약."""

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from test_hwpx_tomd import (
    DRAWTEXT_P,
    MERGED_TABLE,
    ORPHAN_MARKER_RUN,
    PIC_P,
    TAIL_P,
    p,
    tc,
)


_SOURCE = Path(__file__).resolve().parents[1] / "src"
# 별도 프로세스에서 import하므로 이미 로드한 lxml/엔진이 폴백을 가리지 않는다.
_SCRIPT = r'''
import builtins, dataclasses, json, sys
sys.path.insert(0, sys.argv[1])
mode, path = sys.argv[2:]
if mode in ('ImportError', 'OSError'):
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == 'lxml' or name.startswith('lxml.'):
            raise getattr(builtins, mode)('test unavailable lxml')
        return original_import(name, *args, **kwargs)
    builtins.__import__ = guarded_import
from hwpx_tomd import HwpxError, convert, to_markdown
from hwpx_tomd import core
try:
    result = convert(path)
    assert to_markdown(path) == result.markdown
    print(json.dumps({'backend': core.etree.__name__, 'result': dataclasses.asdict(result)}, ensure_ascii=False))
except HwpxError as exc:
    print(json.dumps({'backend': core.etree.__name__, 'error_type': type(exc).__name__, 'error': str(exc)}, ensure_ascii=False))
'''


def _run(path, mode):
    command = [sys.executable]
    if mode == "stdlib":
        command.append("-S")
    command.extend(["-c", _SCRIPT, str(_SOURCE), mode, str(path)])
    completed = subprocess.run(
        command, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("mode", ["stdlib", "ImportError", "OSError"])
def test_optional_lxml_import_failure_keeps_reading(make_hwpx, mode):
    result = _run(make_hwpx(p("표준 라이브러리만으로 읽기 ①")), mode)
    assert result["backend"] == "xml.etree.ElementTree"
    assert result["result"]["markdown"] == "표준 라이브러리만으로 읽기 ①"
    assert result["result"]["recall"] == 1.0
    assert result["result"]["char_recall"] == 1.0
    assert result["result"]["warnings"] == []


_INNER = "<hp:tbl><hp:tr>" + tc(0, 0, "안쪽 첫째") + tc(1, 0, "안쪽 둘째") + "</hp:tr></hp:tbl>"


def _wrapper(outside="", after="", inner=_INNER):
    return (
        "<hp:p><hp:run><hp:tbl><hp:tr><hp:tc>"
        '<hp:cellAddr colAddr="0" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/>'
        "<hp:subList>" + outside + "<hp:p><hp:run>" + inner
        + "</hp:run></hp:p>" + after + "</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    )


@pytest.mark.parametrize("body", [
    TAIL_P + DRAWTEXT_P + MERGED_TABLE,
    _wrapper(),
    _wrapper(p("표 앞 본문 보존"), p("표 뒤 본문 보존")),
    _wrapper(inner=_INNER + _INNER.replace("안쪽", "형제")),
    p("합법 공백\t줄바꿈\n보존") + p("불법\x00제어문자\x01복구"),
    p("정상 본문") + ORPHAN_MARKER_RUN,
    p("그림 경고") + PIC_P,
    '<!--section 주석--><?section metadata?>' + p('① 앞<!--주석-->뒤 ② 앞<?instruction metadata?>뒤'),
], ids=["text-and-table", "wrapper", "outside-text", "sibling-tables", "control-bytes", "missing-markers", "image-warning", "comments-and-pis"])
def test_backends_return_identical_conversion_results(make_hwpx, body):
    probe = subprocess.run([sys.executable, "-c", "from lxml import etree"], capture_output=True)
    if probe.returncode:
        pytest.skip("lxml 비교 환경이 설치되어 있지 않습니다")
    path = make_hwpx(body)
    lxml_result = _run(path, "lxml")
    stdlib_result = _run(path, "stdlib")
    assert lxml_result["backend"] == "lxml.etree"
    assert stdlib_result["backend"] == "xml.etree.ElementTree"
    assert stdlib_result["result"] == lxml_result["result"]


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
def test_comments_and_processing_instructions_preserve_text(make_hwpx, mode):
    body = '<!--section 주석--><?section metadata?>' + p('① 앞<!--주석-->뒤 ② 앞<?instruction metadata?>뒤')
    result = _run(make_hwpx(body), mode)["result"]
    assert result["markdown"] == "① 앞뒤 ② 앞뒤"
    assert result["recall"] == result["char_recall"] == 1.0
    assert result["warnings"] == []


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
@pytest.mark.parametrize("siblings", [False, True])
def test_nested_tables_keep_surrounding_text_and_siblings(make_hwpx, mode, siblings):
    inner = _INNER + (_INNER.replace("안쪽", "형제") if siblings else "")
    body = _wrapper(p("표 앞 본문"), p("표 뒤 본문"), inner)
    result = _run(make_hwpx(body), mode)["result"]
    for text in ["표 앞 본문", "표 뒤 본문", "안쪽 첫째", "안쪽 둘째"]:
        assert result["markdown"].count(text) == 1
    assert "| 안쪽 첫째 | 안쪽 둘째 |" in result["markdown"]
    if siblings:
        assert "| 형제 첫째 | 형제 둘째 |" in result["markdown"]
    assert result["recall"] == result["char_recall"] == 1.0
    assert result["warnings"] == []


@pytest.mark.parametrize("section", [b"<unclosed>", b"<unclosed>\x00"])
def test_stdlib_broken_xml_keeps_parse_error(tmp_path, section):
    path = tmp_path / "broken.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", section)
    result = _run(path, "stdlib")
    assert result["backend"] == "xml.etree.ElementTree"
    assert result["error_type"] == "HwpxParseError"
    assert "section XML 파싱에 실패했습니다" in result["error"]
    if b"\x00" in section:
        assert "제거하고 재시도했으나 여전히 손상" in result["error"]


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
@pytest.mark.parametrize("control_byte", [b"", b"\x00"])
@pytest.mark.parametrize("encoding", [b"NOT-A-CODEC", b"UTF-32"])
def test_invalid_xml_encoding_keeps_parse_error(tmp_path, mode, control_byte, encoding):
    path = tmp_path / "invalid-encoding.hwpx"
    section = b'<?xml version="1.0" encoding="' + encoding + b'"?><sec>' + control_byte + b'</sec>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", section)
    result = _run(path, mode)
    assert result["error_type"] == "HwpxParseError"
    assert "Contents/section0.xml" in result["error"]
    assert ("제거하고 재시도했으나 여전히 손상" in result["error"]) == bool(control_byte)
