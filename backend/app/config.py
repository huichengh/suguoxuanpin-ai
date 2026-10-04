"""应用配置"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_URL = f"sqlite:///{(DATA_DIR / 'suguo.db').as_posix()}"
SECRET_KEY = "suguo-ai-competition-demo-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

DEMO_DISCLAIMER = "模拟演示数据，不代表华润苏果真实经营数据"
DEMO_SOURCE = "基于公开行业数据构造"
DEFAULT_STORE = "华润苏果（南京江宁黄金海岸广场店）"