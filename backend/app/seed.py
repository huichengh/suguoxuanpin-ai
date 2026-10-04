"""演示数据初始化

严格按附件原始内容导入，不修改任何数值。
附件参考结果（association_rules / category_health）与系统重算结果分开存储，
通过 source 字段区分，UI 显示来源与是否通过当前阈值。
"""
import hashlib
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from .config import DATA_DIR, DEFAULT_STORE, DEMO_DISCLAIMER, DEMO_SOURCE
from .database import Base, engine, SessionLocal
from .models import (
    AssociationRule, AuditLog, Category, CategoryHealthResult, CategorySales,
    DataQualityReport, DataUpload, DemandRecord, KnowledgeDoc, ModelSetting,
    Role, Store, Transaction, TransactionItem, User,
)
from .algorithms import association as assoc_algo
from .algorithms import data_quality as dq
from .algorithms import health as health_algo
from .utils.security import hash_password

CATEGORY_META = {
    "生鲜蔬果": ("引流品类", "社区家庭日常餐桌", "高频民生刚需，引流与流量入口", 1),
    "肉禽蛋品": ("主力品类", "社区家庭正餐需求", "品质与新鲜度取胜的中高毛利主力", 2),
    "粮油调味": ("利润品类", "家庭厨房基础调味", "自有品牌渗透率最高的利润品类", 3),
    "食品饮料": ("主力品类", "上班族与学生客群", "品牌集中、SKU 精简空间大", 4),
    "日化清洁": ("后场品类", "家庭日用刚需", "低频但稳定，聚焦高频刚需单品", 5),
    "家居用品": ("后场品类", "家庭清洁与收纳", "周转慢、坪效低，需严格控制面积", 6),
    "纺织服装": ("后场品类", "季节性家庭服饰", "非核心品类，评估退出", 7),
    # 交易明细（dataset_transactions_sample.csv）中的两个品类，
    # 在 category_sales 中没有对应数据，因此在「品类健康诊断」中无评分，
    # 但在小类分析与关联陈列中正常参与统计。平台如实保留两套口径，不做合并。
    "火锅食材": ("引流品类", "家庭聚餐场景", "关联陈列潜力强，适合火锅专区", 8),
    "烘焙用品": ("后场品类", "家庭烘焙场景", "DIY 烘焙长尾品类，客群窄但连带率高", 9),
}

# 两个数据集的品类口径差异说明（用于前端如实展示）
CATEGORY_COVERAGE_NOTE = {
    "sales_only": ["家居用品", "纺织服装"],
    "transaction_only": ["火锅食材", "烘焙用品"],
    "common": ["生鲜蔬果", "肉禽蛋品", "粮油调味", "食品饮料", "日化清洁"],
    "note": (
        "附件的两份数据存在品类口径差异：品类销售数据含「家居用品、纺织服装」"
        "但交易明细中没有；交易明细含「火锅食材、烘焙用品」但品类销售数据中没有。"
        "平台如实保留两套口径，不做人工合并——"
        "「家居用品、纺织服装」因缺少销售数据无法参与健康度评分；"
        "「火锅食材、烘焙用品」有小类与关联规则数据，但无健康度评分。"
    ),
}

DEFAULT_WEIGHTS = {"sales": 0.30, "margin": 0.30, "turnover": 0.20, "space": 0.20}


def _dataset_file(name: str) -> Optional[Path]:
    p = DATA_DIR / name
    return p if p.exists() else None


def _version_of(path: Path) -> str:
    h = hashlib.md5(path.read_bytes()).hexdigest()[:10]
    return f"v1-{h}"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def seed_all(reset: bool = False) -> dict:
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        result = {"steps": []}
        _seed_roles_users(db, result)
        _seed_store(db, result)
        _seed_categories(db, result)
        _seed_settings(db, result)
        _seed_knowledge(db, result)
        uploads = _seed_datasets(db, result)
        _recalc_health(db, uploads, result)
        _recalc_association(db, uploads, result)
        _build_subcategories(db, result)
        _fill_default_store_metrics(db, result)
        db.commit()
        result["success"] = True
        return result
    except Exception as e:  # noqa
        db.rollback()
        result = {"success": False, "error": str(e)}
        raise
    finally:
        db.close()


# ---------------- 基础主数据 ----------------

def _seed_roles_users(db: Session, result: dict):
    if db.query(Role).count() > 0:
        result["steps"].append("角色与用户已存在，跳过")
        return

    roles = [
        Role(code="admin", name="管理员", description="系统全部权限",
             permissions=["*"]),
        Role(code="buyer", name="采购经理", description="商品比较、选品建议、新品、审批申请",
             permissions=["compare", "recommendation", "new_product", "approval_submit", "data_read"]),
        Role(code="category_mgr", name="品类经理", description="品类诊断、关联规则、需求预测、品类优化",
             permissions=["category_health", "association", "forecast", "compare", "data_read"]),
        Role(code="store_mgr", name="门店店长", description="查看本门店分析、查看建议、提交反馈",
             permissions=["dashboard", "read_analysis", "feedback", "approval_submit", "data_read"]),
        Role(code="viewer", name="普通查看人员", description="只读",
             permissions=["dashboard", "data_read"]),
    ]
    db.add_all(roles)
    db.flush()

    users = [
        User(username="admin", full_name="系统管理员", password_hash=hash_password("admin123"),
             role_id=roles[0].id, is_active=True),
        User(username="buyer", full_name="采购经理", password_hash=hash_password("buyer123"),
             role_id=roles[1].id, is_active=True),
        User(username="category", full_name="品类经理", password_hash=hash_password("category123"),
             role_id=roles[2].id, is_active=True),
        User(username="store", full_name="门店店长", password_hash=hash_password("store123"),
             role_id=roles[3].id, is_active=True),
        User(username="viewer", full_name="普通查看", password_hash=hash_password("viewer123"),
             role_id=roles[4].id, is_active=True),
    ]
    db.add_all(users)
    result["steps"].append(f"创建 {len(roles)} 个角色、{len(users)} 个用户")


def _seed_store(db: Session, result: dict):
    if db.query(Store).count() > 0:
        result["steps"].append("门店已存在，跳过")
        return
    s = Store(
        code="NJ-JN-001", name=DEFAULT_STORE, city="南京", district="江宁区",
        business_district="黄金海岸广场商圈", store_type="社区购物中心店",
        area_sqm=3200, is_default=True, is_demo=True,
        # 门店画像字段留空：当前附件无 POI / 人口数据，不得编造
        pop_3km=None, consumption_power="待接入",
        main_competitors="待接入", delivery_capability="待接入",
    )
    db.add(s)
    db.flush()
    for u in db.query(User).all():
        if u.username == "store":
            u.store_id = s.id
    result["steps"].append(f"创建门店：{s.name}")


def _seed_categories(db: Session, result: dict):
    if db.query(Category).count() > 0:
        result["steps"].append("品类已存在，跳过")
        return
    cats = []
    for name, (role, target, pos, order) in CATEGORY_META.items():
        cats.append(Category(
            code=f"C{order:03d}", name=name, category_role=role,
            stp_target=target, positioning=pos, sort_order=order, is_demo=True,
        ))
    db.add_all(cats)
    db.flush()
    result["steps"].append(f"创建 {len(cats)} 个品类")


def _seed_settings(db: Session, result: dict):
    if db.query(ModelSetting).count() > 0:
        result["steps"].append("算法参数已存在，跳过")
        return
    settings = [
        ModelSetting(key="category_health_weights", category="algorithm",
                     value=DEFAULT_WEIGHTS, description="品类健康度评分权重（销量/毛利/周转/坪效）"),
        ModelSetting(key="compare_weights", category="algorithm",
                     value=DEFAULT_WEIGHTS, description="选品比较模型权重（销量/毛利/周转/坪效）"),
        ModelSetting(key="apriori_min_support", category="algorithm", value=0.02,
                     description="Apriori 最小支持度"),
        ModelSetting(key="apriori_min_confidence", category="algorithm", value=0.50,
                     description="Apriori 最小置信度"),
        ModelSetting(key="apriori_min_lift", category="algorithm", value=1.50,
                     description="Apriori 最小提升度"),
        ModelSetting(key="apriori_top_n", category="algorithm", value=20,
                     description="关联规则显示数量 TopN"),
        ModelSetting(key="apriori_group_by", category="algorithm", value="product_name",
                     description="购物篮聚合字段：product_name（演示默认）/ sku_code（真实数据）"),
        ModelSetting(key="forecast_horizon", category="algorithm", value=4,
                     description="需求预测期数"),
        ModelSetting(key="risk_turnover_threshold", category="algorithm", value=45.0,
                     description="库存周转天数风险阈值"),
        ModelSetting(key="risk_space_threshold", category="algorithm", value=600.0,
                     description="坪效风险阈值（元/㎡/月）"),
        ModelSetting(key="risk_stockout_threshold", category="algorithm", value=8,
                     description="缺货次数风险阈值"),
        ModelSetting(key="risk_score_threshold", category="algorithm", value=55.0,
                     description="健康度低于三星的分数线"),
    ]
    db.add_all(settings)
    result["steps"].append(f"创建 {len(settings)} 项算法参数")


def _seed_knowledge(db: Session, result: dict):
    if db.query(KnowledgeDoc).count() > 0:
        return
    docs = [
        KnowledgeDoc(title="品类健康度评分模型", category="算法模型",
                     content="综合得分 = 销量贡献×0.30 + 毛利贡献×0.30 + 库存周转×0.20 + 坪效×0.20。"
                             "各指标标准化到 0-100。库存周转天数越低越好，采用逆向标准化。"
                             "85分以上为优秀，70-84良好，55-69一般，40-54较差，40以下差。低于55分标记需重点优化。",
                     tags="健康度,评分模型,权重"),
        KnowledgeDoc(title="ECR 品类管理流程", category="品类管理",
                     content="品类定义 → 品类角色 → 品类评估 → 目标 → 策略 → 战术 → 执行 → 回顾。"
                             "本平台的品类健康诊断对应「评估」环节，风险预警对应「回顾」环节。",
                     tags="ECR,品类管理"),
        KnowledgeDoc(title="STP 战略定位", category="战略框架",
                     content="目标客群为社区家庭与民生刚需消费者；核心定位为「家门口的社区厨房 + 高性价比民生超市」。"
                             "品类角色划分为引流品类、主力品类、利润品类、后场品类。",
                     tags="STP,定位"),
        KnowledgeDoc(title="人货场分析框架", category="战略框架",
                     content="人：社区家庭、上班族、中老年居民、学生。货：生鲜、肉禽蛋、粮油调味、食品饮料、日化、家居。"
                             "场：社区门店 + 线上渠道 + 场景化陈列。本平台关联陈列模块对应「场」的优化。",
                     tags="人货场"),
        KnowledgeDoc(title="Apriori 关联规则参数", category="算法模型",
                     content="默认 min_support=0.02、min_confidence=0.50、min_lift=1.50、TopN=20。"
                             "演示数据商品编码高度离散，默认按「交易号+商品名称」构建购物篮；"
                             "真实企业数据 SKU 编码稳定后可切换为商品编码。",
                     tags="Apriori,关联规则,陈列"),
        KnowledgeDoc(title="数据真实性与免责声明", category="数据治理",
                     content="本平台当前使用的数据均为基于公开行业数据构造的模拟演示数据，不代表华润苏果真实经营数据。"
                             "附件参考结果与系统实时重算结果严格区分并标注来源。平台不会为缺失的数据生成任何虚构结果。",
                     tags="数据治理,免责声明"),
        KnowledgeDoc(title="自有品牌品类级判断逻辑", category="品类管理",
                     content="当前仅支持品类级判断：毛利贡献高、健康度中上的品类适合引入自有品牌。"
                             "SKU 级替代模型需要品牌标识、SKU 毛利率、竞品价格带等数据，平台不做无数据支撑的预测。",
                     tags="自有品牌"),
    ]
    db.add_all(docs)
    result["steps"].append(f"创建 {len(docs)} 条 AI 知识库文档")


# ---------------- 数据集导入 ----------------

def _register_upload(db: Session, dataset_type: str, path: Path, rows: int,
                     quality: Optional[dict], note: str) -> DataUpload:
    up = DataUpload(
        dataset_type=dataset_type,
        original_filename=path.name,
        stored_path=f"data/{path.name}",
        version=_version_of(path),
        row_count=rows,
        uploaded_by="system",
        uploaded_at=datetime.utcnow(),
        is_demo=True,
        source_note=note,
        status="loaded",
    )
    db.add(up)
    db.flush()
    if quality:
        rep = DataQualityReport(
            dataset_type=dataset_type, dataset_version=up.version,
            total_rows=quality["total_rows"],
            completeness=quality["completeness"], consistency=quality["consistency"],
            validity=quality["validity"], uniqueness=quality["uniqueness"],
            timeliness=quality["timeliness"], overall_score=quality["overall_score"],
            issues=quality["issues"], uploaded_by="system",
        )
        db.add(rep)
        db.flush()
        up.quality_report_id = rep.id
    return up


def _seed_datasets(db: Session, result: dict) -> dict:
    uploads = {}
    note = f"{DEMO_SOURCE}（{DEMO_DISCLAIMER}）"

    # 1. 品类销售
    p = _dataset_file("dataset_category_sales.csv")
    if p:
        df = _read_csv(p)
        q = dq.check_quality(df, "category_sales")
        up = _register_upload(db, "category_sales", p, len(df), q, note)
        cat_map = {c.name: c.id for c in db.query(Category).all()}
        for _, row in df.iterrows():
            cid = cat_map.get(row["品类名称"])
            if not cid:
                continue
            db.add(CategorySales(
                category_id=cid, month=str(row["月份"]),
                sales_qty=float(row["销量(件)"]), sales_amount=float(row["销售额(元)"]),
                gross_profit=float(row["毛利额(元)"]), turnover_days=float(row["库存周转天数"]),
                sales_per_sqm=float(row["坪效(元/㎡/月)"]), stockout_count=int(row["缺货次数"]),
                sku_count=int(row["SKU数量"]), source_dataset_id=up.id,
            ))
        db.flush()
        uploads["category_sales"] = up.id
        result["steps"].append(f"导入品类销售 {len(df)} 行（质量分 {q['overall_score']}）")

    # 2. 交易明细
    p = _dataset_file("dataset_transactions_sample.csv")
    if p:
        df = _read_csv(p)
        q = dq.check_quality(df, "transactions")
        up = _register_upload(db, "transactions", p, len(df), q, note)
        tx_cache: dict = {}
        for _, row in df.iterrows():
            tx_no = str(row["交易号"])
            tx = tx_cache.get(tx_no)
            if tx is None:
                tx = Transaction(transaction_no=tx_no, trans_date=_parse_date(row["交易日期"]),
                                 source_dataset_id=up.id)
                db.add(tx)
                db.flush()
                tx_cache[tx_no] = tx
            db.add(TransactionItem(
                transaction_id=tx.id, sku_code=str(row["商品编码"]),
                product_name=str(row["商品名称"]).strip(), category_name=str(row["品类"]),
                quantity=float(row["数量"]), unit_price=float(row["单价(元)"]),
                amount=round(float(row["数量"]) * float(row["单价(元)"]), 2),
                source_dataset_id=up.id,
            ))
        db.flush()
        uploads["transactions"] = up.id
        result["steps"].append(
            f"导入交易明细 {len(df)} 行 / {len(tx_cache)} 笔交易（质量分 {q['overall_score']}）"
        )

    # 3. 需求预测
    p = _dataset_file("dataset_demand_forecast.csv")
    if p:
        df = _read_csv(p)
        q = dq.check_quality(df, "demand_forecast")
        up = _register_upload(db, "demand_forecast", p, len(df), q, note)
        cat_map = {c.name: c.id for c in db.query(Category).all()}
        for _, row in df.iterrows():
            cid = cat_map.get(str(row["品类"]))
            if not cid:
                continue
            def _f(k):
                v = row.get(k)
                return None if pd.isna(v) else float(v)
            db.add(DemandRecord(
                category_id=cid, week_no=int(row["周次"]), period_label=str(row["日期"]),
                actual_qty=_f("历史销量(件)"), forecast_qty=_f("预测销量(件)"),
                lower_bound=_f("预测下界(件)"), upper_bound=_f("预测上界(件)"),
                data_type="history" if str(row["数据类型"]) == "历史数据" else "forecast",
                is_simulated=True, source_dataset_id=up.id,
                algorithm="附件模拟预测结果",
                parameters={"source": "attachment_simulated"},
            ))
        db.flush()
        uploads["demand_forecast"] = up.id
        result["steps"].append(f"导入需求预测 {len(df)} 行（质量分 {q['overall_score']}）")

    # 4. 关联规则（附件参考结果，原样保留）
    p = _dataset_file("dataset_association_rules.csv")
    if p:
        df = _read_csv(p)
        q = dq.check_quality(df, "association_rules")
        up = _register_upload(db, "association_rules", p, len(df), q, note)
        params = {"min_support": 0.02, "min_confidence": 0.50, "min_lift": 1.50}
        for _, row in df.iterrows():
            conf = float(row["置信度"])
            lift = float(row["提升度"])
            passes = conf >= params["min_confidence"] and lift >= params["min_lift"]
            db.add(AssociationRule(
                antecedent=str(row["前项商品(A)"]), consequent=str(row["后项商品(B)"]),
                support=float(row["支持度"]), confidence=conf, lift=lift,
                display_rule=f"{row['前项商品(A)']} → {row['后项商品(B)']}",
                display_suggestion=str(row.get("陈列建议") or ""),
                source="attachment", passes_threshold=passes, item_count=2,
                source_dataset_id=up.id,
                algorithm="附件预置参考结果",
                parameters={**params, "note": "附件原始结果，未按当前阈值过滤或修改"},
            ))
        db.flush()
        uploads["association_rules"] = up.id
        npass = int(df.apply(lambda r: float(r["置信度"]) >= 0.5 and float(r["提升度"]) >= 1.5, axis=1).sum())
        result["steps"].append(
            f"导入附件关联规则 {len(df)} 条（原样保留，其中 {npass} 条通过当前默认阈值）"
        )

    # 5. 品类健康度（附件参考结果）
    p = _dataset_file("dataset_category_health.csv")
    if p:
        df = _read_csv(p)
        q = dq.check_quality(df, "category_health")
        up = _register_upload(db, "category_health", p, len(df), q, note)
        cat_map = {c.name: c.id for c in db.query(Category).all()}
        for _, row in df.iterrows():
            cid = cat_map.get(str(row["品类名称"]))
            if not cid:
                continue
            db.add(CategoryHealthResult(
                category_id=cid, source="attachment",
                overall_score=float(row["综合评分"]),
                grade=str(row["健康度等级"]), stars=str(row["评级"]),
                sales_contribution=float(row.get("销量贡献(%)") or 0),
                margin_contribution=float(row.get("毛利贡献(%)") or 0),
                avg_turnover_days=float(row.get("周转天数") or 0),
                suggestion=str(row.get("优化建议") or ""),
                alert_light=str(row.get("预警灯") or ""),
                source_dataset_id=up.id,
                algorithm="附件预置参考结果",
                parameters={"note": "附件原始结果，未修改"},
            ))
        db.flush()
        uploads["category_health"] = up.id
        result["steps"].append(f"导入附件品类健康度 {len(df)} 条（原样保留）")

    return uploads


def _parse_date(v) -> Optional[date]:
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


# ---------------- 算法重算 ----------------

def _recalc_health(db: Session, uploads: dict, result: dict):
    ds_id = uploads.get("category_sales")
    if not ds_id:
        return
    p = _dataset_file("dataset_category_sales.csv")
    df = _read_csv(p)
    rows = health_algo.score_categories(df, DEFAULT_WEIGHTS, months_window=12)
    cat_map = {c.name: c for c in db.query(Category).all()}

    db.query(CategoryHealthResult).filter(
        CategoryHealthResult.source == "system"
    ).delete(synchronize_session=False)

    params = {**DEFAULT_WEIGHTS, "months_window": 12, "normalization": "minmax",
              "turnover_direction": "reverse(越低越好)"}
    for r in rows:
        c = cat_map.get(r["category"])
        if not c:
            continue
        db.add(CategoryHealthResult(
            category_id=c.id, source="system",
            overall_score=r["overall_score"], grade=r["grade"], stars=r["stars"],
            sales_score=r["sales_score"], margin_score=r["margin_score"],
            turnover_score=r["turnover_score"], space_score=r["space_score"],
            sales_contribution=r["sales_contribution"], margin_contribution=r["margin_contribution"],
            avg_turnover_days=r["avg_turnover_days"], avg_sales_per_sqm=r["avg_sales_per_sqm"],
            total_stockout=r["stockout_count"], sku_count=int(r["avg_sku_count"]),
            sales_trend=r["sales_trend"], margin_trend=r["margin_trend"],
            turnover_trend=r["turnover_trend"], space_trend=r["space_trend"],
            diagnosis=r["diagnosis"], suggestion=r["suggestion"], alert_light=r["alert_light"],
            source_dataset_id=ds_id,
            algorithm="品类健康度评分模型 v1.0", parameters=params,
        ))
    db.flush()
    result["steps"].append(f"系统重算品类健康度 {len(rows)} 个品类")


def _recalc_association(db: Session, uploads: dict, result: dict):
    ds_id = uploads.get("transactions")
    if not ds_id:
        return
    p = _dataset_file("dataset_transactions_sample.csv")
    df = _read_csv(p)
    out = assoc_algo.run_association_analysis(df, group_by="product_name")
    db.query(AssociationRule).filter(
        AssociationRule.source == "realtime"
    ).delete(synchronize_session=False)

    for r in out["rules"]:
        db.add(AssociationRule(
            antecedent=r["antecedent"], consequent=r["consequent"],
            support=r["support"], confidence=r["confidence"], lift=r["lift"],
            display_rule=r["display_rule"], display_suggestion=r["display_suggestion"],
            source="realtime", passes_threshold=True, item_count=r["item_count"],
            source_dataset_id=ds_id,
            algorithm="Apriori 实时重算",
            parameters={**out["params"], "basket_key": "交易号 + 商品名称"},
        ))
    db.flush()
    db.add(AuditLog(user="system", action="算法重算",
                    target="association_rules",
                    detail=f"Apriori 实时重算，{len(out['rules'])} 条规则通过阈值",
                    ip="127.0.0.1"))
    result["steps"].append(
        f"Apriori 实时重算：{out['basket_count']} 笔交易篮 / {out['item_count']} 个商品项 → {len(out['rules'])} 条规则"
    )


def _build_subcategories(db: Session, result: dict):
    """聚合小类指标并跑 ABC 分类。必须在交易明细与 Apriori 之后执行。"""
    from .services import subcategory as sub_svc

    res = sub_svc.rebuild_subcategories(db, "system")
    if not res.get("success"):
        result["steps"].append(f"小类聚合失败：{res.get('message')}")
        return
    abc = res.get("abc") or {}
    result["steps"].append(
        f"聚合小类 {res['count']} 个 ｜ ABC分类："
        f"A类{abc.get('classes', [{}])[0].get('count', 0)}个 / "
        f"B类{abc.get('classes', [{}, {}])[1].get('count', 0)}个 / "
        f"C类{abc.get('classes', [{}, {}, {}])[2].get('count', 0)}个"
    )


def _fill_default_store_metrics(db: Session, result: dict):
    """为默认门店填入从附件数据可真实计算的经营指标。

    只填能从 category_sales.csv 算出的字段（月销售额、月毛利额、销量、周转、坪效、缺货、SKU数）。
    毛利率、会员占比、客流、健康度等附件无数据的字段保持 NULL。
    """
    s = db.query(Store).filter_by(is_default=True).first()
    if not s:
        return

    rows = db.query(CategorySales).all()
    if not rows:
        return

    months = sorted({r.month for r in rows})
    recent = [r for r in rows if r.month in months[-1:]]   # 最近一个月
    if not recent:
        return

    sales_amount = sum(r.sales_amount or 0 for r in recent)
    gross_profit = sum(r.gross_profit or 0 for r in recent)
    s.sales_amount = round(sales_amount, 2)
    s.gross_profit = round(gross_profit, 2)
    s.gross_margin_rate = round(gross_profit / sales_amount * 100, 2) if sales_amount else None
    s.sales_qty = round(sum(r.sales_qty or 0 for r in recent), 2)
    s.turnover_days = round(sum(r.turnover_days or 0 for r in recent) / len(recent), 2)
    s.sales_per_sqm = round(sum(r.sales_per_sqm or 0 for r in recent) / len(recent), 2)
    s.sku_count = int(sum(r.sku_count or 0 for r in recent))
    s.stockout_count = int(sum(r.stockout_count or 0 for r in recent))
    s.data_source = f"附件 dataset_category_sales.csv（{recent[0].month}）"
    s.data_updated_at = datetime.utcnow()
    s.created_by = "system"

    # 综合健康度用系统重算的品类健康度均值（该字段有真实计算依据）
    from .models import CategoryHealthResult
    h = db.query(CategoryHealthResult).filter_by(source="system").all()
    if h:
        s.health_score = round(sum(x.overall_score or 0 for x in h) / len(h), 2)

    db.flush()
    result["steps"].append(
        f"默认门店经营指标（{recent[0].month}）："
        f"月销售额 {s.sales_amount:,.0f} 元、毛利额 {s.gross_profit:,.0f} 元、"
        f"毛利率 {s.gross_margin_rate}%、健康度均值 {s.health_score}"
    )


if __name__ == "__main__":
    res = seed_all(reset=True)
    print(json.dumps(res, ensure_ascii=False, indent=2))