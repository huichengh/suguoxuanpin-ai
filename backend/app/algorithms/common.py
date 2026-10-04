"""算法层公共工具：标准化与权重校验"""
from typing import Dict, Iterable, List, Optional


class MissingFieldError(ValueError):
    """必需字段缺失时抛出，由 API 层转为 400 + 明确提示"""

    def __init__(self, missing: Iterable[str], context: str = ""):
        self.missing = list(missing)
        msg = f"数据字段缺失：{', '.join(self.missing)}"
        if context:
            msg += f"（{context}）"
        super().__init__(msg)


def minmax_normalize(values: List[float], higher_is_better: bool = True) -> List[float]:
    """Min-Max 标准化到 0-100。

    higher_is_better=False 用于「库存周转天数」这类越低越好的指标，
    做逆向归一化，避免周转天数长反而得高分。
    """
    n = len(values)
    if n == 0:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        # 全部相同：给中性分 60，避免除零并保留区分度
        return [60.0] * n
    if higher_is_better:
        return [round((v - lo) / (hi - lo) * 100, 2) for v in values]
    return [round((hi - v) / (hi - lo) * 100, 2) for v in values]


def validate_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """权重校验：非负，总和必须接近 1，否则抛错（评分模型的前提）。"""
    cleaned = {}
    for k, v in weights.items():
        fv = float(v)
        if fv < 0:
            raise ValueError(f"权重不能为负数：{k}={fv}")
        cleaned[k] = fv
    total = sum(cleaned.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"权重之和必须为 1，当前为 {total:.4f}")
    return cleaned


def weighted_score(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    return round(sum(scores.get(k, 0.0) * w for k, w in weights.items()), 2)


def grade_of(score: float) -> tuple:
    """返回 (等级, 星级, 是否低于三星)"""
    if score >= 85:
        return "优秀", "★★★★★", False
    if score >= 70:
        return "良好", "★★★★☆", False
    if score >= 55:
        return "一般", "★★★☆☆", False
    if score >= 40:
        return "较差", "★★☆☆☆", True
    return "差", "★☆☆☆☆", True


def trend_pct(series: List[float], window: int = 3) -> Optional[float]:
    """近 window 期 vs 前 window 期的环比变化率(%)，数据不足返回 None。"""
    if len(series) < window * 2:
        return None
    recent = sum(series[-window:]) / window
    prev = sum(series[-window * 2:-window]) / window
    if prev == 0:
        return None
    return round((recent - prev) / prev * 100, 2)