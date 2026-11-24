<template>
  <section class="page page-sample" data-testid="page-sample">
    <header class="page-head">
      <div>
        <h2>页面字段试跑</h2>
        <p class="page-desc">
          搜索生成字段样本定位数据，从候选片段直接发起单字段复跑；按商品身份核对旧位置与新页面取值，
          字段映射消费同一份定位数据，页面改版后历史样本照常可查。
        </p>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text" data-testid="error-text">{{ errorMessage }}</p>
    <p v-if="infoMessage" class="info-text" data-testid="info-text">{{ infoMessage }}</p>

    <!-- 1. 页面结构版本 -->
    <article class="panel" data-testid="version-panel">
      <h3>页面结构版本（每次按实际页面版本保存位置）</h3>
      <div class="version-grid">
        <div
          v-for="page in versions"
          :key="page.version"
          class="version-card"
          :class="{ active: page.active }"
          :data-testid="`version-card-${page.version}`"
        >
          <div class="version-head">
            <strong>{{ page.version }} · {{ page.title }}</strong>
            <span v-if="page.active" class="badge badge-on" data-testid="active-badge">当前生效</span>
          </div>
          <p class="muted">{{ page.remark }}</p>
          <ol class="segment-list">
            <li v-for="seg in page.segments" :key="seg.product_id" :class="{ ad: seg.is_ad }">
              第{{ seg.segment_index }}段：{{ seg.product_name }}
              <span class="muted">（{{ seg.product_id }}{{ seg.is_ad ? '，广告' : '' }}，价 {{ seg.fields.price }}）</span>
            </li>
          </ol>
          <button
            v-if="!page.active"
            class="btn"
            type="button"
            :data-testid="`activate-${page.version}`"
            @click="onActivate(page.version)"
          >
            切换为生效版本
          </button>
        </div>
      </div>
    </article>

    <!-- 2. 商品搜索：生成字段样本定位数据 -->
    <article class="panel" data-testid="search-panel">
      <h3>商品搜索 · 生成字段样本定位数据</h3>
      <form class="filter-bar" @submit.prevent="onSearch">
        <label class="filter-item">
          <span>商品关键词</span>
          <input v-model="keyword" data-testid="search-keyword" placeholder="留空返回全部商品" />
        </label>
        <label class="filter-item">
          <span>页面版本</span>
          <select v-model="searchVersion" data-testid="search-version">
            <option value="">当前生效版本（{{ activeVersion }}）</option>
            <option v-for="page in versions" :key="page.version" :value="page.version">{{ page.version }}</option>
          </select>
        </label>
        <button class="btn primary" type="submit" data-testid="search-submit" :disabled="loading">
          {{ loading ? '搜索中…' : '搜索并生成样本' }}
        </button>
      </form>
    </article>

    <!-- 3. 历史搜索记录与候选片段 -->
    <article class="panel" data-testid="search-records">
      <h3>搜索记录与候选片段（历史样本照常可查）</h3>
      <p v-if="!searches.length" class="muted">暂无搜索记录，先发起一次商品搜索。</p>
      <div v-for="record in searches" :key="record.id" class="record-card" :data-testid="`search-record-${record.id}`">
        <div class="record-head" @click="toggleRecord(record.id)">
          <strong>
            #{{ record.id }} 关键词「{{ record.keyword || '全部' }}」
            <span class="muted">· {{ record.searched_at }}</span>
          </strong>
          <span class="badge" :data-testid="`record-version-${record.id}`">
            固化页面版本 {{ record.page_version }} · {{ record.candidate_count }} 个候选
          </span>
          <span class="link">{{ expanded[record.id] ? '收起' : '展开候选片段' }}</span>
        </div>

        <div v-if="expanded[record.id]" class="candidate-wrap">
          <div
            v-for="candidate in record.candidates"
            :key="candidate.product_id"
            class="candidate-card"
            :data-testid="`candidate-${record.id}-${candidate.product_id}`"
          >
            <div class="candidate-head">
              <strong>{{ candidate.product_name }}</strong>
              <span class="muted">
                {{ candidate.product_id }} · 第{{ candidate.segment_index }}段 ·
                样本基于 {{ record.page_version }}
              </span>
            </div>
            <table class="data-table sample-table">
              <thead>
                <tr>
                  <th>字段</th>
                  <th>样本值</th>
                  <th>字段样本定位数据（locator）</th>
                  <th>单字段复跑</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sample in candidate.field_samples" :key="sample.field">
                  <td>{{ sample.field }}</td>
                  <td data-testid="sample-value">{{ sample.field_value ?? '—' }}</td>
                  <td><code>{{ sample.locator }}</code></td>
                  <td>
                    <button
                      class="link"
                      type="button"
                      :data-testid="`trial-${record.id}-${candidate.product_id}-${sample.field}`"
                      @click="onTrial(record.id, candidate.product_id, sample.field)"
                    >
                      按此位置复跑
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </article>

    <!-- 4. 单字段试跑结果 -->
    <article class="panel" data-testid="trial-panel">
      <h3>单字段复跑结果（只取所选商品和字段，不重算无关商品）</h3>
      <p v-if="!trials.length" class="muted">暂无试跑记录，在候选片段中点击「按此位置复跑」发起。</p>
      <div v-for="trial in trials" :key="trial.id" class="trial-card" :data-testid="`trial-card-${trial.id}`">
        <div class="trial-head">
          <strong>
            #{{ trial.id }} {{ trial.product_name }}（{{ trial.product_id }}）字段 {{ trial.field }}
          </strong>
          <span class="badge">扫描商品 {{ trial.scanned_product_count }} 个 / 字段 {{ trial.scanned_field_count }} 个</span>
          <span :class="trial.has_diff ? 'badge badge-diff' : 'badge badge-ok'" data-testid="trial-flag">
            {{ trial.has_diff ? '存在差异' : '与旧样本一致' }}
          </span>
        </div>
        <p class="trial-message" data-testid="trial-message">{{ trial.message }}</p>
        <table class="data-table compare-table">
          <thead>
            <tr>
              <th>来源</th>
              <th>页面版本</th>
              <th>片段位置</th>
              <th>读出值</th>
              <th>定位指纹</th>
            </tr>
          </thead>
          <tbody>
            <tr data-testid="old-row">
              <td>旧样本（搜索记录 #{{ trial.search_id }}）</td>
              <td>{{ trial.old_sample.page_version }}</td>
              <td>第{{ trial.old_sample.segment_index }}段</td>
              <td>{{ trial.old_sample.field_value ?? '—' }}</td>
              <td><code>{{ trial.old_sample.locator }}</code></td>
            </tr>
            <tr class="new-row" data-testid="new-row">
              <td>本次采用的页面位置</td>
              <td>{{ trial.new_sample.page_version }}</td>
              <td>第{{ trial.new_sample.segment_index }}段</td>
              <td>{{ trial.new_sample.field_value ?? '—' }}</td>
              <td><code>{{ trial.new_sample.locator }}</code></td>
            </tr>
          </tbody>
        </table>

        <form class="mapping-form" @submit.prevent="onMapping(trial.id)">
          <label>
            <span>映射目标字段</span>
            <input v-model="formFor(trial.id).target" data-testid="mapping-target" placeholder="如 standard_price" required />
          </label>
          <label>
            <span>转换函数</span>
            <select v-model="formFor(trial.id).transform" data-testid="mapping-transform">
              <option value="">原样</option>
              <option value="money">金额（money）</option>
              <option value="int">整数（int）</option>
              <option value="upper">大写</option>
              <option value="lower">小写</option>
            </select>
          </label>
          <button class="btn primary" type="submit" :data-testid="`mapping-submit-${trial.id}`">
            发起字段映射试跑
          </button>
        </form>
      </div>
    </article>

    <!-- 5. 字段映射结果与差异 -->
    <article class="panel" data-testid="mapping-panel">
      <h3>字段映射结果（消费字段样本定位数据）</h3>
      <p v-if="!mappingDiffs.length" class="muted">暂无映射差异；存在页面差异的映射试跑会在此沉淀，可重新打开核对。</p>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>商品</th>
            <th>字段映射</th>
            <th>采用来源</th>
            <th>旧样本值</th>
            <th>实际读出</th>
            <th>映射值</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="diff in mappingDiffs" :key="diff.id" :data-testid="`mapping-diff-${diff.id}`">
            <td>{{ diff.id }}</td>
            <td>{{ diff.product_name }}（{{ diff.product_id }}）</td>
            <td>{{ diff.field }} → {{ diff.target_field }}</td>
            <td>
              {{ diff.source_basis === 'new_position' ? '新页面位置' : '旧样本' }}
              <span class="muted">{{ diff.source_page_version }} 第{{ diff.source_segment_index }}段</span>
            </td>
            <td>{{ diff.old_sample_value ?? '—' }}</td>
            <td>{{ diff.actual_value ?? '—' }}</td>
            <td><strong>{{ diff.mapped_value }}</strong></td>
            <td :data-testid="`mapping-diff-status-${diff.id}`">{{ diff.status }}</td>
            <td>
              <button class="link" type="button" :data-testid="`mapping-diff-open-${diff.id}`" @click="openMappingDiff(diff.id)">
                重新打开
              </button>
              <button
                v-if="diff.status !== '已核对'"
                class="link"
                type="button"
                :data-testid="`mapping-diff-review-${diff.id}`"
                @click="onReviewMapping(diff.id)"
              >
                核对
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </article>

    <!-- 6. 试跑差异核对 -->
    <article class="panel" data-testid="diff-panel">
      <h3>试跑差异核对</h3>
      <p v-if="!diffs.length" class="muted">暂无位置或取值差异。</p>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>商品/字段</th>
            <th>旧位置 → 新位置</th>
            <th>旧值 → 新值</th>
            <th>差异类型</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="diff in diffs" :key="diff.id" :data-testid="`diff-${diff.id}`">
            <td>{{ diff.id }}</td>
            <td>{{ diff.product_name }} · {{ diff.field }}</td>
            <td>
              {{ diff.old_page_version }} 第{{ diff.old_segment_index }}段
              → {{ diff.new_page_version }} 第{{ diff.new_segment_index }}段
            </td>
            <td>{{ diff.old_value ?? '—' }} → <strong>{{ diff.new_value ?? '—' }}</strong></td>
            <td>
              <span v-if="diff.segment_shifted">片段位移 </span>
              <span v-if="diff.value_changed">取值变化</span>
            </td>
            <td :data-testid="`diff-status-${diff.id}`">{{ diff.status }}</td>
            <td>
              <button class="link" type="button" :data-testid="`diff-open-${diff.id}`" @click="openDiff(diff.id)">
                重新打开
              </button>
              <button
                v-if="diff.status !== '已核对'"
                class="link"
                type="button"
                :data-testid="`diff-review-${diff.id}`"
                @click="onReviewDiff(diff.id)"
              >
                核对
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </article>

    <!-- 差异详情弹层：值班员重新打开核对 -->
    <div v-if="openedDiff" class="modal-backdrop" data-testid="diff-modal" @click.self="openedDiff = null">
      <div class="modal">
        <h3>试跑差异详情 #{{ openedDiff.id }}</h3>
        <dl class="detail-list">
          <dt>商品 / 字段</dt><dd>{{ openedDiff.product_name }}（{{ openedDiff.product_id }}）· {{ openedDiff.field }}</dd>
          <dt>旧样本位置</dt><dd>{{ openedDiff.old_page_version }} 第{{ openedDiff.old_segment_index }}段，值 {{ openedDiff.old_value ?? '—' }}</dd>
          <dt>新页面位置</dt><dd>{{ openedDiff.new_page_version }} 第{{ openedDiff.new_segment_index }}段，值 {{ openedDiff.new_value ?? '—' }}</dd>
          <dt>差异类型</dt>
          <dd>
            <span v-if="openedDiff.version_changed">页面版本变更 </span>
            <span v-if="openedDiff.segment_shifted">片段位移 </span>
            <span v-if="openedDiff.value_changed">取值变化</span>
          </dd>
          <dt>核对状态</dt><dd>{{ openedDiff.status }}</dd>
        </dl>
        <div class="page-actions">
          <button class="btn" type="button" @click="openedDiff = null">关闭</button>
          <button
            v-if="openedDiff.status !== '已核对'"
            class="btn primary"
            type="button"
            data-testid="modal-review"
            @click="onReviewDiff(openedDiff.id)"
          >
            标记已核对
          </button>
        </div>
      </div>
    </div>

    <div v-if="openedMappingDiff" class="modal-backdrop" data-testid="mapping-modal" @click.self="openedMappingDiff = null">
      <div class="modal">
        <h3>字段映射差异详情 #{{ openedMappingDiff.id }}</h3>
        <dl class="detail-list">
          <dt>映射关系</dt><dd>{{ openedMappingDiff.field }} → {{ openedMappingDiff.target_field }}（{{ openedMappingDiff.transform || '原样' }}）</dd>
          <dt>本次采用</dt>
          <dd>
            {{ openedMappingDiff.source_basis === 'new_position' ? '新页面位置实际读出值' : '旧样本值' }}
            （{{ openedMappingDiff.source_page_version }} 第{{ openedMappingDiff.source_segment_index }}段）
          </dd>
          <dt>旧样本值 / 实际读出</dt><dd>{{ openedMappingDiff.old_sample_value ?? '—' }} / {{ openedMappingDiff.actual_value ?? '—' }}</dd>
          <dt>映射值</dt><dd><strong>{{ openedMappingDiff.mapped_value }}</strong></dd>
          <dt>核对状态</dt><dd>{{ openedMappingDiff.status }}</dd>
        </dl>
        <div class="page-actions">
          <button class="btn" type="button" @click="openedMappingDiff = null">关闭</button>
          <button
            v-if="openedMappingDiff.status !== '已核对'"
            class="btn primary"
            type="button"
            data-testid="modal-mapping-review"
            @click="onReviewMapping(openedMappingDiff.id)"
          >
            标记已核对
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  activateVersion,
  createMappingTrial,
  createSearch,
  createTrial,
  fetchDiffs,
  fetchMappingDiffs,
  fetchSearches,
  fetchTrials,
  fetchVersions,
  reviewDiff,
  reviewMappingDiff,
} from '@/api/page-sample-service'
import type {
  FieldTrial,
  MappingDiff,
  PageVersion,
  SampleDiff,
  SearchRecord,
} from '@/data/page-sample-types'

const versions = ref<PageVersion[]>([])
const activeVersion = ref('')
const keyword = ref('商品A')
const searchVersion = ref('')
const searches = ref<SearchRecord[]>([])
const trials = ref<FieldTrial[]>([])
const diffs = ref<SampleDiff[]>([])
const mappingDiffs = ref<MappingDiff[]>([])
const expanded = reactive<Record<number, boolean>>({})
const mappingForms = reactive<Record<number, { target: string; transform: string }>>({})
const openedDiff = ref<SampleDiff | null>(null)
const openedMappingDiff = ref<MappingDiff | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const infoMessage = ref('')

function flash(message: string, isError = false) {
  if (isError) {
    errorMessage.value = message
    infoMessage.value = ''
  } else {
    infoMessage.value = message
    errorMessage.value = ''
  }
}

async function loadAll() {
  try {
    const [versionPayload, searchPayload, trialPayload, diffPayload, mappingPayload] = await Promise.all([
      fetchVersions(),
      fetchSearches(),
      fetchTrials(),
      fetchDiffs(),
      fetchMappingDiffs(),
    ])
    versions.value = versionPayload.items
    activeVersion.value = versionPayload.active_version
    searches.value = [...searchPayload.items].reverse()
    trials.value = [...trialPayload.items].reverse()
    diffs.value = [...diffPayload.items].reverse()
    mappingDiffs.value = [...mappingPayload.items].reverse()
  } catch (error) {
    flash(error instanceof Error ? error.message : '页面试跑数据加载失败', true)
  }
}

async function onActivate(version: string) {
  try {
    const result = await activateVersion(version)
    flash(result.message)
    await loadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '版本切换失败', true)
  }
}

async function onSearch() {
  loading.value = true
  try {
    const result = await createSearch(keyword.value.trim(), searchVersion.value || undefined)
    expanded[result.search.id] = true
    flash(result.message)
    await loadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '搜索失败', true)
  } finally {
    loading.value = false
  }
}

function toggleRecord(id: number) {
  expanded[id] = !expanded[id]
}

function formFor(runId: number): { target: string; transform: string } {
  if (!mappingForms[runId]) {
    mappingForms[runId] = { target: 'standard_price', transform: 'money' }
  }
  return mappingForms[runId]
}

async function onTrial(searchId: number, productId: string, field: string) {
  try {
    const result = await createTrial({ search_id: searchId, product_id: productId, field })
    flash(result.message)
    await loadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '复跑失败', true)
  }
}

async function onMapping(runId: number) {
  const form = formFor(runId)
  if (!form.target) {
    flash('请填写映射目标字段', true)
    return
  }
  try {
    const result = await createMappingTrial({
      run_id: runId,
      target_field: form.target,
      transform: form.transform,
    })
    flash(result.message)
    await loadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '映射试跑失败', true)
  }
}

async function onReviewDiff(id: number) {
  try {
    const result = await reviewDiff(id)
    flash(result.message)
    await loadAll()
    if (openedDiff.value?.id === id) {
      openedDiff.value = diffs.value.find((item) => item.id === id) ?? null
    }
  } catch (error) {
    flash(error instanceof Error ? error.message : '核对失败', true)
  }
}

async function onReviewMapping(id: number) {
  try {
    const result = await reviewMappingDiff(id)
    flash(result.message)
    await loadAll()
    if (openedMappingDiff.value?.id === id) {
      openedMappingDiff.value = mappingDiffs.value.find((item) => item.id === id) ?? null
    }
  } catch (error) {
    flash(error instanceof Error ? error.message : '核对失败', true)
  }
}

function openDiff(id: number) {
  openedDiff.value = diffs.value.find((item) => item.id === id) ?? null
}

function openMappingDiff(id: number) {
  openedMappingDiff.value = mappingDiffs.value.find((item) => item.id === id) ?? null
}

onMounted(loadAll)
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.panel h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
.info-text {
  color: #166534;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
}
.version-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}
.version-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  background: #fafbfc;
}
.version-card.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand) inset;
}
.version-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.segment-list {
  margin: 8px 0;
  padding-left: 20px;
  font-size: 13px;
}
.segment-list li.ad {
  color: #b45309;
}
.badge {
  display: inline-block;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  background: #f8fafc;
  white-space: nowrap;
}
.badge-on {
  background: #dcfce7;
  border-color: #86efac;
  color: #166534;
}
.badge-diff {
  background: #fef2f2;
  border-color: #fecaca;
  color: #b42318;
}
.badge-ok {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}
.record-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}
.record-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  cursor: pointer;
  background: #f8fafc;
}
.candidate-wrap {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.candidate-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 6px;
}
.sample-table code,
.compare-table code {
  font-size: 12px;
  color: #334155;
}
.trial-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: #fafbfc;
}
.trial-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.trial-message {
  margin: 8px 0;
  font-size: 13px;
  color: #1e3a8a;
}
.new-row {
  background: #eff6ff;
}
.mapping-form {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  margin-top: 10px;
  flex-wrap: wrap;
}
.mapping-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.mapping-form input,
.mapping-form select,
.filter-item select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  min-width: 160px;
}
.detail-list {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 8px 12px;
  margin: 0 0 16px;
  font-size: 13px;
}
.detail-list dt {
  color: var(--muted);
}
.detail-list dd {
  margin: 0;
}
</style>
