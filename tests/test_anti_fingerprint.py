"""
反指纹测试（v4 spec 任务10）—— 验证系统对训练集表面值不敏感。

对训练文档做三种扰动，断言判断结果不变：
1. 年份替换（2026→2031）
2. KPI 数值扰动（百分比值-7）
3. 项目领域名替换（输电线路→燃气管网）

任何一篇文档的 label 变了 = 还有指纹未清，回头查。
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from src.agent_orchestration.graph import run_sync
from src.agent_orchestration.io import to_text

TXT_DIR = BASE / "训练集" / "convert_text"


def mutate_year(text: str) -> str:
    """年份替换：所有 XXXX年 → 年份+5"""
    return re.sub(r'(\d{4})年', lambda m: f"{int(m.group(1)) + 5}年", text)


def mutate_kpi(text: str) -> str:
    """KPI 数值扰动：百分比值 -7（最小保持 1）"""
    return re.sub(
        r'(\d+(?:\.\d+)?)\s*%',
        lambda m: f"{max(1, int(float(m.group(1))) - 7)}%",
        text,
    )


def mutate_domain(text: str) -> str:
    """项目领域名替换"""
    replacements = {
        "输电线路": "燃气管网",
        "配电网": "供热管网",
        "变电站": "换热站",
        "电缆": "管道",
        "电网": "管网",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def test_anti_fingerprint():
    """主测试：至少 3 篇文档，扰动后 label 不变"""
    # 选 3 篇：一篇立项申请书通过、一篇计划任务书通过、一篇计划任务书不通过
    test_files = [
        "一种变电站设备红外测温辅助定位装置.txt",  # 立项申请书 通过
        "1 基于深度学习的输电线路隐患智能识别技术研究.txt",  # 计划任务书 不通过
        "2 面向配电网的分布式能源优化调度方法研究.txt",  # 计划任务书 不通过
    ]

    mutations = [
        ("年份+5", mutate_year),
        ("KPI数值-7", mutate_kpi),
        ("领域名替换", mutate_domain),
    ]

    failures = []
    for fname in test_files:
        fpath = TXT_DIR / fname
        if not fpath.exists():
            print(f"  ⚠️ 跳过（文件不存在）: {fname}")
            continue

        text = to_text(str(fpath))
        # 用纯规则模式（不用 LLM，确保可复现）
        orig_state = run_sync(text, use_llm=False)
        orig_label = orig_state.result.label if orig_state.result else "错误"
        print(f"\n  📄 {fname[:50]}")
        print(f"     原始 label: {orig_label}")

        for mut_name, mut_fn in mutations:
            mutated = mut_fn(text)
            # 确保变异确实改变了文本
            if mutated == text:
                print(f"     {mut_name}: 文本未变化，跳过")
                continue

            mut_state = run_sync(mutated, use_llm=False)
            mut_label = mut_state.result.label if mut_state.result else "错误"

            if mut_label != orig_label:
                failures.append(f"{fname} | {mut_name}: {orig_label} → {mut_label}")
                print(f"     ❌ {mut_name}: {orig_label} → {mut_label} (变了！有指纹)")
            else:
                print(f"     ✅ {mut_name}: {mut_label} (不变)")

    print(f"\n{'='*60}")
    if failures:
        print(f"❌ 反指纹测试失败 ({len(failures)} 项):")
        for f in failures:
            print(f"   {f}")
        return 1
    else:
        print("✅ 反指纹测试全部通过 — 系统对训练集表面值不敏感")
        return 0


if __name__ == "__main__":
    sys.exit(test_anti_fingerprint())
