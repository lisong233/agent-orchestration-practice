"""
完整评估脚本 — 对训练集全量回测，输出完整的分类指标。

用法：
  python eval/backtest.py                  # 纯规则模式（不需要 API key）
  python eval/backtest.py --llm            # LLM 增强模式（需要 ANTHROPIC_AUTH_TOKEN）
  python eval/backtest.py --verbose        # 逐文档打印详细结果

输出：
  - 混淆矩阵（通过/不通过）
  - Precision / Recall / F1（每类 + 宏平均）
  - 按文档类型分组统计
  - 错误详情
"""
import json, sys, asyncio, argparse
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

TXT_DIR = BASE / "训练集" / "convert_text"
LABELS_PATH = BASE / "data" / "labels_mapped.json"


def load_data():
    """加载全部测试数据"""
    with open(LABELS_PATH, encoding="utf-8") as f:
        labels = json.load(f)

    docs = []
    for txt_file in sorted(TXT_DIR.glob("*.txt")):
        with open(txt_file, encoding="utf-8") as f:
            text = f.read()
        label = labels.get(txt_file.name, "???")
        docs.append({
            "file": txt_file.name,
            "text": text,
            "label": label,
        })
    return docs


def detect_doc_type(text: str) -> str:
    if "科技项目计划任务书" in text[:500]:
        return "计划任务书"
    if "职工技术创新项目立项申请书" in text[:500]:
        return "立项申请书"
    return "未知"


async def run_evaluation(docs: list, use_llm: bool = False, verbose: bool = False):
    """运行全量回测"""
    from src.agent_orchestration.graph import AuditPipeline

    pipeline = AuditPipeline(use_llm=use_llm)

    results = []
    for doc in docs:
        doc_type = detect_doc_type(doc["text"])
        state = await pipeline.run(
            doc["text"], intent="综合评审",
            verbose=verbose
        )

        predicted = state.result.label if state.result else "错误"
        correct = predicted == doc["label"]

        results.append({
            "file": doc["file"],
            "label": doc["label"],
            "predicted": predicted,
            "correct": correct,
            "doc_type": doc_type,
            "reason": state.result.reason if state.result else state.error,
            "error": state.error,
        })

        if verbose:
            status = "✓" if correct else "✗"
            print(f"  {status} {doc['label']:4s} → {predicted:4s} | {doc_type} | {doc['file'][:50]}")

    return results


def compute_metrics(results: list) -> dict:
    """计算完整的分类指标"""
    # 混淆矩阵
    tp = sum(1 for r in results if r["label"] == "通过" and r["correct"])
    tn = sum(1 for r in results if r["label"] == "不通过" and r["correct"])
    fp = sum(1 for r in results if r["predicted"] == "通过" and r["label"] == "不通过")
    fn = sum(1 for r in results if r["predicted"] == "不通过" and r["label"] == "通过")

    # Precision / Recall / F1
    pos_precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    pos_recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    pos_f1 = 2 * pos_precision * pos_recall / (pos_precision + pos_recall) if (pos_precision + pos_recall) > 0 else 0

    neg_precision = tn / (tn + fn) if (tn + fn) > 0 else 0
    neg_recall = tn / (tn + fp) if (tn + fp) > 0 else 0
    neg_f1 = 2 * neg_precision * neg_recall / (neg_precision + neg_recall) if (neg_precision + neg_recall) > 0 else 0

    total = len(results)
    accuracy = sum(1 for r in results if r["correct"]) / total if total else 0

    return {
        "total": total,
        "accuracy": accuracy,
        "confusion_matrix": {
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        },
        "通过": {
            "precision": pos_precision,
            "recall": pos_recall,
            "f1": pos_f1,
            "support": tp + fn,
        },
        "不通过": {
            "precision": neg_precision,
            "recall": neg_recall,
            "f1": neg_f1,
            "support": tn + fp,
        },
        "macro_avg": {
            "precision": (pos_precision + neg_precision) / 2,
            "recall": (pos_recall + neg_recall) / 2,
            "f1": (pos_f1 + neg_f1) / 2,
        },
    }


def print_report(results: list, metrics: dict):
    """打印格式化评估报告"""
    m = metrics
    cm = m["confusion_matrix"]

    print(f"\n{'='*60}")
    print(f"  评 估 报 告")
    print(f"{'='*60}")

    # 混淆矩阵
    print(f"\n  混淆矩阵")
    print(f"  {'':>12} {'预测通过':>10} {'预测不通过':>10}")
    print(f"  {'实际通过':>12} {cm['tp']:>10} {cm['fn']:>10}")
    print(f"  {'实际不通过':>12} {cm['fp']:>10} {cm['tn']:>10}")

    # 整体指标
    print(f"\n  综合准确率: {m['accuracy']:.1%} ({sum(1 for r in results if r['correct'])}/{m['total']})")

    # 分类指标
    print(f"\n  {'':>12} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>8}")
    for cls in ["通过", "不通过"]:
        c = m[cls]
        print(f"  {cls:>12} {c['precision']:>9.1%} {c['recall']:>9.1%} {c['f1']:>9.1%} {c['support']:>8}")

    macro = m["macro_avg"]
    print(f"  {'宏平均':>12} {macro['precision']:>9.1%} {macro['recall']:>9.1%} {macro['f1']:>9.1%}")

    # 按文档类型分组
    for dtype in ["立项申请书", "计划任务书"]:
        d_results = [r for r in results if r["doc_type"] == dtype]
        if not d_results:
            continue
        d_correct = sum(1 for r in d_results if r["correct"])
        d_pass = sum(1 for r in d_results if r["label"] == "通过")
        d_fail = sum(1 for r in d_results if r["label"] == "不通过")
        d_tp = sum(1 for r in d_results if r["label"] == "通过" and r["correct"])
        print(f"\n  【{dtype}】准确率: {d_correct}/{len(d_results)} = {d_correct/len(d_results):.1%}")
        print(f"    通过 Recall: {d_tp}/{d_pass}" + (f" = {d_tp/d_pass:.1%}" if d_pass else " N/A"))
        print(f"    样本: 通过{d_pass} / 不通过{d_fail}")

    # 错误详情
    errors = [r for r in results if not r["correct"]]
    if errors:
        print(f"\n  ⚠️ 预测错误 ({len(errors)}个):")
        for r in errors:
            print(f"    {r['label']} → {r['predicted']} | {r['doc_type']} | {r['file'][:50]}")
            reason = r.get("reason", r.get("error", ""))
            if reason:
                print(f"    原因: {reason[:100]}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AI 军团 — 全量回测评估")
    parser.add_argument("--llm", action="store_true", help="启用 LLM 增强模式")
    parser.add_argument("--verbose", "-v", action="store_true", help="逐文档打印")
    args = parser.parse_args()

    docs = load_data()
    print(f"加载 {len(docs)} 篇文档 (通过 {sum(1 for d in docs if d['label']=='通过')} / "
          f"不通过 {sum(1 for d in docs if d['label']=='不通过')})")
    print(f"模式: {'LLM 增强' if args.llm else '纯规则引擎'}")

    results = asyncio.run(run_evaluation(docs, use_llm=args.llm, verbose=args.verbose))
    metrics = compute_metrics(results)
    print_report(results, metrics)

    return 0 if metrics["accuracy"] >= 0.6 else 1


if __name__ == "__main__":
    sys.exit(main())
