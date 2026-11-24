"""页面字段试跑领域服务。

业务目标（对应需求）：
- 搜索商品页面时为每个命中的商品字段生成「字段样本定位数据」，记录页面结构版本、
  商品身份、片段序号、字段名、字段值与定位指纹；定位跟着页面版本走，历史样本照常可查。
- 从搜索结果的候选片段可以直接发起「单字段复跑」：复跑只取所选位置对应的商品和字段，
  不重算无关商品；按商品身份（product_id）在当前页面里定位，避免把同名列的另一商品
  读进选中行。
- 页面结构版本变化（如插入广告）后，同一条历史搜索记录仍可发起复跑，复跑结果同时
  携带旧样本位置、当前页面位置和两者读出的值，供值班员核对差异。
- 字段映射消费样本定位数据：映射试跑基于某次复跑的实际取值产出映射值，并记录本次
  采用的是旧样本还是新位置，差异落库后可重新打开核对。

该服务不依赖数据库和第三方库，全部数据保存在内存仓库的独立表中，重启回到种子状态。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

# ---------------------------------------------------------------------------
# 演示用页面快照。两段页面的结构差异正好覆盖验收场景：
# V1 主商品 A 在第二段、价格 5；广告插入后的 V2 中 A 移到第三段、价格改成 6。
# 每个片段都带 product_id，定位以商品身份为准，而不是片段序号或列名。
# ---------------------------------------------------------------------------
SEED_PAGE_VERSIONS: list[dict[str, Any]] = [
    {
        "id": 1,
        "page_key": "shop-search",
        "version": "v1",
        "title": "搜索结果页（广告插入前）",
        "active": True,
        "remark": "两段报价结构，主商品 A 位于第二段",
        "segments": [
            {
                "segment_index": 1,
                "product_id": "B",
                "product_name": "商品B",
                "is_ad": False,
                "fields": {"price": 8, "title": "商品B", "stock": 12},
            },
            {
                "segment_index": 2,
                "product_id": "A",
                "product_name": "商品A",
                "is_ad": False,
                "fields": {"price": 5, "title": "商品A", "stock": 30},
            },
        ],
    },
    {
        "id": 2,
        "page_key": "shop-search",
        "version": "v2",
        "title": "搜索结果页（广告插入后）",
        "active": False,
        "remark": "网页在首段后插入广告，商品 A 移到第三段且价格调整为 6",
        "segments": [
            {
                "segment_index": 1,
                "product_id": "B",
                "product_name": "商品B",
                "is_ad": False,
                "fields": {"price": 8, "title": "商品B", "stock": 12},
            },
            {
                "segment_index": 2,
                "product_id": "AD-1",
                "product_name": "广告位",
                "is_ad": True,
                "fields": {"price": 99, "title": "广告位", "stock": 0},
            },
            {
                "segment_index": 3,
                "product_id": "A",
                "product_name": "商品A",
                "is_ad": False,
                "fields": {"price": 6, "title": "商品A", "stock": 30},
            },
        ],
    },
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PageSampleService:
    """页面版本、字段样本定位、单字段试跑与差异核对的领域服务。"""

    MODULE = "page_sample"
    ENTITY = "字段样本"

    # 内存仓库中的表名
    T_VERSIONS = "page_sample_versions"
    T_SEARCHES = "page_sample_searches"
    T_RUNS = "page_sample_runs"
    T_DIFFS = "page_sample_diffs"
    T_MAPPER_DIFFS = "field_mapper_diffs"

    def __init__(self) -> None:
        self._seeded = False

    # -- 初始化与基础读取 ---------------------------------------------------
    def ensure_seed(self) -> None:
        """首次访问时把演示页面版本写入内存仓库，后续请求复用同一份数据。"""
        if self._seeded:
            return
        versions = store.rows(self.T_VERSIONS)
        if not versions:
            for page in SEED_PAGE_VERSIONS:
                stored = {key: value for key, value in page.items()}
                stored["segments"] = [dict(segment) for segment in page["segments"]]
                versions.append(stored)
        self._seeded = True

    def list_versions(self) -> list[dict[str, Any]]:
        self.ensure_seed()
        return store.rows(self.T_VERSIONS)

    def get_version(self, version: str | None = None) -> dict[str, Any] | None:
        """按版本号取页面；不传版本号时返回当前生效版本。"""
        self.ensure_seed()
        pages = store.rows(self.T_VERSIONS)
        if version:
            return next((page for page in pages if page["version"] == version), None)
        return next((page for page in pages if page.get("active")), pages[-1])

    def activate_version(self, version: str) -> dict[str, Any]:
        """切换当前生效的页面结构版本（模拟广告插入等页面结构更正）。"""
        self.ensure_seed()
        target = self.get_version(version)
        if target is None:
            raise KeyError(f"页面版本 {version} 不存在")
        for page in store.rows(self.T_VERSIONS):
            page["active"] = page["version"] == version
        return target

    def find_segment(self, page: dict[str, Any], product_id: str) -> dict[str, Any] | None:
        """在指定页面内按商品身份定位片段，而不是按片段序号或同名列取值。"""
        return next(
            (segment for segment in page["segments"] if segment["product_id"] == product_id),
            None,
        )

    # -- 字段样本定位数据 ---------------------------------------------------
    @staticmethod
    def _locator_fingerprint(page_version: str, segment_index: int, product_id: str, field: str) -> str:
        return f"{page_version}#seg{segment_index}#{product_id}#{field}"

    def _build_sample(
        self,
        page: dict[str, Any],
        segment: dict[str, Any],
        field: str,
    ) -> dict[str, Any]:
        """为单个商品字段生成样本定位数据。"""
        return {
            "page_version": page["version"],
            "product_id": segment["product_id"],
            "product_name": segment["product_name"],
            "segment_index": segment["segment_index"],
            "is_ad": segment["is_ad"],
            "field": field,
            "field_value": segment["fields"].get(field),
            "locator": self._locator_fingerprint(
                page["version"], segment["segment_index"], segment["product_id"], field
            ),
        }

    # -- 商品搜索：生成候选片段与样本定位数据 -------------------------------
    def search_products(self, keyword: str, page_version: str | None = None) -> dict[str, Any]:
        """搜索商品并为命中商品的每个字段生成样本定位数据。

        每次按实际页面版本保存搜索记录：记录里固化当时的版本号和样本，页面改版后
        历史记录照常可查，仍可从同一条记录发起复跑。
        """
        self.ensure_seed()
        page = self.get_version(page_version)
        if page is None:
            raise KeyError(f"页面版本 {page_version} 不存在")

        keyword = (keyword or "").strip()
        candidates: list[dict[str, Any]] = []
        for segment in page["segments"]:
            if segment["is_ad"]:
                # 广告片段不属于可试跑的商品候选，但仍保留在页面结构里用于解释位移
                continue
            if keyword and keyword not in segment["product_name"] and keyword != segment["product_id"]:
                continue
            samples = [
                self._build_sample(page, segment, field)
                for field in segment["fields"]
            ]
            candidates.append({
                "product_id": segment["product_id"],
                "product_name": segment["product_name"],
                "segment_index": segment["segment_index"],
                "is_ad": segment["is_ad"],
                "field_samples": samples,
            })

        record = {
            "id": store.next_id(self.T_SEARCHES),
            "keyword": keyword,
            "page_version": page["version"],
            "page_title": page["title"],
            "searched_at": _now(),
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        store.rows(self.T_SEARCHES).append(record)
        return record

    def list_searches(self) -> list[dict[str, Any]]:
        self.ensure_seed()
        return store.rows(self.T_SEARCHES)

    def get_search(self, search_id: int) -> dict[str, Any] | None:
        self.ensure_seed()
        return store.find(self.T_SEARCHES, search_id)

    def _find_candidate(self, search_record: dict[str, Any], product_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in search_record["candidates"] if item["product_id"] == product_id),
            None,
        )

    # -- 单字段试跑（复跑） -------------------------------------------------
    def run_field_trial(
        self,
        *,
        search_id: int,
        product_id: str,
        field: str,
        target_version: str | None = None,
    ) -> dict[str, Any]:
        """从候选片段直接发起单字段复跑。

        - 只解析所选位置对应的商品和字段，不重算页面上的无关商品。
        - 旧位置来自搜索记录固化的样本；新位置在「当前生效页面」上按商品身份重新定位，
          因此即使同名列里有多个商品，也只会读回选中商品本身。
        - target_version 可显式指定复跑采用的页面版本，默认取当前生效版本。
        """
        self.ensure_seed()
        search_record = self.get_search(search_id)
        if search_record is None:
            raise KeyError(f"搜索记录 {search_id} 不存在或已归档")
        candidate = self._find_candidate(search_record, product_id)
        if candidate is None:
            raise KeyError(f"搜索记录 {search_id} 的候选片段中没有商品 {product_id}")

        old_sample = next(
            (sample for sample in candidate["field_samples"] if sample["field"] == field),
            None,
        )
        if old_sample is None:
            raise KeyError(f"商品 {product_id} 在该搜索记录中没有字段 {field} 的样本")

        current_page = self.get_version(target_version)
        if current_page is None:
            raise KeyError(f"页面版本 {target_version} 不存在")
        current_segment = self.find_segment(current_page, product_id)
        if current_segment is None:
            raise KeyError(f"商品 {product_id} 在页面版本 {current_page['version']} 中已下架，无法复跑")

        new_sample = self._build_sample(current_page, current_segment, field)
        version_changed = old_sample["page_version"] != new_sample["page_version"]
        shifted = old_sample["segment_index"] != new_sample["segment_index"]
        value_changed = old_sample["field_value"] != new_sample["field_value"]
        has_diff = shifted or value_changed

        trial = {
            "id": store.next_id(self.T_RUNS),
            "search_id": search_id,
            "product_id": product_id,
            "product_name": candidate["product_name"],
            "field": field,
            "requested_from_version": search_record["page_version"],
            "used_page_version": current_page["version"],
            "used_page_title": current_page["title"],
            "old_sample": old_sample,
            "new_sample": new_sample,
            "version_changed": version_changed,
            "segment_shifted": shifted,
            "value_changed": value_changed,
            "has_diff": has_diff,
            "scanned_product_count": 1,
            "scanned_field_count": 1,
            "ran_at": _now(),
            "message": self._trial_message(old_sample, new_sample, version_changed, shifted, value_changed),
        }
        store.rows(self.T_RUNS).append(trial)

        if has_diff:
            diff = {
                "id": store.next_id(self.T_DIFFS),
                "trial_id": trial["id"],
                "search_id": search_id,
                "product_id": product_id,
                "product_name": candidate["product_name"],
                "field": field,
                "old_page_version": old_sample["page_version"],
                "old_segment_index": old_sample["segment_index"],
                "old_value": old_sample["field_value"],
                "new_page_version": new_sample["page_version"],
                "new_segment_index": new_sample["segment_index"],
                "new_value": new_sample["field_value"],
                "version_changed": version_changed,
                "segment_shifted": shifted,
                "value_changed": value_changed,
                "status": "待核对",
                "created_at": _now(),
            }
            store.rows(self.T_DIFFS).append(diff)
            trial["diff_id"] = diff["id"]
        else:
            trial["diff_id"] = None
        return trial

    @staticmethod
    def _trial_message(
        old_sample: dict[str, Any],
        new_sample: dict[str, Any],
        version_changed: bool,
        shifted: bool,
        value_changed: bool,
    ) -> str:
        if not shifted and not value_changed:
            version_note = (
                f"（页面已由 {old_sample['page_version']} 更新为 {new_sample['page_version']}，"
                "但该商品位置与取值均未变化）"
                if version_changed
                else ""
            )
            return (
                f"复跑采用页面 {new_sample['page_version']}，商品 {new_sample['product_id']} "
                f"仍在第 {new_sample['segment_index']} 段，字段 {new_sample['field']} "
                f"读出 {new_sample['field_value']}，与旧样本一致{version_note}"
            )
        parts = [
            f"复跑采用页面 {new_sample['page_version']}（旧样本来自 {old_sample['page_version']}）",
            f"商品 {new_sample['product_id']} 由第 {old_sample['segment_index']} 段移至第 "
            f"{new_sample['segment_index']} 段" if shifted else "",
            f"字段 {new_sample['field']} 取值由 {old_sample['field_value']} 变为 "
            f"{new_sample['field_value']}" if value_changed else "",
        ]
        return "，".join(part for part in parts if part)

    def list_runs(self, search_id: int | None = None) -> list[dict[str, Any]]:
        self.ensure_seed()
        rows = store.rows(self.T_RUNS)
        if search_id is not None:
            rows = [row for row in rows if row["search_id"] == search_id]
        return rows

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        self.ensure_seed()
        return store.find(self.T_RUNS, run_id)

    # -- 差异核对 -----------------------------------------------------------
    def list_diffs(self) -> list[dict[str, Any]]:
        self.ensure_seed()
        return store.rows(self.T_DIFFS)

    def get_diff(self, diff_id: int) -> dict[str, Any] | None:
        self.ensure_seed()
        return store.find(self.T_DIFFS, diff_id)

    def review_diff(self, diff_id: int) -> dict[str, Any]:
        """值班员核对差异后标记，差异本身保留可随时重新打开。"""
        self.ensure_seed()
        diff = self.get_diff(diff_id)
        if diff is None:
            raise KeyError(f"差异 {diff_id} 不存在")
        diff["status"] = "已核对"
        diff["reviewed_at"] = _now()
        return diff

    # -- 字段映射消费样本定位数据 -------------------------------------------
    def run_mapping_trial(
        self,
        *,
        run_id: int,
        target_field: str,
        transform: str = "",
        default: Any = "",
    ) -> dict[str, Any]:
        """字段映射基于某次单字段复跑的实际取值产出映射值。

        映射消费的是样本定位数据：结果明确记录采用的页面版本、片段位置，以及本次
        依据的是旧样本还是新位置读出的值，避免来源不可追溯。
        """
        self.ensure_seed()
        trial = self.get_run(run_id)
        if trial is None:
            raise KeyError(f"试跑记录 {run_id} 不存在")

        old_sample = trial["old_sample"]
        new_sample = trial["new_sample"]
        # 默认按当前页面新位置的实际读出值做映射；值未变化时两者等价。
        source = "new_position" if trial["has_diff"] else "sample"
        source_sample = new_sample if source == "new_position" else old_sample
        raw_value = source_sample["field_value"]
        if raw_value is None or raw_value == "":
            raw_value = default
        mapped_value = self._apply_transform(raw_value, transform)

        mapper_diff = None
        if trial["has_diff"]:
            mapper_diff = {
                "id": store.next_id(self.T_MAPPER_DIFFS),
                "run_id": run_id,
                "search_id": trial["search_id"],
                "product_id": trial["product_id"],
                "product_name": trial["product_name"],
                "field": trial["field"],
                "target_field": target_field,
                "source_basis": "new_position",
                "source_page_version": source_sample["page_version"],
                "source_segment_index": source_sample["segment_index"],
                "old_sample_value": old_sample["field_value"],
                "actual_value": new_sample["field_value"],
                "mapped_value": mapped_value,
                "transform": transform,
                "status": "待核对",
                "created_at": _now(),
            }
            store.rows(self.T_MAPPER_DIFFS).append(mapper_diff)

        return {
            "run_id": run_id,
            "product_id": trial["product_id"],
            "product_name": trial["product_name"],
            "source_field": trial["field"],
            "target_field": target_field,
            "source_basis": source,
            "source_basis_label": "新页面位置实际读出值" if source == "new_position" else "样本定位值",
            "used_page_version": source_sample["page_version"],
            "used_segment_index": source_sample["segment_index"],
            "old_sample": old_sample,
            "new_sample": new_sample,
            "raw_value": raw_value,
            "transform": transform,
            "mapped_value": mapped_value,
            "mapper_diff_id": mapper_diff["id"] if mapper_diff else None,
            "ran_at": _now(),
        }

    @staticmethod
    def _apply_transform(value: Any, transform: str) -> Any:
        if transform == "upper":
            return str(value).upper()
        if transform == "lower":
            return str(value).lower()
        if transform == "int":
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return 0
        if transform == "money":
            try:
                return round(float(value), 2)
            except (ValueError, TypeError):
                return value
        return value

    def list_mapper_diffs(self) -> list[dict[str, Any]]:
        self.ensure_seed()
        return store.rows(self.T_MAPPER_DIFFS)

    def get_mapper_diff(self, mapper_diff_id: int) -> dict[str, Any] | None:
        self.ensure_seed()
        return store.find(self.T_MAPPER_DIFFS, mapper_diff_id)

    def review_mapper_diff(self, mapper_diff_id: int) -> dict[str, Any]:
        self.ensure_seed()
        diff = self.get_mapper_diff(mapper_diff_id)
        if diff is None:
            raise KeyError(f"字段映射差异 {mapper_diff_id} 不存在")
        diff["status"] = "已核对"
        diff["reviewed_at"] = _now()
        return diff


page_sample_service = PageSampleService()
