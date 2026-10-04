"""需求预测

当前附件的预测值为模拟结果，直接展示并标注「模拟预测结果」。
真实预测能力预留 Prophet / 移动平均两种路径：
历史数据不足 12 期时明确提示样本有限，不伪造精度。
"""
from typing import Dict, List, Optional

import pandas as pd

MIN_HISTORY_PERIODS = 12
RECOMMENDED_MIN_PERIODS = 24


def classify_trend(future_avg: float, recent_avg: float, threshold: float = 5.0) -> Dict:
    """趋势分类：明显上涨/温和上涨/基本稳定/温和下降/明显下降"""
    if recent_avg == 0:
        return {"level": "数据不足", "change_pct": None}
    change = (future_avg - recent_avg) / recent_avg * 100
    if change >= threshold * 2:
        level = "明显上涨"
    elif change >= threshold:
        level = "温和上涨"
    elif change <= -threshold * 2:
        level = "明显下降"
    elif change <= -threshold:
        level = "温和下降"
    else:
        level = "基本稳定"
    return {"level": level, "change_pct": round(change, 2)}


def assess_risk(level: str, upper_lower_gap: float, stockout: Optional[float] = None) -> Dict:
    """需求风险：结合趋势方向与预测区间宽度判断。"""
    factors = []
    if level in ("明显上涨", "温和上涨"):
        factors.append("需求上行，补货压力上升")
    elif level in ("明显下降", "温和下降"):
        factors.append("需求下行，需控制备货避免积压")
    else:
        factors.append("需求平稳")

    if upper_lower_gap > 40:
        factors.append("预测区间较宽，预测不确定性较高")
    elif upper_lower_gap <= 20:
        factors.append("预测区间较窄，预测置信度相对较高")

    if stockout is not None and stockout >= 10:
        factors.append(f"历史缺货 {int(stockout)} 次，上行期存在缺货风险")

    if level in ("明显上涨",) or (stockout or 0) >= 15:
        risk = "高"
    elif level in ("温和上涨", "温和下降", "明显下降"):
        risk = "中"
    else:
        risk = "低"
    return {"risk_level": risk, "factors": factors}


def build_forecast_view(
    category: str,
    history: List[Dict],
    forecasts: List[Dict],
    stockout_count: Optional[float] = None,
) -> Dict:
    """组装单品类预测视图。history/forecasts 为按周次升序的记录列表。"""
    actual_vals = [h["actual_qty"] for h in history if h.get("actual_qty") is not None]
    future_vals = [f["forecast_qty"] for f in forecasts if f.get("forecast_qty") is not None]

    if len(actual_vals) < MIN_HISTORY_PERIODS:
        sample_note = f"历史数据仅 {len(actual_vals)} 期，少于建议的 {MIN_HISTORY_PERIODS} 期，历史数据量有限，预测结果仅供趋势参考。"
        sample_sufficient = False
    elif len(actual_vals) < RECOMMENDED_MIN_PERIODS:
        sample_note = f"历史数据 {len(actual_vals)} 期，达到最低要求但低于推荐的 {RECOMMENDED_MIN_PERIODS} 期，预测结果仅供趋势参考。"
        sample_sufficient = False
    else:
        sample_note = f"历史数据 {len(actual_vals)} 期，样本量满足建模要求。"
        sample_sufficient = True

    future_avg = round(sum(future_vals) / len(future_vals), 2) if future_vals else None
    recent_avg = round(sum(actual_vals[-4:]) / min(4, len(actual_vals)), 2) if actual_vals else None

    trend = classify_trend(future_avg, recent_avg) if future_avg and recent_avg else {"level": "数据不足", "change_pct": None}

    gaps = [(f["upper_bound"] - f["lower_bound"]) / f["forecast_qty"] * 100
            for f in forecasts if f.get("upper_bound") and f.get("lower_bound") and f.get("forecast_qty")]
    avg_gap = round(sum(gaps) / len(gaps), 2) if gaps else 0.0

    risk = assess_risk(trend["level"], avg_gap, stockout_count)

    series = []
    for h in history:
        series.append({
            "period": h["period_label"],
            "week_no": h["week_no"],
            "actual": h["actual_qty"],
            "forecast": None,
            "lower": None,
            "upper": None,
            "type": "history",
        })
    for f in forecasts:
        series.append({
            "period": f["period_label"],
            "week_no": f["week_no"],
            "actual": None,
            "forecast": f["forecast_qty"],
            "lower": f["lower_bound"],
            "upper": f["upper_bound"],
            "type": "forecast",
        })

    return {
        "category": category,
        "series": series,
        "future_avg": future_avg,
        "recent_avg": recent_avg,
        "trend_level": trend["level"],
        "change_pct": trend["change_pct"],
        "avg_interval_width_pct": avg_gap,
        "risk": risk,
        "sample_note": sample_note,
        "sample_sufficient": sample_sufficient,
        "history_periods": len(actual_vals),
        "forecast_periods": len(future_vals),
        "is_simulated": True,
        "data_label": "模拟预测结果",
    }


def moving_average_forecast(history: List[float], periods: int = 4, window: int = 4) -> List[float]:
    """备用预测路径：移动平均。历史数据不足时明确不承诺精度。"""
    if len(history) < window:
        raise ValueError(f"历史数据不足 {window} 期，无法执行移动平均预测（当前 {len(history)} 期）")
    preds = []
    series = list(history)
    for _ in range(periods):
        avg = sum(series[-window:]) / window
        preds.append(round(avg, 2))
        series.append(avg)
    return preds