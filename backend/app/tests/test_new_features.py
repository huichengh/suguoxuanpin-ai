"""新增功能测试：小类比较降级、ABC 分类、货架空间优化

对应本轮升级的 A（小类比较）、C（ABC 分类）、D（货架优化）三个模块。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.algorithms import abc as abc_algo
from app.algorithms import shelf as shelf_algo
from app.algorithms import sub_compare as sub_cmp
from app.algorithms.common import MissingFieldError

DATA = Path(__file__).resolve().parent.parent.parent / "data"


@pytest.fixture(scope="module")
def tx_df():
    return pd.read_csv(DATA / "dataset_transactions_sample.csv", encoding="utf-8-sig")


@pytest.fixture(scope="module")
def sub_items(tx_df):
    """从交易明细聚合出的小类指标（与服务层口径一致）"""
    d = tx_df.copy()
    d["金额"] = d["数量"] * d["单价(元)"]
    g = d.groupby(["品类", "商品名称"]).agg(
        sales_qty=("数量", "sum"),
        sales_amount=("金额", "sum"),
        avg_price=("单价(元)", "mean"),
        txn=("交易号", "nunique"),
    ).reset_index()
    g["qty_per_transaction"] = g["sales_qty"] / g["txn"]
    g["max_lift"] = 0.0
    return g.rename(columns={"品类": "category", "商品名称": "name"}).to_dict("records")


# ==================== A. 小类比较 ====================

def test_sub_compare_reduces_to_two_dimensions(sub_items):
    """小类无毛利/周转/坪效，必须降级为两维并明确说明原因"""
    cands = [
        {"name": i["name"], "sales_qty": i["sales_qty"], "sales_amount": i["sales_amount"],
         "gross_profit": None, "turnover_days": None, "sales_per_sqm": None}
        for i in sub_items[:5]
    ]
    res = sub_cmp.compare_subcategories(cands)
    assert res["success"] is True
    assert res["model"]["mode"] == "reduced", "缺字段时必须降级"
    assert set(res["model"]["missing"]) == {"gross_profit", "turnover_days", "sales_per_sqm"}
    assert "毛利额" in res["model"]["reason"]
    assert "不做推算" in res["model"]["reason"], "必须说明平台不推算"
    assert "数据中心" in res["model"]["upgrade_hint"], "应给出升级路径"


def test_sub_compare_uses_four_dimensions_when_data_complete():
    """字段齐全时自动切回四维模型"""
    cands = [
        {"name": "A", "sales_qty": 100, "sales_amount": 1000, "gross_profit": 300,
         "turnover_days": 10, "sales_per_sqm": 500},
        {"name": "B", "sales_qty": 200, "sales_amount": 900, "gross_profit": 200,
         "turnover_days": 30, "sales_per_sqm": 300},
    ]
    res = sub_cmp.compare_subcategories(cands)
    assert res["model"]["mode"] == "full"
    assert "turnover_days" in res["items"][0]["scores"], "四维模型应包含周转得分"


def test_sub_compare_never_fabricates_missing_metrics(sub_items):
    """关键：降级模型下不得输出毛利、周转、坪效得分"""
    cands = [
        {"name": i["name"], "sales_qty": i["sales_qty"], "sales_amount": i["sales_amount"],
         "gross_profit": None, "turnover_days": None, "sales_per_sqm": None}
        for i in sub_items[:4]
    ]
    res = sub_cmp.compare_subcategories(cands)
    for item in res["items"]:
        assert set(item["scores"].keys()) == {"sales_qty", "sales_amount"}, \
            f"{item['name']} 出现了不该有的评分维度：{item['scores'].keys()}"
        assert item["raw"]["gross_profit"] is None


def test_sub_compare_ranking_matches_sales(sub_items):
    cands = [
        {"name": i["name"], "sales_qty": i["sales_qty"], "sales_amount": i["sales_amount"]}
        for i in sub_items[:6]
    ]
    res = sub_cmp.compare_subcategories(cands)
    assert res["success"] is True
    # 两维模型下销量与销售额各占一半权重；此处两者同向，冠军应一致
    top = max(cands, key=lambda c: c["sales_qty"])
    assert res["items"][0]["name"] == top["name"]
    assert [r["priority"] for r in res["items"]] == ["A", "B", "C", "D", "E", "F"]


def test_sub_compare_requires_2_to_6():
    one = [{"name": "A", "sales_qty": 1, "sales_amount": 1}]
    assert sub_cmp.compare_subcategories(one)["success"] is False
    assert sub_cmp.compare_subcategories(one * 7)["success"] is False


def test_sub_compare_weights_must_sum_to_one(sub_items):
    cands = [{"name": i["name"], "sales_qty": i["sales_qty"], "sales_amount": i["sales_amount"]}
             for i in sub_items[:3]]
    with pytest.raises(ValueError, match="权重之和必须为 1"):
        sub_cmp.compare_subcategories(cands, {"sales_qty": 0.5, "sales_amount": 0.2})


def test_sub_compare_unavailable_when_core_metrics_missing():
    cands = [
        {"name": "A", "sales_qty": None, "sales_amount": 100},
        {"name": "B", "sales_qty": 50, "sales_amount": None},
    ]
    res = sub_cmp.compare_subcategories(cands)
    assert res["success"] is False
    assert "缺少必要字段" in res["message"]


# ==================== C. ABC 分类 ====================

def test_abc_classification_thresholds(sub_items):
    res = abc_algo.abc_classify(sub_items)
    assert res["success"] is True
    assert res["total_items"] == len(sub_items)

    cum = 0.0
    for r in res["rows"]:
        cum += r["share_pct"]
        if cum <= 70.0 + 0.1:
            assert r["abc_class"] == "A", f"{r['name']} 累计{cum:.1f}% 应为 A 类"
        elif cum <= 90.0 + 0.1:
            assert r["abc_class"] == "B", f"{r['name']} 累计{cum:.1f}% 应为 B 类"
        else:
            assert r["abc_class"] == "C", f"{r['name']} 累计{cum:.1f}% 应为 C 类"


def test_abc_rows_sorted_by_amount_desc(sub_items):
    res = abc_algo.abc_classify(sub_items)
    amounts = [r["sales_amount"] for r in res["rows"]]
    assert amounts == sorted(amounts, reverse=True)


def test_abc_shares_sum_to_100(sub_items):
    res = abc_algo.abc_classify(sub_items)
    total = sum(c["sales_pct"] for c in res["classes"])
    assert abs(total - 100) < 0.5
    assert abs(sum(r["share_pct"] for r in res["rows"]) - 100) < 0.5


def test_abc_cumulative_is_monotonic(sub_items):
    res = abc_algo.abc_classify(sub_items)
    cums = [r["cumulative_pct"] for r in res["rows"]]
    assert cums == sorted(cums), "累计占比必须单调递增"


def test_abc_counts_sum_to_total(sub_items):
    res = abc_algo.abc_classify(sub_items)
    assert sum(c["count"] for c in res["classes"]) == res["total_items"]


def test_abc_thresholds_configurable(sub_items):
    strict = abc_algo.abc_classify(sub_items, a_thresh=0.50, b_thresh=0.80)
    strict_a = strict["classes"][0]["count"]
    default_a = abc_algo.abc_classify(sub_items)["classes"][0]["count"]
    assert strict_a < default_a, "A 类阈值越低，A 类商品数应越少"


def test_abc_reports_data_limitation(sub_items):
    """均价区分度低时必须如实提示，不能装作效果很好"""
    res = abc_algo.abc_classify(sub_items)
    avg = res["data_discrimination"]["avg_price"]
    if avg["low"]:
        assert res["data_limitation"], "区分度偏低时必须给出说明"
        assert "不对数据做任何修饰" in res["data_limitation"]


def test_abc_rejects_empty_data():
    res = abc_algo.abc_classify([])
    assert res["success"] is False
    assert "销售额" in res["missing_data"][0]


# ==================== D. 货架空间优化 ====================

def test_shelf_area_sums_to_total(sub_items):
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0)
    assert res["success"] is True
    total = sum(r["suggest_area"] for r in res["items"])
    assert abs(total - 20.0) < 0.05, f"分配面积之和应等于总面积，实际 {total}"


def test_shelf_shares_sum_to_100(sub_items):
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0)
    assert abs(sum(r["share_pct"] for r in res["items"]) - 100) < 0.5


def test_shelf_alpha_controls_concentration(sub_items):
    """α 越大越集中（纯按销售额），α 越小越均衡"""
    concentrated = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0, alpha=1.0)
    balanced = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0, alpha=0.2)
    c_top = max(r["share_pct"] for r in concentrated["items"])
    b_top = max(r["share_pct"] for r in balanced["items"])
    assert c_top > b_top, "α=1 的最大占比应高于 α=0.2"


def test_shelf_min_share_constraint(sub_items):
    """下限约束不应让所有商品都变成平均分配（70个商品时2%下限不可行）"""
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0, alpha=0.65)
    shares = [r["share_pct"] for r in res["items"]]
    assert len(set(round(s, 2) for s in shares)) > 1, "占比不应完全相同"
    assert res["min_share"] < 100 / len(sub_items) + 0.1, "下限必须可行"


def test_shelf_high_sales_gets_more_area(sub_items):
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0, alpha=1.0)
    by_name = {r["name"]: r for r in res["items"]}
    hi = max(sub_items, key=lambda x: x["sales_amount"])
    lo = min(sub_items, key=lambda x: x["sales_amount"])
    assert by_name[hi["name"]]["suggest_area"] > by_name[lo["name"]]["suggest_area"], \
        f"销售额最高的 {hi['name']} 面积应大于最低的 {lo['name']}"
    # items 按单位产出排序，不按面积排序
    assert res["items"] == sorted(res["items"], key=lambda r: -r["sales_per_sqm"])


def test_shelf_sales_per_sqm_is_consistent(sub_items):
    """单位产出必须与展示的销售额/面积一致（算法内部用未舍入面积，误差应极小）"""
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=30.0)
    for r in res["items"][:5]:
        expected = r["sales_amount"] / r["suggest_area"]
        assert abs(r["sales_per_sqm"] - expected) / expected < 0.01, \
            f"{r['name']} 单位产出 {r['sales_per_sqm']} 与展示值算出的 {expected:.1f} 偏差过大"


def test_shelf_rejects_zero_area(sub_items):
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=0)
    assert res["success"] is False
    assert "总面积必须大于 0" in res["message"]


def test_shelf_rejects_no_valid_data():
    res = shelf_algo.allocate_shelf_space([{"name": "A", "sales_amount": 0}])
    assert res["success"] is False
    assert "销售额" in res["missing_data"][0]


def test_shelf_provides_greedy_comparison(sub_items):
    """贪心对比要说明纯贪心会牺牲长尾"""
    res = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0)
    g = res["greedy_comparison"]
    assert "capacity_slots" in g
    assert "note" in g
    assert "牺牲长尾" in g["note"]


def test_shelf_by_category_two_level_allocation(sub_items):
    """二级分配：大类先分，再在类内分，面积总和应守恒"""
    first = shelf_algo.allocate_shelf_space(sub_items, total_area=20.0)
    cat_area = {}
    for r in first["items"]:
        cat_area[r["category"]] = cat_area.get(r["category"], 0) + r["suggest_area"]

    detail = shelf_algo.reallocate_by_category(sub_items, cat_area)
    assert detail, "二级分配应返回结果"
    total = sum(r["suggest_area"] for r in detail)
    assert abs(total - 20.0) < 0.1, f"二级分配面积之和 {total} 应约等于 20"
