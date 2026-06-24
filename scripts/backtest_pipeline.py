"""
P3 管线回测 — 对全量训练集跑管线，验证准确率。
使用单事件循环，比逐个 asyncio.run() 快很多。
"""
import json, asyncio, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aiarmy.graph import AuditPipeline


async def main():
    BASE = Path(__file__).parent.parent
    TXT_DIR = BASE / "训练集" / "convert_text"
    LABELS_PATH = BASE / "data" / "labels_mapped.json"

    with open(LABELS_PATH, encoding="utf-8") as f:
        labels = json.load(f)

    pipeline = AuditPipeline(use_llm=False)
    correct = total = 0

    for txt_file, label in labels.items():
        path = TXT_DIR / txt_file
        if not path.exists():
            print(f"⚠️ 文件不存在: {txt_file}")
            continue

        with open(path, encoding="utf-8") as f:
            text = f.read()

        state = await pipeline.run(text)
        total += 1
        is_correct = state.result.label == label
        correct += 1 if is_correct else 0

        status = "✓" if is_correct else "✗"
        title = state.fields.title if state.fields else "N/A"
        dtype = state.doc_type.value if state.doc_type else "?"
        print(f"{status} {label:4s} → {state.result.label:4s} | {dtype:6s} | {txt_file[:50]}")

    print(f"\n准确率: {correct}/{total} = {correct/total:.1%}" if total else "N/A")

    # 按类型统计
    from collections import defaultdict
    by_type = defaultdict(lambda: {"correct": 0, "total": 0})
    for txt_file, label in labels.items():
        path = TXT_DIR / txt_file
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        state = await pipeline.run(text)
        dt = state.doc_type.value if state.doc_type else "?"
        by_type[dt]["total"] += 1
        if state.result.label == label:
            by_type[dt]["correct"] += 1

    for dt, stats in by_type.items():
        print(f"  [{dt}] {stats['correct']}/{stats['total']} = {stats['correct']/stats['total']:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
