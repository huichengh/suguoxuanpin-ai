"""数据中心接口：上传、质量检查、数据集管理"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...algorithms import data_quality as dq
from ...config import DATA_DIR, DEMO_DISCLAIMER, DEMO_SOURCE
from ...database import get_db
from ...models import (
    AuditLog, Category, CategorySales, DataQualityReport, DataUpload,
    DemandRecord, SkuProduct, Store, Transaction, TransactionItem, User,
)
from ..deps import get_current_user, require_admin

router = APIRouter(prefix="/api/data", tags=["数据中心"])

DATASET_LABELS = {k: v["label"] for k, v in dq.DATASET_SCHEMAS.items()}


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(DataUpload).order_by(DataUpload.id).all()
    reports = {r.dataset_type: r for r in db.query(DataQualityReport).all()}
    counts = {
        "category_sales": db.query(CategorySales).count(),
        "transactions": db.query(TransactionItem).count(),
        "demand_forecast": db.query(DemandRecord).count(),
        "sku_products": db.query(SkuProduct).count(),
        "store_profile": db.query(Store).count(),
    }
    return {
        "items": [
            {
                "id": u.id,
                "dataset_type": u.dataset_type,
                "label": DATASET_LABELS.get(u.dataset_type, u.dataset_type),
                "filename": u.original_filename,
                "stored_path": u.stored_path,
                "version": u.version,
                "row_count": u.row_count,
                "db_rows": counts.get(u.dataset_type),
                "uploaded_by": u.uploaded_by,
                "uploaded_at": u.uploaded_at.isoformat() if u.uploaded_at else None,
                "is_demo": u.is_demo,
                "source_note": u.source_note,
                "status": u.status,
                "quality": (
                    {
                        "overall_score": reports[u.dataset_type].overall_score,
                        "completeness": reports[u.dataset_type].completeness,
                        "consistency": reports[u.dataset_type].consistency,
                        "validity": reports[u.dataset_type].validity,
                        "uniqueness": reports[u.dataset_type].uniqueness,
                        "timeliness": reports[u.dataset_type].timeliness,
                        "issue_count": len(reports[u.dataset_type].issues or []),
                        "issues": reports[u.dataset_type].issues,
                        "checked_at": reports[u.dataset_type].checked_at.isoformat(),
                    }
                    if u.dataset_type in reports else None
                ),
            }
            for u in rows
        ],
        "supported_types": [
            {"type": k, "label": v["label"], "required_fields": v["required"]}
            for k, v in dq.DATASET_SCHEMAS.items()
        ],
        "demo_label": DEMO_DISCLAIMER,
    }


@router.get("/quality")
def data_quality(dataset_type: Optional[str] = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    q = db.query(DataQualityReport)
    if dataset_type:
        q = q.filter(DataQualityReport.dataset_type == dataset_type)
    rows = q.all()
    return {
        "items": [
            {
                "dataset_type": r.dataset_type,
                "label": DATASET_LABELS.get(r.dataset_type, r.dataset_type),
                "version": r.dataset_version,
                "total_rows": r.total_rows,
                "completeness": r.completeness, "consistency": r.consistency,
                "validity": r.validity, "uniqueness": r.uniqueness,
                "timeliness": r.timeliness,
                "overall_score": r.overall_score,
                "grade": dq.quality_grade(r.overall_score),
                "issues": r.issues or [],
                "checked_at": r.checked_at.isoformat() if r.checked_at else None,
            }
            for r in rows
        ],
        "note": "数据质量问题只展示不静默修复，由用户选择自动清洗、人工确认或保留原始值。",
    }


@router.get("/template/{dataset_type}")
def download_template(dataset_type: str):
    if dataset_type not in dq.DATASET_SCHEMAS:
        raise HTTPException(404, detail=f"未知数据集类型：{dataset_type}")
    content = dq.template_csv(dataset_type)
    return PlainTextResponse(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="template_{dataset_type}.csv"'},
    )


@router.post("/upload")
def upload_dataset(
    file: UploadFile = File(...),
    dataset_type: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if dataset_type not in dq.DATASET_SCHEMAS:
        raise HTTPException(400, detail=f"未知数据集类型：{dataset_type}，可选：{', '.join(dq.DATASET_SCHEMAS)}")

    fname = file.filename or "upload.csv"
    if not fname.lower().endswith(".csv"):
        raise HTTPException(400, detail="仅支持 CSV 文件")

    # 原始文件落盘保存，保留可追溯性
    raw_dir = DATA_DIR / "uploads"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    raw_path = raw_dir / f"{stamp}_{fname}"
    with raw_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        df = pd.read_csv(raw_path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, detail="文件编码无法解析，请另存为 UTF-8 编码的 CSV")
    except Exception as e:
        raise HTTPException(400, detail=f"CSV 解析失败：{e}")

    report = dq.check_quality(df, dataset_type)

    import hashlib
    version = f"v-{stamp}-{hashlib.md5(raw_path.read_bytes()).hexdigest()[:6]}"

    up = DataUpload(
        dataset_type=dataset_type, original_filename=fname,
        stored_path=f"data/uploads/{raw_path.name}", version=version,
        row_count=len(df), uploaded_by=user.username, uploaded_at=datetime.utcnow(),
        is_demo=False, source_note="用户上传数据", status="loaded",
    )
    db.add(up)
    db.flush()

    qrep = DataQualityReport(
        dataset_type=dataset_type, dataset_version=version, total_rows=len(df),
        completeness=report["completeness"], consistency=report["consistency"],
        validity=report["validity"], uniqueness=report["uniqueness"],
        timeliness=report["timeliness"], overall_score=report["overall_score"],
        issues=report["issues"], uploaded_by=user.username,
    )
    db.add(qrep)
    db.flush()
    up.quality_report_id = qrep.id

    db.add(AuditLog(user=user.username, action="upload_dataset", target=f"{dataset_type}:{fname}",
                    detail=f"{len(df)} 行，质量分 {report['overall_score']}", ip="127.0.0.1"))
    db.commit()

    return {
        "success": True,
        "upload_id": up.id,
        "version": version,
        "stored_path": up.stored_path,
        "row_count": len(df),
        "quality": report,
        "imported_to_db": False,
        "message": (
            f"文件已保存并完成质量检查（{len(df)} 行，质量分 {report['overall_score']}）。"
            "发现问题项请选择处理方式后再导入业务表：自动清洗 / 人工确认 / 保留原始值。"
        ),
        "options": ["auto_clean", "manual_confirm", "keep_raw"],
    }


class ImportRequest(BaseModel):
    upload_id: int
    dataset_type: str
    strategy: str = "keep_raw"     # auto_clean / manual_confirm / keep_raw


@router.post("/import")


def import_to_db(body: ImportRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    """把已上传的数据集导入业务表。strategy 决定如何处理质量问题。"""
    up = db.query(DataUpload).filter(DataUpload.id == body.upload_id).first()
    if not up:
        raise HTTPException(404, detail="上传记录不存在")

    path = DATA_DIR.parent / up.stored_path if not up.stored_path.startswith("data/") else Path(up.stored_path)
    full = DATA_DIR / Path(up.stored_path).name if not Path(up.stored_path).is_absolute() else Path(up.stored_path)
    if not full.exists():
        cand = DATA_DIR / "uploads" / Path(up.stored_path).name
        full = cand if cand.exists() else path
    if not full.exists():
        raise HTTPException(400, detail=f"找不到原始文件：{up.stored_path}")

    df = pd.read_csv(full, encoding="utf-8-sig")
    if body.strategy == "auto_clean":
        df = df.dropna(how="all").drop_duplicates()
    ds_type = body.dataset_type

    if ds_type == "sku_products":
        n = _import_sku(db, df, up.id, user.username)
    elif ds_type == "store_profile":
        n = _import_store(db, df, user.username)
    else:
        raise HTTPException(400, detail=f"数据集类型 {ds_type} 暂不支持导入业务表，请使用对应模块的上传入口")

    up.status = "cleaned" if body.strategy == "auto_clean" else "loaded"
    db.add(AuditLog(user=user.username, action="import_dataset", target=f"{ds_type}:{up.original_filename}",
                    detail=f"策略 {body.strategy}，导入 {n} 行", ip="127.0.0.1"))
    db.commit()
    return {"success": True, "imported": n, "strategy": body.strategy,
            "message": f"已导入 {n} 行到业务表。"}


SKU_FIELD_MAP = {
    "商品名称": "product_name", "商品编码": "sku_code", "SKU": "sku_code",
    "品类": "category_name", "品牌": "brand", "是否自有品牌": "is_private_label",
    "采购价": "purchase_price", "零售价": "retail_price", "建议零售价": "retail_price",
    "毛利率": "gross_margin_rate", "预计毛利率": "gross_margin_rate",
    "销量": "sales_qty", "销量(件)": "sales_qty", "销售额": "sales_amount",
    "销售额(元)": "sales_amount", "毛利额": "gross_profit",
    "周转": "turnover_days", "周转天数": "turnover_days", "库存周转天数": "turnover_days",
    "坪效": "sales_per_sqm", "供应商": "supplier", "规格": "spec",
    "包装": "packaging", "季节": "season", "缺货次数": "stockout_count",
    "货架占用": "shelf_area", "目标客群适配度": "target_group_fit",
    "促销属性": "is_promotion", "新品属性": "is_new",
}
BOOL_FIELDS = {"is_private_label", "is_promotion", "is_new"}
FLOAT_FIELDS = {
    "purchase_price", "retail_price", "gross_margin_rate", "sales_qty",
    "sales_amount", "gross_profit", "turnover_days", "sales_per_sqm",
    "shelf_area", "target_group_fit",
}
INT_FIELDS = {"stockout_count"}


def _import_sku(db: Session, df: pd.DataFrame, upload_id: int, username: str) -> int:
    cols = {}
    for src, dst in SKU_FIELD_MAP.items():
        if src in df.columns and dst not in cols:
            cols[src] = dst
    if "product_name" not in cols.values():
        raise HTTPException(400, detail="SKU 数据缺少「商品名称」或「商品编码」列")

    cats = {c.name: c for c in db.query(Category).all()}
    count = 0
    for _, row in df.iterrows():
        vals = {}
        for src, dst in cols.items():
            v = row[src]
            if pd.isna(v):
                vals[dst] = None
            elif dst in BOOL_FIELDS:
                vals[dst] = str(v).strip() in ("是", "true", "True", "1", "自有品牌")
            elif dst in FLOAT_FIELDS:
                try:
                    vals[dst] = float(v)
                except (TypeError, ValueError):
                    vals[dst] = None
            elif dst in INT_FIELDS:
                try:
                    vals[dst] = int(float(v))
                except (TypeError, ValueError):
                    vals[dst] = 0
            else:
                vals[dst] = str(v).strip()
        if not vals.get("product_name"):
            continue
        code = vals.pop("sku_code", None) or f"SKU{vals['product_name']}"
        cat_name = vals.pop("category_name", None)
        if db.query(SkuProduct).filter_by(sku_code=code).first():
            continue
        db.add(SkuProduct(
            sku_code=code, is_demo=False,
            category=cats.get(cat_name) if cat_name else None,
            **vals
        ))
        count += 1
    db.flush()
    return count


STORE_FIELD_MAP = {
    "门店名称": "name", "商圈": "business_district", "城市": "city", "区县": "district",
    "门店类型": "store_type", "营业面积": "area_sqm",
    "3公里人口": "pop_3km", "居民占比": "resident_ratio", "办公人群占比": "office_ratio",
    "学生占比": "student_ratio", "中老年占比": "senior_ratio",
    "消费能力": "consumption_power", "住宅POI": "poi_residential",
    "办公POI": "poi_office", "学校POI": "poi_school",
    "主要竞品": "main_competitors", "配送能力": "delivery_capability",
}


def _import_store(db: Session, df: pd.DataFrame, username: str) -> int:
    count = 0
    for _, row in df.iterrows():
        vals = {}
        for src, dst in STORE_FIELD_MAP.items():
            if src in df.columns and not pd.isna(row[src]):
                vals[dst] = float(row[src]) if dst not in ("name", "business_district", "city",
                                                          "district", "store_type", "consumption_power",
                                                          "main_competitors", "delivery_capability") else str(row[src]).strip()
        if "name" not in vals:
            continue
        if db.query(Store).filter_by(name=vals["name"]).first():
            continue
        db.add(Store(code=f"UP-{count+1:03d}", is_demo=False, **vals))
        count += 1
    db.flush()
    return count


@router.get("/datasets/{dataset_type}/download")
def download_cleaned(dataset_type: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """导出数据库中的清洗后结果，供人工核对。"""
    filename = f"export_{dataset_type}.csv"
    if dataset_type == "category_sales":
        rows = db.query(CategorySales).all()
        data = [{
            "品类ID": r.category.code if r.category else "",
            "品类名称": r.category.name if r.category else "",
            "月份": r.month, "销量(件)": r.sales_qty, "销售额(元)": r.sales_amount,
            "毛利额(元)": r.gross_profit, "库存周转天数": r.turnover_days,
            "坪效(元/㎡/月)": r.sales_per_sqm, "缺货次数": r.stockout_count,
            "SKU数量": r.sku_count,
        } for r in rows]
    elif dataset_type == "association_rules":
        from ...models import AssociationRule
        rows = db.query(AssociationRule).all()
        data = [{
            "规则ID": r.id, "前项商品(A)": r.antecedent, "后项商品(B)": r.consequent,
            "支持度": r.support, "置信度": r.confidence, "提升度": r.lift,
            "陈列建议": r.display_suggestion, "来源": r.source,
            "是否通过当前阈值": r.passes_threshold,
        } for r in rows]
    elif dataset_type == "category_health":
        from ...models import CategoryHealthResult
        rows = db.query(CategoryHealthResult).filter_by(source="system").all()
        data = [{
            "品类ID": r.category.code if r.category else "",
            "品类名称": r.category.name if r.category else "",
            "综合评分": r.overall_score, "健康度等级": r.grade, "评级": r.stars,
            "销量贡献(%)": r.sales_contribution, "毛利贡献(%)": r.margin_contribution,
            "周转天数": r.avg_turnover_days, "坪效得分": r.space_score,
            "预警灯": r.alert_light, "优化建议": r.suggestion,
        } for r in rows]
    else:
        raise HTTPException(400, detail=f"暂不支持导出 {dataset_type}")

    csv = pd.DataFrame(data).to_csv(index=False)
    return PlainTextResponse(csv, media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})