"""核心算法测试

覆盖需求文档第二十九节的重点测试项：
1. 品类评分权重之和是否为 1
2. 周转天数是否正确采用逆向评分
3. 缺失字段是否触发错误提示
4. Apriori 是否以交易号构建购物篮
5. 演示数据默认是否按照「商品名称」聚合
6. support/confidence/lift 是否正确计算
7. 导入参考关联规则时是否保留原始结果
8. 实时重算结果是否按照当前阈值过滤
9. AI 是否拒绝编造缺失经营数据
10. Level 3 建议是否必须进入人工审批
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.algorithms import advisor
from app.algorithms import association as assoc_algo
from app.algorithms import compare as cmp_algo
from app.algorithms import data_quality as dq
from app.algorithms import forecast as fc_algo
from app.algorithms import health as health_algo
from app.algorithms.common import MissingFieldError, minmax_normalize, validate_weights

DATA = Path(__file__).resolve().parent.parent.parent / "data"


@pytest.fixture(scope="module")
def sales_df():
    return pd.read_csv(DATA / "dataset_category_sales.csv", encoding="utf-8-sig")


@pytest.fixture(scope="module")
def tx_df():
    return pd.read_csv(DATA / "dataset_transactions_sample.csv", encoding="utf-8-sig")


# ---------- 1. 权重之和必须为 1 ----------

def test_weights_must_sum_to_one():
    assert validate_weights({"sales": 0.3, "margin": 0.3, "turnover": 0.2, "space": 0.2})
    with pytest.raises(ValueError, match="权重之和必须为 1"):
        validate_weights({"sales": 0.3, "margin": 0.3, "turnover": 0.2, "space": 0.5})
    with pytest.raises(ValueError, match="不能为负数"):
        validate_weights({"sales": -0.1, "margin": 0.5, "turnover": 0.3, "space": 0.3})


def test_default_weights_sum_to_one(sales_df):
    total = sum(health_algo.DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"默认权重之和应为 1，实际 {total}"


# ---------- 2. 周转天数必须逆向标准化 ----------

def test_turnover_reverse_normalization():
    values = [10.0, 30.0, 60.0, 90.0]
    scores = minmax_normalize(values, higher_is_better=False)
    assert scores[0] > scores[-1], "周转天数最少的品类必须得分最高（逆向标准化）"
    assert scores[0] == 100.0
    assert scores[-1] == 0.0
    # 正向标准化会给出相反结果，验证两者确实相反
    forward = minmax_normalize(values, higher_is_better=True)
    assert forward[0] < forward[-1]


def test_turnover_days_direction_in_health_scores(sales_df):
    rows = health_algo.score_categories(sales_df)
    by_name = {r["category"]: r for r in rows}
    # 生鲜蔬果周转约 11.5 天，纺织服装约 87 天，生鲜得分必须更高
    assert by_name["生鲜蔬果"]["avg_turnover_days"] < by_name["纺织服装"]["avg_turnover_days"]
    assert by_name["生鲜蔬果"]["turnover_score"] > by_name["纺织服装"]["turnover_score"]


def test_slow_turnover_category_scores_low(sales_df):
    """纺织服装周转最慢，其周转维度得分应接近 0。"""
    rows = health_algo.score_categories(sales_df)
    slowest = min(rows, key=lambda r: r["turnover_score"])
    assert slowest["category"] == "纺织服装"
    assert slowest["turnover_score"] == 0.0


# ---------- 3. 缺失字段必须报错 ----------

def test_missing_field_raises_error(sales_df):
    broken = sales_df.drop(columns=["库存周转天数"])
    with pytest.raises(MissingFieldError) as e:
        health_algo.score_categories(broken)
    assert "库存周转天数" in str(e.value)


def test_missing_transaction_field_raises(tx_df):
    broken = tx_df.drop(columns=["交易号"])
    with pytest.raises(assoc_algo.BasketKeyError):
        assoc_algo.build_baskets(broken)


def test_sku_compare_missing_metrics_raises():
    cands = [
        {"id": "A", "name": "商品A", "sales_qty": 100, "sales_amount": 1000,
         "gross_profit": 200, "turnover_days": 10, "sales_per_sqm": 500},
        {"id": "B", "name": "商品B", "sales_qty": 50, "sales_amount": 500,
         "gross_profit": None, "turnover_days": 20, "sales_per_sqm": 300},
    ]
    with pytest.raises(MissingFieldError) as e:
        cmp_algo.compare_candidates(cands)
    assert "gross_profit" in str(e.value)


def test_data_quality_reports_missing_columns():
    df = pd.DataFrame({"品类ID": ["C1"], "品类名称": ["生鲜"]})
    r = dq.check_quality(df, "category_sales")
    assert r["issue_count"] > 0
    assert any(i["issue_type"] == "字段缺失" for i in r["issues"])
    assert r["overall_score"] < 100


# ---------- 4 & 5. 购物篮构建与商品名称聚合 ----------

def test_baskets_built_by_transaction_no(tx_df):
    baskets = assoc_algo.build_baskets(tx_df, group_by="product_name")
    assert len(baskets) == tx_df["交易号"].nunique(), "每个交易号应构成一个购物篮"
    assert all(isinstance(b, set) for b in baskets)
    assert all(len(b) > 0 for b in baskets)


def test_demo_default_uses_product_name(tx_df):
    """演示数据默认按商品名称聚合，商品数应远小于商品编码数。"""
    name_baskets = assoc_algo.build_baskets(tx_df, group_by="product_name")
    code_baskets = assoc_algo.build_baskets(tx_df, group_by="sku_code")
    name_items = len(set().union(*name_baskets))
    code_items = len(set().union(*code_baskets))
    assert name_items < code_items, "商品名称数应少于商品编码数（编码高度离散）"
    assert name_items == 70, f"演示数据应聚合出 70 个商品名称，实际 {name_items}"


def test_unknown_group_by_raises(tx_df):
    with pytest.raises(assoc_algo.BasketKeyError):
        assoc_algo.build_baskets(tx_df, group_by="not_exist")


# ---------- 6. support / confidence / lift 计算正确性 ----------

def test_metric_formulas_on_known_baskets():
    # 构造 10 个购物篮：A 出现在 5 个，A∧B 出现在 3 个，B 出现在 4 个
    baskets = [{"A"}] * 2 + [{"A", "B"}] * 3 + [{"B"}] + [{"C"}] * 4
    out = assoc_algo.generate_rules(baskets, min_support=0.0, min_confidence=0.0,
                                    min_lift=0.0, top_n=100)
    rules = {(r["antecedent"], r["consequent"]): r for r in out["rules"]}
    assert ("A", "B") in rules
    r = rules[("A", "B")]
    assert abs(r["support"] - 0.3) < 1e-6, f"support 应为 0.3，实际 {r['support']}"
    assert abs(r["confidence"] - 0.6) < 1e-6, f"confidence 应为 0.6，实际 {r['confidence']}"
    # lift = confidence / support(B) = 0.6 / 0.4 = 1.5
    assert abs(r["lift"] - 1.5) < 1e-4, f"lift 应为 1.5，实际 {r['lift']}"


def test_lift_gt_one_means_positive_correlation(tx_df):
    out = assoc_algo.run_association_analysis(tx_df, min_support=0.02,
                                              min_confidence=0.5, min_lift=1.5)
    assert out["rules"], "默认参数应能产出规则"
    for r in out["rules"]:
        assert r["lift"] >= 1.5
        assert r["confidence"] >= 0.5
        assert r["support"] >= 0.02


def test_business_pairs_are_discovered(tx_df):
    """演示数据应能发现业务上有意义的组合。

    注意：默认阈值（conf≥0.50）下共 30 条规则通过，TopN=20 会做一次截断，
    因此这里用更大的 top_n 验证算法本身能发现业务组合。
    火锅底料→丸子的置信度为 0.4727，低于默认阈值，需放宽阈值才能出现 ——
    这正是平台需要区分「附件参考结果」与「实时重算结果」的原因。
    """
    out = assoc_algo.run_association_analysis(tx_df, top_n=100)
    pairs = {frozenset([r["antecedent"], r["consequent"]]) for r in out["rules"]}
    assert frozenset(["牛奶", "面包"]) in pairs, "应发现 牛奶 → 面包 关联"
    assert frozenset(["西红柿", "鸡蛋"]) in pairs, "应发现 西红柿 → 鸡蛋 关联"

    # 放宽置信度阈值后，火锅底料 + 丸子应出现
    loose = assoc_algo.run_association_analysis(
        tx_df, min_support=0.02, min_confidence=0.45, min_lift=1.5, top_n=100)
    loose_pairs = {frozenset([r["antecedent"], r["consequent"]]) for r in loose["rules"]}
    assert frozenset(["火锅底料", "丸子"]) in loose_pairs, "放宽阈值后应发现 火锅底料 ↔ 丸子 关联"


def test_lift_in_reasonable_range(tx_df):
    """修正 lift 公式后，提升度应落在合理区间（不再出现 10+ 的异常值）。"""
    out = assoc_algo.run_association_analysis(tx_df)
    lifts = [r["lift"] for r in out["rules"]]
    assert lifts, "应产出规则"
    assert max(lifts) < 10, f"提升度最大值 {max(lifts)} 异常，lift 公式可能有误"
    assert min(lifts) >= 1.5


# ---------- 7 & 8. 附件结果保留 + 实时结果按阈值过滤 ----------

def test_threshold_filtering_keeps_and_marks():
    params = {"min_confidence": 0.50, "min_lift": 1.50}
    high = assoc_algo.rule_to_dict_stub if False else None
    # 直接用 API 层的判定逻辑
    from app.services.analytics import rule_to_dict

    class R:
        id = 1
        antecedent, consequent = "A", "B"
        support, confidence, lift = 0.05, 0.60, 2.0
        display_rule, display_suggestion = "A → B", ""
        source, item_count = "attachment", 2
        algorithm, source_dataset_id = "附件预置参考结果", 1
        parameters = {"note": "附件原始结果"}

    d = rule_to_dict(R(), params)
    assert d["passes_threshold"] is True
    assert d["source_label"] == "附件参考关联规则"

    R.confidence, R.lift = 0.42, 1.68   # 附件中确实存在低于阈值的规则
    d2 = rule_to_dict(R(), params)
    assert d2["passes_threshold"] is False, "低于阈值的附件规则应被标记为未通过"
    assert d2["source"] == "attachment", "附件原始结果必须保留 source 标记"
    assert d2["confidence"] == 0.42, "附件原始数值不得被修改"


def test_attachment_rules_in_dataset_have_original_values():
    df = pd.read_csv(DATA / "dataset_association_rules.csv", encoding="utf-8-sig")
    below = df[(df["置信度"] < 0.5) | (df["提升度"] < 1.5)]
    assert len(below) > 0, "附件中应确实存在未通过默认阈值的规则"
    # 平台不得删除这些行
    assert len(df) == 20


# ---------- 9. AI 不得编造缺失数据 ----------

def test_ai_refuses_when_no_sku_data():
    status = cmp_algo.sku_data_sufficient([])
    assert status is False
    assert cmp_algo.missing_sku_fields([]) == []


def test_sku_sufficiency_requires_all_metrics():
    cands = [{"name": "A", "sales_qty": 1, "sales_amount": 1, "gross_profit": 1,
              "turnover_days": 1, "sales_per_sqm": 1}]
    assert cmp_algo.sku_data_sufficient(cands) is True
    cands[0]["turnover_days"] = None
    assert cmp_algo.sku_data_sufficient(cands) is False
    assert "turnover_days" in cmp_algo.missing_sku_fields(cands)


def test_private_label_is_category_level_only():
    rows = health_algo.score_categories(
        pd.read_csv(DATA / "dataset_category_sales.csv", encoding="utf-8-sig"))
    r = advisor.private_label_opportunity(rows)
    assert r["level"] == "品类级建议"
    assert len(r["missing_data"]) > 0
    assert "SKU" in r["level_note"] or "SKU" in "".join(r["missing_data"])


def test_forecast_flags_insufficient_history():
    v = fc_algo.build_forecast_view(
        "测试品类",
        [{"week_no": i, "period_label": f"W{i}", "actual_qty": 100 + i} for i in range(1, 5)],
        [{"week_no": 5, "period_label": "W5", "forecast_qty": 120,
          "lower_bound": 100, "upper_bound": 140}],
    )
    assert v["sample_sufficient"] is False
    assert "历史数据量有限" in v["sample_note"]


def test_forecast_trend_classification():
    assert fc_algo.classify_trend(120, 100)["level"] == "明显上涨"
    assert fc_algo.classify_trend(107, 100)["level"] == "温和上涨"
    assert fc_algo.classify_trend(100, 100)["level"] == "基本稳定"
    assert fc_algo.classify_trend(93, 100)["level"] == "温和下降"
    assert fc_algo.classify_trend(80, 100)["level"] == "明显下降"


def test_moving_average_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="历史数据不足"):
        fc_algo.moving_average_forecast([100, 110], periods=4, window=4)


# ---------- 10. Level 3 必须进入人工审批 ----------

def test_level3_suggestions_require_approval(sales_df):
    rows = health_algo.score_categories(sales_df)
    fcs = []
    suggestions = advisor.generate_daily_suggestions(rows, fcs, {"rules": [], "params": {}})
    for s in suggestions:
        if s["risk_level"] == "Level 3":
            assert s["requires_approval"] is True, f"Level 3 建议「{s['title']}」必须要求人工审批"


def test_risky_categories_marked_needing_approval(sales_df):
    rows = health_algo.score_categories(sales_df)
    suggestions = advisor.generate_daily_suggestions(rows, [], {"rules": [], "params": {}})
    risky = [s for s in suggestions if "重点优化" in s["title"] or "精简" in s["title"]]
    assert risky, "低健康度品类应产生需优化建议"
    assert all(s["requires_approval"] for s in risky if s["risk_level"] == "Level 3")


def test_comprehensive_plan_cites_multiple_dimensions(sales_df):
    rows = health_algo.score_categories(sales_df)
    plan = advisor.generate_comprehensive_plan(rows, [], {"rules": []})
    for group in ["优先扩充", "建议保持", "重点观察", "建议精简", "建议退出"]:
        for item in plan[group]:
            assert item["data_basis"], f"{group} 中的 {item['category']} 缺少数据依据"
            assert item["multi_dimension"], f"{group} 中的 {item['category']} 缺少多维判断说明"
            # 数据依据必须包含多个维度，而非单一健康分
            dims = sum(1 for k in ["健康度", "销量贡献", "毛利贡献", "周转", "坪效", "缺货", "需求趋势"]
                       if k in item["data_basis"])
            assert dims >= 4, f"{item['category']} 的数据依据只覆盖 {dims} 个维度，应至少 4 个"


# ---------- 健康度模型补充 ----------

def test_health_grades(sales_df):
    rows = health_algo.score_categories(sales_df)
    for r in rows:
        s = r["overall_score"]
        expected = "优秀" if s >= 85 else "良好" if s >= 70 else "一般" if s >= 55 else "较差" if s >= 40 else "差"
        assert r["grade"] == expected


def test_health_ranks_sorted(sales_df):
    rows = health_algo.score_categories(sales_df)
    scores = [r["overall_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_health_ranking_matches_healthiness(sales_df):
    """综合排名应与健康度一致，且最差品类应被标记为低于三星。"""
    rows = health_algo.score_categories(sales_df)
    assert rows[0]["category"] == "生鲜蔬果"
    assert rows[-1]["category"] == "纺织服装"
    assert rows[-1]["below_three_star"] is True


def test_contributions_sum_to_100(sales_df):
    rows = health_algo.score_categories(sales_df)
    assert abs(sum(r["sales_contribution"] for r in rows) - 100) < 0.5
    assert abs(sum(r["margin_contribution"] for r in rows) - 100) < 0.5


# ---------- 比较引擎 ----------

def test_compare_ranking_and_priority():
    cands = [
        {"id": 1, "name": "A", "sales_qty": 1000, "sales_amount": 10000, "gross_profit": 2000,
         "turnover_days": 10, "sales_per_sqm": 900},
        {"id": 2, "name": "B", "sales_qty": 500, "sales_amount": 5000, "gross_profit": 800,
         "turnover_days": 40, "sales_per_sqm": 400},
        {"id": 3, "name": "C", "sales_qty": 200, "sales_amount": 2000, "gross_profit": 200,
         "turnover_days": 90, "sales_per_sqm": 150},
    ]
    r = cmp_algo.compare_candidates(cands)
    assert r["best"] == "A"
    assert [i["priority"] for i in r["items"]] == ["A", "B", "C"]
    assert r["items"][-1]["recommendation"]["action"] in ("建议精简", "建议退出")


def test_compare_requires_2_to_6():
    one = [{"id": 1, "name": "A", "sales_qty": 1, "sales_amount": 1, "gross_profit": 1,
            "turnover_days": 1, "sales_per_sqm": 1}]
    with pytest.raises(ValueError, match="至少需要 2 个"):
        cmp_algo.compare_candidates(one)
    many = one * 7
    with pytest.raises(ValueError, match="最多支持 6 个"):
        cmp_algo.compare_candidates(many)


def test_compare_weights_affect_ranking():
    cands = [
        {"id": 1, "name": "高量低利", "sales_qty": 1000, "sales_amount": 10000, "gross_profit": 500,
         "turnover_days": 30, "sales_per_sqm": 300},
        {"id": 2, "name": "低量高利", "sales_qty": 300, "sales_amount": 9000, "gross_profit": 4000,
         "turnover_days": 20, "sales_per_sqm": 800},
    ]
    sales_first = cmp_algo.compare_candidates(cands, {"sales": 0.6, "margin": 0.2, "turnover": 0.1, "space": 0.1})
    margin_first = cmp_algo.compare_candidates(cands, {"sales": 0.2, "margin": 0.6, "turnover": 0.1, "space": 0.1})
    assert sales_first["best"] == "高量低利"
    assert margin_first["best"] == "低量高利", "提高毛利权重后结论应反转"


def test_ai_judgement_includes_risk_and_condition():
    cands = [
        {"id": 1, "name": "A", "sales_qty": 1000, "sales_amount": 10000, "gross_profit": 2000,
         "turnover_days": 10, "sales_per_sqm": 900},
        {"id": 2, "name": "B", "sales_qty": 100, "sales_amount": 1000, "gross_profit": 50,
         "turnover_days": 95, "sales_per_sqm": 80},
    ]
    j = cmp_algo.build_ai_judgement(cmp_algo.compare_candidates(cands))
    assert j["why"] and j["max_risk"] and j["change_condition"]
    assert "仅供辅助决策" in j["disclaimer"]


# ---------- 数据质量 ----------

def test_quality_detects_logic_error():
    df = pd.DataFrame({
        "品类ID": ["C1", "C2"], "品类名称": ["生鲜", "日化"],
        "月份": ["2026-01", "2026-02"], "销量(件)": [100, 200],
        "销售额(元)": [1000, 2000], "毛利额(元)": [1500, 500],   # 第一行毛利>销售额
        "库存周转天数": [10, 20], "坪效(元/㎡/月)": [500, 600],
        "缺货次数": [1, 2], "SKU数量": [100, 200],
    })
    r = dq.check_quality(df, "category_sales")
    assert any(i["issue_type"] == "逻辑不一致" for i in r["issues"])
    assert r["consistency"] < 100


def test_quality_detects_duplicate_key():
    df = pd.DataFrame({
        "品类ID": ["C1", "C1"], "品类名称": ["生鲜", "生鲜"],
        "月份": ["2026-01", "2026-01"], "销量(件)": [100, 100],
        "销售额(元)": [1000, 1000], "毛利额(元)": [200, 200],
        "库存周转天数": [10, 10], "坪效(元/㎡/月)": [500, 500],
        "缺货次数": [1, 1], "SKU数量": [100, 100],
    })
    r = dq.check_quality(df, "category_sales")
    assert any(i["issue_type"] == "主键重复" for i in r["issues"])
    assert r["uniqueness"] < 100


def test_quality_template_has_required_fields():
    for t in dq.DATASET_SCHEMAS:
        csv = dq.template_csv(t)
        header = csv.splitlines()[0]
        for f in dq.DATASET_SCHEMAS[t]["required"]:
            assert f in header, f"{t} 模板缺少字段 {f}"
