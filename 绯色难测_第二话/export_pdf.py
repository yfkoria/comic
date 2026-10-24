#!/usr/bin/env python3
"""校验十二张真实漫画页，无损导出 PDF，并生成第二话交付包。"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import fitz
from PIL import Image

DIRECTORY = Path(__file__).resolve().parent
PDF_PATH = DIRECTORY / "绯色难测_第二话.pdf"
ZIP_PATH = DIRECTORY / "绯色难测_第二话_完整包.zip"
PAGE_NAMES = tuple(f"page-{number:02d}.png" for number in range(1, 13))
REQUIRED_SUPPORT = (
    "第二话分镜.md", "逐页制作提示.json", "生成记录.json", "README.md", "export_pdf.py"
)
REFERENCE_FILES = ("参考/绯英校园版.png", "参考/爻光校园版.png", "参考/第一话画风.png")
GENERATED_SUPPORT = ("最终页序.json", "图片检查.json")
EXPECTED_SIZE = (1024, 1536)


def json_write(path: Path, data: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decoded_pixels(path: Path) -> tuple[tuple[int, int], str]:
    with Image.open(path) as picture:
        if picture.format != "PNG":
            raise ValueError(f"扩展名为 PNG，但真实格式不符：{path.name}")
        picture.verify()
    with Image.open(path) as picture:
        picture.load()
        if picture.size != EXPECTED_SIZE:
            raise ValueError(f"{path.name} 尺寸为 {picture.size}，应为 {EXPECTED_SIZE}")
        if picture.mode not in ("RGB", "RGBA"):
            raise ValueError(f"{path.name} 并非 RGB/RGBA 彩色漫画页：{picture.mode}")
        rgba = picture.convert("RGBA")
        if rgba.getextrema()[3] != (255, 255):
            raise ValueError(f"{path.name} 包含透明像素，请先检查成稿")
        rgb = picture.convert("RGB")
        if all(low == high for low, high in rgb.getextrema()):
            raise ValueError(f"{path.name} 为纯色空白图片")
        return picture.size, hashlib.sha256(rgb.tobytes()).hexdigest()


def generation_sources() -> dict[int, list[str]]:
    data = json.loads((DIRECTORY / "生成记录.json").read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("pages", data.get("records", []))
    if not isinstance(data, list):
        raise ValueError("生成记录.json 应包含逐页记录列表")
    sources: dict[int, list[str]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        number = row.get("page", row.get("number"))
        try:
            number = int(number)
        except (ValueError, TypeError):
            continue
        entries: list[str] = []
        for key in ("source", "generated_path", "path", "paths", "sources"):
            value = row.get(key)
            if isinstance(value, str):
                entries.append(value)
            elif isinstance(value, list):
                entries.extend(item for item in value if isinstance(item, str))
        sources[number] = list(dict.fromkeys(entries))
    return sources


def verify_pdf(path: Path, records: list[dict]) -> None:
    with fitz.open(path) as pdf:
        if pdf.page_count != len(PAGE_NAMES):
            raise ValueError(f"PDF 页数错误：{pdf.page_count}")
        for index, record in enumerate(records):
            page = pdf[index]
            width, height = record["resolution"]
            if abs(page.rect.width - width / 2) > .001 or abs(page.rect.height - height / 2) > .001:
                raise ValueError(f"PDF 第 {index + 1} 页比例错误")
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB, alpha=False)
            if (pixmap.width, pixmap.height) != (width, height):
                raise ValueError(f"PDF 第 {index + 1} 页还原尺寸错误")
            actual = hashlib.sha256(pixmap.samples).hexdigest()
            if actual != record["decoded_rgb_sha256"]:
                raise ValueError(f"PDF 第 {index + 1} 页像素未完整保留")


def main() -> None:
    for name in PAGE_NAMES + REQUIRED_SUPPORT + REFERENCE_FILES:
        path = DIRECTORY / name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"缺少真实文件或文件为空：{path}")
        allowed_parent = DIRECTORY / "参考" if name in REFERENCE_FILES else DIRECTORY
        if path.resolve().parent != allowed_parent:
            raise SystemExit(f"交付文件必须位于其白名单目录内，且不能通过软链接跳出：{path}")

    sources = generation_sources()
    records = []
    order = []
    for number, name in enumerate(PAGE_NAMES, 1):
        path = DIRECTORY / name
        size, pixels = decoded_pixels(path)
        digest = sha256(path)
        records.append({
            "page": number, "file": name, "bytes": path.stat().st_size,
            "resolution": list(size), "sha256": digest, "decode": "ok",
            "decoded_rgb_sha256": pixels,
        })
        origins = sources.get(number) or [name]
        order.append({"page": number, "file": name, "source": origins[-1],
                      "sources": origins, "sha256": digest})
    if len({row["sha256"] for row in records}) != len(PAGE_NAMES):
        raise SystemExit("检测到重复页面，请先核对十二页成稿")

    temporary_pdf = PDF_PATH.with_suffix(".pdf.tmp")
    try:
        with fitz.open() as document:
            document.set_metadata({"title": "绯色难测 · 第二话 · 阳光不考试",
                                   "author": "《绯色难测》漫画改编",
                                   "subject": "十二页全彩漫画"})
            for record in records:
                width, height = record["resolution"]
                page = document.new_page(width=width / 2, height=height / 2)
                page.insert_image(page.rect, filename=str(DIRECTORY / record["file"]), keep_proportion=True)
            document.save(temporary_pdf, garbage=4, deflate=True)
        verify_pdf(temporary_pdf, records)
        temporary_pdf.replace(PDF_PATH)
    finally:
        temporary_pdf.unlink(missing_ok=True)

    json_write(DIRECTORY / "最终页序.json", order)
    json_write(DIRECTORY / "图片检查.json", {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "expected_pages": 12, "actual_pages": len(records), "all_decode_ok": True,
        "duplicate_pages": False, "pdf_pages": 12,
        "pdf_rendered_pixels_match_sources": True,
        "pdf_bytes": PDF_PATH.stat().st_size, "pdf_sha256": sha256(PDF_PATH),
        "images": records,
    })

    members = PAGE_NAMES + (PDF_PATH.name,) + REQUIRED_SUPPORT + GENERATED_SUPPORT + REFERENCE_FILES
    temporary_zip = ZIP_PATH.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for name in members:
                archive.write(DIRECTORY / name, arcname="绯色难测_第二话/" + name)
        with zipfile.ZipFile(temporary_zip) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"交付包校验失败：{bad}")
            if len(archive.namelist()) != len(members):
                raise ValueError("交付包文件数量错误")
        temporary_zip.replace(ZIP_PATH)
    finally:
        temporary_zip.unlink(missing_ok=True)
    print(json.dumps({"pages": len(records), "pdf": str(PDF_PATH),
                      "pdf_bytes": PDF_PATH.stat().st_size, "zip": str(ZIP_PATH),
                      "zip_bytes": ZIP_PATH.stat().st_size,
                      "zip_files": len(members), "all_checks_passed": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
