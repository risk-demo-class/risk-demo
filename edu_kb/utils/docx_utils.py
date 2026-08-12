# -*- coding: utf-8 -*-
"""
docx（Word 讲义） -> Markdown 转换工具

纯标准库实现（zipfile + xml.etree），无需安装 python-docx。
支持：
  - 标题样式（heading N / 一级标题~六级标题 / 文档主标题 / 次标题）
  - 代码样式（代码样式 / HTML Code / HTML Preformatted / HTML Typewriter）
  - 表格（Table Grid 等）
  - 图片（word/media 下的图片抽取到 images 目录，并替换为 Markdown 图片引用）
"""
import os
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _q(tag: str) -> str:
    """构造带命名空间的标签"""
    return f"{{{W_NS}}}{tag}"


def _read_relationships(zf: zipfile.ZipFile) -> dict:
    """读取 word/_rels/document.xml.rels，返回 rId -> target 映射"""
    rels = {}
    try:
        root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        for rel in root:
            rid = rel.get("Id")
            target = rel.get("Target") or ""
            if rid:
                rels[rid] = target
    except KeyError:
        pass
    return rels


def _read_styles(zf: zipfile.ZipFile) -> dict:
    """读取 styles.xml，返回 styleId -> 样式名 映射"""
    styles = {}
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
        for style in root:
            sid = style.get(f"{{{W_NS}}}styleId")
            name_el = style.find(f"{_q('name')}")
            if sid and name_el is not None:
                styles[sid] = name_el.get(f"{{{W_NS}}}val") or ""
    except KeyError:
        pass
    return styles


def _style_to_heading(style_name: str):
    """
    将样式名映射为 Markdown 标题级别。
    返回 1-6 的整数，非标题返回 None。
    """
    if not style_name:
        return None
    name = style_name.strip()

    # 英文 heading N
    m = re.fullmatch(r"heading\s*([1-6])", name, re.IGNORECASE)
    if m:
        return int(m.group(1))

    # 中文“标题 N”
    m = re.fullmatch(r"标题\s*([1-6])", name)
    if m:
        return int(m.group(1))

    # 中文“一级标题”~“六级标题”（在“文档主标题”之下，整体 +1 级）
    level_cn = {
        "一级标题": 2,
        "二级标题": 3,
        "三级标题": 4,
        "四级标题": 5,
        "五级标题": 6,
        "六级标题": 6,
        "半括号标题（五级）": 6,
        "圆括号标题（六级标题）": 6,
    }
    if name in level_cn:
        return level_cn[name]

    # 文档主标题 / 次标题
    if name in ("文档主标题", "Title", "文档标题"):
        return 1
    if name in ("次标题", "Subtitle", "副标题"):
        return 2
    return None


def _is_code_style(style_name: str) -> bool:
    if not style_name:
        return False
    name = style_name.strip()
    return any(
        kw in name
        for kw in ("代码", "Code", "Preformatted", "Typewriter", "token", "token")
    )


def _is_table_header_style(style_name: str) -> bool:
    return bool(style_name) and ("表头" in style_name or "Header" in style_name)


def _extract_paragraph(zf: zipfile.ZipFile, rels: dict, p_el, images_dir: Path) -> str:
    """
    提取段落内容（文本 + 图片），返回 Markdown 片段
    """
    parts = []
    style_name = ""
    pPr = p_el.find(_q("pPr"))
    if pPr is not None:
        pStyle = pPr.find(_q("pStyle"))
        if pStyle is not None:
            style_name = pStyle.get(f"{{{W_NS}}}val") or ""

    # 遍历段落内部所有节点（保留顺序）
    for child in p_el:
        tag = child.tag
        if tag == _q("r"):
            # 一个 run
            for rc in child:
                if rc.tag == _q("t"):
                    parts.append(rc.text or "")
                elif rc.tag == _q("tab"):
                    parts.append("\t")
                elif rc.tag == _q("br"):
                    parts.append("\n")
                elif rc.tag == _q("drawing"):
                    img_md = _extract_drawing(zf, rels, rc, images_dir)
                    if img_md:
                        parts.append(img_md)
                elif rc.tag == _q("footnoteReference"):
                    continue
        elif tag == _q("hyperlink"):
            for rc in child:
                if rc.tag == _q("r"):
                    for rc2 in rc:
                        if rc2.tag == _q("t"):
                            parts.append(rc2.text or "")
                        elif rc2.tag == _q("drawing"):
                            img_md = _extract_drawing(zf, rels, rc2, images_dir)
                            if img_md:
                                parts.append(img_md)
        elif tag == _q("smartTag"):
            for rc in child:
                if rc.tag == _q("r"):
                    for rc2 in rc:
                        if rc2.tag == _q("t"):
                            parts.append(rc2.text or "")
        elif tag == _q("bookmarkStart") or tag == _q("bookmarkEnd"):
            continue

    text = "".join(parts).strip()

    heading_level = _style_to_heading(style_name)
    if heading_level:
        if text:
            return f"{'#' * heading_level} {text}"
        return ""

    if _is_code_style(style_name) and text:
        return f"```\n{text}\n```"

    return text


def _extract_drawing(zf: zipfile.ZipFile, rels: dict, drawing_el, images_dir: Path) -> str:
    """从 drawing 元素中提取图片，保存到 images 目录并返回 Markdown 引用"""
    try:
        blip = drawing_el.find(f".//{{{A_NS}}}blip")
        if blip is None:
            return ""
        # 注意：r:embed 使用的是 officeDocument 关系命名空间（R_NS），而非包级 REL_NS
        embed = blip.get(f"{{{R_NS}}}embed")
        if not embed or embed not in rels:
            return ""
        target = rels[embed]
        # target 形如 media/image1.png
        media_name = os.path.basename(target.replace("\\", "/"))
        if not media_name:
            return ""

        images_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w.\-]", "_", media_name)
        dest = images_dir / safe_name
        # 重名保护
        if not dest.exists():
            dest.write_bytes(zf.read(f"word/{target.lstrip('/')}"))
        return f"![{Path(media_name).stem}](images/{safe_name})"
    except Exception:
        return ""


def _extract_table(zf: zipfile.ZipFile, rels: dict, tbl_el, images_dir: Path) -> str:
    """提取表格为 Markdown 表格"""
    rows = []
    for tr in tbl_el.findall(_q("tr")):
        cells = []
        for tc in tr.findall(_q("tc")):
            cell_texts = []
            for p in tc.findall(_q("p")):
                cell_texts.append(_extract_paragraph(zf, rels, p, images_dir))
            cells.append(" ".join(t for t in cell_texts if t).replace("\n", " "))
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    normalized = [r + [""] * (col_count - len(r)) for r in rows]
    lines = []
    header = normalized[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def docx_to_markdown(docx_path: str, output_dir: str = None, images_subdir: str = "images") -> dict:
    """
    将 docx 文件转换为 Markdown。

    :param docx_path: 源 docx 文件路径
    :param output_dir: 输出目录（md 与 images 目录都在此目录下）
    :param images_subdir: 图片输出子目录名
    :return: {"md_path": str, "md_content": str, "image_count": int}
    """
    docx_path = str(docx_path)
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"指定的 docx 文件不存在：{docx_path}")

    docx_name = Path(docx_path).stem
    output_dir_obj = Path(output_dir) if output_dir else Path(docx_path).parent
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir_obj / images_subdir

    with zipfile.ZipFile(docx_path) as zf:
        rels = _read_relationships(zf)
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find(_q("body"))

        md_parts = []
        image_count = 0
        if body is not None:
            for child in body:
                if child.tag == _q("p"):
                    line = _extract_paragraph(zf, rels, child, images_dir)
                    if line:
                        md_parts.append(line)
                elif child.tag == _q("tbl"):
                    table_md = _extract_table(zf, rels, child, images_dir)
                    if table_md:
                        md_parts.append(table_md)
                elif child.tag == _q("sectPr"):
                    continue

    md_content = "\n\n".join(md_parts).strip() + "\n"

    if images_dir.exists():
        image_count = len(list(images_dir.glob("*")))

    md_path = None
    if output_dir:
        md_path = str(output_dir_obj / f"{docx_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    return {
        "md_path": md_path,
        "md_content": md_content,
        "image_count": image_count,
        "docx_path": docx_path,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = docx_to_markdown(sys.argv[1], output_dir="output")
        print(result)
