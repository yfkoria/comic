#!/usr/bin/env python3
"""将同目录的十张漫画页按顺序、无裁切地嵌入 PDF。"""

from __future__ import annotations

import struct
from pathlib import Path

from reportlab import rl_config
from reportlab.pdfgen import canvas

rl_config.useA85 = 0


DIRECTORY = Path(__file__).resolve().parent
OUTPUT = DIRECTORY / "绯色难测_第一话.pdf"
PAGE_NAMES = tuple(f"page-{number:02d}.png" for number in range(1, 11))
POINTS_PER_PIXEL = 72 / 144


def png_size(path: Path) -> tuple[int, int]:
    """只读取 PNG 头中的尺寸，不缩放或改写源图。"""
    with path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"不是有效的 PNG 文件：{path.name}")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise ValueError(f"图片尺寸无效：{path.name}")
    return width, height


def main() -> None:
    pages: list[tuple[Path, tuple[int, int]]] = []
    for name in PAGE_NAMES:
        path = DIRECTORY / name
        if not path.is_file():
            raise SystemExit(f"缺少漫画页：{path}\n请先放齐 page-01.png 至 page-10.png。")
        if path.resolve().parent != DIRECTORY:
            raise SystemExit(f"漫画页必须位于脚本所在目录内：{path}")
        try:
            pages.append((path, png_size(path)))
        except ValueError as error:
            raise SystemExit(str(error)) from error

    temporary_output = OUTPUT.with_suffix(".pdf.tmp")
    try:
        document = canvas.Canvas(str(temporary_output), pageCompression=1)
        document.setTitle("绯色难测 · 第一话 · 同学，上课时间翻墙")
        document.setAuthor("《绯色难测》漫画改编")
        for path, (pixel_width, pixel_height) in pages:
            page_width = pixel_width * POINTS_PER_PIXEL
            page_height = pixel_height * POINTS_PER_PIXEL
            document.setPageSize((page_width, page_height))
            document.drawImage(
                str(path),
                0,
                0,
                width=page_width,
                height=page_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            document.showPage()
        document.save()
        temporary_output.replace(OUTPUT)
    except Exception:
        temporary_output.unlink(missing_ok=True)
        raise
    print(f"已导出 10 页：{OUTPUT}")


if __name__ == "__main__":
    main()
