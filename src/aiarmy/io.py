"""
文档 I/O 层 — 统一的文档→文本转换入口。
开发环境用 doc-read CLI（全局安装），Docker 环境用 python-docx 兜底。
"""
import subprocess
import os
from pathlib import Path


def to_text(file_path: str | Path) -> str:
    """
    将文档转换为纯文本。支持 .txt / .docx / .doc / .pdf。
    策略：
    1. .txt → 直接读
    2. .docx/.doc/.pdf → doc-read CLI（开发）或 python-docx（兜底）
    """
    path = Path(file_path)

    # .txt 直接读
    if path.suffix.lower() == ".txt":
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    # 二进制格式 → 尝试 doc-read CLI
    if path.suffix.lower() in (".docx", ".doc", ".pdf"):
        # 方式 A：doc-read CLI（全局已安装）
        try:
            result = subprocess.run(
                ["doc-read", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            # 如果 doc-read 返回了内容但 returncode 非零，也尝试使用
            if result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 方式 B：python-docx 兜底（Docker 环境无 doc-read CLI）
        try:
            from docx import Document
            doc = Document(str(path))
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text)
            # 也读表格
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    paragraphs.append(" | ".join(cells))
            return "\n".join(paragraphs)
        except ImportError:
            pass

        # 方式 C：终极兜底 — 尝试当文本读（用于某些非标准格式）
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
                if len(content.strip()) > 50:
                    return content
        except Exception:
            pass

        raise RuntimeError(
            f"无法解析 {path.suffix} 文件。请安装 doc-read CLI 或 python-docx。"
            f"\n  开发环境：pip install doc-read"
            f"\n  Docker 环境：pip install python-docx"
        )

    raise ValueError(f"不支持的文件格式: {path.suffix}")


def detect_doc_type_from_path(file_path: str | Path) -> str | None:
    """从文件扩展名推断文档类型"""
    suffix = Path(file_path).suffix.lower()
    if suffix in (".docx", ".doc", ".pdf", ".txt"):
        return None  # 需要读内容才能判断
    return None
