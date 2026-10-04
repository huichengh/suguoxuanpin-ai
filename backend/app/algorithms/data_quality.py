"""数据质量检查

六个维度：完整性 / 一致性 / 有效性 / 唯一性 / 时效性 / 数值范围。
发现问题不静默修复，只输出问题清单 + 处理建议。
"""
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

DATASET_SCHEMAS = {
    "category_sales": {
        "label": "品类销售数据",
        "required": ["品类ID", "品类名称", "月份", "销量(件)", "销售额(元)", "毛利额(元)",
                     "库存周转天数", "坪效(元/㎡/月)", "缺货次数", "SKU数量"],
        "numeric": ["销量(件)", "销售额(元)", "毛利额(元)", "库存周转天数", "坪效(元/㎡/月)",
                    "缺货次数", "SKU数量"],
        "key": ["品类ID", "月份"],
        "non_negative": ["销量(件)", "销售额(元)", "毛利额(元)", "缺货次数", "SKU数量"],
        "date_field": "月份",
    },
    "transactions": {
        "label": "交易明细数据",
        "required": ["交易号", "商品编码", "商品名称", "品类", "数量", "交易日期", "单价(元)"],
        "numeric": ["数量", "单价(元)"],
        "key": ["交易号", "商品编码"],
        "non_negative": ["数量", "单价(元)"],
        "date_field": "交易日期",
    },
    "demand_forecast": {
        "label": "需求历史数据",
        "required": ["品类", "周次", "日期", "数据类型"],
        "numeric": ["周次", "历史销量(件)", "预测销量(件)", "预测下界(件)", "预测上界(件)"],
        "key": ["品类", "周次"],
        "non_negative": ["历史销量(件)", "预测销量(件)"],
        "date_field": "周次",
    },
    "association_rules": {
        "label": "关联规则结果",
        "required": ["前项商品(A)", "后项商品(B)", "支持度", "置信度", "提升度"],
        "numeric": ["支持度", "置信度", "提升度"],
        "key": ["前项商品(A)", "后项商品(B)"],
        "range": {"支持度": (0, 1), "置信度": (0, 1), "提升度": (0, 100)},
        "date_field": None,
    },
    "category_health": {
        "label": "品类健康度结果",
        "required": ["品类ID", "品类名称", "综合评分", "健康度等级"],
        "numeric": ["综合评分", "销量贡献(%)", "毛利贡献(%)", "周转天数", "坪效得分"],
        "key": ["品类ID"],
        "range": {"综合评分": (0, 100)},
        "date_field": None,
    },
    "sku_products": {
        "label": "SKU 候选商品数据",
        "required": ["商品名称", "品类"],
        "numeric": ["采购价", "零售价", "销量", "销售额", "毛利率"],
        "key": ["商品名称"],
        "non_negative": ["采购价", "零售价", "销量", "销售额"],
        "date_field": None,
    },
    "store_profile": {
        "label": "门店画像数据",
        "required": ["门店名称", "商圈"],
        "numeric": ["3公里人口", "居民占比", "办公人群占比", "学生占比", "中老年占比"],
        "key": ["门店名称"],
        "range": {"居民占比": (0, 100), "办公人群占比": (0, 100), "学生占比": (0, 100), "中老年占比": (0, 100)},
        "date_field": None,
    },
}


def check_quality(df: pd.DataFrame, dataset_type: str) -> Dict:
    schema = DATASET_SCHEMAS.get(dataset_type)
    if not schema:
        raise ValueError(f"未知数据集类型：{dataset_type}")

    total_rows = int(len(df))
    issues: List[Dict] = []

    # 1. 字段完整性
    missing_cols = [c for c in schema["required"] if c not in df.columns]
    extra_cols = [c for c in df.columns if c not in schema["required"]]

    completeness = 100.0
    if missing_cols:
        completeness = 100 * (1 - len(missing_cols) / len(schema["required"]))
        issues.append({
            "field": ", ".join(missing_cols),
            "issue_type": "字段缺失",
            "count": len(missing_cols),
            "severity": "高",
            "suggestion": f"上传数据需包含字段：{', '.join(missing_cols)}。可下载对应模板补齐。",
        })
    else:
        null_counts = {c: int(df[c].isna().sum()) for c in schema["required"] if df[c].isna().any()}
        if null_counts:
            total_null = sum(null_counts.values())
            expected = total_rows * len(schema["required"]) or 1
            completeness = max(0.0, 100 * (1 - total_null / expected))
            for c, n in null_counts.items():
                issues.append({
                    "field": c, "issue_type": "空值", "count": n,
                    "severity": "中" if n / total_rows < 0.1 else "高",
                    "suggestion": f"字段「{c}」有 {n} 行为空，建议人工确认是缺失还是应填 0，平台不会自动填充。",
                })

    # 2. 唯一性（主键重复）
    key = schema.get("key", [])
    dup_count = 0
    if key and all(c in df.columns for c in key):
        dup = df.duplicated(subset=key, keep=False)
        dup_count = int(dup.sum())
        if dup_count:
            issues.append({
                "field": " + ".join(key), "issue_type": "主键重复", "count": dup_count,
                "severity": "高",
                "suggestion": f"主键（{' + '.join(key)}）存在 {dup_count} 行重复，请确认是否重复上传或数据源异常。",
            })
    uniqueness = max(0.0, 100 * (1 - dup_count / total_rows)) if total_rows else 100.0

    # 3. 有效性（数值型与非负约束）
    validity = 100.0
    numeric = [c for c in schema.get("numeric", []) if c in df.columns]
    for c in numeric:
        coerced = pd.to_numeric(df[c], errors="coerce")
        bad = int((coerced.isna() & df[c].notna()).sum())
        if bad:
            validity -= bad / total_rows * 100
            issues.append({
                "field": c, "issue_type": "类型异常", "count": bad, "severity": "中",
                "suggestion": f"字段「{c}」有 {bad} 行无法解析为数值，请检查是否混入文本或千分位符号。",
            })
        if c in schema.get("non_negative", []):
            neg = int((coerced < 0).sum())
            if neg:
                validity -= neg / total_rows * 100
                issues.append({
                    "field": c, "issue_type": "数值范围异常", "count": neg, "severity": "中",
                    "suggestion": f"字段「{c}」存在 {neg} 个负值，销售/数量类指标通常不应为负。",
                })

    for c, (lo, hi) in (schema.get("range") or {}).items():
        if c in df.columns:
            coerced = pd.to_numeric(df[c], errors="coerce")
            out = int(((coerced < lo) | (coerced > hi)).sum())
            if out:
                validity -= out / total_rows * 100
                issues.append({
                    "field": c, "issue_type": "数值范围异常", "count": out, "severity": "中",
                    "suggestion": f"字段「{c}」有 {out} 行超出合理区间 [{lo}, {hi}]。",
                })

    validity = max(0.0, min(100.0, validity))

    # 4. 一致性（毛利额不超过销售额等逻辑校验）
    consistency = 100.0
    if "销售额(元)" in df.columns and "毛利额(元)" in df.columns:
        amt = pd.to_numeric(df["销售额(元)"], errors="coerce")
        gp = pd.to_numeric(df["毛利额(元)"], errors="coerce")
        bad = int((gp > amt).sum())
        if bad:
            consistency -= bad / total_rows * 100
            issues.append({
                "field": "毛利额(元)", "issue_type": "逻辑不一致", "count": bad, "severity": "高",
                "suggestion": f"有 {bad} 行毛利额大于销售额，请核对数据口径。",
            })
    if "预测下界(件)" in df.columns and "预测上界(件)" in df.columns:
        lo = pd.to_numeric(df["预测下界(件)"], errors="coerce")
        hi = pd.to_numeric(df["预测上界(件)"], errors="coerce")
        bad = int((lo > hi).sum())
        if bad:
            consistency -= bad / total_rows * 100
            issues.append({
                "field": "预测区间", "issue_type": "逻辑不一致", "count": bad, "severity": "中",
                "suggestion": f"有 {bad} 行预测下界大于上界，置信区间方向异常。",
            })
    consistency = max(0.0, min(100.0, consistency))

    # 5. 时效性
    timeliness = 100.0
    date_field = schema.get("date_field")
    date_note = "该数据集无时间字段，时效性不适用。"
    if date_field and date_field in df.columns:
        parsed = pd.to_datetime(df[date_field], errors="coerce", format="mixed")
        if parsed.notna().any():
            latest = parsed.max()
            months = (datetime.now() - latest).days / 30.4
            timeliness = max(0.0, 100 - months * 4)
            date_note = f"数据最新月份为 {latest.strftime('%Y-%m')}，距今约 {months:.0f} 个月。"
            if months > 6:
                issues.append({
                    "field": date_field, "issue_type": "时效性", "count": 1, "severity": "低",
                    "suggestion": f"数据最新为 {latest.strftime('%Y-%m')}，距今较久，趋势判断需谨慎。",
                })
        else:
            timeliness = 60.0
            date_note = f"字段「{date_field}」无法解析为日期。"
            issues.append({
                "field": date_field, "issue_type": "日期解析失败", "count": int(parsed.isna().sum()),
                "severity": "中", "suggestion": f"「{date_field}」格式不统一，建议统一为 YYYY-MM 或 YYYY-MM-DD。",
            })
    timeliness = round(max(0.0, min(100.0, timeliness)), 2)

    if extra_cols:
        issues.append({
            "field": ", ".join(extra_cols), "issue_type": "多余字段", "count": len(extra_cols),
            "severity": "低", "suggestion": "以下字段不在标准模板中，导入时会被忽略：保留原始文件即可。",
        })

    completeness = round(completeness, 2)
    overall = round(
        completeness * 0.25 + consistency * 0.20 + validity * 0.25
        + uniqueness * 0.15 + timeliness * 0.15, 2
    )

    return {
        "dataset_type": dataset_type,
        "dataset_label": schema["label"],
        "total_rows": total_rows,
        "total_columns": int(len(df.columns)),
        "completeness": completeness,
        "consistency": round(consistency, 2),
        "validity": validity,
        "uniqueness": round(uniqueness, 2),
        "timeliness": timeliness,
        "overall_score": overall,
        "grade": quality_grade(overall),
        "issues": issues,
        "issue_count": len(issues),
        "date_note": date_note,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def quality_grade(score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "一般"
    return "待改善"


def template_csv(dataset_type: str) -> str:
    """生成上传模板（表头 + 一行示例）。"""
    schema = DATASET_SCHEMAS[dataset_type]
    header = ",".join(schema["required"])
    sample = {
        "category_sales": "C001,生鲜蔬果,2026-09,10000,140000,25000,11,1300,1,450",
        "transactions": "100001,SKU00001,大米,粮油调味,2,2026-07-11,30.32",
        "demand_forecast": "生鲜蔬果,1,2026-W01,7493,,,,历史数据",
        "association_rules": "1,牛奶,面包,0.085,0.623,2.84,早餐组合，建议相邻陈列",
        "category_health": "C001,生鲜蔬果,92,优秀,★★★★★,28,18,12,85,保持优势,绿灯",
        "sku_products": "示例商品,粮油调味,某品牌,28.5,39.9,15,某供应商,社区家庭,5kg,袋装,全年,高性价比",
        "store_profile": "示例门店,江宁 Golden Coast,120000,70,15,5,20,中等,30,10,3,某连锁超市,支持",
    }
    return f"{header}\n{sample.get(dataset_type, '')}\n"