"""
全量 LLM 回测（v5.1 prompt 大修后）——在 NAS 容器内运行。
输入：/app/_backtest/<文件名>.txt（预解析文本）+ /app/_backtest/labels.json
流程：use_llm=True + 类型自动检测（不 override），连测类型发掘 + 内容优先裁决。
输出：逐篇 类型/label/各verdict/evidence，末尾汇总混淆矩阵。
"""
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, "/app")
from src.aiarmy.graph import AuditPipeline

BT = Path("/app/_backtest")
labels = json.loads((BT / "labels.json").read_text(encoding="utf-8"))

async def main():
    pipe = AuditPipeline(use_llm=True)
    results = []
    for i, (fname, truth) in enumerate(labels.items(), 1):
        txt_path = BT / (fname + ".txt")
        if not txt_path.exists():
            print(f"[{i}/{len(labels)}] ⚠️ 缺文本: {fname}")
            continue
        raw = txt_path.read_text(encoding="utf-8")
        t0 = time.time()
        try:
            # 不传 doc_type_override → 触发类型自动检测
            state = await pipe.run(raw, intent="综合评审", verbose=False)
            dt = time.time() - t0
            pred = state.result.label
            dtype = state.doc_type.value if state.doc_type else "未知"
            verds = [f"{v.rule_id}:{'P' if v.passed else 'F'}" for v in state.verdicts]
            ok = "✓" if pred == truth else "✗"
            print(f"[{i}/{len(labels)}] {ok} {fname[:32]:<34} 类型={dtype} 真值={truth} 预测={pred} ({dt:.1f}s)")
            print(f"        verdicts: {' '.join(verds)}  rev={state.revision_count}")
            for m in state.result.matched_rules:
                print(f"        └ {m['rule_id']}: {m['evidence'][:75]}")
            results.append((fname, truth, pred, dtype, ok == "✓"))
        except Exception as e:
            print(f"[{i}/{len(labels)}] ❌ {fname[:32]}: {type(e).__name__}: {str(e)[:80]}")
            results.append((fname, truth, "ERROR", "?", False))

    # 汇总
    print("\n" + "=" * 60)
    total = len(results)
    correct = sum(1 for r in results if r[4])
    # 混淆矩阵
    tp = sum(1 for _, t, p, _, _ in results if t == "通过" and p == "通过")
    tn = sum(1 for _, t, p, _, _ in results if t == "不通过" and p == "不通过")
    fp = sum(1 for _, t, p, _, _ in results if t == "不通过" and p == "通过")
    fn = sum(1 for _, t, p, _, _ in results if t == "通过" and p == "不通过")
    type_ok = sum(1 for _, _, _, d, _ in results if d != "未知" and d != "?")
    print(f"综合准确率: {correct}/{total} = {correct/total*100:.1f}%")
    print(f"混淆矩阵: TP(真通过)={tp} TN(真不通过)={tn} FP(误通过)={fp} FN(漏通过)={fn}")
    print(f"通过类召回: {tp}/{tp+fn if tp+fn else 1}  |  类型检测成功: {type_ok}/{total}")

asyncio.run(main())
