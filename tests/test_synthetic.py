"""
合成样本测试（v4 spec 任务11）—— 验证确定性规则正反触发。

构造最小但格式完整的合成文档，验证每条规则的 pass/fail 逻辑。
注意：立项申请书需要同时含审批栏+承诺书（完整格式），
计划任务书团队信息用真实姓名（不含 成员\d+ 占位符）。
"""
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from src.agent_orchestration.graph import run_sync


# ── 立项申请书完整模板（含审批 + 承诺书）──
LIXIANG_TEMPLATE_PASS = """职工技术创新项目立项申请书
项目名称：{title}

一、项目概述
本项目针对电力行业{domain}领域的关键技术问题，拟开展核心技术攻关与装置研制。
项目具有明确的技术创新点和可量化的考核指标。

二、申请部门意见
申请部门意见：经审核，该项目符合申报条件，同意推荐。
日期：2025年3月15日

三、科技管理部门意见
科技管理部门意见：经审核，同意推荐申报。
日期：2025年4月1日

四、承诺书
项目负责人：{signer}
日期：2025年3月15日

五、预算
总经费：50万元
材料费：20万元
测试加工费：15万元
知识产权费：2万元
"""

LIXIANG_TEMPLATE_FAIL = """职工技术创新项目立项申请书
项目名称：{title}

一、项目概述
本项目针对电力行业{domain}领域的关键技术问题，拟开展核心技术攻关与装置研制。

二、申请部门意见
申请部门意见：
（盖章）
日期：  年  月  日

三、科技管理部门意见
科技管理部门意见：
（盖章）
日期：  年  月  日

四、承诺书
项目负责人：{signer}
日期：{sign_date}

五、预算
总经费：50万元
"""


def test_r01_approval():
    """R-01 审批签章完整性：有日期+意见→通过，空白→不通过"""
    # 通过案例：审批栏填了日期和意见（承诺书也需完整，否则 R-02 会拖累）
    doc_pass = LIXIANG_TEMPLATE_PASS.format(title="测试项目-审批完整", domain="变电检修", signer="张三")
    state = run_sync(doc_pass, use_llm=False)
    r01 = [v for v in state.verdicts if v.rule_id == "R-01"]
    assert r01 and r01[0].passed, f"R-01 应通过，实际: {r01[0].passed if r01 else '未找到'}"
    print("  ✅ R-01 通过案例: 审批签章完整")

    # 不通过案例：审批栏空白（承诺书也不完整，但不影响 R-01 判断）
    doc_fail = LIXIANG_TEMPLATE_FAIL.format(title="测试项目-审批空白", domain="变电检修",
                                             signer="（签字）", sign_date="  年  月  日")
    state = run_sync(doc_fail, use_llm=False)
    r01 = [v for v in state.verdicts if v.rule_id == "R-01"]
    assert r01 and not r01[0].passed, f"R-01 应不通过，实际: {r01[0].passed if r01 else '未找到'}"
    print("  ✅ R-01 不通过案例: 审批栏空白")


def test_r02_commitment():
    """R-02 承诺书签署完整性：真实签名→通过，占位符→不通过"""
    # 通过案例
    doc_pass = LIXIANG_TEMPLATE_PASS.format(title="测试项目-承诺完整", domain="变电检修", signer="李四")
    state = run_sync(doc_pass, use_llm=False)
    r02 = [v for v in state.verdicts if v.rule_id == "R-02"]
    assert r02 and r02[0].passed, f"R-02 应通过，实际: {r02[0].passed if r02 else '未找到'}"
    print("  ✅ R-02 通过案例: 承诺书签署完整")

    # 不通过案例：占位符签名
    doc_fail = LIXIANG_TEMPLATE_PASS.format(title="测试项目-承诺占位", domain="变电检修", signer="（签字）")
    state = run_sync(doc_fail, use_llm=False)
    r02 = [v for v in state.verdicts if v.rule_id == "R-02"]
    assert r02 and not r02[0].passed, f"R-02 应不通过，实际: {r02[0].passed if r02 else '未找到'}"
    print("  ✅ R-02 不通过案例: 占位符签名")


# ── 计划任务书模板 ──
PLAN_TEMPLATE = """科技项目计划任务书
项目名称：{title}

一、项目摘要
{summary}

二、项目组人员情况
负责人：{leader}
成员：{members}

三、考核指标
{review_status}

四、经费预算
总经费：80万元
材料费：30万元
测试加工费：25万元
差旅费：5万元
知识产权费：2万元
审计费：1万元
监理费：0.5万元
管理费：16.5万元
"""


def test_r05_template():
    """R-05 模板填写规范性：含填写说明→不通过，不含→通过"""
    # 不通过案例：含填写说明
    doc_fail = PLAN_TEMPLATE.format(
        title="测试项目-模板残留",
        summary="【填写说明：请在此处填写项目摘要，删除本提示后提交】本项目针对电网测试问题。",
        leader="王五",
        members="赵工、钱工、孙工",
        review_status="装置准确率 ≥92%\n系统可用率 ≥99%",
    )
    state = run_sync(doc_fail, use_llm=False)
    r05 = [v for v in state.verdicts if v.rule_id == "R-05"]
    assert r05 and not r05[0].passed, f"R-05 应不通过（模板残留），实际: {r05[0].passed if r05 else '未找到'}"
    print("  ✅ R-05 不通过案例: 模板残留")

    # 通过案例：无填写说明
    doc_pass = PLAN_TEMPLATE.format(
        title="测试项目-模板干净",
        summary="本项目针对配电网故障定位精度不足的问题，拟开展基于行波法的故障定位技术研究。",
        leader="王五",
        members="赵工、钱工、孙工",
        review_status="装置准确率 ≥92%\n系统可用率 ≥99%",
    )
    state = run_sync(doc_pass, use_llm=False)
    r05 = [v for v in state.verdicts if v.rule_id == "R-05"]
    # R-05 可能不触发（quick_check 返回 None 时由于 use_llm=False → 从严判不通过，但那是 R-07 行为）
    # 这里只验证 R-05 正则不误判
    if r05:
        assert r05[0].passed, f"R-05 应通过（无模板残留），实际: {r05[0].passed}"
    print("  ✅ R-05 通过案例: 无模板残留触发")


def test_r06_team():
    """R-06 团队信息真实性：编号占位符→不通过，真实姓名→通过"""
    # 不通过案例：含"成员10""成员11"占位符
    doc_fail = PLAN_TEMPLATE.format(
        title="测试项目-团队占位符",
        summary="本项目针对变电设备监测技术问题，拟开展智能诊断算法研究。",
        leader="郑工",
        members="刘工、王工、李工、赵工、孙工、周工、吴工、郑工、成员10、成员11",
        review_status="装置准确率 ≥92%\n系统可用率 ≥99%",
    )
    state = run_sync(doc_fail, use_llm=False)
    r06 = [v for v in state.verdicts if v.rule_id == "R-06"]
    assert r06 and not r06[0].passed, f"R-06 应不通过（占位符成员），实际: {r06[0].passed if r06 else '未找到'}"
    print("  ✅ R-06 不通过案例: 占位符成员")

    # 通过案例：真实姓名（不含"成员\d+"格式）
    doc_pass = PLAN_TEMPLATE.format(
        title="测试项目-团队真实",
        summary="本项目针对变电设备监测技术问题，拟开展智能诊断算法研究。",
        leader="郑工",
        members="刘工、王工、李工、赵工",
        review_status="装置准确率 ≥92%\n系统可用率 ≥99%",
    )
    state = run_sync(doc_pass, use_llm=False)
    r06 = [v for v in state.verdicts if v.rule_id == "R-06"]
    if r06:
        assert r06[0].passed, f"R-06 应通过（无占位符），实际: {r06[0].passed}"
    print("  ✅ R-06 通过案例: 无占位符成员")


def main():
    print("🔬 合成样本测试\n")
    tests = [
        ("R-01 审批签章完整性", test_r01_approval),
        ("R-02 承诺书签署完整性", test_r02_commitment),
        ("R-05 模板填写规范性", test_r05_template),
        ("R-06 团队信息真实性", test_r06_team),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        print(f"\n  [{name}]")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"    ❌ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"    ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"  通过: {passed}/{len(tests)}, 失败: {failed}/{len(tests)}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
