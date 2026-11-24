"""__NAME__领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。"""
from __future__ import annotations

from app.services.base import BaseModuleService


class FieldMapperService(BaseModuleService):
    MODULE = "field_mapper"
    ENTITY = "映射方案"
    OPERATION_TERM = "转换"
    LIST_FIELDS = ["方案标识", "来源字段", "目标字段", "转换函数", "默认取值", "映射版本", "适用站点", "依赖字段"]
    REQUIRED_FIELDS = ["方案标识", "来源字段", "目标字段"]
    STATUS_ORDER = ["草稿", "待校验", "已生效", "已停用"]
    ACTION_RULES = {"提交校验": "待校验", "启用映射": "已生效", "停用映射": "已停用"}
    NEGATIVE_ACTIONS = ["停用映射"]

    def domain_map_fields(self, source_data: dict, mapping_rules: list[dict]) -> dict:
        """根据映射规则将来源字段转换为目标字段。"""
        result: dict = {}
        for rule in mapping_rules:
            src_field = rule.get("source", "")
            tgt_field = rule.get("target", "")
            default = rule.get("default", "")
            transform = rule.get("transform", "")

            value = source_data.get(src_field, default)
            if transform == "upper":
                value = str(value).upper()
            elif transform == "lower":
                value = str(value).lower()
            elif transform == "int":
                try:
                    value = int(float(value))
                except (ValueError, TypeError):
                    value = 0
            result[tgt_field] = value
        return result

    def domain_map_sample(
        self,
        run_id: int,
        target_field: str,
        transform: str = "",
        default: object = "",
    ) -> dict:
        """消费字段样本定位数据做映射试跑。

        真正的页面定位与复跑逻辑由页面字段试跑服务持有，这里只表达字段映射领域的
        消费关系：映射值必须能追溯到具体页面版本、片段位置以及旧样本/新位置来源。
        """
        from app.services.page_sample import page_sample_service

        return page_sample_service.run_mapping_trial(
            run_id=run_id,
            target_field=target_field,
            transform=transform,
            default=default,
        )

    def domain_sample_diffs(self) -> list[dict]:
        """返回字段映射消费样本后沉淀的差异，供值班员重新打开核对。"""
        from app.services.page_sample import page_sample_service

        return page_sample_service.list_mapper_diffs()
