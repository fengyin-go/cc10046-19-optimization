"""页面字段试跑路由：页面版本、样本定位搜索、单字段复跑、差异与映射试跑。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.field_mapper import FieldMapperService
from app.services.page_sample import page_sample_service

router = APIRouter(prefix="/api/page-sample", tags=["页面字段试跑"])

_mapper = FieldMapperService()


class SearchPayload(BaseModel):
    keyword: str = ""
    page_version: str | None = None


class ActivatePayload(BaseModel):
    version: str


class TrialPayload(BaseModel):
    search_id: int
    product_id: str
    field: str
    target_version: str | None = None


class MappingTrialPayload(BaseModel):
    run_id: int
    target_field: str
    transform: str = ""
    default: Any = Field(default="")


def _raise_key_error(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


@router.get("/versions")
def get_versions() -> dict[str, Any]:
    """页面结构版本列表，active 标记当前生效版本；历史版本照常可查。"""
    pages = page_sample_service.list_versions()
    current = next((page["version"] for page in pages if page.get("active")), None)
    return {"items": pages, "active_version": current}


@router.post("/versions/activate")
def activate_version(payload: ActivatePayload) -> dict[str, Any]:
    try:
        page = page_sample_service.activate_version(payload.version)
    except KeyError as exc:
        raise _raise_key_error(exc) from exc
    return {"ok": True, "message": f"当前生效页面已切换为 {page['version']}", "page": page}


@router.post("/searches")
def create_search(payload: SearchPayload) -> dict[str, Any]:
    """搜索商品并生成字段样本定位数据，按实际页面版本固化搜索记录。"""
    try:
        record = page_sample_service.search_products(payload.keyword, payload.page_version)
    except KeyError as exc:
        raise _raise_key_error(exc) from exc
    return {"ok": True, "message": f"已按页面 {record['page_version']} 生成 {record['candidate_count']} 条候选片段",
            "search": record}


@router.get("/searches")
def get_searches() -> dict[str, Any]:
    return {"items": page_sample_service.list_searches()}


@router.get("/searches/{search_id}")
def get_search(search_id: int) -> dict[str, Any]:
    record = page_sample_service.get_search(search_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"搜索记录 {search_id} 不存在")
    return record


@router.post("/trials")
def create_trial(payload: TrialPayload) -> dict[str, Any]:
    """从候选片段直接发起单字段复跑，只解析所选商品和字段。"""
    try:
        trial = page_sample_service.run_field_trial(
            search_id=payload.search_id,
            product_id=payload.product_id,
            field=payload.field,
            target_version=payload.target_version,
        )
    except KeyError as exc:
        raise _raise_key_error(exc) from exc
    return {"ok": True, "message": trial["message"], "trial": trial}


@router.get("/trials")
def get_trials(search_id: int | None = None) -> dict[str, Any]:
    return {"items": page_sample_service.list_runs(search_id)}


@router.get("/trials/{run_id}")
def get_trial(run_id: int) -> dict[str, Any]:
    trial = page_sample_service.get_run(run_id)
    if trial is None:
        raise HTTPException(status_code=404, detail=f"试跑记录 {run_id} 不存在")
    return trial


@router.get("/diffs")
def get_diffs() -> dict[str, Any]:
    return {"items": page_sample_service.list_diffs()}


@router.get("/diffs/{diff_id}")
def get_diff(diff_id: int) -> dict[str, Any]:
    diff = page_sample_service.get_diff(diff_id)
    if diff is None:
        raise HTTPException(status_code=404, detail=f"差异 {diff_id} 不存在")
    return diff


@router.post("/diffs/{diff_id}/review")
def review_diff(diff_id: int) -> dict[str, Any]:
    try:
        diff = page_sample_service.review_diff(diff_id)
    except KeyError as exc:
        raise _raise_key_error(exc) from exc
    return {"ok": True, "message": "差异已核对，记录保留可随时重新打开", "diff": diff}


@router.post("/mapping-trials")
def create_mapping_trial(payload: MappingTrialPayload) -> dict[str, Any]:
    """字段映射消费样本定位数据：基于某次复跑产出映射值并标注来源位置。"""
    try:
        result = _mapper.domain_map_sample(
            run_id=payload.run_id,
            target_field=payload.target_field,
            transform=payload.transform,
            default=payload.default,
        )
    except KeyError as exc:
        raise _raise_key_error(exc) from exc
    return {
        "ok": True,
        "message": (
            f"映射值 {result['mapped_value']} 采用页面 {result['used_page_version']} "
            f"第 {result['used_segment_index']} 段的{result['source_basis_label']}"
        ),
        "mapping": result,
    }


@router.get("/mapping-diffs")
def get_mapping_diffs() -> dict[str, Any]:
    return {"items": _mapper.domain_sample_diffs()}


@router.get("/mapping-diffs/{diff_id}")
def get_mapping_diff(diff_id: int) -> dict[str, Any]:
    diff = page_sample_service.get_mapper_diff(diff_id)
    if diff is None:
        raise HTTPException(status_code=404, detail=f"字段映射差异 {diff_id} 不存在")
    return diff


@router.post("/mapping-diffs/{diff_id}/review")
def review_mapping_diff(diff_id: int) -> dict[str, Any]:
    try:
        diff = page_sample_service.review_mapper_diff(diff_id)
    except KeyError as exc:
        raise _raise_key_error(exc) from exc
    return {"ok": True, "message": "映射差异已核对，可随时重新打开", "diff": diff}
