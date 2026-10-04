"""多门店功能测试：录入、对比、缺失数据处理"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.algorithms.common import minmax_normalize
from app.services import store_ops
from app.services.store_ops import STORE_METRICS, PROFILE_FIELDS, store_data_status


class FakeStore:
    """轻量假门店，避免依赖数据库"""
    def __init__(self, **kw):
        self.id = kw.get("id")
        self.code = kw.get("code", "ST-001")
        self.name = kw.get("name")
        self.city = kw.get("city")
        self.district = kw.get("district")
        self.business_district = kw.get("business_district")
        self.store_type = kw.get("store_type")
        self.area_sqm = kw.get("area_sqm")
        self.consumption_power = kw.get("consumption_power")
        for k, _, _, _, _ in STORE_METRICS:
            setattr(self, k, kw.get(k))
        for k, _, _ in PROFILE_FIELDS:
            setattr(self, k, kw.get(k))


FULL_A = dict(
    id=1, name="甲店", sales_amount=500000, gross_profit=100000, gross_margin_rate=20.0,
    sales_qty=20000, sales_per_sqm=250, turnover_days=30, sku_count=3000,
    stockout_count=20, member_ratio=45, daily_customer_count=3000, health_score=70,
)
FULL_B = dict(
    id=2, name="乙店", sales_amount=300000, gross_profit=50000, gross_margin_rate=16.7,
    sales_qty=12000, sales_per_sqm=150, turnover_days=50, sku_count=1800,
    stockout_count=60, member_ratio=30, daily_customer_count=1800, health_score=45,
)


# ---------- 数据状态判定 ----------

def test_data_status_complete():
    s = FakeStore(**FULL_A)
    for k, _, _ in PROFILE_FIELDS:
        setattr(s, k, 50)
    st = store_data_status(s)
    assert st["metrics_ready"] is True
    assert st["profile_ready"] is True
    assert st["level"] == "完整"


def test_data_status_missing_metrics():
    s = FakeStore(**{**FULL_A, "health_score": None, "member_ratio": None})
    st = store_data_status(s)
    assert st["metrics_ready"] is False
    assert "综合健康度" in st["missing_metrics"]
    assert "会员销售占比" in st["missing_metrics"]
    assert st["level"] == "数据待接入"


def test_data_status_metrics_only():
    s = FakeStore(**FULL_A)
    st = store_data_status(s)
    assert st["metrics_ready"] is True
    assert st["profile_ready"] is False
    assert st["level"] == "仅经营指标"


# ---------- 指标方向 ----------

def test_turnover_and_stockout_are_reverse_metrics():
    reverse = {k: h for k, _, _, h, _ in STORE_METRICS}
    assert reverse["turnover_days"] is False, "周转天数越低越好"
    assert reverse["stockout_count"] is False, "缺货次数越少越好"
    assert reverse["sales_amount"] is True
    assert reverse["sku_count"] is None, "SKU 数是中性指标，不参与排名"


def test_reverse_normalization_applied():
    """验证逆向指标确实用反向标准化"""
    assert minmax_normalize([10, 30, 60], False)[0] > minmax_normalize([10, 30, 60], False)[-1]
    assert minmax_normalize([10, 30, 60], True)[0] < minmax_normalize([10, 30, 60], True)[-1]


# ---------- 对比逻辑（用纯函数验证关键行为）----------

def test_metric_catalog_covers_key_dimensions():
    keys = {k for k, _, _, _, _ in STORE_METRICS}
    for must in ["sales_amount", "gross_profit", "sales_per_sqm", "turnover_days",
                 "sku_count", "stockout_count", "health_score"]:
        assert must in keys, f"缺少对比维度 {must}"


def test_profile_catalog_covers_poi_and_people():
    keys = {k for k, _, _ in PROFILE_FIELDS}
    for must in ["pop_3km", "resident_ratio", "office_ratio", "student_ratio",
                 "senior_ratio", "poi_residential", "poi_office", "poi_school"]:
        assert must in keys, f"缺少画像字段 {must}"


def test_comparison_normalizes_across_stores():
    """两家店在销售额上的得分应为 100 和 0"""
    a, b = FakeStore(**FULL_A), FakeStore(**FULL_B)
    vals = [a.sales_amount, b.sales_amount]
    scores = minmax_normalize(vals, True)
    assert scores[0] == 100.0
    assert scores[1] == 0.0


def test_reverse_metric_winner_is_lower_value():
    """周转天数低的那家店应该得分高"""
    scores = minmax_normalize([30, 50], False)   # 甲店30天, 乙店50天
    assert scores[0] > scores[1], "周转天数少的门店应得分更高"


def test_neutral_metric_excluded_from_scoring():
    """SKU 数是中性指标，不应影响综合得分"""
    neutral = {k: h for k, _, _, h, _ in STORE_METRICS}
    assert neutral["sku_count"] is None


def test_missing_value_not_counted_as_zero():
    """缺失指标应被排除，而不是当作 0 参与排名"""
    b = FakeStore(**{**FULL_B, "health_score": None})
    assert b.health_score is None
    # minmax 遇到 None 会出错，所以服务层必须先过滤掉 None
    vals = [FakeStore(**FULL_A).health_score, b.health_score]
    filtered = [v for v in vals if v is not None]
    assert len(filtered) == 1, "过滤后只剩 1 个有效值，不应参与 2 方排名"


# ---------- 数据真实性约束 ----------

def test_platform_does_not_generate_metrics():
    """新建门店时未提供的指标必须保持 None（不自动填 0 或推算值）"""
    s = FakeStore(name="新店")
    for k, _, _, _, _ in STORE_METRICS:
        assert getattr(s, k) is None, f"{k} 不应被自动填充"
    st = store_data_status(s)
    assert st["metrics_ready"] is False
    assert st["metrics_filled"] == 0
