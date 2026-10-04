"""购物篮关联规则挖掘（Apriori + 规则生成）

自实现，不依赖 mlxtend，便于精确控制与测试。
默认以「交易号 + 商品名称」构建购物篮 —— 当前演示数据商品编码高度离散，
同一商品名称存在多个编码，按编码直接分析会得到无意义的规则。
真实企业数据接入后 SKU 编码稳定，可切换 group_by="sku_code"。
"""
from typing import Dict, List, Optional

import pandas as pd

REQUIRED_COLUMNS = {"交易号", "商品名称"}

# group_by 的逻辑键 → CSV 实际列名
GROUP_BY_COLUMNS = {
    "product_name": "商品名称",
    "sku_code": "商品编码",
}

DEFAULT_PARAMS = {
    "min_support": 0.02,
    "min_confidence": 0.50,
    "min_lift": 1.50,
    "top_n": 20,
    "group_by": "product_name",   # product_name / sku_code
}


class BasketKeyError(ValueError):
    pass


def build_baskets(df: pd.DataFrame, group_by: str = "product_name") -> List[set]:
    """把明细聚合成一篮子一个 set。"""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise BasketKeyError(f"交易明细字段缺失：{', '.join(missing)}")
    col = GROUP_BY_COLUMNS.get(group_by)
    if col is None:
        raise BasketKeyError(f"未知的聚合字段：{group_by}")
    if col not in df.columns:
        raise BasketKeyError(f"指定的聚合字段不存在：{col}")

    tmp = df[["交易号", col]].copy()
    tmp[col] = tmp[col].astype(str).str.strip()
    baskets = tmp.groupby("交易号")[col].agg(lambda s: set(s)).tolist()
    return [b for b in baskets if b]


def build_inverted_index(baskets: List[set]) -> Dict[str, set]:
    """倒排索引：商品 -> 含该商品的篮子编号集合。

    用集合交集算支持度，避免逐篮遍历，是本算法性能的关键。
    """
    index: Dict[str, set] = {}
    for i, b in enumerate(baskets):
        for item in b:
            index.setdefault(item, set()).add(i)
    return index


def _support(postings: List[set], total: int) -> float:
    """多个商品的联合支持度 = 篮子编号集合交集大小 / 总篮数。"""
    if not postings:
        return 0.0
    cur = set(postings[0])
    for p in postings[1:]:
        cur &= p
        if not cur:
            return 0.0
    return len(cur) / total


def apriori(baskets: List[set], min_support: float = 0.02, max_len: int = 2) -> List[tuple]:
    """频繁项集挖掘（倒排索引加速）。

    默认 max_len=2：商超关联陈列最实用的是二元组合，
    三元以上项集数量随品类扩张迅速膨胀，业务价值低且挤占 TopN。
    """
    total = len(baskets)
    if total == 0:
        return []
    index = build_inverted_index(baskets)
    frequent: List[tuple] = []

    # L1
    level_items = []
    for item, postings in index.items():
        sup = len(postings) / total
        if sup >= min_support:
            frequent.append((frozenset([item]), sup))
            level_items.append(item)

    if max_len >= 2:
        for i in range(len(level_items)):
            for j in range(i + 1, len(level_items)):
                a, b = level_items[i], level_items[j]
                sup = _support([index[a], index[b]], total)
                if sup >= min_support:
                    frequent.append((frozenset([a, b]), sup))

    return frequent


def generate_rules(
    baskets: List[set],
    min_support: float = 0.02,
    min_confidence: float = 0.50,
    min_lift: float = 1.50,
    top_n: int = 20,
    group_by: str = "product_name",
) -> Dict:
    total = len(baskets)
    if total == 0:
        return {"rules": [], "basket_count": 0, "item_count": 0,
                "params": {"min_support": min_support, "min_confidence": min_confidence,
                           "min_lift": min_lift, "top_n": top_n, "group_by": group_by}}

    freq = apriori(baskets, min_support=min_support)
    support_map = {fs: sup for fs, sup in freq}
    max_len = max((len(fs) for fs, _ in freq), default=1)

    rules: List[Dict] = []
    for itemset, sup in freq:
        if len(itemset) < 2:
            continue
        items = sorted(itemset)
        # 前项 = 除最后一个元素外的组合
        for i in range(len(items)):
            antecedent = items[:i] + items[i + 1:]
            consequent = items[i]
            a_sup = support_map.get(frozenset(antecedent))
            b_sup = support_map.get(frozenset([consequent]))
            if a_sup is None or not a_sup:
                continue
            confidence = sup / a_sup
            if confidence < min_confidence:
                continue
            # lift = P(A∧B) / (P(A)·P(B)) = confidence / P(B)
            if b_sup is None or not b_sup:
                continue
            lift = confidence / b_sup
            if lift < min_lift:
                continue
            rules.append({
                "antecedent": " + ".join(antecedent),
                "consequent": consequent,
                "support": round(sup, 6),
                "confidence": round(confidence, 6),
                "lift": round(lift, 4),
                "antecedent_set": antecedent,
                "consequent_set": consequent,
                "item_count": len(itemset),
                "basket_count": int(round(sup * total)),
            })

    rules.sort(key=lambda r: (r["lift"] * r["confidence"]), reverse=True)
    rules = rules[:top_n]
    for r in rules:
        r["strength"] = strength_label(r["lift"], r["confidence"])
        r["display_rule"] = f"{r['antecedent']} → {r['consequent']}"
        r["display_suggestion"] = display_suggestion(r)
        r["business_explanation"] = business_explanation(r)

    item_set = set()
    for b in baskets:
        item_set |= b

    return {
        "rules": rules,
        "basket_count": total,
        "item_count": len(item_set),
        "max_itemset_len": max_len,
        "total_candidate_rules": len(rules),
        "params": {
            "min_support": min_support,
            "min_confidence": min_confidence,
            "min_lift": min_lift,
            "top_n": top_n,
            "group_by": group_by,
        },
    }


def strength_label(lift: float, confidence: float) -> str:
    if lift >= 3.0 and confidence >= 0.6:
        return "极强关联"
    if lift >= 2.0:
        return "强关联"
    if lift >= 1.5:
        return "中等关联"
    return "弱关联"


def business_explanation(r: Dict) -> str:
    lift = r["lift"]
    conf = r["confidence"]
    if lift >= 3.0:
        return f"购买「{r['consequent']}」的顾客中有 {conf*100:.1f}% 同时购买了「{r['antecedent']}」，提升度 {lift} 表明两者同现概率是随机情况下的 {lift} 倍，属于极强关联。"
    if lift >= 2.0:
        return f"「{r['antecedent']}」带动「{r['consequent']}」的能力较强（提升度 {lift}），置信度 {conf*100:.1f}%，适合做关联陈列与组合促销。"
    return f"提升度 {lift}，高于随机基准但强度有限，可作为辅助陈列参考，不建议单独做组合促销。"


def display_suggestion(r: Dict) -> str:
    a, b = r["antecedent"], r["consequent"]
    return f"「{a}」与「{b}」相邻陈列；组合促销可设为满额优惠或第二件折扣。"


def baskets_from_pairs(pairs: List[tuple]) -> List[set]:
    """直接从 (交易号, 商品) 列表构建购物篮，避免构造中间 DataFrame。"""
    groups: Dict[str, set] = {}
    for tx, item in pairs:
        groups.setdefault(tx, set()).add(item)
    return list(groups.values())


def run_from_pairs(
    pairs: List[tuple],
    min_support: float = 0.02,
    min_confidence: float = 0.50,
    min_lift: float = 1.50,
    top_n: int = 20,
    group_by: str = "product_name",
) -> Dict:
    baskets = baskets_from_pairs(pairs)
    return generate_rules(baskets, min_support, min_confidence, min_lift, top_n, group_by)


def run_association_analysis(
    df: pd.DataFrame,
    min_support: float = 0.02,
    min_confidence: float = 0.50,
    min_lift: float = 1.50,
    top_n: int = 20,
    group_by: str = "product_name",
) -> Dict:
    baskets = build_baskets(df, group_by=group_by)
    return generate_rules(baskets, min_support, min_confidence, min_lift, top_n, group_by)


def item_profile(result: Dict, item: str) -> Optional[Dict]:
    """查看某商品的最强关联商品。"""
    rules = result.get("rules", [])
    rel = [r for r in rules if item in r["antecedent"] or item == r["consequent"]]
    if not rel:
        return None
    rel.sort(key=lambda r: r["lift"], reverse=True)
    freq = sum(1 for r in rel)
    return {
        "item": item,
        "rule_count": len(rel),
        "appear_in_rules": freq,
        "top_relations": [
            {
                "partner": r["consequent"] if item in r["antecedent"] else r["antecedent"],
                "direction": "后项" if item in r["antecedent"] else "前项",
                "lift": r["lift"],
                "confidence": r["confidence"],
                "support": r["support"],
            }
            for r in rel[:6]
        ],
    }