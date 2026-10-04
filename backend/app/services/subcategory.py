"""小类数据层：从交易明细实时聚合 70 个小类的真实指标

数据来源约束（重要）：
附件 dataset_transactions_sample.csv 只提供
交易号、商品编码、商品名称、品类、数量、交易日期、单价(元)
因此小类层可得：销量、销售额、均价、成交笔数、连带率、关联度
小类层不可得（平台留空，不用大类数据摊派）：毛利额、周转天数、坪效
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..algorithms import abc as abc_algo
from ..models import (
    AssociationRule, Category, DataUpload, ModelRunLog, SubCategory,
)

SUB_PARAMS = {
    "group_key": "交易号 + 商品名称",
    "metrics": ["sales_qty", "sales_amount", "avg_price", "transaction_count", "qty_per_transaction"],
    "unavailable_metrics": ["gross_profit", "turnover_days", "sales_per_sqm"],
    "unavailable_reason": "附件交易明细不含成本、库存与陈列面积字段，无法推导毛利、周转与坪效",
}


def _parse_date(v) -> Optional[date]:
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def rebuild_subcategories(db: Session, user: str = "system") -> Dict:
    """从 transaction_items 重新聚合小类指标。"""
    from ..models import TransactionItem

    rows = db.execute(
        select(
            TransactionItem.product_name,
            TransactionItem.category_name,
            func.sum(TransactionItem.quantity),
            func.sum(TransactionItem.amount),
            func.avg(TransactionItem.unit_price),
            func.count(func.distinct(TransactionItem.transaction_id)),
        ).group_by(TransactionItem.product_name, TransactionItem.category_name)
    ).all()

    if not rows:
        return {"success": False, "message": "数据库中没有交易明细，无法聚合小类数据"}

    # 单价与均价按每条明细的中位数更稳健，这里用 SQL 聚合的 avg 作为近似
    base = {}
    for name, cat, qty, amount, price, txn in rows:
        if not name:
            continue
        qty = float(qty or 0)
        amount = float(amount or 0)
        base[name] = {
            "product_name": name,
            "category_name": cat,
            "sales_qty": round(qty, 2),
            "sales_amount": round(amount, 2),
            "avg_price": round(float(price or 0), 2),
            "transaction_count": int(txn or 0),
            "qty_per_transaction": round(qty / txn, 3) if txn else None,
        }

    # 日期范围（有销售的起止日期）
    dr = db.execute(
        select(
            func.min(TransactionItem.__table__.c.id),
        )
    ).first()

    ds = db.query(DataUpload).filter(DataUpload.dataset_type == "transactions").first()
    ds_id = ds.id if ds else None

    # 关联度：从实时 Apriori 结果回填
    rules = db.query(AssociationRule).filter(AssociationRule.source == "realtime").all()
    assoc: Dict[str, Dict] = {}
    for r in rules:
        for n in {r.antecedent, r.consequent}:
            a = assoc.setdefault(n, {"count": 0, "max_lift": 0.0, "top_partner": ""})
            a["count"] += 1
            if (r.lift or 0) > a["max_lift"]:
                a["max_lift"] = r.lift or 0.0
                a["top_partner"] = r.consequent if n == r.antecedent else r.antecedent

    cats = {c.name: c.id for c in db.query(Category).all()}

    db.query(SubCategory).delete(synchronize_session=False)
    db.flush()

    now = datetime.utcnow()
    count = 0
    for name, b in base.items():
        a = assoc.get(name, {})
        cid = cats.get(b["category_name"])
        db.add(SubCategory(
            category_id=cid,
            name=name,
            sales_qty=b["sales_qty"],
            sales_amount=b["sales_amount"],
            avg_price=b["avg_price"],
            transaction_count=b["transaction_count"],
            qty_per_transaction=b["qty_per_transaction"],
            # 以下字段附件无数据源，保持 None 表示「未接入」
            gross_profit=None,
            turnover_days=None,
            sales_per_sqm=None,
            association_count=a.get("count", 0),
            max_lift=round(a.get("max_lift", 0.0), 4),
            top_partner=a.get("top_partner", ""),
            is_demo=True,
            source_dataset_id=ds_id,
            algorithm="小类指标实时聚合",
            parameters={**SUB_PARAMS, "association_source": "realtime_apriori"},
            created_at=now,
            updated_at=now,
        ))
        count += 1
    db.flush()

    # 立即跑 ABC 分类并回写
    abc_result = apply_abc(db, user)

    db.add(ModelRunLog(
        algorithm="小类指标聚合",
        parameters=SUB_PARAMS,
        dataset="transactions",
        status="success",
        output=f"{count} 个小类",
        duration_ms=0,
    ))
    db.commit()

    return {
        "success": True,
        "count": count,
        "abc": abc_result,
        "params": SUB_PARAMS,
    }


def apply_abc(db: Session, user: str = "system") -> Dict:
    """跑 ABC 分类并把结果回写到小类表。"""
    subs = db.query(SubCategory).all()
    items = [
        {
            "name": s.name,
            "category": s.category.name if s.category else None,
            "sales_amount": s.sales_amount,
            "sales_qty": s.sales_qty,
        }
        for s in subs
    ]
    result = abc_algo.abc_classify(items)
    if not result.get("success"):
        return result

    by_name = {r["name"]: r for r in result["rows"]}

    # 小类综合得分：销量贡献 50% + 销售额贡献 50%（小类层无毛利/周转/坪效）
    from ..algorithms.common import minmax_normalize
    names = [s.name for s in subs]
    qty_scores = minmax_normalize([s.sales_qty or 0 for s in subs], True)
    amt_scores = minmax_normalize([s.sales_amount or 0 for s in subs], True)
    idx = {n: i for i, n in enumerate(names)}
    score_map = {
        n: round(qty_scores[idx[n]] * 0.5 + amt_scores[idx[n]] * 0.5, 2) for n in names
    }
    qty_map = {n: qty_scores[idx[n]] for n in names}
    amt_map = {n: amt_scores[idx[n]] for n in names}

    # 按大类内排名
    by_cat: Dict[str, List[SubCategory]] = {}
    for s in subs:
        by_cat.setdefault(s.category.name if s.category else "未分类", []).append(s)

    for cat, group in by_cat.items():
        ranked = sorted(group, key=lambda x: -(x.sales_amount or 0))
        for i, s in enumerate(ranked, 1):
            s.rank_in_category = i
            row = by_name.get(s.name)
            if row:
                s.sub_score = score_map.get(s.name, 0)
                s.sub_score_sales = qty_map.get(s.name)
                s.sub_score_amount = amt_map.get(s.name)
                s.cluster_label = f"ABC-{row['abc_class']}"
                s.updated_at = datetime.utcnow()

    db.flush()
    result["written_back"] = True
    result["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    return result


def subcategory_list(db: Session, category_id: Optional[int] = None,
                     keyword: Optional[str] = None) -> List[Dict]:
    q = db.query(SubCategory)
    if category_id:
        q = q.filter(SubCategory.category_id == category_id)
    if keyword:
        q = q.filter(SubCategory.name.like(f"%{keyword}%"))
    rows = q.order_by(SubCategory.sales_amount.desc()).all()

    total_amount = sum(r.sales_amount or 0 for r in rows) or 1
    return [
        {
            "id": r.id,
            "category_id": r.category_id,
            "category": r.category.name if r.category else "未分类",
            "name": r.name,
            "sales_qty": r.sales_qty,
            "sales_amount": r.sales_amount,
            "amount_share_pct": round((r.sales_amount or 0) / total_amount * 100, 2),
            "avg_price": r.avg_price,
            "transaction_count": r.transaction_count,
            "qty_per_transaction": r.qty_per_transaction,
            "association_count": r.association_count,
            "max_lift": r.max_lift,
            "top_partner": r.top_partner,
            "gross_profit": r.gross_profit,
            "turnover_days": r.turnover_days,
            "sales_per_sqm": r.sales_per_sqm,
            "data_status": _data_status(r),
            "abc_class": (r.cluster_label or "").replace("ABC-", "") or None,
            "rank_in_category": r.rank_in_category,
            "shelf_area": r.shelf_area,
            "is_demo": r.is_demo,
        }
        for r in rows
    ]


def _data_status(r: SubCategory) -> Dict:
    missing = []
    if r.gross_profit is None:
        missing.append("毛利额")
    if r.turnover_days is None:
        missing.append("周转天数")
    if r.sales_per_sqm is None:
        missing.append("坪效")
    return {
        "complete": len(missing) == 0,
        "missing": missing,
        "note": (
            "小类层毛利、周转、坪效字段在附件中不存在，平台不做推算。"
            if missing else "字段完整，可进行四维评价。"
        ),
    }
