#!/usr/bin/env python3
"""验证十四张成稿，无损导出第五话 PDF 与可独立阅读的交付包。"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import fitz
from PIL import Image

DIRECTORY = Path(__file__).resolve().parent
EPISODE = "绯色难测_第五话"
TITLE = "不可测变量"
PAGE_COUNT = 14
EXPECTED_PANELS = 64
EXPECTED_SIZE = (1024, 1536)
PAGE_NAMES = tuple(f"page-{number:02d}.png" for number in range(1, PAGE_COUNT + 1))
PDF_PATH = DIRECTORY / f"{EPISODE}.pdf"
FULL_ZIP_PATH = DIRECTORY / f"{EPISODE}_完整包.zip"
IMAGE_ZIP_PATH = DIRECTORY / f"{EPISODE}_原图包.zip"
GITHUB_FILE_LIMIT = 100 * 1024 * 1024
REQUIRED_SUPPORT = (
    "第五话分镜.md", "逐页制作提示.json", "生成记录.json", "README.md", "export_pdf.py"
)
GENERATED_SUPPORT = ("最终页序.json", "图片检查.json")
REFERENCE_FILES = ()  # 使用逐页制作提示 references 自动收集包内 PNG 参考。
PACKAGE_BEGIN = "<!-- package-status:begin -->"
PACKAGE_END = "<!-- package-status:end -->"


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


def require_file(name: str) -> Path:
    path = DIRECTORY / name
    allowed_parent = DIRECTORY / "参考" if name.startswith("参考/") else DIRECTORY
    if path.resolve().parent != allowed_parent:
        raise ValueError(f"交付文件越出白名单目录或包含跳出目录的软链接：{name}")
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"缺少真实文件或文件为空：{name}")
    return path


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
            raise ValueError(f"{path.name} 不是 RGB/RGBA 彩色漫画页")
        if picture.convert("RGBA").getextrema()[3] != (255, 255):
            raise ValueError(f"{path.name} 存在透明像素，请先检查成稿")
        rgb = picture.convert("RGB")
        if all(low == high for low, high in rgb.getextrema()):
            raise ValueError(f"{path.name} 为纯色空白图片")
        return picture.size, hashlib.sha256(rgb.tobytes()).hexdigest()


def records_from_json(name: str) -> list[dict]:
    data = json.loads(require_file(name).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("pages", data.get("records", []))
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError(f"{name} 应包含逐页记录列表")
    return data


def generation_sources() -> dict[int, dict]:
    result: dict[int, dict] = {}
    for row in records_from_json("生成记录.json"):
        try:
            number = int(row.get("page", row.get("number")))
        except (ValueError, TypeError):
            continue
        if number in result:
            raise ValueError(f"生成记录含重复页码：{number}")
        source = row.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"第 {number} 页缺少当前采用的 source，不能用历史列表代替")
        history = row.get("history", row.get("sources", row.get("paths", [])))
        if isinstance(history, str):
            history = [history]
        if not isinstance(history, list):
            history = []
        # source 是当前采用的成稿，历史列表的顺序不得改变这一选择。
        result[number] = {"source": source if isinstance(source, str) and source else None,
                          "history": history}
    if set(result) != set(range(1, PAGE_COUNT + 1)):
        raise ValueError(f"生成记录页码应覆盖 1 至 {PAGE_COUNT}，实际为 {sorted(result)}")
    return result


def prompt_references() -> tuple[tuple[str, ...], int]:
    references = []
    pages = set()
    count = 0
    panel_count = 0
    for row in records_from_json("逐页制作提示.json"):
        try:
            page = int(row.get("page", row.get("number")))
        except (ValueError, TypeError) as error:
            raise ValueError("制作提示缺少有效页码") from error
        if page in pages:
            raise ValueError(f"制作提示含重复页码：{page}")
        pages.add(page)
        panels = row.get("panels")
        if not isinstance(panels, list) or not panels:
            raise ValueError(f"第 {page} 页缺少逐格分镜")
        panel_count += len(panels)
        values = row.get("references", [])
        if not isinstance(values, list):
            raise ValueError(f"第 {page} 页 references 应为列表")
        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"第 {page} 页存在非字符串参考路径")
            parsed = urlsplit(value)
            name = unquote(parsed.path)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError(f"绘图参考必须是包内相对路径：{value}")
            if name != posixpath.normpath(name) or name.startswith("/") or "\\" in name:
                raise ValueError(f"绘图参考路径不规范：{value}")
            if name not in PAGE_NAMES and not (
                name.startswith("参考/") and len(Path(name).parts) == 2 and Path(name).suffix.lower() == ".png"
            ):
                raise ValueError(f"绘图参考不在漫画页或参考目录内：{value}")
            require_file(name)
            references.append(name)
            count += 1
    if pages != set(range(1, PAGE_COUNT + 1)):
        raise ValueError(f"制作提示页码应覆盖 1 至 {PAGE_COUNT}，实际为 {sorted(pages)}")
    if panel_count != EXPECTED_PANELS:
        raise ValueError(f"逐页提示总格数为 {panel_count}，应为 {EXPECTED_PANELS}")
    return tuple(dict.fromkeys(references)), count


def verify_pdf(path: Path, images: list[dict]) -> None:
    with fitz.open(path) as document:
        if document.page_count != PAGE_COUNT:
            raise ValueError(f"PDF 页数错误：{document.page_count}")
        for index, record in enumerate(images):
            page = document[index]
            width, height = record["resolution"]
            if abs(page.rect.width - width / 2) > .001 or abs(page.rect.height - height / 2) > .001:
                raise ValueError(f"PDF 第 {index + 1} 页比例错误")
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB, alpha=False)
            if (pixmap.width, pixmap.height) != (width, height):
                raise ValueError(f"PDF 第 {index + 1} 页还原尺寸错误")
            if hashlib.sha256(pixmap.samples).hexdigest() != record["decoded_rgb_sha256"]:
                raise ValueError(f"PDF 第 {index + 1} 页像素未完整保留")


def export_pdf(images: list[dict]) -> None:
    temporary = PDF_PATH.with_suffix(".pdf.tmp")
    try:
        with fitz.open() as document:
            document.set_metadata({"title": f"绯色难测 · 第五话 · {TITLE}",
                                   "author": "《绯色难测》漫画改编",
                                   "subject": f"{PAGE_COUNT} 页全彩漫画"})
            for record in images:
                width, height = record["resolution"]
                page = document.new_page(width=width / 2, height=height / 2)
                page.insert_image(page.rect, filename=str(DIRECTORY / record["file"]), keep_proportion=True)
            document.save(temporary, garbage=4, deflate=True)
        verify_pdf(temporary, images)
        temporary.replace(PDF_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def update_readme(include_pdf: bool) -> None:
    path = DIRECTORY / "README.md"
    text = path.read_text(encoding="utf-8")
    if text.count(PACKAGE_BEGIN) != 1 or text.count(PACKAGE_END) != 1:
        raise ValueError("README 缺少唯一的交付状态标记，请保留 package-status 标记")
    if include_pdf:
        section = (f"交付包：`{FULL_ZIP_PATH.name}`，包含 {PAGE_COUNT} 张原始 PNG、PDF、分镜、"
                   "制作记录、参考图和导出脚本。\n\n"
                   f"[连续阅读 PDF]({PDF_PATH.name})\n\n"
                   "ZIP 使用 Deflate 压缩，成稿图片不缩放、不拆分。")
    else:
        section = (f"原图包：`{IMAGE_ZIP_PATH.name}`，包含 {PAGE_COUNT} 张原始 PNG、分镜、"
                   "制作记录、参考图和导出脚本，**不含 PDF**。\n\n"
                   f"PDF `{PDF_PATH.name}` 单独交付；请从交付页面另行下载，或在解压后的目录运行导出脚本。"
                   "因包含 PDF 的完整 ZIP 超过 GitHub 的 100 MiB 单文件上限，原图包省去重复的 PDF 内容。"
                   "原始 PNG 和 PDF 的画面质量保持不变。")
    before = text.split(PACKAGE_BEGIN, 1)[0]
    after = text.split(PACKAGE_END, 1)[1]
    path.write_text(before + PACKAGE_BEGIN + "\n" + section + "\n" + PACKAGE_END + after, encoding="utf-8")


def markdown_targets(text: str) -> list[str]:
    targets = []
    inline = r'!?\[[^\]\n]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)'
    definitions = r'^\s*\[[^\]\n]+\]:\s*(?:<([^>]+)>|(\S+))'
    html = r'''(?:src|href)\s*=\s*["']([^"']+)["']'''
    for pattern in (inline, definitions):
        targets.extend(first or second for first, second in re.findall(pattern, text, flags=re.MULTILINE))
    targets.extend(re.findall(html, text, flags=re.IGNORECASE))
    return targets


def verify_package_links(members: tuple[str, ...], references: tuple[str, ...]) -> int:
    available = set(members)
    for name in references:
        if name not in available:
            raise ValueError(f"制作提示参考不在交付包内：{name}")
    checked = 0
    for name in members:
        if not name.endswith(".md"):
            continue
        text = (DIRECTORY / name).read_text(encoding="utf-8")
        for target in markdown_targets(text):
            parsed = urlsplit(target)
            if parsed.scheme in ("http", "https", "mailto") or parsed.netloc:
                continue
            if parsed.scheme:
                raise ValueError(f"Markdown 存在不可移植的链接：{name} → {target}")
            link_path = unquote(parsed.path)
            if not link_path:
                continue
            if link_path.startswith("/") or "\\" in link_path:
                raise ValueError(f"Markdown 应使用包内相对路径：{name} → {target}")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), link_path))
            if resolved not in available:
                raise ValueError(f"Markdown 链接目标不在交付包内：{name} → {target}")
            checked += 1
    return checked


def create_zip(path: Path, members: tuple[str, ...]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as archive:
        for name in members:
            archive.write(require_file(name), arcname=EPISODE + "/" + name)
    with zipfile.ZipFile(path) as archive:
        expected = {EPISODE + "/" + name for name in members}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(members):
            raise ValueError("ZIP 文件清单不符或含重复条目")
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC 校验失败：{bad}")


def main() -> None:
    for name in PAGE_NAMES + REQUIRED_SUPPORT + REFERENCE_FILES:
        require_file(name)
    references, reference_count = prompt_references()
    sources = generation_sources()
    images = []
    order = []
    for number, name in enumerate(PAGE_NAMES, 1):
        path = require_file(name)
        size, pixels = decoded_pixels(path)
        digest = sha256(path)
        images.append({"page": number, "file": name, "bytes": path.stat().st_size,
                       "resolution": list(size), "sha256": digest, "decode": "ok",
                       "decoded_rgb_sha256": pixels})
        source = sources.get(number, {})
        order.append({"page": number, "file": name, "source": source.get("source") or name,
                      "history": source.get("history", []), "sha256": digest})
    if len({row["decoded_rgb_sha256"] for row in images}) != PAGE_COUNT:
        raise ValueError("检测到像素相同的重复页面，请先核对全部成稿")
    export_pdf(images)
    json_write(DIRECTORY / "最终页序.json", order)
    extra_references = tuple(name for name in references if name not in PAGE_NAMES + REFERENCE_FILES)
    base_members = PAGE_NAMES + REQUIRED_SUPPORT + GENERATED_SUPPORT + REFERENCE_FILES + extra_references
    temporary_zip = DIRECTORY / f"{EPISODE}_交付包.zip.tmp"
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "expected_pages": PAGE_COUNT, "actual_pages": len(images),
              "storyboard_panels": EXPECTED_PANELS, "all_decode_ok": True,
              "duplicate_pages": False, "pdf_pages": PAGE_COUNT,
              "pdf_rendered_pixels_match_sources": True, "pdf_bytes": PDF_PATH.stat().st_size,
              "pdf_sha256": sha256(PDF_PATH), "images": images}
    try:
        for include_pdf in (True, False):
            update_readme(include_pdf)
            members = base_members + ((PDF_PATH.name,) if include_pdf else ())
            markdown_count = verify_package_links(members, references)
            report.update({"package_includes_pdf": include_pdf,
                           "markdown_relative_links_checked": markdown_count,
                           "prompt_reference_links_checked": reference_count,
                           "markdown_and_prompt_references_in_package": True})
            json_write(DIRECTORY / "图片检查.json", report)
            create_zip(temporary_zip, members)
            if temporary_zip.stat().st_size <= GITHUB_FILE_LIMIT:
                output = FULL_ZIP_PATH if include_pdf else IMAGE_ZIP_PATH
                temporary_zip.replace(output)
                stale = IMAGE_ZIP_PATH if include_pdf else FULL_ZIP_PATH
                stale.unlink(missing_ok=True)
                break
            if not include_pdf:
                raise ValueError("不含 PDF 的原图包仍超过 100 MiB；保留原图与 PDF，未发布超限 ZIP")
        else:
            raise ValueError("未能生成交付包")
    finally:
        temporary_zip.unlink(missing_ok=True)
    print(json.dumps({"pages": PAGE_COUNT, "panels": EXPECTED_PANELS, "pdf": str(PDF_PATH),
                      "pdf_bytes": PDF_PATH.stat().st_size, "zip": str(output),
                      "zip_bytes": output.stat().st_size, "zip_files": len(members),
                      "zip_contains_pdf": include_pdf, "zip_crc_verified": True,
                      "markdown_relative_links_checked": markdown_count,
                      "prompt_reference_links_checked": reference_count,
                      "github_limit_bytes": GITHUB_FILE_LIMIT,
                      "pdf_exceeds_github_limit": PDF_PATH.stat().st_size > GITHUB_FILE_LIMIT,
                      "all_checks_passed": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
