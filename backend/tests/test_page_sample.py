"""页面字段试跑领域测试：覆盖样本定位、单字段复跑、同名列保护与映射消费。

直接运行：.venv/bin/python -I tests/test_page_sample.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.page_sample import PageSampleService, page_sample_service


def fresh_service() -> PageSampleService:
    """每个用例使用独立服务与全新内存仓库，避免相互污染。"""
    from app import store as store_module

    service = PageSampleService()
    for table in (
        PageSampleService.T_VERSIONS,
        PageSampleService.T_SEARCHES,
        PageSampleService.T_RUNS,
        PageSampleService.T_DIFFS,
        PageSampleService.T_MAPPER_DIFFS,
    ):
        store_module.store.rows(table).clear()
    service._seeded = False
    service.ensure_seed()
    return service


class TestPageSampleSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.service = fresh_service()

    def test_default_active_version_is_v1(self):
        page = self.service.get_version()
        self.assertEqual(page["version"], "v1")

    def test_search_builds_field_sample_locators(self):
        record = self.service.search_products("商品A")
        self.assertEqual(record["page_version"], "v1")
        self.assertEqual(record["candidate_count"], 1)
        candidate = record["candidates"][0]
        self.assertEqual(candidate["segment_index"], 2)
        price = next(s for s in candidate["field_samples"] if s["field"] == "price")
        self.assertEqual(price["field_value"], 5)
        self.assertEqual(price["locator"], "v1#seg2#A#price")

    def test_ad_segment_is_not_a_candidate(self):
        self.service.activate_version("v2")
        record = self.service.search_products("")
        ids = {c["product_id"] for c in record["candidates"]}
        self.assertNotIn("AD-1", ids)
        self.assertEqual(ids, {"A", "B"})


class TestFieldTrial(unittest.TestCase):
    def setUp(self) -> None:
        self.service = fresh_service()
        self.search = self.service.search_products("商品A")

    def test_trial_only_scans_selected_product_and_field(self):
        self.service.activate_version("v2")
        trial = self.service.run_field_trial(
            search_id=self.search["id"], product_id="A", field="price")
        self.assertEqual(trial["scanned_product_count"], 1)
        self.assertEqual(trial["scanned_field_count"], 1)
        self.assertEqual(trial["used_page_version"], "v2")

    def test_trial_compares_old_sample_with_new_position(self):
        self.service.activate_version("v2")
        trial = self.service.run_field_trial(
            search_id=self.search["id"], product_id="A", field="price")
        self.assertEqual(trial["old_sample"]["field_value"], 5)
        self.assertEqual(trial["old_sample"]["segment_index"], 2)
        self.assertEqual(trial["new_sample"]["field_value"], 6)
        self.assertEqual(trial["new_sample"]["segment_index"], 3)
        self.assertTrue(trial["segment_shifted"])
        self.assertTrue(trial["value_changed"])
        self.assertTrue(trial["has_diff"])
        self.assertIsNotNone(trial["diff_id"])

    def test_same_named_column_does_not_pull_other_product(self):
        """广告插入后第二段是广告价 99，复跑 A 必须按商品身份读到第三段的 6。"""
        self.service.activate_version("v2")
        trial = self.service.run_field_trial(
            search_id=self.search["id"], product_id="A", field="price")
        ad = self.service.find_segment(self.service.get_version(), "AD-1")
        self.assertEqual(ad["fields"]["price"], 99)
        self.assertEqual(trial["new_sample"]["field_value"], 6)
        self.assertNotEqual(trial["new_sample"]["field_value"], ad["fields"]["price"])

    def test_version_change_without_shift_or_value_is_not_a_diff(self):
        full_search = self.service.search_products("")
        self.service.activate_version("v2")
        trial = self.service.run_field_trial(
            search_id=full_search["id"], product_id="B", field="price")
        self.assertTrue(trial["version_changed"])
        self.assertFalse(trial["segment_shifted"])
        self.assertFalse(trial["value_changed"])
        self.assertFalse(trial["has_diff"])
        self.assertIsNone(trial["diff_id"])
        self.assertEqual(trial["new_sample"]["field_value"], 8)

    def test_explicit_target_version(self):
        self.service.activate_version("v2")
        trial = self.service.run_field_trial(
            search_id=self.search["id"], product_id="A", field="price",
            target_version="v1")
        self.assertEqual(trial["used_page_version"], "v1")
        self.assertFalse(trial["has_diff"])

    def test_unknown_product_in_candidate_rejected(self):
        with self.assertRaises(KeyError):
            self.service.run_field_trial(
                search_id=self.search["id"], product_id="C", field="price")

    def test_unknown_search_rejected(self):
        with self.assertRaises(KeyError):
            self.service.run_field_trial(search_id=999, product_id="A", field="price")

    def test_history_search_keeps_v1_sample_after_version_switch(self):
        self.service.activate_version("v2")
        reopened = self.service.get_search(self.search["id"])
        self.assertEqual(reopened["page_version"], "v1")
        sample = reopened["candidates"][0]["field_samples"][0]
        self.assertEqual(sample["page_version"], "v1")


class TestDiffReview(unittest.TestCase):
    def setUp(self) -> None:
        self.service = fresh_service()
        self.search = self.service.search_products("商品A")
        self.service.activate_version("v2")
        self.trial = self.service.run_field_trial(
            search_id=self.search["id"], product_id="A", field="price")

    def test_diff_persisted_and_reopenable(self):
        diff = self.service.get_diff(self.trial["diff_id"])
        self.assertEqual(diff["status"], "待核对")
        self.assertEqual(diff["old_value"], 5)
        self.assertEqual(diff["new_value"], 6)
        reviewed = self.service.review_diff(diff["id"])
        self.assertEqual(reviewed["status"], "已核对")
        # 核对后记录仍在，可随时重新打开
        self.assertIsNotNone(self.service.get_diff(diff["id"]))


class TestMappingConsumesSample(unittest.TestCase):
    def setUp(self) -> None:
        self.service = fresh_service()
        search = self.service.search_products("商品A")
        self.service.activate_version("v2")
        self.trial = self.service.run_field_trial(
            search_id=search["id"], product_id="A", field="price")

    def test_mapping_uses_new_position_value_and_records_basis(self):
        mapping = self.service.run_mapping_trial(
            run_id=self.trial["id"], target_field="standard_price", transform="money")
        self.assertEqual(mapping["mapped_value"], 6.0)
        self.assertEqual(mapping["source_basis"], "new_position")
        self.assertEqual(mapping["used_page_version"], "v2")
        self.assertEqual(mapping["used_segment_index"], 3)
        self.assertEqual(mapping["old_sample"]["field_value"], 5)
        self.assertEqual(mapping["new_sample"]["field_value"], 6)

    def test_mapping_diff_reopenable_after_review(self):
        mapping = self.service.run_mapping_trial(
            run_id=self.trial["id"], target_field="standard_price")
        diff_id = mapping["mapper_diff_id"]
        self.assertIsNotNone(diff_id)
        diff = self.service.get_mapper_diff(diff_id)
        self.assertEqual(diff["actual_value"], 6)
        self.service.review_mapper_diff(diff_id)
        reopened = self.service.get_mapper_diff(diff_id)
        self.assertEqual(reopened["status"], "已核对")
        self.assertEqual(reopened["mapped_value"], 6)

    def test_no_diff_trial_creates_no_mapping_diff(self):
        full_search = self.service.search_products("")
        trial_b = self.service.run_field_trial(
            search_id=full_search["id"], product_id="B", field="price")
        mapping = self.service.run_mapping_trial(
            run_id=trial_b["id"], target_field="standard_price")
        self.assertIsNone(mapping["mapper_diff_id"])
        self.assertEqual(mapping["source_basis"], "sample")


class TestFieldMapperDelegation(unittest.TestCase):
    def test_field_mapper_service_consumes_sample_locator(self):
        from app.services.field_mapper import FieldMapperService

        service = fresh_service()
        search = service.search_products("商品A")
        service.activate_version("v2")
        trial = service.run_field_trial(
            search_id=search["id"], product_id="A", field="price")
        mapper = FieldMapperService()
        result = mapper.domain_map_sample(trial["id"], "standard_price", "money")
        self.assertEqual(result["mapped_value"], 6.0)
        self.assertEqual(result["used_page_version"], "v2")
        self.assertTrue(mapper.domain_sample_diffs())


class TestPageSampleRouter(unittest.TestCase):
    """直接调用端点函数，验证 HTTP 层的载荷契约与 404 语义。"""

    def setUp(self) -> None:
        from app.routers import page_sample as router

        self.router = router
        self.service = fresh_service()

    def test_full_http_flow(self):
        from fastapi import HTTPException

        versions = self.router.get_versions()
        self.assertEqual(versions["active_version"], "v1")

        search_payload = self.router.create_search(
            self.router.SearchPayload(keyword="商品A"))
        search_id = search_payload["search"]["id"]
        self.assertTrue(search_payload["ok"])

        self.router.activate_version(self.router.ActivatePayload(version="v2"))

        trial_payload = self.router.create_trial(
            self.router.TrialPayload(
                search_id=search_id, product_id="A", field="price"))
        trial = trial_payload["trial"]
        self.assertEqual(trial["new_sample"]["field_value"], 6)
        self.assertIn("采用页面 v2", trial_payload["message"])

        mapping_payload = self.router.create_mapping_trial(
            self.router.MappingTrialPayload(
                run_id=trial["id"], target_field="standard_price", transform="money"))
        diff_id = mapping_payload["mapping"]["mapper_diff_id"]
        self.assertEqual(mapping_payload["mapping"]["mapped_value"], 6.0)

        review_payload = self.router.review_mapping_diff(diff_id)
        self.assertTrue(review_payload["ok"])
        self.assertEqual(self.router.get_mapping_diff(diff_id)["status"], "已核对")

    def test_unknown_product_returns_404(self):
        from fastapi import HTTPException

        search = self.router.create_search(
            self.router.SearchPayload(keyword="商品A"))["search"]
        with self.assertRaises(HTTPException) as ctx:
            self.router.create_trial(
                self.router.TrialPayload(
                    search_id=search["id"], product_id="C", field="price"))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
