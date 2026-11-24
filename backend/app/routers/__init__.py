"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import resource
from app.routers import chains
from app.routers import page_sample

# page_sample 含 /api/page-sample 固定前缀，需要放在通配 /api/{module} 资源路由之前。
ROUTERS = [page_sample, resource, chains]
