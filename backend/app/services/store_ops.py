"""多门店服务：门店录入、经营指标对比、差异分析

数据真实性约束：
- 附件 dataset_category_sales.csv 只提供一家门店（黄金海岸广场店）的数据
- 其余门店的经营指标必须由用户录入或上传，平台不生成、不推算、不复制
- 缺失字段在对比中显示「待接入」，不参与该维度的排名
"""
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..algorithms.common import minmax_normalize
from ..models import AuditLog, Store, User

# 对比维度定义：key → (标签, 单位, 越高越好, 数据来源说明)
STORE_METRICS = [
    ("sales_amount", "月销售额", "元", True, "门店月度销售总额"),
    ("gross_profit", "月毛利额", "元", True, "销售额 - 成本"),
    ("gross_margin_rate", "毛利率", "%", True, "毛利额 / 销售额"),
    ("sales_qty", "月销量", "件", True, "销售件数"),
    ("sales_per_sqm", "坪效", "元/㎡/月", True, "销售额 / 营业面积"),
    ("turnover_days", "库存周转", "天", False, "周转天数越低越好（逆向标准化）"),
    ("sku_count", "在售SKU数", "个", None, "商品数，非越大越好"),
    ("stockout_count", "月缺货次数", "次", False, "越少越好"),
    ("member_ratio", "会员销售占比", "%", True, "会员消费贡献"),
    ("daily_customer_count", "日均客流", "人", True, "门店日均客流量"),
    ("health_score", "综合健康度", "分", True, "0-100，平台评分模型输出"),
]

# 画像维度（用于 STP / 千店千面定位）
PROFILE_FIELDS = [
    ("pop_3km", "3公里人口", "人"),
    ("resident_ratio", "居民占比", "%"),
    ("office_ratio", "办公人群占比", "%"),
    ("student_ratio", "学生占比", "%"),
    ("senior_ratio", "中老年占比", "%"),
    ("poi_residential", "住宅POI", "个"),
    ("poi_office", "办公POI", "个"),
    ("poi_school", "学校POI", "个"),
]


def store_data_status(s: Store) -> Dict:
    """检查一家门店的数据完整度。"""
    missing_metrics = [
        label for key, label, _, _, _ in STORE_METRICS if getattr(s, key, None) is None
    ]
    missing_profile = [
        label for key, label, _ in PROFILE_FIELDS if getattr(s, key, None) in (None, "")
    ]
    metrics_ready = len(missing_metrics) == 0
    return {
        "metrics_ready": metrics_ready,
        "metrics_total": len(STORE_METRICS),
        "metrics_filled": len(STORE_METRICS) - len(missing_metrics),
        "missing_metrics": missing_metrics,
        "profile_ready": len(missing_profile) == 0,
        "profile_filled": len(PROFILE_FIELDS) - len(missing_profile),
        "missing_profile": missing_profile,
        "level": "完整" if metrics_ready and not missing_profile else ("仅经营指标" if metrics_ready else "数据待接入"),
    }


def list_stores(db: Session) -> List[Dict]:
    rows = db.query(Store).order_by(Store.is_default.desc(), Store.id).all()
    return [
        {
            "id": s.id, "code": s.code, "name": s.name,
            "city": s.city, "district": s.district,
            "business_district": s.business_district,
            "store_type": s.store_type, "area_sqm": s.area_sqm,
            "is_default": s.is_default, "is_demo": s.is_demo,
            "consumption_power": s.consumption_power,
            "main_competitors": s.main_competitors,
            "delivery_capability": s.delivery_capability,
            "profile": {
                k: getattr(s, k) for k, _, _ in PROFILE_FIELDS
            },
            "metrics": {
                k: getattr(s, k) for k, _, _, _, _ in STORE_METRICS
            },
            "data_status": store_data_status(s),
            "data_source": s.data_source,
            "data_updated_at": s.data_updated_at.isoformat() if s.data_updated_at else None,
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in rows
    ]


def create_store(db: Session, user: str, payload: Dict) -> Store:
    """新增门店。code 自动生成。"""
    n = db.query(Store).count() + 1
    s = Store(
        code=payload.get("code") or f"ST-{n:03d}",
        name=payload["name"],
        city=payload.get("city"),
        district=payload.get("district"),
        business_district=payload.get("business_district"),
        store_type=payload.get("store_type"),
        area_sqm=payload.get("area_sqm"),
        is_default=False,
        is_demo=payload.get("is_demo", True),
        created_by=user,
        data_source=payload.get("data_source") or "人工录入",
        data_updated_at=datetime.utcnow() if payload.get("sales_amount") is not None else None,
    )
    for key, _, _, _, _ in STORE_METRICS:
        if payload.get(key) is not None:
            setattr(s, key, payload[key])
    for key, _, _ in PROFILE_FIELDS:
        if payload.get(key) is not None:
            setattr(s, key, payload[key])
    for key in ("consumption_power", "main_competitors", "delivery_capability"):
        if payload.get(key) is not None:
            setattr(s, key, payload[key])
    db.add(s)
    db.flush()
    db.add(AuditLog(user=user, action="create_store", target=s.name,
                    detail=f"新增门店 {s.code}", ip="127.0.0.1"))
    db.commit()
    return s


def update_store_metrics(db: Session, user: str, store_id: int, payload: Dict) -> Store:
    s = db.query(Store).filter(Store.id == store_id).first()
    if not s:
        raise ValueError("门店不存在")
    changed = []
    for key, _, _, _, _ in STORE_METRICS:
        if key in payload:
            old = getattr(s, key, None)
            new = payload[key]
            if old != new:
                changed.append(f"{key}: {old} → {new}")
            setattr(s, key, new)
    for key, _, _ in PROFILE_FIELDS:
        if key in payload:
            setattr(s, key, payload[key])
    for key in ("consumption_power", "main_competitors", "delivery_capability", "data_source", "store_type", "area_sqm"):
        if key in payload and payload[key] is not None:
            setattr(s, key, payload[key])
    s.data_updated_at = datetime.utcnow()
    db.add(AuditLog(user=user, action="update_store_metrics", target=s.name,
                    detail="; ".join(changed) or "无变化", ip="127.0.0.1"))
    db.commit()
    return s


def compare_stores(db: Session, store_ids: List[int]) -> Dict:
    """多门店对比。只对有数据的维度做排名，缺失维度标记「待接入」。"""
    if len(store_ids) < 2:
        return {"success": False, "message": "至少选择 2 家门店才能对比"}

    stores = db.query(Store).filter(Store.id.in_(store_ids)).all()
    if len(stores) != len(set(store_ids)):
        found = {s.id for s in stores}
        return {"success": False, "message": f"门店不存在：{[i for i in store_ids if i not in found]}"}

    # 逐维度计算
    dims = []
    for key, label, unit, higher_better, desc in STORE_METRICS:
        vals = [getattr(s, key, None) for s in stores]
        have = [v for v in vals if v is not None]
        dim = {
            "key": key, "label": label, "unit": unit,
            "higher_is_better": higher_better,
            "description": desc,
            "available_count": len(have),
            "total_count": len(stores),
            "complete": len(have) == len(stores),
            "values": [
                {"store_id": s.id, "store": s.name, "value": getattr(s, key, None)}
                for s in stores
            ],
        }
        if len(have) >= 2 and higher_better is not None:
            scores = minmax_normalize([float(getattr(s, key) or 0) for s in stores], higher_better)
            for i, s in enumerate(stores):
                if getattr(s, key, None) is not None:
                    dim["values"][i]["score"] = scores[i]
            # 所有维度的 score 都是「越高越好」的单向得分，直接按 score 降序即最优
            ranked = sorted(
                [v for v in dim["values"] if "score" in v],
                key=lambda v: -v["score"],
            )
            if ranked:
                dim["best"] = ranked[0]["store"]
                dim["worst"] = ranked[-1]["store"]
        dims.append(dim)

    # 画像对比
    profiles = []
    for key, label, unit in PROFILE_FIELDS:
        profiles.append({
            "key": key, "label": label, "unit": unit,
            "values": [{"store_id": s.id, "store": s.name, "value": getattr(s, key, None)} for s in stores],
            "complete": all(getattr(s, key, None) not in (None, "") for s in stores),
        })

    # 综合得分：只对有数据的维度做归一化加权
    scored_stores = []
    for i, s in enumerate(stores):
        total_w, acc = 0.0, 0.0
        for d in dims:
            v = d["values"][i].get("value")
            if v is None or d["higher_is_better"] is None or "score" not in d["values"][i]:
                continue
            w = 1.0
            acc += d["values"][i]["score"] * w
            total_w += w
        scored_stores.append({
            "store_id": s.id, "store": s.name,
            "code": s.code, "city": s.city, "district": s.district,
            "business_district": s.business_district,
            "store_type": s.store_type, "area_sqm": s.area_sqm,
            "consumption_power": s.consumption_power,
            "overall_score": round(acc / total_w, 2) if total_w > 0 else None,
            "scored_dimensions": int(total_w),
            "data_status": store_data_status(s),
        })

    ranked = sorted(
        [x for x in scored_stores if x["overall_score"] is not None],
        key=lambda x: -x["overall_score"],
    )
    for i, x in enumerate(ranked, 1):
        x["rank"] = i

    ready = [x for x in scored_stores if x["overall_score"] is not None]
    not_ready = [x for x in scored_stores if x["overall_score"] is None]

    # 差异分析：找出各店最强/最弱维度
    insights = []
    if len(ready) >= 2:
        for d in dims:
            if d.get("best") and d["available_count"] >= 2:
                vals = [v for v in d["values"] if v["value"] is not None]
                if len(vals) >= 2:
                    nums = [v["value"] for v in vals]
                    rng = max(nums) - min(nums)
                    if rng > 0:
                        ratio = max(nums) / min(nums) if min(nums) > 0 else 0
                        insights.append({
                            "dimension": d["label"],
                            "best_store": d["best"],
                            "range": round(rng, 2),
                            "ratio": round(ratio, 2),
                            "values": {v["store"]: v["value"] for v in vals},
                            "significant": ratio >= 1.5,
                        })
        insights.sort(key=lambda x: -(x["ratio"] if x["ratio"] > 0 else 0))

    return {
        "success": True,
        "count": len(stores),
        "dimensions": dims,
        "profiles": profiles,
        "stores": scored_stores,
        "ranking": ranked,
        "not_ranked": not_ready,
        "insights": insights,
        "significant_count": sum(1 for i in insights if i["significant"]),
        "summary": (
            f"已对比 {len(ready)} 家门店的经营数据"
            + (f"，{len(not_ready)} 家因缺少数据未参与排名" if not_ready else "")
            + f"。共分析 {len(dims)} 个维度，其中 {sum(1 for d in dims if d['complete'])} 个维度数据完整。"
        ),
        "method_note": (
            "综合得分 = 各维度标准化得分的算术平均。周转天数与缺货次数为逆向指标"
            "（数值越低越好），采用逆向标准化；SKU 数为中性指标，不参与排名。"
            "缺失数据的维度不参与该店得分计算，也不做推算填充。"
        ),
        "data_caveat": (
            "附件仅提供黄金海岸广场店一家门店的经营数据。其余门店的指标为人工录入，"
            "录入前请确认数据来源与授权。平台不会为门店生成或推算任何经营数据。"
        ),
    }
