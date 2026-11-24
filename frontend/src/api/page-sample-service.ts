/** 页面字段试跑接口封装：页面版本、搜索、单字段复跑、差异与映射试跑。 */
import { request } from './client'
import type {
  FieldTrial,
  MappingDiff,
  MappingTrial,
  PageVersion,
  SampleDiff,
  SearchRecord,
} from '@/data/page-sample-types'

const BASE = '/api/page-sample'

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    let detail = fallback
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* 保留兜底文案 */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function fetchVersions(): Promise<{ items: PageVersion[]; active_version: string }> {
  return readJson(await request(`${BASE}/versions`), '页面版本读取失败')
}

export async function activateVersion(version: string): Promise<{ ok: boolean; message: string }> {
  const response = await request(`${BASE}/versions/activate`, {
    method: 'POST',
    body: JSON.stringify({ version }),
  })
  return readJson(response, '页面版本切换失败')
}

export async function createSearch(keyword: string, pageVersion?: string): Promise<{
  ok: boolean
  message: string
  search: SearchRecord
}> {
  const response = await request(`${BASE}/searches`, {
    method: 'POST',
    body: JSON.stringify({ keyword, page_version: pageVersion ?? null }),
  })
  return readJson(response, '商品搜索失败')
}

export async function fetchSearches(): Promise<{ items: SearchRecord[] }> {
  return readJson(await request(`${BASE}/searches`), '搜索记录读取失败')
}

export async function createTrial(input: {
  search_id: number
  product_id: string
  field: string
  target_version?: string | null
}): Promise<{ ok: boolean; message: string; trial: FieldTrial }> {
  const response = await request(`${BASE}/trials`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return readJson(response, '单字段复跑失败')
}

export async function fetchTrials(searchId?: number): Promise<{ items: FieldTrial[] }> {
  const query = searchId ? `?search_id=${searchId}` : ''
  return readJson(await request(`${BASE}/trials${query}`), '试跑记录读取失败')
}

export async function fetchDiffs(): Promise<{ items: SampleDiff[] }> {
  return readJson(await request(`${BASE}/diffs`), '试跑差异读取失败')
}

export async function reviewDiff(diffId: number): Promise<{ ok: boolean; message: string }> {
  const response = await request(`${BASE}/diffs/${diffId}/review`, { method: 'POST' })
  return readJson(response, '差异核对失败')
}

export async function createMappingTrial(input: {
  run_id: number
  target_field: string
  transform?: string
  default?: string | number
}): Promise<{ ok: boolean; message: string; mapping: MappingTrial }> {
  const response = await request(`${BASE}/mapping-trials`, {
    method: 'POST',
    body: JSON.stringify({ transform: '', default: '', ...input }),
  })
  return readJson(response, '映射试跑失败')
}

export async function fetchMappingDiffs(): Promise<{ items: MappingDiff[] }> {
  return readJson(await request(`${BASE}/mapping-diffs`), '映射差异读取失败')
}

export async function reviewMappingDiff(diffId: number): Promise<{ ok: boolean; message: string }> {
  const response = await request(`${BASE}/mapping-diffs/${diffId}/review`, { method: 'POST' })
  return readJson(response, '映射差异核对失败')
}
