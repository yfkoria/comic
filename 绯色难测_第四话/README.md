# 绯色难测 · 第四话 · 本座带伞

十四页全彩漫画，1024×1536。承接前话，按原作推进校园工作日常，两位教师的关系保持慢热。

<!-- package-status:begin -->
交付包：`绯色难测_第四话_完整包.zip`，包含 14 张原始 PNG、PDF、分镜、制作记录、参考图和导出脚本。

[连续阅读 PDF](绯色难测_第四话.pdf)

ZIP 使用 Deflate 压缩，成稿图片不缩放、不拆分。
<!-- package-status:end -->

- [逐格分镜](第四话分镜.md)
- [逐页制作提示](逐页制作提示.json)
- [生成记录](生成记录.json)
- [最终页序](最终页序.json)
- [图片与 PDF 检查结果](图片检查.json)

按页码从 01 到 14 阅读，每页从上到下，同排从左到右。

| 页码 | 原图 | 页码 | 原图 |
| --- | --- | --- | --- |
| 01 | [page-01.png](page-01.png) | 08 | [page-08.png](page-08.png) |
| 02 | [page-02.png](page-02.png) | 09 | [page-09.png](page-09.png) |
| 03 | [page-03.png](page-03.png) | 10 | [page-10.png](page-10.png) |
| 04 | [page-04.png](page-04.png) | 11 | [page-11.png](page-11.png) |
| 05 | [page-05.png](page-05.png) | 12 | [page-12.png](page-12.png) |
| 06 | [page-06.png](page-06.png) | 13 | [page-13.png](page-13.png) |
| 07 | [page-07.png](page-07.png) | 14 | [page-14.png](page-14.png) |

角色与画风参考随包提供，参考清单见逐页制作提示的 `references`。这些路径均使用包内相对路径，导出脚本会把实际使用的参考 PNG 自动加入交付包；本话其他已完成页面也可用作后续页的参考。生成记录中的旧绝对路径仅供历史溯源，阅读成稿与重新导出不依赖这些路径。最终页序的 `source` 记录当前采用的来源，`history` 独立保存历史版本。

PDF 按原比例无损嵌入十四张成稿 PNG。导出脚本完整解码图片，检查空白和像素重复页，并将 PDF 以原始分辨率还原后逐页核对 RGB 像素。检查文件记录每页字节数、分辨率与 SHA-256；ZIP 另行校验 CRC、文件清单、Markdown 相对链接和绘图提示中的参考路径。

重新导出：在装有 PyMuPDF 和 Pillow 的 Python 环境中执行 `python export_pdf.py`。脚本仅在十四张成稿和全部支持文件齐备时导出。ZIP 使用 Deflate 压缩；若包含 PDF 的 ZIP 超过 100 MiB，将自动改为不含 PDF 的原图包，PDF 仍单独保留。导出不会生成或替换漫画图片，也不会拆分或降低原图分辨率。包内不含原作小说、其他话漫画或旧交付包。
