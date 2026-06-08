# hwpx-tomd 이미지 추출 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `convert`/`to_markdown`에 `image_dir`·`image_ref_prefix` 옵션을 추가해 HWPX 본문 이미지를 추출하고, reading-order 위치에 참조를 삽입하며, docparse `inject()` 호환 매핑 JSON을 생성한다.

**Architecture:** `zipfile`+`lxml`만 사용. `image_dir` 지정 시에만 `BinData/`를 추출하고 `render_block_lines`의 `pic` 분기에서 `![image](prefix+파일명)`을 삽입한다. id→파일 매핑은 zip namelist의 stem 매칭(`imageN` → `BinData/imageN.*`)으로 한다(content.hpf 파싱 불필요). `image_dir=None`이면 현행 동작 100% 불변.

**Tech Stack:** Python 3.10+, lxml, zipfile(표준), pytest.

---

## File Structure

- `src/hwpx_tomd/core.py` — `ConversionResult` 필드 추가, 헬퍼 5개 신설, `render_block_lines`/`_render_roots`/`convert`/`to_markdown` 수정
- `src/hwpx_tomd/cli.py` — `--image-dir`/`--image-prefix` 인자, `_image_map.json` 저장
- `tests/conftest.py` — `make_hwpx`에 `bindata` 인자 추가
- `tests/test_hwpx_tomd.py` — 이미지 테스트 추가
- `docs/superpowers/specs/2026-06-09-image-extraction-design.md` — spec 정정(매핑 방식: stem 매칭)

설계 메모(전체 task 공통):
- 확장자 화이트리스트 `_RASTER_EXTS = {"jpg","jpeg","png","gif","bmp","tiff","tif","webp"}`
- 매핑 JSON 항목: `{ "image_id", "file", "ext", "ocr_eligible", "ko_alt": None }`, 키는 md 참조 문자열 `![image]({prefix}{fname})`
- zip은 `image_dir` 지정 시에만 추가로 2회 연다(매핑 1회 + 추출 1회). 미지정 시 추가 open 0.

---

## Task 1: 하위호환 보장 (ConversionResult 필드 + make_hwpx bindata)

**Files:**
- Modify: `tests/conftest.py`
- Modify: `src/hwpx_tomd/core.py` (`ConversionResult` 106-137)
- Test: `tests/test_hwpx_tomd.py`

- [ ] **Step 1: conftest의 make_hwpx에 bindata 인자 추가**

`tests/conftest.py`의 `_make` 함수를 수정:
```python
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
```

- [ ] **Step 2: 하위호환 테스트 작성 (실패해야 함)**

`tests/test_hwpx_tomd.py` 끝에 추가:
```python
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
```

- [ ] **Step 3: 실패 확인**

Run: `pytest tests/test_hwpx_tomd.py::test_image_dir_none_keeps_current_behavior -v`
Expected: FAIL with `AttributeError: 'ConversionResult' object has no attribute 'extracted_images'`

- [ ] **Step 4: ConversionResult에 필드 추가**

`src/hwpx_tomd/core.py`의 dataclass 본문(현재 133-137)을 다음으로 교체:
```python
    markdown: str
    recall: float
    warnings: list[str] = field(default_factory=list)
    image_count: int = 0
    char_recall: float = 1.0
    extracted_images: int = 0
    image_map: dict = field(default_factory=dict)
```
docstring `Attributes:`에 두 줄 추가:
```
        extracted_images: image_dir 지정 시 실제 추출된 고유 이미지 파일 수(미지정 0).
        image_map: docparse inject() 호환 매핑. 키는 md 참조 문자열,
            값은 {image_id, file, ext, ocr_eligible, ko_alt}. 미지정 시 빈 dict.
```

- [ ] **Step 5: 통과 확인**

Run: `pytest tests/test_hwpx_tomd.py::test_image_dir_none_keeps_current_behavior -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_hwpx_tomd.py src/hwpx_tomd/core.py
git commit -m "feat(images): ConversionResult에 extracted_images·image_map 필드 추가"
```

---

## Task 2: 순수 헬퍼 함수 (_bindata_files, _ocr_eligible)

**Files:**
- Modify: `src/hwpx_tomd/core.py` (count_images 근처에 추가)
- Test: `tests/test_hwpx_tomd.py`

- [ ] **Step 1: 헬퍼 단위 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_hwpx_tomd.py::test_bindata_files_stem_match tests/test_hwpx_tomd.py::test_ocr_eligible -v`
Expected: FAIL with `ImportError: cannot import name '_bindata_files'`

- [ ] **Step 3: 헬퍼 구현**

`src/hwpx_tomd/core.py`의 `count_images` 함수 바로 아래에 추가:
```python
_RASTER_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp"}


def _ocr_eligible(ext: str) -> bool:
    """확장자가 OCR/Vision으로 읽을 수 있는 래스터 포맷이면 True (wmf/emf 등은 False)."""
    return ext.lower() in _RASTER_EXTS


def _bindata_files(zf) -> dict[str, str]:
    """zip에서 binaryItemIDRef(=파일 stem) -> BinData zip 경로 매핑.

    실측상 본문 ``binaryItemIDRef="image1"``은 ``BinData/image1.jpg``의 stem과
    일치하므로 content.hpf 파싱 없이 namelist의 stem 매칭으로 충분하다.
    """
    out: dict[str, str] = {}
    for n in zf.namelist():
        parts = n.split("/")
        if len(parts) >= 2 and parts[-2].lower() == "bindata" and parts[-1]:
            stem = parts[-1].rsplit(".", 1)[0]
            out[stem] = n
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_hwpx_tomd.py::test_bindata_files_stem_match tests/test_hwpx_tomd.py::test_ocr_eligible -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hwpx_tomd/core.py tests/test_hwpx_tomd.py
git commit -m "feat(images): BinData stem 매핑·ocr_eligible 헬퍼 추가"
```

---

## Task 3: 이미지 참조 삽입 (_ImageCtx + render_block_lines/_render_roots)

**Files:**
- Modify: `src/hwpx_tomd/core.py` (`render_block_lines` 350-393, `_render_roots` 479-513, 헬퍼 추가)
- Test: `tests/test_hwpx_tomd.py`

- [ ] **Step 1: 참조 삽입 테스트 작성 (convert 통합 전, 내부 경로 직접 검증)**

```python
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
    # reading order: 앞 문단 < 이미지 < 뒤 문단
    assert md.index("앞 문단") < md.index("![image]") < md.index("뒤 문단")
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_hwpx_tomd.py::test_image_ref_inserted_reading_order -v`
Expected: FAIL with `ImportError: cannot import name '_ImageCtx'`

- [ ] **Step 3: _ImageCtx 추가 + render 분기 구현**

`src/hwpx_tomd/core.py`의 `_bindata_files` 아래에 추가:
```python
class _ImageCtx:
    """이미지 참조 삽입용 컨텍스트. render 중 pic을 만나면 참조를 만들고 사용 id를 모은다."""

    def __init__(self, id_to_file: dict[str, str], prefix: str):
        self.id_to_file = id_to_file   # id -> "BinData/imageN.ext"
        self.prefix = prefix
        self.used: dict[str, str] = {}  # id -> "imageN.ext"(basename), 등장 순서 보존

    def ref_for(self, idref: str) -> "str | None":
        zippath = self.id_to_file.get(idref)
        if not zippath:
            return None
        fname = zippath.split("/")[-1]
        self.used.setdefault(idref, fname)
        return f"![image]({self.prefix}{fname})"
```

`render_block_lines` 시그니처에 `image_ctx=None` 추가하고 `rec` 내부 `tbl`/`p`/`t` 분기 사이에 `pic` 분기를 넣는다. 수정 후 함수:
```python
def render_block_lines(
    para, cell_br: bool = False, merge_fill: bool = False, image_ctx=None
) -> list[str]:
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
            elif tag == "pic" and image_ctx is not None:
                idref = None
                for sub in child.iter():
                    if localname(sub.tag) == "img":
                        idref = sub.get("binaryItemIDRef")
                        break
                if idref:
                    ref = image_ctx.ref_for(idref)
                    if ref:
                        flush()
                        lines.append("")
                        lines.append(ref)
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
```
주의: `pic` 분기는 `image_ctx is not None`일 때만 매칭되므로, `image_ctx=None`(기본)이면 기존처럼 `else: rec(child)`로 떨어져 동작이 완전히 동일하다(pic 내부엔 `<hp:t>`가 없어 무해).

- [ ] **Step 4: _render_roots에 image_ctx 전달**

`_render_roots` 시그니처와 render 호출을 수정:
```python
def _render_roots(
    roots, cell_br: bool, merge_fill: bool = False, image_ctx=None
) -> tuple[str, set[str], str]:
```
함수 내부 `render_block_lines(...)` 호출(현재 497-499)을 다음으로 교체:
```python
                all_lines += render_block_lines(
                    child, cell_br=cell_br, merge_fill=merge_fill,
                    image_ctx=image_ctx,
                )
```

- [ ] **Step 5: 통과 확인**

Run: `pytest tests/test_hwpx_tomd.py::test_image_ref_inserted_reading_order -v`
Expected: PASS

- [ ] **Step 6: 회귀 확인 (기존 동작 불변)**

Run: `pytest tests/ -q`
Expected: 기존 33개 + 신규 전부 PASS (image_ctx 기본 None이라 무영향)

- [ ] **Step 7: Commit**

```bash
git add src/hwpx_tomd/core.py tests/test_hwpx_tomd.py
git commit -m "feat(images): _ImageCtx와 render pic 분기로 reading-order 참조 삽입"
```

---

## Task 4: convert 통합 (추출 + 매핑 JSON)

**Files:**
- Modify: `src/hwpx_tomd/core.py` (`convert` 516-609, 추출 헬퍼 추가)
- Test: `tests/test_hwpx_tomd.py`

- [ ] **Step 1: 추출·매핑·중복 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_hwpx_tomd.py -k "image_extracted_and_mapped or image_prefix or duplicate_image or wmf_not" -v`
Expected: FAIL with `TypeError: convert() got an unexpected keyword argument 'image_dir'`

- [ ] **Step 3: 추출·매핑 헬퍼 추가**

`src/hwpx_tomd/core.py`의 `_ImageCtx` 아래에 추가:
```python
def _extract_used(filepath: PathLike, ctx: "_ImageCtx", image_dir: str) -> int:
    """ctx.used의 이미지를 image_dir로 추출한다(고유 파일만). 추출 수를 반환."""
    import os
    os.makedirs(image_dir, exist_ok=True)
    n = 0
    with zipfile.ZipFile(filepath, "r") as zf:
        for idref, fname in ctx.used.items():
            zippath = ctx.id_to_file.get(idref)
            if not zippath:
                continue
            try:
                data = zf.read(zippath)
            except KeyError:
                continue
            with open(os.path.join(image_dir, fname), "wb") as fh:
                fh.write(data)
            n += 1
    return n


def _build_image_map(ctx: "_ImageCtx") -> dict:
    """ctx.used -> docparse inject() 호환 매핑 dict."""
    out: dict[str, dict] = {}
    for idref, fname in ctx.used.items():
        ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
        rel = f"{ctx.prefix}{fname}"
        ref = f"![image]({rel})"
        out[ref] = {
            "image_id": idref,
            "file": rel,
            "ext": ext,
            "ocr_eligible": _ocr_eligible(ext),
            "ko_alt": None,
        }
    return out
```

- [ ] **Step 4: convert 시그니처·본문 수정**

`convert`의 시그니처(516-522)에 두 파라미터를 추가:
```python
def convert(
    filepath: PathLike,
    *,
    cell_br: bool = False,
    merge_fill: bool = False,
    recall_threshold: float = RECALL_WARN_THRESHOLD,
    image_dir: "str | None" = None,
    image_ref_prefix: str = "",
) -> ConversionResult:
```
본문 앞부분(현재 556-560)을 다음으로 교체:
```python
    roots = _read_section_roots(filepath)

    image_ctx = None
    if image_dir is not None:
        with zipfile.ZipFile(filepath, "r") as zf:
            id_to_file = _bindata_files(zf)
        image_ctx = _ImageCtx(id_to_file, image_ref_prefix)

    markdown, gt_words, src_text = _render_roots(
        roots, cell_br=cell_br, merge_fill=merge_fill, image_ctx=image_ctx
    )
    image_count = count_images(roots)

    extracted_images = 0
    image_map: dict = {}
    if image_ctx is not None:
        extracted_images = _extract_used(filepath, image_ctx, image_dir)
        image_map = _build_image_map(image_ctx)
```
그리고 마지막 `return ConversionResult(...)`(603-609)에 두 필드를 추가:
```python
    return ConversionResult(
        markdown=markdown,
        recall=recall,
        warnings=warnings,
        image_count=image_count,
        char_recall=char_recall,
        extracted_images=extracted_images,
        image_map=image_map,
    )
```

- [ ] **Step 5: 통과 확인**

Run: `pytest tests/test_hwpx_tomd.py -k "image_extracted_and_mapped or image_prefix or duplicate_image or wmf_not" -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/hwpx_tomd/core.py tests/test_hwpx_tomd.py
git commit -m "feat(images): convert(image_dir=)로 추출+매핑 JSON 생성"
```

---

## Task 5: 자가검증 경고 보강

**Files:**
- Modify: `src/hwpx_tomd/core.py` (`convert`의 이미지 경고 블록 596-601)
- Test: `tests/test_hwpx_tomd.py`

- [ ] **Step 1: 경고 테스트 작성**

```python
def test_image_warning_mentions_extracted(make_hwpx, tmp_path):
    src = make_hwpx(PIC_P + PIC_P, bindata={"image1.jpg": b"x"})
    result = convert(src, image_dir=str(tmp_path / "i"))
    joined = " ".join(result.warnings)
    assert "추출" in joined and "OCR" in joined  # 추출 완료 + OCR 필요 안내


def test_image_warning_unchanged_without_dir(make_hwpx):
    src = make_hwpx(PIC_P, bindata={"image1.jpg": b"x"})
    result = convert(src)
    assert any("이미지 1개" in w for w in result.warnings)  # 기존 경고 유지
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_hwpx_tomd.py -k "image_warning" -v`
Expected: `test_image_warning_mentions_extracted` FAIL (현재 경고에 "추출" 없음)

- [ ] **Step 3: 이미지 경고 블록 수정**

`convert`의 이미지 경고 블록(현재 596-601)을 다음으로 교체:
```python
    if image_count:
        if image_dir is not None:
            non_ocr = sum(
                1 for v in image_map.values() if not v["ocr_eligible"]
            )
            msg = (
                f"본문 이미지 {image_count}개 배치(고유 {extracted_images}개) "
                f"추출 완료. 그림 속 텍스트는 OCR 필요(이 패키지 범위 밖)."
            )
            if non_ocr:
                msg += f" 단 {non_ocr}개는 비래스터(WMF 등)라 OCR/Vision 부적합, 변환 필요."
            warnings.append(msg)
        else:
            warnings.append(
                f"본문에 이미지 {image_count}개가 있습니다. 이미지 안의 텍스트"
                "(제목·도표·캡션 등)는 추출되지 않으므로, 그래픽에 글자가 있으면 "
                "누락될 수 있습니다(self-recall은 XML 텍스트 기준이라 이를 감지하지 못함). "
                "이미지 파일이 필요하면 convert(image_dir=...)를 사용하세요."
            )
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_hwpx_tomd.py -k "image_warning" -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hwpx_tomd/core.py tests/test_hwpx_tomd.py
git commit -m "feat(images): image_dir 사용 시 추출·OCR·WMF 경고 보강"
```

---

## Task 6: to_markdown 전달 + CLI

**Files:**
- Modify: `src/hwpx_tomd/core.py` (`to_markdown` 612-)
- Modify: `src/hwpx_tomd/cli.py`
- Test: `tests/test_hwpx_tomd.py`

- [ ] **Step 1: to_markdown·CLI 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_hwpx_tomd.py -k "to_markdown_passes_image or cli_image_dir" -v`
Expected: FAIL with `TypeError: to_markdown() got an unexpected keyword argument 'image_dir'`

- [ ] **Step 3: to_markdown 수정**

`to_markdown`(612-)을 다음으로 교체(기존 docstring은 유지):
```python
def to_markdown(
    filepath: PathLike,
    *,
    cell_br: bool = False,
    merge_fill: bool = False,
    image_dir: "str | None" = None,
    image_ref_prefix: str = "",
) -> str:
    return convert(
        filepath,
        cell_br=cell_br,
        merge_fill=merge_fill,
        image_dir=image_dir,
        image_ref_prefix=image_ref_prefix,
    ).markdown
```

- [ ] **Step 4: CLI 인자·저장 추가**

`src/hwpx_tomd/cli.py`의 `build_parser`에 `--merge-fill` 인자 정의 다음(58행 이후)에 추가:
```python
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
```
`main`의 `convert(...)` 호출(82행)을 다음으로 교체:
```python
        result = convert(
            in_path,
            cell_br=args.cell_br,
            merge_fill=args.merge_fill,
            image_dir=args.image_dir,
            image_ref_prefix=args.image_prefix,
        )
```
경고 출력 루프(111-112) 바로 앞에 매핑 JSON 저장을 추가:
```python
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
```

- [ ] **Step 5: 통과 확인**

Run: `pytest tests/test_hwpx_tomd.py -k "to_markdown_passes_image or cli_image_dir" -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add src/hwpx_tomd/core.py src/hwpx_tomd/cli.py tests/test_hwpx_tomd.py
git commit -m "feat(images): to_markdown 전달 + CLI --image-dir/--image-prefix"
```

---

## Task 7: 전체 회귀 + spec 정정 + 문서

**Files:**
- Modify: `docs/superpowers/specs/2026-06-09-image-extraction-design.md`
- Modify: `CLAUDE.md` 또는 `README.md`(사용 예시)
- Test: 전체

- [ ] **Step 1: 전체 테스트 실행 (회귀 가드)**

Run: `pytest tests/ -v`
Expected: 기존 33개 + 신규 전부 PASS

- [ ] **Step 2: spec의 매핑 방식 정정**

`docs/superpowers/specs/2026-06-09-image-extraction-design.md` 3.2의 "매니페스트(`Contents/content.hpf`)에서 ... 매핑을 읽는다" 문장을, 실제 구현(stem 매칭)에 맞게 정정:
> zip namelist에서 `BinData/{id}.*`의 stem을 `binaryItemIDRef`와 매칭한다(실측상 일치하므로 content.hpf 파싱은 불필요).

같은 정정을 3.4에 반영한다:
- "매니페스트 파싱 실패 → stem 매칭 폴백" 행은 "stem 매칭이 기본 경로"로 수정.
- "BinData 누락·깨짐 → `file=null`(참조 유지)" 행은 "**참조 자체를 생략**(깨진 링크 방지)"으로 수정. 구현상 `id_to_file`에 없는 id는 `ref_for`가 `None`을 반환해 참조를 만들지 않으므로 `image_map`·md 어디에도 깨진 항목이 남지 않는다.

- [ ] **Step 3: README/CLAUDE.md에 사용 예시 추가**

`README.md`(또는 `CLAUDE.md`의 개발 명령어 섹션)에 추가:
```markdown
# 이미지 추출(OCR 파이프라인용)
hwpx-tomd doc.hwpx --image-dir ./imgs --image-prefix img/
# → md에 ![image](img/imageN) 참조, ./imgs에 이미지 + _image_map.json
```
라이브러리:
```python
result = convert("doc.hwpx", image_dir="imgs", image_ref_prefix="img/")
result.image_map      # docparse inject() 호환 매핑
result.extracted_images
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-09-image-extraction-design.md README.md CLAUDE.md
git commit -m "docs(images): spec 매핑 방식 정정 + 사용 예시 추가"
```

---

## 완료 기준
- `image_dir=None`에서 기존 33개 테스트 전부 통과(하위호환).
- `image_dir` 지정 시: 고유 파일 추출, reading-order 참조, docparse 호환 `image_map`, WMF `ocr_eligible=false`, 중복 1회 추출, CLI `_image_map.json` 저장.
- 의존성 추가 0(zipfile+lxml), 무API·읽기전용 철학 유지.
