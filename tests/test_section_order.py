"""구역 순서는 recall로 검출되지 않으므로 Markdown 본문 순서를 직접 검사한다."""

from pathlib import Path
import zipfile

import pytest

from conftest import _SEC_HEADER, _SEC_FOOTER
from test_hwpx_tomd import p
from test_xml_backends import _run


def _document(tmp_path, *, order=None, mutate=None):
    path = tmp_path / "sections.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        for index in reversed(range(11)):
            archive.writestr(f"Contents/section{index}.xml",
                             _SEC_HEADER + p(f"구역 {index}") + _SEC_FOOTER)
        if order is not None:
            items = ''.join(f'<opf:item id="s{i}" href="section{i}.xml"/>' for i in range(11))
            refs = ''.join(f'<opf:itemref idref="s{i}"/>' for i in order)
            content = ('<opf:package xmlns:opf="http://www.idpf.org/2007/opf">'
                       f'<opf:manifest>{items}</opf:manifest><opf:spine>{refs}</opf:spine>'
                       '</opf:package>')
            archive.writestr("Contents/content.hpf", mutate(content) if mutate else content)
    return path


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
def test_eleven_sections_without_spine_follow_numeric_order(tmp_path, mode):
    result = _run(_document(tmp_path), mode)["result"]
    assert result["markdown"].splitlines() == [f"구역 {i}" for i in range(11)]
    assert result["recall"] == result["char_recall"] == 1.0


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
def test_eleven_sections_follow_declared_spine_order(tmp_path, mode):
    order = [10, 2, 0, 9, 1, 8, 3, 7, 4, 6, 5]
    result = _run(_document(tmp_path, order=order), mode)["result"]
    assert result["markdown"].splitlines() == [f"구역 {i}" for i in order]
    assert result["recall"] == result["char_recall"] == 1.0


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
@pytest.mark.parametrize("mutation", [
    lambda xml: xml.replace('href="section10.xml"', 'href="missing.xml"'),
    lambda xml: xml.replace('idref="s10"', 'idref="missing"'),
    lambda xml: xml.replace('<opf:itemref idref="s10"/>', ''),
    lambda xml: xml.replace('<opf:itemref idref="s10"/>', '<opf:itemref idref="s9"/>'),
    lambda xml: xml.replace('</opf:package>', ''),
], ids=["missing-file", "missing-id", "unreferenced-section", "duplicate-section", "malformed-hpf"])
def test_invalid_spine_fails_instead_of_silent_reordering_or_dropping(tmp_path, mode, mutation):
    report = _run(_document(tmp_path, order=list(range(11)), mutate=mutation), mode)
    assert report.get("error_type") == "HwpxParseError", report


@pytest.mark.parametrize("mode", ["lxml", "stdlib"])
def test_hwpx_document_generated_root_hrefs_are_readable(mode):
    # HwpxDocument.new() 기반 공개용 합성 파일: header도 spine에 있고 href는 ZIP 루트 기준.
    path = Path(__file__).parent / "fixtures/root-hrefs.hwpx"
    report = _run(path, mode)
    assert "result" in report, report
    markdown = report["result"]["markdown"]
    assert "기존 앞" in markdown and "기존 뒤" in markdown
    assert report["result"]["recall"] == report["result"]["char_recall"] == 1.0
