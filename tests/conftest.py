"""테스트 공용 픽스처: 합성 HWPX 파일 생성기.

공개 repo가 될 수 있으므로 출판사·학교 자료 등 저작물은 픽스처에 넣지 않는다.
여기서는 결함 재현용으로 직접 제작한 최소 HWPX(zip + XML)만 동적으로 만든다.

우리 파서가 실제로 읽는 부분만 채운다:
  - ``Contents/section0.xml``  : 본문(파서가 파싱하는 대상)
  - ``META-INF/manifest.xml``  : 암호화 감지(encryption-data 존재 여부)
"""

import zipfile

import pytest

# section0.xml의 네임스페이스 선언 래퍼
_SEC_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<hs:sec "
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
)
_SEC_FOOTER = "</hs:sec>"

# 평문 manifest: encryption-data가 없다.
_PLAIN_MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
    '<manifest:file-entry manifest:full-path="Contents/section0.xml" '
    'manifest:media-type="application/xml"/>'
    "</manifest:manifest>"
)

# 암호화 manifest: encryption-data를 포함한다.
_ENCRYPTED_MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
    '<manifest:file-entry manifest:full-path="Contents/section0.xml" '
    'manifest:media-type="application/xml">'
    '<manifest:encryption-data manifest:checksum-type="SHA-256"/>'
    "</manifest:file-entry>"
    "</manifest:manifest>"
)


@pytest.fixture
def make_hwpx(tmp_path):
    """body(section0.xml의 <hs:sec> 내부 XML 조각)로 합성 HWPX를 만든다.

    Args:
        body_xml: ``<hs:sec>`` 안에 들어갈 본문 XML 조각.
        name: 생성할 파일 이름.
        encrypted: True이면 manifest에 encryption-data를 넣어 암호화로 위장한다.
        bindata: {파일명: bytes} 매핑. 각 항목을 BinData/<파일명>으로 zip에 기록(이미지 추출 테스트용).

    Returns:
        생성된 .hwpx 파일의 :class:`pathlib.Path`.
    """

    def _make(body_xml="", *, name="doc.hwpx", encrypted=False, bindata=None):
        path = tmp_path / name
        section_xml = _SEC_HEADER + body_xml + _SEC_FOOTER
        manifest = _ENCRYPTED_MANIFEST if encrypted else _PLAIN_MANIFEST
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("META-INF/manifest.xml", manifest)
            zf.writestr("Contents/section0.xml", section_xml)
            for fname, data in (bindata or {}).items():
                zf.writestr(f"BinData/{fname}", data)
        return path

    return _make
