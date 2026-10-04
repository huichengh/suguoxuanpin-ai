"""SQLAlchemy 数据模型 —— 全套业务表"""
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Text, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)      # admin / buyer / category_mgr / store_mgr / viewer
    name = Column(String(100), nullable=False)
    description = Column(Text)
    permissions = Column(JSON, default=list)                    # 权限码列表
    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(100))
    password_hash = Column(String(255), nullable=False)          # bcrypt 哈希，绝不明文
    role_id = Column(Integer, ForeignKey("roles.id"))
    store_id = Column(Integer, ForeignKey("stores.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)
    role = relationship("Role", back_populates="users")
    store = relationship("Store")


class Store(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    city = Column(String(50))
    district = Column(String(50))
    business_district = Column(String(100))       # 商圈
    store_type = Column(String(50))               # 社区店 / 购物中心店
    area_sqm = Column(Float)                      # 营业面积
    is_default = Column(Boolean, default=False)
    is_demo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 门店画像（千店千面）—— 允许为空，空则前端显示"数据待接入"
    pop_3km = Column(Integer)                      # 3公里人口
    resident_ratio = Column(Float)                # 居民占比
    office_ratio = Column(Float)                  # 办公人群占比
    student_ratio = Column(Float)                 # 学生占比
    senior_ratio = Column(Float)                  # 中老年占比
    consumption_power = Column(String(50))        # 消费能力
    poi_residential = Column(Integer)
    poi_office = Column(Integer)
    poi_school = Column(Integer)
    main_competitors = Column(String(255))
    delivery_capability = Column(String(100))

    # --- 多门店对比所需的经营指标（可选录入，缺失时对比页面显示「数据待接入」）---
    # 附件只有一家门店的数据，其余门店需人工录入或上传
    sales_amount = Column(Float)                # 月销售额（元）
    gross_profit = Column(Float)                # 月毛利额（元）
    gross_margin_rate = Column(Float)           # 毛利率（%）
    sales_qty = Column(Float)                   # 月销量（件）
    turnover_days = Column(Float)               # 库存周转天数
    sales_per_sqm = Column(Float)               # 坪效（元/㎡/月）
    sku_count = Column(Integer)                 # 在售 SKU 数
    stockout_count = Column(Integer)            # 月缺货次数
    member_ratio = Column(Float)                # 会员销售占比（%）
    daily_customer_count = Column(Integer)      # 日均客流量（人）
    health_score = Column(Float)                # 综合健康度（0-100）
    open_date = Column(Date)                    # 开业日期
    data_source = Column(String(100))           # 数据来源说明
    data_updated_at = Column(DateTime)          # 经营数据更新时间

    # 录入人与时间（审计用）
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)     # C001
    name = Column(String(100), nullable=False, unique=True)
    category_role = Column(String(50))           # 品类角色：引流/主力/利润/后场
    stp_target = Column(String(255))              # STP 目标客群
    positioning = Column(String(255))             # 品类定位
    sort_order = Column(Integer, default=0)
    is_demo = Column(Boolean, default=True)


class SubCategory(Base):
    """小类（商品）层。由交易明细实时聚合，不独立维护。

    注意：附件数据中小类层只有销量/销售额/均价/笔数/关联度，
    没有毛利、周转、坪效字段。这三个字段留空表示「数据未接入」，
    平台不会用大类数据摊派填充。
    """
    __tablename__ = "sub_categories"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), index=True)
    name = Column(String(100), nullable=False, index=True)

    # --- 交易明细可得的真实指标 ---
    sales_qty = Column(Float)              # 销量（件）
    sales_amount = Column(Float)           # 销售额（元）
    avg_price = Column(Float)              # 均价（元）
    transaction_count = Column(Integer)     # 成交笔数
    qty_per_transaction = Column(Float)    # 客单件数
    first_sale_date = Column(Date)
    last_sale_date = Column(Date)
    active_days = Column(Integer)          # 有销售的天数

    # --- 关联度（由 Apriori 结果回填）---
    association_count = Column(Integer, default=0)   # 参与的关联规则数
    max_lift = Column(Float)                       # 最高提升度
    top_partner = Column(String(100))              # 最强关联商品

    # --- 以下字段当前无数据源，保留扩展位 ---
    gross_profit = Column(Float)          # 毛利额：附件无此字段
    turnover_days = Column(Float)         # 周转天数：附件无此字段
    sales_per_sqm = Column(Float)         # 坪效：附件无此字段
    shelf_area = Column(Float)            # 建议货架面积（由 D 模块计算写入）

    # --- 算法结果 ---
    cluster_label = Column(String(30))    # 聚类结果
    sub_score = Column(Float)             # 小类综合得分
    sub_score_sales = Column(Float)
    sub_score_amount = Column(Float)
    rank_in_category = Column(Integer)
    is_demo = Column(Boolean, default=True)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    algorithm = Column(String(100))
    parameters = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("Category")


class SkuProduct(Base):
    """SKU 级商品。当前附件无 SKU 经营指标，记录数可能为 0。"""
    __tablename__ = "sku_products"
    id = Column(Integer, primary_key=True)
    sku_code = Column(String(80), unique=True, nullable=False)
    product_name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"))
    brand = Column(String(100))
    is_private_label = Column(Boolean, default=False)
    purchase_price = Column(Float)
    retail_price = Column(Float)
    supplier = Column(String(200))
    spec = Column(String(100))
    packaging = Column(String(100))
    season = Column(String(50))
    shelf_area = Column(Float)                    # 货架占用（㎡）
    is_new = Column(Boolean, default=False)
    sales_qty = Column(Float)
    sales_amount = Column(Float)
    gross_profit = Column(Float)
    gross_margin_rate = Column(Float)
    turnover_days = Column(Float)
    sales_per_sqm = Column(Float)
    stockout_count = Column(Integer, default=0)
    target_group_fit = Column(Float)             # 目标客群适配度 0-100
    is_promotion = Column(Boolean, default=False)
    is_demo = Column(Boolean, default=True)
    category = relationship("Category")


class DataUpload(Base):
    __tablename__ = "data_uploads"
    id = Column(Integer, primary_key=True)
    dataset_type = Column(String(50), nullable=False)  # category_sales / transactions / ...
    original_filename = Column(String(255))
    stored_path = Column(String(500))
    version = Column(String(50))
    row_count = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    is_demo = Column(Boolean, default=True)
    source_note = Column(String(255))
    status = Column(String(50), default="loaded")      # loaded / cleaned / failed
    quality_report_id = Column(Integer, ForeignKey("data_quality_reports.id"))


class CategorySales(Base):
    __tablename__ = "category_sales"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), index=True)
    month = Column(String(10), index=True)           # YYYY-MM
    sales_qty = Column(Float)
    sales_amount = Column(Float)
    gross_profit = Column(Float)
    turnover_days = Column(Float)
    sales_per_sqm = Column(Float)
    stockout_count = Column(Integer, default=0)
    sku_count = Column(Integer)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    category = relationship("Category")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    transaction_no = Column(String(60), index=True, nullable=False)
    trans_date = Column(Date, index=True)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))


class TransactionItem(Base):
    __tablename__ = "transaction_items"
    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), index=True)
    sku_code = Column(String(80), index=True)
    product_name = Column(String(200), index=True, nullable=False)
    category_name = Column(String(100), index=True)
    quantity = Column(Float)
    unit_price = Column(Float)
    amount = Column(Float)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))


class CategoryHealthResult(Base):
    """品类健康度结果。source=attachment 为附件预置参考；system 为系统重算。"""
    __tablename__ = "category_health_results"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), index=True)
    source = Column(String(30), default="system")     # system / attachment
    overall_score = Column(Float)
    grade = Column(String(10))
    stars = Column(String(10))
    sales_score = Column(Float)
    margin_score = Column(Float)
    turnover_score = Column(Float)
    space_score = Column(Float)
    sales_contribution = Column(Float)                 # %
    margin_contribution = Column(Float)                 # %
    avg_turnover_days = Column(Float)
    avg_sales_per_sqm = Column(Float)
    total_stockout = Column(Integer)
    sku_count = Column(Integer)
    sales_trend = Column(Float)
    margin_trend = Column(Float)
    turnover_trend = Column(Float)
    space_trend = Column(Float)
    diagnosis = Column(Text)
    suggestion = Column(Text)
    alert_light = Column(String(20))
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    algorithm = Column(String(100))
    parameters = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    category = relationship("Category")


class AssociationRule(Base):
    __tablename__ = "association_rules"
    id = Column(Integer, primary_key=True)
    antecedent = Column(String(200), index=True)
    consequent = Column(String(200), index=True)
    support = Column(Float)
    confidence = Column(Float)
    lift = Column(Float)
    display_rule = Column(String(500))
    display_suggestion = Column(Text)
    source = Column(String(30), default="attachment")   # attachment / realtime
    passes_threshold = Column(Boolean, default=True)    # 是否通过当前参数阈值
    item_count = Column(Integer)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    algorithm = Column(String(100))
    parameters = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class DemandRecord(Base):
    """需求历史 + 预测合并表，数据类型区分 history / forecast。"""
    __tablename__ = "demand_records"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), index=True)
    week_no = Column(Integer)
    period_label = Column(String(20))
    actual_qty = Column(Float)
    forecast_qty = Column(Float)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    data_type = Column(String(20))                     # history / forecast
    is_simulated = Column(Boolean, default=True)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    algorithm = Column(String(100))
    parameters = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    category = relationship("Category")


class CandidateProduct(Base):
    __tablename__ = "candidate_products"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"))
    brand = Column(String(100))
    purchase_price = Column(Float)
    suggested_retail_price = Column(Float)
    expected_margin_rate = Column(Float)
    supplier = Column(String(200))
    target_consumer = Column(String(200))
    spec = Column(String(100))
    packaging = Column(String(100))
    season = Column(String(50))
    selling_point = Column(Text)
    is_private_label = Column(Boolean, default=False)
    reference_sku = Column(String(200))
    completeness_score = Column(Float)
    potential_level = Column(String(30))               # 高潜力 / 中等潜力 / 谨慎试销
    evaluation = Column(JSON)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    category = relationship("Category")


class ModelSetting(Base):
    __tablename__ = "model_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSON)                                # 结构化参数
    value_text = Column(Text)
    category = Column(String(50), default="algorithm")
    description = Column(String(255))
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow)
    previous_value = Column(JSON)
    change_reason = Column(Text)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id = Column(Integer, primary_key=True)
    job_type = Column(String(50))
    status = Column(String(30), default="success")
    algorithm = Column(String(100))
    parameters = Column(JSON)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    result_summary = Column(JSON)
    duration_ms = Column(Integer)
    triggered_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class AiRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True)
    source_module = Column(String(50))
    title = Column(String(300))
    content = Column(Text)
    data_basis = Column(Text)
    affected_categories = Column(String(255))
    priority = Column(String(20))                       # 高 / 中 / 低
    risk_level = Column(String(30))                     # Level 1 / Level 2 / Level 3
    requires_approval = Column(Boolean, default=False)
    decision_status = Column(String(30), default="待审")
    is_demo = Column(Boolean, default=True)
    source_dataset_id = Column(Integer, ForeignKey("data_uploads.id"))
    parameters = Column(JSON)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True)
    recommendation_id = Column(Integer, ForeignKey("ai_recommendations.id"))
    source_module = Column(String(50))
    ai_suggestion = Column(Text)
    data_basis = Column(Text)
    risk_level = Column(String(30))
    applicant = Column(String(100))
    approver = Column(String(100))
    status = Column(String(30), default="待审批")       # 待审批/已通过/已驳回/已撤回
    approval_comment = Column(Text)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime)


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"
    id = Column(Integer, primary_key=True)
    dataset_type = Column(String(50))
    dataset_version = Column(String(50))
    total_rows = Column(Integer)
    completeness = Column(Float)
    consistency = Column(Float)
    validity = Column(Float)
    uniqueness = Column(Float)
    timeliness = Column(Float)
    overall_score = Column(Float)
    issues = Column(JSON)                              # [{field, count, severity, suggestion}]
    checked_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(String(100))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user = Column(String(100))
    action = Column(String(255))
    target = Column(String(255))
    detail = Column(Text)
    ip = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelRunLog(Base):
    __tablename__ = "model_run_logs"
    id = Column(Integer, primary_key=True)
    algorithm = Column(String(100))
    parameters = Column(JSON)
    dataset = Column(String(100))
    status = Column(String(30))
    output = Column(Text)
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeDoc(Base):
    """AI 知识库条目"""
    __tablename__ = "knowledge_docs"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    category = Column(String(50))
    content = Column(Text)
    tags = Column(String(255))
    is_active = Column(Boolean, default=True)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow)


class AgentConversation(Base):
    __tablename__ = "agent_conversations"
    id = Column(Integer, primary_key=True)
    session_id = Column(String(80), index=True)
    user = Column(String(100))
    role = Column(String(20))                          # user / assistant
    content = Column(Text)
    tools_used = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)