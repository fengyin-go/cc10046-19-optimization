/** 页面字段试跑相关类型，与后端 app/services/page_sample.py 的载荷保持一致。 */

export type FieldSample = {
  page_version: string
  product_id: string
  product_name: string
  segment_index: number
  is_ad: boolean
  field: string
  field_value: string | number | null
  locator: string
}

export type CandidateSegment = {
  product_id: string
  product_name: string
  segment_index: number
  is_ad: boolean
  field_samples: FieldSample[]
}

export type PageSegment = {
  segment_index: number
  product_id: string
  product_name: string
  is_ad: boolean
  fields: Record<string, string | number>
}

export type PageVersion = {
  id: number
  page_key: string
  version: string
  title: string
  active: boolean
  remark: string
  segments: PageSegment[]
}

export type SearchRecord = {
  id: number
  keyword: string
  page_version: string
  page_title: string
  searched_at: string
  candidate_count: number
  candidates: CandidateSegment[]
}

export type FieldTrial = {
  id: number
  search_id: number
  product_id: string
  product_name: string
  field: string
  requested_from_version: string
  used_page_version: string
  used_page_title: string
  old_sample: FieldSample
  new_sample: FieldSample
  version_changed: boolean
  segment_shifted: boolean
  value_changed: boolean
  has_diff: boolean
  scanned_product_count: number
  scanned_field_count: number
  ran_at: string
  message: string
  diff_id: number | null
}

export type SampleDiff = {
  id: number
  trial_id: number
  search_id: number
  product_id: string
  product_name: string
  field: string
  old_page_version: string
  old_segment_index: number
  old_value: string | number | null
  new_page_version: string
  new_segment_index: number
  new_value: string | number | null
  version_changed: boolean
  segment_shifted: boolean
  value_changed: boolean
  status: string
  created_at: string
  reviewed_at?: string
}

export type MappingTrial = {
  run_id: number
  product_id: string
  product_name: string
  source_field: string
  target_field: string
  source_basis: string
  source_basis_label: string
  used_page_version: string
  used_segment_index: number
  old_sample: FieldSample
  new_sample: FieldSample
  raw_value: string | number | null
  transform: string
  mapped_value: string | number
  mapper_diff_id: number | null
  ran_at: string
}

export type MappingDiff = SampleDiff & {
  run_id: number
  target_field: string
  source_basis: string
  source_page_version: string
  source_segment_index: number
  old_sample_value: string | number | null
  actual_value: string | number | null
  mapped_value: string | number
  transform: string
}
