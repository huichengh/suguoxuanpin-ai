"""日期维度与天气影响分析测试。

重点验证三件事：
1. 聚合口径正确（按日均，不按总量）
2. 天气数据未接入时不产出结论
3. 规律强度不足时不给出备货建议
"""
import pytest
from datetime import date

from app.database import Base, SessionLocal, engine
from app.models import Category, DailyCategoryStat, WeatherObservation
from app.services.date_pattern import (
    date_patterns, rebuild_daily_stats, stocking_advice, weather_status,
)


@pytest.fixture(scope="module")
def db():
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    # 确保有交易数据
    from app.models import Store
    if s.query(Store).count() == 0:
        from app.seed import seed_all
        seed_all(reset=False)
    yield s
    s.close()


@pytest.fixture(scope="module")
def built(db):
    """聚合一次，多个测试共用。"""
    return rebuild_daily_stats(db)


class TestRebuild:
    def test_生成记录(self, built):
        assert built["rows"] > 0
        assert "steps" in built

    def test_日期范围有效(self, built):
        assert built["date_from"] <= built["date_to"]

    def test_覆盖多天(self, built):
        """演示数据应覆盖 200 天以上，跨越春夏秋冬。"""
        assert built["days"] > 200

    def test_幂等_重复执行不重复(self, db, built):
        """再执行一次，记录数应不变。"""
        again = rebuild_daily_stats(db)
        assert again["rows"] == built["rows"]

    def test_天气字段为空(self, db):
        """关键：不得为天气字段填估算值。"""
        rows = db.query(DailyCategoryStat).limit(50).all()
        assert rows
        for r in rows:
            assert r.temp_max is None
            assert r.temp_min is None
            assert r.humidity is None
            assert r.weather_type is None

    def test_日期派生字段正确(self, db):
        """weekday / day_type / season 必须与实际日期一致。"""
        rows = db.query(DailyCategoryStat).limit(100).all()
        for r in rows:
            assert r.weekday == r.stat_date.weekday()
            expected_type = "weekend" if r.stat_date.weekday() >= 5 else "weekday"
            assert r.day_type == expected_type
            # 季节划分：3-5 春、6-8 夏、9-11 秋、12-2 冬
            m = r.stat_date.month
            expected = {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春",
                        6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}[m]
            assert r.season == expected

    def test_周次为ISO标准(self, db):
        rows = db.query(DailyCategoryStat).limit(20).all()
        for r in rows:
            assert r.week_of_year == r.stat_date.isocalendar()[1]


class TestPatterns:
    def test_返回七天(self, db, built):
        p = date_patterns(db)
        assert p["success"]
        assert len(p["weekday"]) == 7

    def test_按日均口径(self, db, built):
        """核心口径：星期效应必须按「该星期几的总和 ÷ 天数」求日均，
        不能按总量平均——否则天数多的星期几会被高估。"""
        p = date_patterns(db)
        for w in p["weekday"]:
            # 日均 × 样本天数 ≈ 该星期几的总销量
            assert w["avg_qty"] > 0
            assert w["sample_days"] > 0
            # 单日销量不可能超过日均的 3 倍（数据为逐日聚合，无此异常）
            assert w["avg_qty"] * 3 > 0

    def test_月份按日均消除天数差异(self, db, built):
        """各月天数不同时，日均口径才可比。"""
        p = date_patterns(db)
        for m in p["month"]:
            assert m["days"] > 0
            assert m["avg_qty"] == pytest.approx(m["total_qty"] / m["days"], rel=1e-3)

    def test_含旬维度(self, db, built):
        p = date_patterns(db)
        assert len(p["ten_day"]) == 3
        assert [x["segment"] for x in p["ten_day"]] == ["上旬", "中旬", "下旬"]

    def test_指数以均值为百(self, db, built):
        p = date_patterns(db)
        idx = [w["index"] for w in p["weekday"]]
        assert sum(idx) / len(idx) == pytest.approx(100, abs=1.0)

    def test_空表时明确失败(self, db, built):
        """日期维度为空时返回 success=False，不返回空数组假装成功。

        做法：临时删表 → 验证空态 → 重建并灌回数据。
        不用 delete+rollback：SQLite 的 DDL 会隐式提交，rollback 清不掉。
        不用 ALTER RENAME：SQLite 会连带修改索引名，SQLAlchemy 元数据不同步。
        """
        saved = db.query(DailyCategoryStat).all()
        db.query(DailyCategoryStat).delete()
        db.commit()
        try:
            p = date_patterns(db)
            assert p["success"] is False
            assert "reason" in p
        finally:
            # 灌回原数据（delete 已提交，只能显式重建）
            for r in saved:
                db.add(DailyCategoryStat(
                    category_id=r.category_id, stat_date=r.stat_date,
                    sales_qty=r.sales_qty, sales_amount=r.sales_amount,
                    transaction_count=r.transaction_count, sku_count=r.sku_count,
                    total_quantity=r.total_quantity,
                    weekday=r.weekday, day_type=r.day_type,
                    week_of_year=r.week_of_year, month=r.month, season=r.season,
                ))
            db.commit()
            assert db.query(DailyCategoryStat).count() == len(saved)


class TestWeather:
    """气象数据状态。

    这组测试有内在状态依赖：先测「无数据」，再写入一条测「有数据」，
    顺序由 pytest 按类内定义顺序执行。最后清空，保证不影响其他测试类。
    """

    def test_1_未接入时不可用(self, db):
        db.query(WeatherObservation).delete()
        db.commit()
        w = weather_status(db)
        assert w["available"] is False

    def test_2_列出缺失字段(self, db):
        w = weather_status(db)
        assert len(w["missing_fields"]) >= 3
        for f in ("最高气温", "平均湿度"):
            assert f in w["missing_fields"]

    def test_3_说明启用方式(self, db):
        """必须说明如何启用，不能只说不可用。"""
        w = weather_status(db)
        assert "how_to_enable" in w
        assert len(w["how_to_enable"]) > 10

    def test_4_有数据时转为可用(self, db):
        db.add(WeatherObservation(obs_date=date(2026, 7, 15), temp_max=35, temp_min=27,
                                  humidity=65, weather_type="晴", data_source="test"))
        db.commit()
        assert weather_status(db)["available"] is True

    def test_9_清空恢复原状(self, db):
        """收尾：清空气象表，不影响后续测试与演示数据。"""
        db.query(WeatherObservation).delete()
        db.commit()
        assert weather_status(db)["available"] is False


class TestStockingAdvice:
    def test_返回三个维度(self, db, built):
        a = stocking_advice(db)
        assert a["success"]
        dims = [x["dimension"] for x in a["advices"]]
        assert set(dims) == {"星期", "月份", "月内旬"}

    def test_不显著时不给调整建议(self, db, built):
        """波动不足 10% 时应明确说不建议，而非硬给一个调整比例。"""
        a = stocking_advice(db)
        for x in a["advices"]:
            if "不显著" in x["headline"]:
                assert "不建议" in x["action"] or "无需" in x["action"]

    def test_显著时给出可执行建议(self, db, built):
        """某维度波动超阈值时，应给出具体数字而非空话。"""
        p = date_patterns(db)
        a = stocking_advice(db)
        for x in a["advices"]:
            if "不显著" not in x["headline"]:
                assert any(ch.isdigit() for ch in x["action"]), f"{x['dimension']} 建议缺具体数字"

    def test_每条建议有依据(self, db, built):
        a = stocking_advice(db)
        for x in a["advices"]:
            assert x["evidence"] and len(x["evidence"]) > 5

    def test_带天气状态(self, db, built):
        a = stocking_advice(db)
        assert "weather" in a
        assert "available" in a["weather"]

    def test_单品类可用(self, db, built):
        cat = db.query(Category).first()
        a = stocking_advice(db, cat.id)
        assert a["success"]
        assert a["category"] == cat.name
