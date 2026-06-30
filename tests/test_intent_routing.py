"""
Intent 路由验证（v4 spec 任务12）—— 验证 intent 激活的规则子集符合预期。
"""
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from src.aiarmy.agents.match import _route_by_intent, load_rules


def test_intent_routing():
    """验证不同 intent 各自激活的规则子集"""
    print("🔬 Intent 路由测试\n")

    # 加载全部规则
    all_rules_plan = load_rules("计划任务书")
    all_rules_lixiang = load_rules("立项申请书")

    test_cases = [
        # (doc_type, intent, expected_rule_ids, description)
        ("计划任务书", "", ["R-05", "R-06", "R-07"], "空 intent → 全部"),
        ("计划任务书", "综合评审", ["R-05", "R-06", "R-07"], "综合评审 → 全部"),
        ("计划任务书", "判断创新程度", ["R-07"], "创新程度 → R-07"),
        ("计划任务书", "材料完整性审查", ["R-05"], "材料完整性 → R-05"),
        ("计划任务书", "评估风险", ["R-05", "R-06", "R-07"], "陌生 intent → 兜底全量"),
        ("立项申请书", "", ["R-01", "R-02", "R-03", "R-04"], "空 intent → 全部"),
        ("立项申请书", "材料完整性", ["R-01", "R-02"], "材料完整性 → R-01+R-02（两者 keywords 都含'材料完整'）"),
    ]

    passed = 0
    failed = 0
    for doc_type, intent, expected, desc in test_cases:
        rules = all_rules_plan if doc_type == "计划任务书" else all_rules_lixiang
        selected = _route_by_intent(intent, rules)
        selected_ids = [r["rule_id"] for r in selected]
        expected_ids = expected

        ok = set(selected_ids) == set(expected_ids)
        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"  {status} [{doc_type}] intent='{intent}' ({desc})")
        print(f"     期望: {expected_ids}")
        print(f"     实际: {selected_ids}")
        if not ok:
            extra = set(selected_ids) - set(expected_ids)
            missing = set(expected_ids) - set(selected_ids)
            if extra:
                print(f"     多余: {extra}")
            if missing:
                print(f"     缺失: {missing}")

    print(f"\n{'='*60}")
    print(f"  通过: {passed}/{len(test_cases)}, 失败: {failed}/{len(test_cases)}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(test_intent_routing())
