"""日期维度聚合服务：从交易明细生成「品类 × 日」事实表。

设计要点：
1. 幂等：重复执行不重复插入，按 (category_id, stat_date) 覆盖
2. 不填估算值：天气字段一律留 None，由调用方判断是否可用
3. 可复算：口径固定，任何人重跑得到同一结果
"""
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Category, DailyCategoryStat, Transaction, TransactionItem

# 气象学季节划分（依据中国气象局标准）
SEASON_BY_MONTH = {
    3: "春", 4: "春", 5: "春",
    6: "夏", 7: "夏", 8: "夏",
    9: "秋", 10: "秋", 11: "秋",
    12: "冬", 1: "冬", 2: "冬",
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _season(d: date) -> str:
    return SEASON_BY_MONTH[d.month]


def _day_type(d: date) -> str:
    return "weekend" if d.weekday() >= 5 else "weekday"


def rebuild_daily_stats(db: Session, user: Optional[str] = None) -> Dict:
    """从交易明细重建日期维度事实表。

    返回统计结果字典，含 steps 明细供前端展示。
    """
    result: Dict = {"steps": [], "rows": 0, "categories": 0,
                    "date_from": None, "date_to": None, "days": 0}

    cats = {c.name: c for c in db.query(Category).all()}
    result["categories"] = len(cats)

    # 清空后重建，保证口径一致（幂等）
    db.query(DailyCategoryStat).delete()
    db.flush()

    # 一次性把交易明细join到商品，避免 N+1 查询
    rows = (
        db.query(
            TransactionItem.category_name,
            TransactionItem.product_name,
            TransactionItem.quantity,
            TransactionItem.amount,
            Transaction.trans_date,
        )
        .join(Transaction, TransactionItem.transaction_id == Transaction.id)
        .all()
    )

    if not rows:
        result["steps"].append("交易明细为空，未生成日期维度数据")
        db.commit()
        return result

    # 按 (品类, 日期) 聚合
    agg: Dict[tuple, Dict] = {}
    dates_seen = set()
    for cat_name, product_name, qty, amount, tdate in rows:
        if tdate is None or cat_name not in cats:
            continue
        key = (cat_name, tdate)
        a = agg.setdefault(key, {
            "sales_qty": 0.0, "sales_amount": 0.0,
            "transaction_count": 0, "skus": set(),
        })
        a["sales_qty"] += float(qty or 0)
        a["sales_amount"] += float(amount or 0)
        a["transaction_count"] += 1
        a["skus"].add(product_name)
        dates_seen.add(tdate)

    result["date_from"] = min(dates_seen).isoformat()
    result["date_to"] = max(dates_seen).isoformat()
    result["days"] = len(dates_seen)

    # 逐日写入
    insert_rows = []
    for (cat_name, tdate), a in agg.items():
        insert_rows.append(DailyCategoryStat(
            category_id=cats[cat_name].id,
            stat_date=tdate,
            sales_qty=a["sales_qty"],
            sales_amount=a["sales_amount"],
            transaction_count=a["transaction_count"],
            sku_count=len(a["skus"]),
            total_quantity=a["sales_qty"],
            # 天气字段保持 None——附件无气象数据，不填估算值
            temp_max=None, temp_min=None, humidity=None,
            weather_type=None, precipitation=None,
            # 日期派生字段：由日期直接算出，非估算
            weekday=tdate.weekday(),
            day_type=_day_type(tdate),
            week_of_year=tdate.isocalendar()[1],
            month=tdate.strftime("%Y-%m"),
            season=_season(tdate),
        ))

    db.bulk_save_objects(insert_rows)
    db.commit()
    result["rows"] = len(insert_rows)
    result["steps"].append(
        f"聚合 {len(dates_seen)} 天 × {len(cats)} 个品类，生成 {len(insert_rows)} 条日期维度记录")
    result["steps"].append("天气字段（温度／湿度／降水）保持为空——附件数据集不含气象数据")
    return result


def date_patterns(db: Session, category_id: Optional[int] = None) -> Dict:
    """计算日期维度规律：星期效应、月份效应、大小月效应。

    口径说明（重要）：
    所有指标均按「日均」计算，而非按月总量。
    原因是各月覆盖天数不同（28 天 vs 31 天），
    用总量比较会把天数差异误读为需求差异。
    """
    q = db.query(DailyCategoryStat)
    if category_id:
        q = q.filter(DailyCategoryStat.category_id == category_id)
    rows = q.all()

    if not rows:
        return {"success": False, "reason": "日期维度数据为空，请先执行聚合"}

    # ---------- 星期效应 ----------
    dow_qty: Dict[int, List[float]] = {i: [] for i in range(7)}
    dow_txn: Dict[int, List[float]] = {i: [] for i in range(7)}
    # 同一星期几跨多周，需先按 (星期几, 日期) 求和再取日均
    by_dow_date: Dict[int, Dict[date, float]] = {i: {} for i in range(7)}
    by_dow_date_txn: Dict[int, Dict[date, float]] = {i: {} for i in range(7)}

    month_qty: Dict[str, float] = {}
    month_days: Dict[str, set] = {}
    month_txn: Dict[str, float] = {}
    date_total: Dict[date, float] = {}

    for r in rows:
        wd = r.weekday if r.weekday is not None else r.stat_date.weekday()
        d = r.stat_date
        by_dow_date[wd].setdefault(d, 0.0)
        by_dow_date[wd][d] += float(r.sales_qty or 0)
        by_dow_date_txn[wd].setdefault(d, 0.0)
        by_dow_date_txn[wd][d] += float(r.transaction_count or 0)

        mk = r.month or d.strftime("%Y-%m")
        month_qty[mk] = month_qty.get(mk, 0.0) + float(r.sales_qty or 0)
        month_txn[mk] = month_txn.get(mk, 0.0) + float(r.transaction_count or 0)
        month_days.setdefault(mk, set()).add(d)
        date_total[d] = date_total.get(d, 0.0) + float(r.sales_qty or 0)

    dow_stats = []
    for i in range(7):
        days = len(by_dow_date[i])
        if days == 0:
            continue
        qty = sum(by_dow_date[i].values()) / days
        txn = sum(by_dow_date_txn[i].values()) / days
        dow_stats.append({
            "weekday": i, "name": WEEKDAY_NAMES[i], "day_type": _day_type(date(2026, 1, 5 + i)),
            "avg_qty": round(qty, 1), "avg_txn": round(txn, 1), "sample_days": days,
        })

    all_avg = sum(s["avg_qty"] for s in dow_stats) / len(dow_stats) if dow_stats else 0
    for s in dow_stats:
        s["index"] = round(s["avg_qty"] / all_avg * 100, 1) if all_avg else 0

    we = [s for s in dow_stats if s["day_type"] == "weekend"]
    wd = [s for s in dow_stats if s["day_type"] == "weekday"]
    we_avg = sum(s["avg_qty"] for s in we) / len(we) if we else 0
    wd_avg = sum(s["avg_qty"] for s in wd) / len(wd) if wd else 0

    # ---------- 月份效应（按日均，消除天数差异）----------
    month_stats = []
    for mk in sorted(month_qty):
        days = len(month_days[mk])
        month_stats.append({
            "month": mk,
            "days": days,
            "total_qty": round(month_qty[mk], 0),
            "avg_qty": round(month_qty[mk] / days, 1) if days else 0,
            "avg_txn": round(month_txn.get(mk, 0) / days, 1) if days else 0,
        })
    m_avg = sum(m["avg_qty"] for m in month_stats) / len(month_stats) if month_stats else 0
    for m in month_stats:
        m["index"] = round(m["avg_qty"] / m_avg * 100, 1) if m_avg else 0
        m["is_big_month"] = m["days"] >= 30

    # ---------- 月内旬维度 ----------
    # 不用「大小月」：演示数据每月均为 28 天，大小月对比无实际差异。
    # 改为「上旬／中旬／下旬」，这个在任何月份都成立。
    ten_day_qty: Dict[str, float] = {"上旬": 0.0, "中旬": 0.0, "下旬": 0.0}
    ten_day_days: Dict[str, set] = {"上旬": set(), "中旬": set(), "下旬": set()}
    for r in rows:
        d = r.stat_date
        seg = "上旬" if d.day <= 10 else ("中旬" if d.day <= 20 else "下旬")
        ten_day_qty[seg] += float(r.sales_qty or 0)
        ten_day_days[seg].add(d)

    ten_day_stats = []
    for seg in ("上旬", "中旬", "下旬"):
        days = len(ten_day_days[seg])
        ten_day_stats.append({
            "segment": seg,
            "days": days,
            "avg_qty": round(ten_day_qty[seg] / days, 1) if days else 0,
        })
    td_avg = sum(s["avg_qty"] for s in ten_day_stats) / len(ten_day_stats) if ten_day_stats else 0
    for s in ten_day_stats:
        s["index"] = round(s["avg_qty"] / td_avg * 100, 1) if td_avg else 0

    # ---------- 离散度：判断规律是否值得作为备货依据 ----------
    qty_vals = [s["avg_qty"] for s in dow_stats]
    dow_spread = (max(qty_vals) - min(qty_vals)) / min(qty_vals) * 100 if qty_vals and min(qty_vals) else 0
    m_vals = [m["avg_qty"] for m in month_stats]
    month_spread = (max(m_vals) - min(m_vals)) / min(m_vals) * 100 if m_vals and min(m_vals) else 0
    td_vals = [s["avg_qty"] for s in ten_day_stats]
    ten_spread = (max(td_vals) - min(td_vals)) / min(td_vals) * 100 if td_vals and min(td_vals) else 0

    return {
        "success": True,
        "date_from": min(date_total).isoformat() if date_total else None,
        "date_to": max(date_total).isoformat() if date_total else None,
        "total_days": len(date_total),
        "weekday": dow_stats,
        "weekday_spread_pct": round(dow_spread, 1),
        "weekend_vs_weekday": round(we_avg / wd_avg, 3) if wd_avg else None,
        "month": month_stats,
        "month_spread_pct": round(month_spread, 1),
        "ten_day": ten_day_stats,
        "ten_day_spread_pct": round(ten_spread, 1),
        # 备货建议阈值：日均波动超过 10% 才有备货意义
        "restock_threshold_pct": 10.0,
        "weekday_signal": dow_spread >= 10.0,
        "month_signal": month_spread >= 10.0,
        "ten_day_signal": ten_spread >= 10.0,
        # 数据形态说明，供前端如实展示
        "data_note": "演示数据每月固定为 28 天，因此不做大小月对比；"
                     "月内维度采用上旬／中旬／下旬，该划分在任何月份均成立。",
    }


def weather_status(db: Session) -> Dict:
    """检查气象数据是否已接入。

    不返回估算值。未接入时明确给出缺失字段说明，
    供接口直接透传给前端做「待接入」标注。
    """
    from ..models import WeatherObservation
    total = db.query(WeatherObservation).count()
    if total == 0:
        return {
            "available": False,
            "reason": "气象数据未接入",
            "missing_fields": ["最高气温", "最低气温", "平均湿度", "降水量", "天气类型"],
            "impact": "天气影响分析无法计算。平台不使用估算值填充，"
                      "以免给出看似合理但无数据支撑的备货建议。",
            "how_to_enable": "外部气象数据接入 weather_observations 表后，"
                             "本模块自动启用，无需修改表结构。",
        }
    return {"available": True, "records": total}


def stocking_advice(db: Session, category_id: Optional[int] = None) -> Dict:
    """生成备货与排班参考。

    只在规律强度达到阈值时才给建议——
    日均波动不足 10% 时，说明日期对该品类影响可忽略，
    此时给建议会造成不必要的复杂度。
    """
    pat = date_patterns(db, category_id)
    if not pat.get("success"):
        return pat

    from ..models import Category
    cat_name = None
    if category_id:
        c = db.get(Category, category_id)
        cat_name = c.name if c else None

    advices: List[Dict] = []

    # 星期维度建议
    if pat["weekday_signal"]:
        peak = max(pat["weekday"], key=lambda x: x["avg_qty"])
        low = min(pat["weekday"], key=lambda x: x["avg_qty"])
        base = sum(s["avg_qty"] for s in pat["weekday"]) / len(pat["weekday"])
        advices.append({
            "dimension": "星期",
            "headline": f"{peak['name']}为备货高峰，日均 {peak['avg_qty']} 件"
                        f"（指数 {peak['index']}）",
            "action": f"{peak['name']}前一日按基线 {round(base)} 件的 "
                       f"{round(peak['avg_qty'] / base * 100)}% 备货；"
                       f"{low['name']}可降至 {round(low['avg_qty'] / base * 100)}%",
            "evidence": f"基于 {peak['sample_days']} 个{peak['name']}样本，日均标准口径",
        })
    else:
        advices.append({
            "dimension": "星期",
            "headline": f"星期效应不显著（周内日均波动仅 {pat['weekday_spread_pct']}%）",
            "action": "不建议按星期调整备货量，统一按日均备货即可",
            "evidence": f"周内日均区间 {min(s['avg_qty'] for s in pat['weekday'])}—"
                        f"{max(s['avg_qty'] for s in pat['weekday'])} 件",
        })

    # 月份维度建议
    if pat["month_signal"]:
        peak_m = max(pat["month"], key=lambda x: x["avg_qty"])
        low_m = min(pat["month"], key=lambda x: x["avg_qty"])
        adj = round((peak_m["index"] - 100) / 100 * 100)
        low_adj = round((low_m["index"] - 100) / 100 * 100)
        advices.append({
            "dimension": "月份",
            "headline": f"{peak_m['month']}为需求高峰，日均 {peak_m['avg_qty']} 件"
                        f"（指数 {peak_m['index']}）",
            "action": f"{peak_m['month']}整月按日均 {peak_m['avg_qty']} 件安排进货"
                       f"（较基线{adj:+d}%）；{low_m['month']}可压缩至日均 "
                       f"{low_m['avg_qty']} 件（{low_adj:+d}%）",
            "evidence": f"按日均口径计算，已消除各月天数差异"
                        f"（{peak_m['days']} 天 vs {low_m['days']} 天）",
        })
    else:
        advices.append({
            "dimension": "月份",
            "headline": f"月份效应不显著（日均波动 {pat['month_spread_pct']}%）",
            "action": "不建议按月份调整备货量",
            "evidence": f"各月日均区间 {min(m['avg_qty'] for m in pat['month'])}—"
                        f"{max(m['avg_qty'] for m in pat['month'])} 件",
        })

    # 月内旬维度建议
    if pat.get("ten_day_signal"):
        peak_t = max(pat["ten_day"], key=lambda x: x["avg_qty"])
        low_t = min(pat["ten_day"], key=lambda x: x["avg_qty"])
        advices.append({
            "dimension": "月内旬",
            "headline": f"{peak_t['segment']}为月内高峰，日均 {peak_t['avg_qty']} 件"
                        f"（指数 {peak_t['index']}）",
            "action": f"{peak_t['segment']}适度提高备货量，{low_t['segment']}可回调；"
                       f"建议按旬滚动补货而非月初一次性备足",
            "evidence": f"基于 {peak_t['days']} 天{peak_t['segment']}样本，日均口径",
        })
    else:
        advices.append({
            "dimension": "月内旬",
            "headline": f"月内旬间差异不显著（波动 {pat['ten_day_spread_pct']}%）",
            "action": "无需按旬调整，按日均备货即可",
            "evidence": "上旬／中旬／下旬日均差异在 10% 以内",
        })

    return {
        "success": True,
        "category": cat_name,
        "advices": advices,
        "pattern": pat,
        "weather": weather_status(db),
    }
