<template>
  <div class="page-dock cap-tree-page">
    <aside class="pane-tree pane-tree--wide cap-tree-side">
      <button
        type="button"
        class="tree-item"
        :class="{ 'is-on': treeLayoutMode === 'hierarchical' }"
        @click="treeLayoutMode = 'hierarchical'"
      >
        层次
      </button>
      <button
        type="button"
        class="tree-item"
        :class="{ 'is-on': treeLayoutMode === 'radial' }"
        @click="treeLayoutMode = 'radial'"
      >
        径向
      </button>
      <div class="pane-h">
        <el-button type="primary" :loading="loading" @click="loadAndRender">刷新</el-button>
        <el-button title="回到可读比例。整棵树在右下角缩略图里。" @click="showOverview">全貌</el-button>
        <el-button :loading="exportingImage" @click="exportTreeImage">导出</el-button>
      </div>
      <div class="tree-group">筛选</div>
      <div class="cap-tree-fields">
        <label class="field">
          <span>生态</span>
          <el-select
            v-model="selectedSources"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="生态来源"
          >
            <el-option
              v-for="item in deviceSourceOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
        <div class="field">
          <span>视图</span>
          <div class="seg">
            <button type="button" :class="{ 'is-on': mergeViewMode }" @click="mergeViewMode = true">合并</button>
            <button type="button" :class="{ 'is-on': !mergeViewMode }" @click="mergeViewMode = false">分生态</button>
          </div>
        </div>
        <el-dropdown v-if="mergeViewMode" trigger="click" class="source-legend-dropdown">
          <el-button size="small">
            生态图例
            <span class="source-legend-dropdown__caret">▾</span>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu class="source-legend-menu">
              <el-dropdown-item
                v-for="item in deviceSourceOptions"
                :key="item.value"
                disabled
                class="source-legend-menu__item"
              >
                <i
                  class="source-legend-menu__swatch"
                  :style="{ background: deviceSourceNodeColor(item.value) }"
                />
                <span class="source-legend-menu__label">{{ item.shortLabel }}</span>
                <span class="source-legend-menu__sub">{{ item.label }}</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <label class="field">
          <span>环境表单</span>
          <el-select
            v-model="treeFormChoice"
            filterable
            placeholder="环境表单"
            @change="onFormSelect"
          >
            <el-option v-for="f in homeForms" :key="f.form_id" :label="f.name" :value="f.form_id" />
          </el-select>
        </label>
        <div class="field">
          <span>抽象层</span>
          <div class="seg">
            <button type="button" :class="{ 'is-on': hideAbstractLayer }" @click="hideAbstractLayer = true">隐藏</button>
            <button type="button" :class="{ 'is-on': !hideAbstractLayer }" @click="hideAbstractLayer = false">显示</button>
          </div>
        </div>
        <label class="field">
          <span>一级能力</span>
          <el-select
            v-model="selectedDomainId"
            clearable
            filterable
            placeholder="一级能力"
          >
            <el-option v-for="item in domainOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </label>
        <label class="field">
          <span>二级能力</span>
          <el-select
            v-model="selectedObjectId"
            clearable
            filterable
            placeholder="二级能力"
          >
            <el-option v-for="item in objectOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </label>
        <label class="field">
          <span>三级能力</span>
          <el-select
            v-model="selectedEffectId"
            clearable
            filterable
            placeholder="三级能力"
          >
            <el-option v-for="item in effectOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </label>
        <label class="field">
          <span>抽象设备</span>
          <el-select
            v-model="selectedAbstractType"
            clearable
            filterable
            placeholder="抽象设备"
          >
            <el-option v-for="item in abstractTypeOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </label>
        <label class="field">
          <span>环境属性</span>
          <el-select
            v-model="selectedEnvFilters"
            multiple
            :collapse-tags="shouldCollapseEnvTags"
            collapse-tags-tooltip
            filterable
            placeholder="环境属性"
            class="tree-env-filter-select"
          >
            <el-option v-for="env in envAttributes" :key="env.env_id" :label="env.env_name" :value="env.env_id" />
          </el-select>
        </label>
        <div class="field">
          <span>环境匹配</span>
          <div class="seg">
            <button type="button" :class="{ 'is-on': envFilterMode === 'union' }" @click="envFilterMode = 'union'">并集</button>
            <button type="button" :class="{ 'is-on': envFilterMode === 'intersection' }" @click="envFilterMode = 'intersection'">交集</button>
          </div>
        </div>
        <el-button @click="clearEnvFilters">清空筛选</el-button>
      </div>
    </aside>
    <section class="pane-inspect cap-tree-canvas">
    <div v-if="emptyHint" class="empty-wrap">
      <el-empty :description="emptyHint" />
    </div>
    <div v-else class="tree-layout">
      <div class="tree-main">
        <div ref="containerRef" class="g6-container" />
      </div>
      <aside ref="apiPanelRef" class="api-panel" :class="{ 'api-panel--open': !!selectedConcrete }">
        <div v-if="selectedConcrete" class="api-panel__inner">
          <div class="api-panel__head">
            <h2 class="api-panel__title">API 指令集</h2>
            <p class="api-panel__sub">{{ selectedConcrete.label }}</p>
            <p class="api-panel__meta">效果 ID：{{ selectedConcrete.e_id }}</p>
            <p v-if="selectedPathDetail && !showAllPayloadsForSelected" class="api-panel__path">
              路径：{{ selectedPathDetail.sourceName }} &gt;
              <el-tooltip
                :content="selectedPathDetail.domainDesc"
                placement="top"
                :show-after="180"
                popper-class="cap-tooltip-wrap"
              >
                <span class="api-panel__path-node">{{ selectedPathDetail.domainName }}</span>
              </el-tooltip>
              &gt;
              <el-tooltip
                :content="selectedPathDetail.objectDesc"
                placement="top"
                :show-after="180"
                popper-class="cap-tooltip-wrap"
              >
                <span class="api-panel__path-node">{{ selectedPathDetail.objectName }}</span>
              </el-tooltip>
              <template v-if="selectedPathDetail.effectName">
                &gt;
                <el-tooltip
                  :content="selectedPathDetail.effectDesc"
                  placement="top"
                  :show-after="180"
                  popper-class="cap-tooltip-wrap"
                >
                  <span class="api-panel__path-node">{{ selectedPathDetail.effectName }}</span>
                </el-tooltip>
              </template>
              <template v-if="!hideAbstractLayer">
                &gt; {{ selectedPathDetail.abstractName }}
              </template>
              &gt; {{ selectedPathDetail.concreteName }}
            </p>
            <p class="api-panel__meta">
              当前模式：{{ showAllPayloadsForSelected ? '该设备全部指令集（不受三级能力约束）' : '当前三级能力指令集' }}
            </p>
            <div class="api-panel__controls">
              <el-button
                size="small"
                :type="showAllPayloadsForSelected ? 'danger' : 'default'"
                @click="toggleShowAllPayloads"
              >
                {{ showAllPayloadsForSelected ? '已显示全部指令集' : '显示该设备全部指令集' }}
              </el-button>
            </div>
          </div>
          <div v-loading="panelLoading" class="api-panel__body">
            <template v-if="!panelLoading && filteredPayloads.length === 0">
              <el-empty description="未找到匹配的指令载荷" />
            </template>
            <template v-else-if="filteredPayloads.length > 0">
              <div class="api-cards">
                <article
                  v-for="p in filteredPayloads"
                  :key="p.uid"
                  class="api-card"
                  :class="{
                    'api-card--parameter': isParameterPayload(p),
                    'api-card--strategy': isStrategyPayload(p),
                  }"
                >
                  <header class="api-card__head">
                    <div class="api-card__title">
                      <template v-if="isParameterPayload(p)">
                        能力名：<span class="api-card__param">参数能力</span>
                      </template>
                      <template v-else-if="isStrategyPayload(p)">
                        能力名：<span class="api-card__strategy">场景策略</span>
                      </template>
                      <template v-else-if="p.e_id != null">
                        能力名：
                        <el-tooltip
                          :content="payloadEffectDesc(p.e_id)"
                          placement="top"
                          :show-after="180"
                          popper-class="cap-tooltip-wrap"
                        >
                          <span class="api-card__effect">{{ payloadEffectName(p.e_id) }}</span>
                        </el-tooltip>
                      </template>
                      <template v-else>能力名：<span class="api-card__aux">辅助能力</span></template>
                      <el-tag
                        size="small"
                        class="api-card__kind"
                        :type="payloadKindTagType(p)"
                      >
                        {{ payloadKindLabel(p) }}
                      </el-tag>
                    </div>
                    <div class="api-card__uid">指令 UID：{{ formatPayloadOptionLabel(p) }}</div>
                  </header>
                  <div v-if="p.capability_desc" class="api-card__desc">{{ p.capability_desc }}</div>
                  <div v-if="isParameterPayload(p) || isStrategyPayload(p)" class="api-card__meta">
                    <span class="api-card__meta-key">{{ isStrategyPayload(p) ? '可能有关：' : '可被引用：' }}</span>
                    <span class="api-card__meta-value">
                      {{ formatSupportsEffects(p.supports_e_ids) || '无' }}
                    </span>
                  </div>
                  <div class="api-card__meta">
                    <span class="api-card__meta-key">影响环境属性：</span>
                    <span class="api-card__meta-value">
                      {{ formatEnvImpactNames(p.env_impact).join('、') || '无' }}
                    </span>
                  </div>
                  <div class="api-panel__json-wrap">
                    <div class="api-panel__json-title">api_set</div>
                    <pre
                      class="api-panel__json api-panel__json--copyable"
                      title="单击复制 api_set"
                      @click="copyApiSetToClipboard(p.api_set)"
                    >
                      {{ formatApiSet(p.api_set) }}
                    </pre>
                  </div>
                </article>
              </div>
            </template>
            <section v-if="relatedStrategyPayloads.length" class="doc-sec">
              <h2>可能有关的场景策略（{{ relatedStrategyPayloads.length }}）</h2>
              <div class="api-cards">
                <article
                  v-for="p in relatedStrategyPayloads"
                  :key="`strategy-${p.uid}`"
                  class="api-card api-card--strategy"
                >
                  <header class="api-card__head">
                    <div class="api-card__title">
                      能力名：<span class="api-card__strategy">场景策略</span>
                    </div>
                    <div class="api-card__uid">指令 UID：{{ formatPayloadOptionLabel(p) }}</div>
                  </header>
                  <div v-if="p.capability_desc" class="api-card__desc">{{ p.capability_desc }}</div>
                  <div class="api-card__meta">
                    <span class="api-card__meta-key">可能有关：</span>
                    <span class="api-card__meta-value">{{ formatSupportsEffects(p.supports_e_ids) || '无' }}</span>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </div>
      </aside>
    </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { Graph, NodeEvent, treeToGraphData } from '@antv/g6'
import type { TreeData } from '@antv/g6'

import request from '../api/request'
import { ElMessage } from 'element-plus'
import {
  DEVICE_SOURCE_OPTIONS,
  defaultSelectedSources,
  deviceSourceBookmarkFill,
  deviceSourceLabel,
  deviceSourceNodeColor,
  deviceSourceTreeNodeId,
  isPartialSourceSelection,
  normalizeDeviceSource,
} from '../constants/deviceSources'
import {
  HOME_FORM_CHANGED_EVENT,
  readCurrentHomeFormId,
  writeCurrentHomeFormId,
} from '../constants/homeForm'

interface DomainRow {
  d_id: number
  d_name: string
  d_desc?: string | null
}
interface ObjectRow {
  o_id: number
  d_id: number
  o_name: string
  o_desc?: string | null
}
interface EffectRow {
  e_id: number
  o_id: number
  e_name: string
  e_desc?: string | null
}
interface ConcreteRow {
  c_instance_id: string
  catalog_c_instance_id?: string
  c_brand: string
  a_ref?: string | null
  source?: number
  source_label?: string
}
interface PayloadRow {
  uid: string
  c_instance_id: string
  e_id: number
  env_impact?: number[]
}

interface HomeFormRow {
  form_id: string
  name: string
}

interface HomePlacementRow {
  placement_id: string
  catalog_c_instance_id: string
  display_name: string
  c_brand: string
  a_ref?: string | null
  source?: number
  alias: string
}

interface HomeCommandPrefRow {
  placement_id: string
  payload_uid: string
  weight: number
}

interface CommandPayloadItem {
  uid: string
  c_instance_id: string
  e_id: number | null
  api_set: unknown
  env_impact: number[]
  capability_kind?: string
  capability_desc?: string | null
  supports_e_ids?: number[]
}

interface EnvAttributeRow {
  env_id: number
  env_name: string
}

type EnvFilterMode = 'union' | 'intersection'

interface FilterRecord {
  d_id: number
  d_name: string
  o_id: number
  o_name: string
  e_id: number
  e_name: string
  a_ref: string
  c_instance_id: string
  env_impact: number[]
}

interface SelectedConcrete {
  nodeId: string
  c_instance_id: string
  catalog_c_instance_id?: string
  e_id: number
  label: string
}

interface TreeDatum extends TreeData {
  label: string
  kind: 'source' | 'domain' | 'object' | 'effect' | 'abstract' | 'concrete'
  /** 仅 kind === 'concrete' 时存在；表单实例用 placement_id */
  c_instance_id?: string
  catalog_c_instance_id?: string
  e_id?: number
  /** 具体设备生态来源（合并视图着色用） */
  source?: number
  children?: TreeDatum[]
}

function concreteClassLabel(a_ref?: string | null): string {
  const s = String(a_ref || '').trim()
  return s || '待确认类目'
}

const containerRef = ref<HTMLDivElement | null>(null)
const apiPanelRef = ref<HTMLElement | null>(null)


const graphRef = shallowRef<Graph | null>(null)
const loading = ref(false)
const exportingImage = ref(false)
const emptyHint = ref('')

const selectedNodeId = ref<string | null>(null)
const selectedConcrete = ref<SelectedConcrete | null>(null)
const commandPayloads = ref<CommandPayloadItem[]>([])
const showAllPayloadsForSelected = ref(false)
const panelLoading = ref(false)
const effectNameById = ref<Record<number, string>>({})
const effectDescById = ref<Record<number, string>>({})
const envNameById = ref<Record<number, string>>({})
const envAttributes = ref<EnvAttributeRow[]>([])
const selectedDomainId = ref<number | null>(null)
const selectedObjectId = ref<number | null>(null)
const selectedEffectId = ref<number | null>(null)
const selectedAbstractType = ref<string>('')
const selectedEnvFilters = ref<number[]>([])
const selectedSources = ref<number[]>(defaultSelectedSources())
const deviceSourceOptions = DEVICE_SOURCE_OPTIONS
const envFilterMode = ref<EnvFilterMode>('union')
const shouldCollapseEnvTags = ref(false)
/** 默认隐藏抽象设备层：具体设备直接挂到三级效果节点下 */
const hideAbstractLayer = ref(true)
/** 合并视图：不按生态拆枝，具体设备共挂同一能力父节点，叶子按生态着色 */
const mergeViewMode = ref(false)
/** 树布局：层次树（左→右） / 径向树（中心向外圆周展开） */
const treeLayoutMode = ref<'hierarchical' | 'radial'>('hierarchical')
const homeForms = ref<HomeFormRow[]>([])
const currentFormId = ref('')
/** 空字符串表示尚未选择；FORM_UNMATCHED 表示不按环境表单收窄。 */
const FORM_UNMATCHED = '__unmatched__'
const treeFormChoice = ref('')
const formPlacements = ref<HomePlacementRow[]>([])
const commandPrefWeightByKey = ref<Record<string, number>>({})
const catalogConcretes = ref<ConcreteRow[]>([])
const catalogPayloadKeys = ref<PayloadRow[]>([])
const sourceDomains = ref<DomainRow[]>([])
const sourceObjects = ref<ObjectRow[]>([])
const sourceEffects = ref<EffectRow[]>([])
const sourceConcretes = ref<ConcreteRow[]>([])
const sourcePayloadKeys = ref<PayloadRow[]>([])
let detachGraphSelection: (() => void) | undefined
const graphPanelShiftX = ref(0)
let panelShiftTimer: number | undefined
let latestRenderJobId = 0
let highlightedPathNodeIds: string[] = []
let highlightedPathEdgeIds: string[] = []



function commandPrefKey(placementId: string, payloadUid: string): string {
  return `${placementId}::${payloadUid}`
}

function commandParticipates(placementId: string, uid: string): boolean {
  const key = commandPrefKey(placementId, uid)
  if (!(key in commandPrefWeightByKey.value)) return true
  return (commandPrefWeightByKey.value[key] ?? 1) > 0
}

function matchesEnvFilter(targetEnvIds: number[] | undefined, selectedIds: number[], mode: EnvFilterMode): boolean {
  if (selectedIds.length === 0) return true
  const ids = targetEnvIds || []
  return mode === 'intersection'
    ? selectedIds.every((id) => ids.includes(id))
    : selectedIds.some((id) => ids.includes(id))
}

const filterRecords = computed<FilterRecord[]>(() => {
  const domainById = new Map(sourceDomains.value.map((x) => [x.d_id, x]))
  const objectById = new Map(sourceObjects.value.map((x) => [x.o_id, x]))
  const effectById = new Map(sourceEffects.value.map((x) => [x.e_id, x]))
  const concreteById = new Map(sourceConcretes.value.map((x) => [x.c_instance_id, x]))

  const out: FilterRecord[] = []
  for (const p of sourcePayloadKeys.value) {
    const effect = effectById.get(p.e_id)
    if (!effect) continue
    const obj = objectById.get(effect.o_id)
    if (!obj) continue
    const dom = domainById.get(obj.d_id)
    if (!dom) continue
    const concrete = concreteById.get(p.c_instance_id)
    if (!concrete) continue
    if (!matchesSourceFilter(concrete.source)) continue

    out.push({
      d_id: dom.d_id,
      d_name: dom.d_name,
      o_id: obj.o_id,
      o_name: obj.o_name,
      e_id: effect.e_id,
      e_name: effect.e_name,
      a_ref: concreteClassLabel(concrete.a_ref),
      c_instance_id: p.c_instance_id,
      env_impact: p.env_impact || [],
    })
  }
  return out
})

function recordMatchesSelection(
  rec: FilterRecord,
  exclude: 'domain' | 'object' | 'effect' | 'abstract' | null = null,
): boolean {
  if (exclude !== 'domain' && selectedDomainId.value != null && rec.d_id !== selectedDomainId.value) return false
  if (exclude !== 'object' && selectedObjectId.value != null && rec.o_id !== selectedObjectId.value) return false
  if (exclude !== 'effect' && selectedEffectId.value != null && rec.e_id !== selectedEffectId.value) return false
  if (exclude !== 'abstract' && selectedAbstractType.value && rec.a_ref !== selectedAbstractType.value) return false
  if (!matchesEnvFilter(rec.env_impact, selectedEnvFilters.value, envFilterMode.value)) return false
  return true
}

const domainOptions = computed(() =>
  Array.from(
    new Map(
      filterRecords.value
        .filter((r) => recordMatchesSelection(r, 'domain'))
        .map((r) => [r.d_id, { value: r.d_id, label: `${r.d_name} (ID: ${r.d_id})` }]),
    ).values(),
  ).sort((a, b) => a.label.localeCompare(b.label)),
)

const objectOptions = computed(() =>
  Array.from(
    new Map(
      filterRecords.value
        .filter((r) => recordMatchesSelection(r, 'object'))
        .map((r) => [r.o_id, { value: r.o_id, label: `${r.o_name} (ID: ${r.o_id})` }]),
    ).values(),
  ).sort((a, b) => a.label.localeCompare(b.label)),
)

const effectOptions = computed(() =>
  Array.from(
    new Map(
      filterRecords.value
        .filter((r) => recordMatchesSelection(r, 'effect'))
        .map((r) => [r.e_id, { value: r.e_id, label: `${r.e_name} (ID: ${r.e_id})` }]),
    ).values(),
  ).sort((a, b) => a.label.localeCompare(b.label)),
)

const abstractTypeOptions = computed(() =>
  Array.from(
    new Set(
      filterRecords.value
        .filter((r) => recordMatchesSelection(r, 'abstract'))
        .map((r) => r.a_ref)
    ),
  ).sort((a, b) => a.localeCompare(b)),
)

const filteredPayloads = computed(() => {
  const sc = selectedConcrete.value
  if (!sc) return []
  return commandPayloads.value.filter((p) => {
    if (!matchesEnvFilter(p.env_impact, selectedEnvFilters.value, envFilterMode.value)) return false
    if (!commandParticipates(sc.c_instance_id, p.uid)) return false
    if (showAllPayloadsForSelected.value) return true
    if (payloadKind(p) === 'strategy') return false
    if (p.e_id === sc.e_id) return true
    return isParameterPayload(p) && (p.supports_e_ids || []).includes(sc.e_id)
  })
})

const relatedStrategyPayloads = computed(() => {
  const sc = selectedConcrete.value
  if (!sc || showAllPayloadsForSelected.value) return []
  return commandPayloads.value.filter((p) => {
    if (payloadKind(p) !== 'strategy') return false
    if (!matchesEnvFilter(p.env_impact, selectedEnvFilters.value, envFilterMode.value)) return false
    if (!commandParticipates(sc.c_instance_id, p.uid)) return false
    return (p.supports_e_ids || []).includes(sc.e_id)
  })
})

const selectedPathDetail = computed(() => {
  const sc = selectedConcrete.value
  if (!sc) return null
  const effect = sourceEffects.value.find((x) => x.e_id === sc.e_id)
  const obj = effect ? sourceObjects.value.find((x) => x.o_id === effect.o_id) : null
  const dom = obj ? sourceDomains.value.find((x) => x.d_id === obj.d_id) : null
  const concrete = sourceConcretes.value.find((x) => x.c_instance_id === sc.c_instance_id)
  return {
    sourceName: deviceSourceLabel(concrete?.source, concrete?.source_label),
    domainName: dom?.d_name ?? '未知一级能力',
    domainDesc: (dom?.d_desc || '').trim() || '该一级能力暂无概念说明',
    objectName: obj?.o_name ?? '未知二级能力',
    objectDesc: (obj?.o_desc || '').trim() || '该二级能力暂无概念说明',
    effectName: (effect?.e_name || '').trim(),
    effectDesc: (effect?.e_desc || '').trim() || '该三级能力暂无概念说明',
    abstractName: concreteClassLabel(concrete?.a_ref),
    concreteName: sc.label,
  }
})

function formatPayloadOptionLabel(p: CommandPayloadItem): string {
  return p.uid
}

function payloadKind(p: CommandPayloadItem): 'effect' | 'auxiliary' | 'parameter' | 'strategy' {
  if (p.capability_kind === 'parameter') return 'parameter'
  if (p.capability_kind === 'auxiliary') return 'auxiliary'
  if (p.capability_kind === 'strategy') return 'strategy'
  if (p.capability_kind === 'effect') return 'effect'
  return p.e_id == null ? 'auxiliary' : 'effect'
}



function isParameterPayload(p: CommandPayloadItem): boolean {
  return payloadKind(p) === 'parameter'
}

function isStrategyPayload(p: CommandPayloadItem): boolean {
  return payloadKind(p) === 'strategy'
}

function payloadKindLabel(p: CommandPayloadItem): string {
  const kind = payloadKind(p)
  if (kind === 'auxiliary') return '辅助能力'
  if (kind === 'parameter') return '参数能力'
  if (kind === 'strategy') return '场景策略'
  return '效果能力'
}

function payloadKindTagType(p: CommandPayloadItem): 'info' | 'warning' | 'primary' | 'success' {
  const kind = payloadKind(p)
  if (kind === 'auxiliary') return 'info'
  if (kind === 'parameter') return 'warning'
  if (kind === 'strategy') return 'success'
  return 'primary'
}

function formatSupportsEffects(ids?: number[]): string {
  const arr = ids || []
  if (arr.length === 0) return ''
  return arr.map((id) => payloadEffectName(id)).join('、')
}

function payloadEffectName(eId: number | null): string {
  if (eId == null) return '辅助能力'
  return effectNameById.value[eId] ?? `效果 ${eId}`
}

function payloadEffectDesc(eId: number | null): string {
  if (eId == null) return '该指令未关联三级能力'
  const desc = effectDescById.value[eId]
  return desc && desc.trim() ? desc : '该三级能力暂无概念说明'
}

function formatEnvImpactNames(envIds: number[]): string[] {
  return (envIds || []).map((id) => envNameById.value[id] ?? `环境属性#${id}`)
}

function formatApiSet(apiSet: unknown): string {
  try {
    return JSON.stringify(apiSet, null, 2)
  } catch {
    return String(apiSet)
  }
}

async function copyApiSetToClipboard(apiSet: unknown): Promise<void> {
  const text = formatApiSet(apiSet)
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('api_set 已复制到剪贴板')
  } catch (e) {
    console.error(e)
    ElMessage.error('复制失败，请手动复制')
  }
}

function clearSelectionUi(): void {
  selectedNodeId.value = null
  selectedConcrete.value = null
  commandPayloads.value = []
  showAllPayloadsForSelected.value = false
  highlightedPathNodeIds = []
  highlightedPathEdgeIds = []
}

async function applySelectedNodeVisualState(): Promise<void> {
  const g = graphRef.value
  const id = selectedNodeId.value
  if (!g || !id) return
  await g.setElementState(id, showAllPayloadsForSelected.value ? ['selected', 'all-payloads'] : ['selected'])
  await updatePathHighlight(g)
}

async function toggleShowAllPayloads(): Promise<void> {
  if (!selectedConcrete.value) return
  showAllPayloadsForSelected.value = !showAllPayloadsForSelected.value
  await applySelectedNodeVisualState()
}

function buildSelectedPathNodeIds(): string[] {
  const sc = selectedConcrete.value
  if (!sc) return []
  const effect = sourceEffects.value.find((x) => x.e_id === sc.e_id)
  if (!effect) return []
  const obj = sourceObjects.value.find((x) => x.o_id === effect.o_id)
  if (!obj) return []
  const dom = sourceDomains.value.find((x) => x.d_id === obj.d_id)
  if (!dom) return []
  const concrete = sourceConcretes.value.find((x) => x.c_instance_id === sc.c_instance_id)
  if (!concrete) return []
  const abstractKey = `e-${effect.e_id}-a-${safeIdPart(concreteClassLabel(concrete.a_ref))}`

  if (mergeViewMode.value) {
    return [
      'ecosystem-root',
      `d-${dom.d_id}`,
      `o-${obj.o_id}`,
      `e-${effect.e_id}`,
      ...(hideAbstractLayer.value ? [] : [abstractKey]),
      sc.nodeId,
    ]
  }

  const sourceId = deviceSourceTreeNodeId(concrete.source)
  const pathIds = [
    'ecosystem-root',
    sourceId,
    `${sourceId}-d-${dom.d_id}`,
    `${sourceId}-o-${obj.o_id}`,
    `${sourceId}-e-${effect.e_id}`,
    ...(hideAbstractLayer.value ? [] : [`${sourceId}-${abstractKey}`]),
    sc.nodeId,
  ]
  // 按生态筛选后树中不再有「智能家居生态」根节点
  if (isSourceFilteredView()) {
    return pathIds.filter((id) => id !== 'ecosystem-root')
  }
  return pathIds
}

function isSourceFilteredView(): boolean {
  return isPartialSourceSelection(selectedSources.value)
}

function matchesSourceFilter(source?: number): boolean {
  if (!selectedSources.value.length) return false
  return selectedSources.value.includes(normalizeDeviceSource(source))
}

async function clearPathHighlight(graph?: Graph | null): Promise<void> {
  const g = graph ?? graphRef.value
  if (!g) return
  const nodeIds = highlightedPathNodeIds
  const edgeIds = highlightedPathEdgeIds
  highlightedPathNodeIds = []
  highlightedPathEdgeIds = []
  await Promise.all([
    ...nodeIds.map((id) => g.setElementState(id, [])),
    ...edgeIds.map((id) => g.setElementState(id, [])),
  ])
}

async function updatePathHighlight(graph?: Graph | null): Promise<void> {
  const g = graph ?? graphRef.value
  if (!g) return
  await clearPathHighlight(g)
  if (showAllPayloadsForSelected.value) return
  const ids = buildSelectedPathNodeIds()
  if (ids.length < 2) return
  const ancestorIds = ids.slice(0, -1)
  highlightedPathNodeIds = ancestorIds
  await Promise.all(ancestorIds.map((id) => g.setElementState(id, ['path-focus'])))

  const edgePairs = ids.slice(0, -1).map((src, i) => [src, ids[i + 1]] as const)
  const getEdgeData = (g as unknown as { getEdgeData?: () => Array<Record<string, unknown>> }).getEdgeData
  if (typeof getEdgeData !== 'function') return
  const edges = getEdgeData.call(g) || []
  const edgeIds = edgePairs
    .map(([source, target]) => {
      const hit = edges.find((e) => e.source === source && e.target === target)
      const rawId = hit?.id
      return typeof rawId === 'string' ? rawId : rawId != null ? String(rawId) : ''
    })
    .filter(Boolean)
  highlightedPathEdgeIds = edgeIds
  await Promise.all(edgeIds.map((id) => g.setElementState(id, ['path-focus'])))
}

function clearEnvFilters(): void {
  selectedDomainId.value = null
  selectedObjectId.value = null
  selectedEffectId.value = null
  selectedAbstractType.value = ''
  selectedSources.value = defaultSelectedSources()
  selectedEnvFilters.value = []
  envFilterMode.value = 'union'
  shouldCollapseEnvTags.value = false
}

function syncEnvTagCollapse(): void {
  if (selectedEnvFilters.value.length <= 1) {
    shouldCollapseEnvTags.value = false
    return
  }
  shouldCollapseEnvTags.value = false
  void nextTick(() => {
    const selection = document.querySelector('.tree-env-filter-select .el-select__selection') as HTMLElement | null
    if (!selection) return
    const overflowed = selection.scrollWidth > selection.clientWidth || selection.clientHeight > 34
    shouldCollapseEnvTags.value = overflowed
  })
}

const MINIMAP_W = 188
const MINIMAP_H = 126
const MINIMAP_MARGIN = 12

function placeMinimap(): void {
  const host = containerRef.value
  const mini = host?.querySelector('.cap-tree-minimap') as HTMLElement | null
  if (!host || !mini) return
  const left = Math.max(MINIMAP_MARGIN, host.clientWidth - MINIMAP_W - MINIMAP_MARGIN)
  const top = Math.max(MINIMAP_MARGIN, host.clientHeight - MINIMAP_H - MINIMAP_MARGIN)
  mini.style.left = `${left}px`
  mini.style.top = `${top}px`
}

function trackMinimap(ms = 320): void {
  const start = performance.now()
  const step = (now: number) => {
    placeMinimap()
    if (now - start < ms) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

function getPanelWidthPx(): number {
  const fromDom = apiPanelRef.value?.offsetWidth ?? 0
  if (fromDom > 0) return fromDom
  return Math.min(380, window.innerWidth * 0.42)
}

async function syncGraphPanelShift(open: boolean): Promise<void> {
  const g = graphRef.value
  if (!g) return
  // translateBy 的偏移以视口像素为主，直接使用面板宽度平移，保证可见位移足够明显
  const target = open ? -(getPanelWidthPx() + 24) : 0
  const delta = target - graphPanelShiftX.value
  if (Math.abs(delta) < 0.1) return
  graphPanelShiftX.value = target
  await g.translateBy([delta, 0], { duration: 260 })
}

function destroyGraphSafely(target?: Graph | null): void {
  const g = target ?? graphRef.value
  if (!g) return
  try {
    g.destroy()
  } catch (e) {
    console.warn('[CapTree] graph destroy skipped due to stale instance:', e)
  } finally {
    if (graphRef.value === g) graphRef.value = null
  }
}

async function fetchPayloadsForDevice(cInstanceId: string): Promise<void> {
  panelLoading.value = true
  commandPayloads.value = []
  try {
    const encoded = encodeURIComponent(cInstanceId)
    const res = await request.get<CommandPayloadItem[]>(`/api/command-payloads/${encoded}`, {
      timeout: 60000,
    })
    commandPayloads.value = res.data || []
    if (commandPayloads.value.length === 0) ElMessage.info('该设备暂无指令载荷记录')
  } catch (e) {
    console.error(e)
    ElMessage.error('加载指令载荷失败')
    commandPayloads.value = []
  } finally {
    panelLoading.value = false
  }
}

/** G6 getNodeData 返回 toG6Data()，业务字段在 data 内；少数路径可能摊平 */
function getNodeBizData(
  graph: Graph,
  id: string,
): {
  kind?: TreeDatum['kind']
  label?: string
  c_instance_id?: string
  catalog_c_instance_id?: string
  e_id?: number
} | null {
  const raw = graph.getNodeData(id) as Record<string, unknown> | undefined
  if (!raw) return null
  const nested = raw.data
  if (nested && typeof nested === 'object' && nested !== null && !Array.isArray(nested)) {
    return nested as {
      kind?: TreeDatum['kind']
      label?: string
      c_instance_id?: string
      catalog_c_instance_id?: string
      e_id?: number
    }
  }
  if ('kind' in raw) {
    return raw as {
      kind?: TreeDatum['kind']
      label?: string
      c_instance_id?: string
      catalog_c_instance_id?: string
      e_id?: number
    }
  }
  return null
}

async function activateConcreteByNodeId(graph: Graph, id: string): Promise<void> {
  const data = getNodeBizData(graph, id)
  if (!data) {
    console.debug('[CapTree] 未找到节点业务数据，跳过:', id)
    return
  }
  if (data.kind !== 'concrete') {
    console.debug('[CapTree] 非具体设备节点，跳过:', id, data.kind)
    return
  }
  const cid = data.c_instance_id
  const eid = typeof data.e_id === 'number' ? data.e_id : Number(data.e_id)
  if (cid == null || !Number.isFinite(eid)) {
    console.warn('[CapTree] 具体设备节点缺少 c_instance_id/e_id，无法请求:', id, data)
    return
  }

  // 点击已选中的节点：取消选中
  if (selectedNodeId.value === id) {
    await graph.setElementState(id, [])
    await clearPathHighlight(graph)
    clearSelectionUi()
    return
  }

  // 点击新节点：清除旧状态
  await clearPathHighlight(graph)
  if (selectedNodeId.value) {
    await graph.setElementState(selectedNodeId.value, [])
  }
  
  showAllPayloadsForSelected.value = false
  selectedNodeId.value = id
  
  selectedConcrete.value = {
    nodeId: id,
    c_instance_id: cid,
    catalog_c_instance_id: data.catalog_c_instance_id || cid,
    e_id: eid,
    label: data.label ?? id,
  }
  await applySelectedNodeVisualState()
  // 触发拉起右侧面板和数据请求
  await fetchPayloadsForDevice(data.catalog_c_instance_id || cid)
}

function bindGraphSelection(graph: Graph): () => void {
  const resolveNodeIdFromEvent = (e: {
    targetType?: string
    target?: { id?: unknown }
  }): string | null => {
    if (e.targetType !== undefined && e.targetType !== 'node') return null
    const rawId = e.target?.id
    if (rawId == null) return null
    return typeof rawId === 'string' ? rawId : String(rawId)
  }

  // 1. 节点点击事件
  const onNodeClick = (e: { targetType?: string; target?: { id?: unknown } }) => {
    const targetId = resolveNodeIdFromEvent(e)
    console.log('[CapTree] 点击节点 ID:', targetId)
    if (targetId) void activateConcreteByNodeId(graph, targetId)
  }

  // 2. 鼠标悬停变小手
  const onNodePointerEnter = (e: { targetType?: string; target?: { id?: unknown } }) => {
    const targetId = resolveNodeIdFromEvent(e)
    const data = targetId ? getNodeBizData(graph, targetId) : null
    if (data?.kind === 'concrete') {
      graph.getCanvas().setCursor('pointer')
      return
    }
    graph.getCanvas().setCursor('default')
  }

  // 3. 鼠标移出恢复
  const onNodePointerLeave = () => {
    graph.getCanvas().setCursor('default')
  }

  const onCanvasClick = async () => {
    if (!selectedNodeId.value) return
    await graph.setElementState(selectedNodeId.value, [])
    await clearPathHighlight(graph)
    clearSelectionUi()
  }

  graph.on(NodeEvent.CLICK, onNodeClick as (...args: unknown[]) => void)
  graph.on(NodeEvent.POINTER_ENTER, onNodePointerEnter as (...args: unknown[]) => void)
  graph.on(NodeEvent.POINTER_LEAVE, onNodePointerLeave as (...args: unknown[]) => void)
  graph.on('canvas:click', onCanvasClick as (...args: unknown[]) => void)

  return () => {
    graph.off(NodeEvent.CLICK, onNodeClick as (...args: unknown[]) => void)
    graph.off(NodeEvent.POINTER_ENTER, onNodePointerEnter as (...args: unknown[]) => void)
    graph.off(NodeEvent.POINTER_LEAVE, onNodePointerLeave as (...args: unknown[]) => void)
    graph.off('canvas:click', onCanvasClick as (...args: unknown[]) => void)
  }
}

function safeIdPart(s: string): string {
  return encodeURIComponent(s).replace(/%/g, '_')
}

/** 按可见字符数估算节点宽高（与 10px 字号、居中标签匹配） */
function countTreeLeaves(node: TreeDatum | null | undefined): number {
  if (!node) return 0
  if (!node.children?.length) return 1
  return node.children.reduce((sum, c) => sum + countTreeLeaves(c), 0)
}

function treeMaxDepth(node: TreeDatum | null | undefined, depth = 0): number {
  if (!node) return depth
  if (!node.children?.length) return depth
  return Math.max(...node.children.map((c) => treeMaxDepth(c, depth + 1)))
}

/** 层次视图里能力节点的固定行高；字号不再随整树缩放被压扁。 */
function estimateNodeSize(label: string): [number, number] {
  const text = (label || '').trim()
  if (!text) return [72, 26]
  const chars = [...text]
  const estimatedPx = chars.reduce((sum, ch) => sum + (/[ -~]/.test(ch) ? 7.2 : 12), 0)
  const innerWidth = Math.max(56, Math.min(156, Math.ceil(estimatedPx)))
  return [innerWidth + 16, 26]
}

const LEAF_DOT = 8
const LEAF_ROW = 18

/** 字号保持可读，不再按叶子数量把圆和字一起缩小。 */
function radialDiameterScale(_leafCount: number): number {
  return 1
}

function estimateCircleDiameter(label: string, scale = 1): number {
  const chars = [...(label || '').trim()]
  const len = chars.length
  let base = 48
  if (len <= 2) base = 40
  else if (len <= 4) base = 48
  else if (len <= 7) base = 56
  else if (len <= 12) base = 64
  else base = 70
  return Math.max(28, Math.min(76, Math.round(base * scale)))
}

function shortLabelForCircle(label: string, maxChars: number): string {
  const text = (label || '').trim()
  const chars = [...text]
  if (chars.length <= maxChars) return text
  if (maxChars <= 1) return '…'
  return `${chars.slice(0, maxChars - 1).join('')}…`
}

/**
 * 径向 dendrogram：角向由叶子沿 y 的 nodeSep 映射到近 2π；
 * 半径 ≈ depth * rankSep。按圆形直径反推所需外半径，避免圆周重叠（可超出视口，由 fitView 缩小）。
 */
function computeRadialLayoutMetrics(tree: TreeDatum, _viewportMinSide: number) {
  const leafCount = Math.max(1, countTreeLeaves(tree))
  const depthLevels = Math.max(1, treeMaxDepth(tree))
  const scale = radialDiameterScale(leafCount)
  const sampleLabels: string[] = []
  ;(function walk(n: TreeDatum) {
    sampleLabels.push(n.label || '')
    n.children?.forEach(walk)
  })(tree)
  const diameters = sampleLabels.map((lb) => estimateCircleDiameter(lb, scale))
  const avgD =
    diameters.reduce((a, b) => a + b, 0) / Math.max(1, diameters.length)
  const maxD = Math.max(...diameters, 28)
  // 圆周弦长约需 >= 直径*间隙系数
  const clearance = leafCount > 120 ? 1.2 : leafCount > 60 ? 1.28 : 1.38
  const needOuterR = (leafCount * avgD * clearance) / (2 * Math.PI)
  const minRankSep = Math.ceil(maxD * clearance)
  const rankSep = Math.max(minRankSep, Math.ceil(needOuterR / depthLevels))
  // dendrogram 叶子 height=0，nodeSep 控制叶子 y 间距（再映射为角）；均匀即可
  const nodeSep = Math.max(4, Math.round(avgD * 0.2))
  const subTreeSep = Math.max(6, Math.round(avgD * 0.45))
  const maxLabelChars = 8
  const fontSize = 11
  return {
    leafCount,
    depthLevels,
    scale,
    avgDiameter: avgD,
    maxDiameter: maxD,
    rankSep,
    nodeSep,
    subTreeSep,
    maxLabelChars,
    fontSize,
    outerRadius: rankSep * depthLevels,
  }
}

function layoutLabelOf(d: unknown): string {
  if (d && typeof d === 'object') {
    const o = d as { data?: { label?: string }; label?: string }
    if (o.data?.label != null) return String(o.data.label)
    if (o.label != null) return String(o.label)
  }
  return ' '
}

function layoutKindOf(d: unknown): TreeDatum['kind'] | undefined {
  if (d && typeof d === 'object') {
    const o = d as { data?: { kind?: TreeDatum['kind'] }; kind?: TreeDatum['kind'] }
    return o.data?.kind ?? o.kind
  }
  return undefined
}

function addPath(root: TreeDatum, segments: TreeDatum[]): void {
  let cur = root
  for (const seg of segments) {
    if (!cur.children) cur.children = []
    let next = cur.children.find((c) => c.id === seg.id)
    if (!next) {
      next = {
        id: seg.id,
        label: seg.label,
        kind: seg.kind,
        ...(seg.kind === 'concrete' && seg.c_instance_id != null && seg.e_id != null
          ? {
              c_instance_id: seg.c_instance_id,
              catalog_c_instance_id: seg.catalog_c_instance_id,
              e_id: seg.e_id,
            }
          : {}),
        children: [],
      }
      cur.children.push(next)
    } else if (
      next.kind === 'concrete' &&
      (next.c_instance_id == null || next.e_id == null) &&
      seg.c_instance_id != null &&
      seg.e_id != null
    ) {
      // 防御式回填：若已存在 concrete 分支但缺关键字段，补齐用于点击选中和接口请求
      next.c_instance_id = seg.c_instance_id
      next.catalog_c_instance_id = seg.catalog_c_instance_id
      next.e_id = seg.e_id
    }
    cur = next
  }
}

function buildTree(
  domains: DomainRow[],
  objects: ObjectRow[],
  effects: EffectRow[],
  concretes: ConcreteRow[],
  payloads: PayloadRow[],
  opts?: {
    omitEcosystemRoot?: boolean
    allowedSources?: number[]
    hideAbstractLayer?: boolean
    mergeView?: boolean
  },
): TreeDatum | null {
  const domainById = new Map(domains.map((d) => [d.d_id, d]))
  const objectById = new Map(objects.map((o) => [o.o_id, o]))
  const effectById = new Map(effects.map((e) => [e.e_id, e]))
  const concreteById = new Map(concretes.map((c) => [c.c_instance_id, c]))
  const allowedSources = opts?.allowedSources
  const omitEcosystemRoot = !!opts?.omitEcosystemRoot
  const skipAbstract = !!opts?.hideAbstractLayer
  const mergeView = !!opts?.mergeView

  const root: TreeDatum = {
    id: 'ecosystem-root',
    label: mergeView ? '能力分类（合并）' : '智能家居生态',
    kind: 'source',
    children: [],
  }

  for (const p of payloads) {
    const eid = typeof p.e_id === 'number' ? p.e_id : Number(p.e_id)
    if (!Number.isFinite(eid)) continue

    const cd = concreteById.get(p.c_instance_id)
    if (!cd) continue

    const sourceCode = normalizeDeviceSource(cd.source)
    if (allowedSources && allowedSources.length > 0 && !allowedSources.includes(sourceCode)) {
      continue
    }

    const eff = effectById.get(eid)
    if (!eff) continue

    const obj = objectById.get(eff.o_id)
    if (!obj) continue

    const dom = domainById.get(obj.d_id)
    if (!dom) continue

    const aRef = concreteClassLabel(cd.a_ref)
    const leafLabel =
      (cd.c_brand && cd.c_brand.trim()) ||
      (p.c_instance_id.length > 48 ? `${p.c_instance_id.slice(0, 46)}…` : p.c_instance_id)

    const concreteNode: TreeDatum = {
      id: `c-${safeIdPart(p.c_instance_id)}__e-${eid}`,
      label: leafLabel,
      kind: 'concrete',
      c_instance_id: p.c_instance_id,
      catalog_c_instance_id: cd.catalog_c_instance_id || p.c_instance_id,
      e_id: eid,
      source: sourceCode,
    }

    let segments: TreeDatum[]
    if (mergeView) {
      // 合并视图：Domain → Object → Effect → (Abstract) → Concrete（跨生态共用父节点）
      const abstractId = `e-${eff.e_id}-a-${safeIdPart(aRef)}`
      segments = [
        { id: `d-${dom.d_id}`, label: dom.d_name, kind: 'domain' },
        { id: `o-${obj.o_id}`, label: obj.o_name, kind: 'object' },
        { id: `e-${eff.e_id}`, label: eff.e_name, kind: 'effect' },
      ]
      if (!skipAbstract) {
        segments.push({ id: abstractId, label: aRef, kind: 'abstract' })
      }
      segments.push(concreteNode)
    } else {
      const sourceId = deviceSourceTreeNodeId(cd.source)
      const sourceLabel = deviceSourceLabel(cd.source, cd.source_label)
      // 节点 id 须在整棵树中唯一：跨生态前缀 + 同 a_ref 多效果分支用 e_id
      const abstractId = `${sourceId}-e-${eff.e_id}-a-${safeIdPart(aRef)}`
      segments = [
        { id: sourceId, label: sourceLabel, kind: 'source' },
        { id: `${sourceId}-d-${dom.d_id}`, label: dom.d_name, kind: 'domain' },
        { id: `${sourceId}-o-${obj.o_id}`, label: obj.o_name, kind: 'object' },
        { id: `${sourceId}-e-${eff.e_id}`, label: eff.e_name, kind: 'effect' },
      ]
      if (!skipAbstract) {
        segments.push({ id: abstractId, label: aRef, kind: 'abstract' })
      }
      segments.push(concreteNode)
    }

    addPath(root, segments)
  }

  const hasLeaf =
    root.children &&
    root.children.length > 0 &&
    (function hasConcrete(n: TreeDatum): boolean {
      if (n.kind === 'concrete') return true
      if (!n.children?.length) return false
      return n.children.some(hasConcrete)
    })(root)

  if (!hasLeaf) return null

  // 分生态视图且按来源筛选后：省略总根，直接以生态节点为树根
  if (!mergeView && omitEcosystemRoot && root.children?.length === 1) {
    return root.children[0]
  }
  return root
}

const kindColors: Record<TreeDatum['kind'], string> = {
  source: '#5B8FF9',
  domain: '#61DDAA',
  object: '#65789B',
  effect: '#F6BD16',
  abstract: '#7262fd',
  concrete: '#78D3F8',
}



async function applyCurrentFormPool(formId: string): Promise<void> {
  if (!formId) {
    formPlacements.value = []
    commandPrefWeightByKey.value = {}
    sourceConcretes.value = []
    sourcePayloadKeys.value = []
    return
  }
  const bundle = await request.get<{
    placements: HomePlacementRow[]
    command_prefs: HomeCommandPrefRow[]
  }>(`/api/home/forms/${encodeURIComponent(formId)}`)
  formPlacements.value = bundle.data.placements || []
  commandPrefWeightByKey.value = Object.fromEntries(
    (bundle.data.command_prefs || []).map((p) => [commandPrefKey(p.placement_id, p.payload_uid), p.weight]),
  )
  const catalogById = new Map(catalogConcretes.value.map((c) => [c.c_instance_id, c]))
  sourceConcretes.value = formPlacements.value.map((pl) => {
    const catalog = catalogById.get(pl.catalog_c_instance_id)
    return {
      c_instance_id: pl.placement_id,
      catalog_c_instance_id: pl.catalog_c_instance_id,
      c_brand: pl.display_name || pl.alias || pl.c_brand || catalog?.c_brand || pl.catalog_c_instance_id,
      a_ref: catalog?.a_ref ?? pl.a_ref,
      source: pl.source ?? catalog?.source,
      source_label: catalog?.source_label,
    }
  })
  const placementsByCatalog = new Map<string, HomePlacementRow[]>()
  for (const pl of formPlacements.value) {
    const list = placementsByCatalog.get(pl.catalog_c_instance_id) || []
    list.push(pl)
    placementsByCatalog.set(pl.catalog_c_instance_id, list)
  }
  const expanded: PayloadRow[] = []
  for (const p of catalogPayloadKeys.value) {
    for (const pl of placementsByCatalog.get(p.c_instance_id) || []) {
      if (!commandParticipates(pl.placement_id, p.uid)) continue
      expanded.push({ ...p, c_instance_id: pl.placement_id })
    }
  }
  sourcePayloadKeys.value = expanded
}

function onFormSelect(id: string): void {
  treeFormChoice.value = id
  if (id && id !== FORM_UNMATCHED) {
    currentFormId.value = id
    writeCurrentHomeFormId(id)
  }
  void loadAndRender()
}

async function loadAndRender(): Promise<void> {
  const jobId = ++latestRenderJobId
  loading.value = true
  emptyHint.value = ''
  try {
    const [domainsRes, objectsRes, effectsRes, concretesRes, payloadsRes, envAttrsRes, formsRes] =
      await Promise.all([
      request.get<DomainRow[]>('/api/domains/'),
      request.get<ObjectRow[]>('/api/objects/'),
      request.get<EffectRow[]>('/api/effects/'),
      request.get<ConcreteRow[]>('/api/concrete-devices/'),
      request.get<PayloadRow[]>('/api/command-payloads/tree-keys/', { timeout: 60000 }),
      request.get<EnvAttributeRow[]>('/api/env-attributes/'),
      request.get<HomeFormRow[]>('/api/home/forms/'),
    ])
    if (jobId !== latestRenderJobId) return

    sourceDomains.value = domainsRes.data || []
    sourceObjects.value = objectsRes.data || []
    sourceEffects.value = effectsRes.data || []
    catalogConcretes.value = concretesRes.data || []
    catalogPayloadKeys.value = payloadsRes.data || []
    homeForms.value = formsRes.data || []

    let formId = treeFormChoice.value
    if (!formId || formId === FORM_UNMATCHED || !homeForms.value.some((f) => f.form_id === formId)) {
      formId = currentFormId.value || readCurrentHomeFormId()
    }
    if (!formId || !homeForms.value.some((f) => f.form_id === formId)) {
      formId = homeForms.value[0]?.form_id || ''
    }
    treeFormChoice.value = formId
    if (formId) {
      if (formId !== currentFormId.value) {
        currentFormId.value = formId
        writeCurrentHomeFormId(formId)
      }
      await applyCurrentFormPool(formId)
    } else {
      formPlacements.value = []
      commandPrefWeightByKey.value = {}
      sourceConcretes.value = []
      sourcePayloadKeys.value = []
    }

    const filteredTreeKeys = sourcePayloadKeys.value.filter((p) => {
      const effect = sourceEffects.value.find((x) => x.e_id === p.e_id)
      if (!effect) return false
      const obj = sourceObjects.value.find((x) => x.o_id === effect.o_id)
      if (!obj) return false
      const concrete = sourceConcretes.value.find((x) => x.c_instance_id === p.c_instance_id)
      if (!concrete) return false
      if (!matchesSourceFilter(concrete.source)) return false
      if (!commandParticipates(p.c_instance_id, p.uid)) return false
      const rec: FilterRecord = {
        d_id: obj.d_id,
        d_name: '',
        o_id: obj.o_id,
        o_name: '',
        e_id: effect.e_id,
        e_name: '',
        a_ref: concreteClassLabel(concrete.a_ref),
        c_instance_id: p.c_instance_id,
        env_impact: p.env_impact || [],
      }
      return recordMatchesSelection(rec)
    })

    if (!selectedSources.value.length) {
      emptyHint.value = '请至少选择一个生态来源。'
      detachGraphSelection?.()
      detachGraphSelection = undefined
      destroyGraphSafely()
      return
    }

    const tree = buildTree(
      sourceDomains.value,
      sourceObjects.value,
      sourceEffects.value,
      sourceConcretes.value,
      filteredTreeKeys,
      {
        allowedSources: [...selectedSources.value],
        omitEcosystemRoot: !mergeViewMode.value && isSourceFilteredView(),
        hideAbstractLayer: hideAbstractLayer.value,
        mergeView: mergeViewMode.value,
      },
    )
    effectNameById.value = Object.fromEntries(sourceEffects.value.map((e) => [e.e_id, e.e_name]))
    effectDescById.value = Object.fromEntries(sourceEffects.value.map((e) => [e.e_id, e.e_desc || '']))
    envAttributes.value = envAttrsRes.data || []
    envNameById.value = Object.fromEntries((envAttrsRes.data || []).map((x) => [x.env_id, x.env_name]))

    if (!tree) {
      const hasAnyFilter =
        selectedDomainId.value != null ||
        selectedObjectId.value != null ||
        selectedEffectId.value != null ||
        !!selectedAbstractType.value ||
        selectedEnvFilters.value.length > 0 ||
        isSourceFilteredView()
      emptyHint.value = !treeFormChoice.value
        ? '请先选择环境表单。'
        : !formPlacements.value.length
          ? '当前环境表单还没有实例化设备。请到配置环境录入。'
          : hasAnyFilter
            ? '当前筛选条件下没有可展示的具体设备，请调整筛选条件。'
            : '当前没有可展示的完整路径：请确保存在「具体设备」且已关联「功能指令载荷」指向三级效果。'
      detachGraphSelection?.()
      detachGraphSelection = undefined
      destroyGraphSafely()
      return
    }

    const useMergeColors = mergeViewMode.value
    const graphData = treeToGraphData(tree as TreeData, {
      getNodeData: (datum: TreeData, depth: number) => {
        const d = datum as TreeDatum
        const childList = d.children || []
        return {
          id: d.id,
          data: {
            label: d.label,
            kind: d.kind,
            ...(d.kind === 'concrete' && d.c_instance_id != null && d.e_id != null
              ? {
                  c_instance_id: d.c_instance_id,
                  catalog_c_instance_id: d.catalog_c_instance_id,
                  e_id: d.e_id,
                  source: d.source ?? normalizeDeviceSource(
                    sourceConcretes.value.find((c) => c.c_instance_id === d.c_instance_id)?.source,
                  ),
                }
              : {}),
          },
          depth,
          children: childList.map((c) => c.id),
        }
      },
      getChildren: (datum: TreeData) => (datum as TreeDatum).children || [],
    })

    await nextTick()
    if (jobId !== latestRenderJobId) return
    const el = containerRef.value
    if (!el) return

    const width = el.clientWidth || 1200
    const height = Math.max(240, el.clientHeight || el.offsetHeight || 0)
    const isRadial = treeLayoutMode.value === 'radial'
    const minSide = Math.min(width, height)
    const radialMetrics = isRadial ? computeRadialLayoutMetrics(tree, minSide) : null
    const sizedRect = (label: string): [number, number] => estimateNodeSize(label)
    const circleDiameterOf = (label: string): number =>
      estimateCircleDiameter(label, radialMetrics?.scale ?? 1)
    const isLeaf = (d: unknown) => !isRadial && layoutKindOf(d) === 'concrete'

    detachGraphSelection?.()
    detachGraphSelection = undefined
    clearSelectionUi()

    destroyGraphSafely()
    const graph = new Graph({
      container: el,
      width,
      height,
      autoResize: true,
      padding: isRadial ? 16 : 28,
      zoomRange: isRadial ? [0.55, 2.2] : [0.85, 2.2],
      data: graphData,
      plugins: [
        {
          type: 'minimap',
          size: [188, 126],
          padding: 8,
          position: 'right-bottom',
          className: 'cap-tree-minimap',
          delay: 180,
          containerStyle: {
            border: '1px solid #111',
            background: '#fff',
          },
          maskStyle: {
            border: '1px solid #111',
            background: 'rgba(17, 17, 17, 0.12)',
          },
        },
      ],
      layout: isRadial
        ? {
            type: 'dendrogram',
            radial: true,
            direction: 'LR',
            nodeSep: radialMetrics!.nodeSep,
            rankSep: radialMetrics!.rankSep,
            subTreeSep: radialMetrics!.subTreeSep,
            getWidth: (d: unknown) => circleDiameterOf(layoutLabelOf(d)),
            getHeight: (d: unknown) => circleDiameterOf(layoutLabelOf(d)),
          }
        : {
            type: 'compact-box',
            direction: 'LR',
            getHGap: () => 36,
            getVGap: () => 2,
            getWidth: (d: unknown) => (isLeaf(d) ? LEAF_DOT : sizedRect(layoutLabelOf(d))[0]),
            getHeight: (d: unknown) => (isLeaf(d) ? LEAF_ROW : sizedRect(layoutLabelOf(d))[1]),
          },
      node: {
        type: isRadial ? 'circle' : 'rect',
        style: {
          ...(isRadial ? {} : { radius: 2 }),
          labelPointerEvents: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            d.data?.kind === 'concrete' ? 'auto' : 'none',
          labelCursor: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            d.data?.kind === 'concrete' ? 'pointer' : 'default',
          labelIsBillboard: false,
          port: false,
          draggable: false,
          fill: (d: {
            data?: { kind?: TreeDatum['kind']; source?: number }
          }) => {
            const k = d.data?.kind
            if (!isRadial && k && k !== 'concrete') return '#fff'
            if (useMergeColors && k === 'concrete') {
              return deviceSourceBookmarkFill(
                d.data?.source,
                kindColors.concrete,
                isRadial ? 0.28 : 0.16,
              )
            }
            return k ? kindColors[k] || '#ccc' : '#ccc'
          },
          stroke: (d: { data?: { kind?: TreeDatum['kind'] } }) => {
            const k = d.data?.kind
            if (!isRadial && k && k !== 'concrete') return kindColors[k] || '#111'
            return 'transparent'
          },
          lineWidth: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            !isRadial && d.data?.kind && d.data.kind !== 'concrete' ? 1.25 : 0,
          size: (d: { data?: { label?: string; kind?: TreeDatum['kind'] }; id: string }) => {
            const label = String(d.data?.label ?? d.id)
            if (isRadial) return circleDiameterOf(label)
            if (d.data?.kind === 'concrete') return [LEAF_DOT, LEAF_DOT]
            return sizedRect(label)
          },
          labelText: (d: { data?: { label?: string }; id: string }) => {
            const raw = d.data?.label ?? String(d.id)
            if (isRadial && radialMetrics) {
              return shortLabelForCircle(String(raw), radialMetrics.maxLabelChars)
            }
            return raw
          },
          labelPlacement: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            !isRadial && d.data?.kind === 'concrete' ? 'right' : 'center',
          labelOffsetX: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            !isRadial && d.data?.kind === 'concrete' ? 8 : 0,
          labelFill: '#111',
          labelFontSize: isRadial ? 11 : 12,
          labelLineHeight: isRadial ? 13 : 16,
          labelFontWeight: 400,
          labelWordWrap: false,
          labelTextOverflow: 'ellipsis',
          labelMaxLines: 1,
          labelMaxWidth: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            !isRadial && d.data?.kind === 'concrete' ? 420 : isRadial ? '80%' : '90%',
          labelStroke: '#fff',
          labelLineWidth: (d: { data?: { kind?: TreeDatum['kind'] } }) =>
            isRadial || d.data?.kind === 'concrete' ? 3 : 0,
        },
        state: {
          selected: {
            lineWidth: 3,
            stroke: '#ffe58f',
            shadowColor: 'rgba(0,0,0,0.2)',
            shadowBlur: 12,
          },
          'path-focus': {
            lineWidth: 3,
            stroke: '#409eff',
            shadowColor: 'rgba(64,158,255,0.25)',
            shadowBlur: 10,
          },
          'all-payloads': {
            lineWidth: 3,
            stroke: '#f56c6c',
            shadowColor: 'rgba(245,108,108,0.3)',
            shadowBlur: 12,
          },
        },
      },
      edge: {
        type: isRadial ? 'cubic-radial' : 'cubic-horizontal',
        style: {
          stroke: '#d5d5d0',
          lineWidth: 1,
          pointerEvents: 'none',
        },
        state: {
          'path-focus': {
            stroke: '#409eff',
            lineWidth: 2.6,
          },
        },
      },
      behaviors: ['drag-canvas', 'zoom-canvas'],
    })

    await graph.render()
    if (jobId !== latestRenderJobId) {
      destroyGraphSafely(graph)
      return
    }
    graphRef.value = graph
    graphPanelShiftX.value = 0
    detachGraphSelection = bindGraphSelection(graph)
    await showReadableView(graph)
    trackMinimap(520)
    await syncGraphPanelShift(!!selectedConcrete.value)
  } catch (e) {
    if (jobId !== latestRenderJobId) return
    console.error(e)
    const msg =
      e instanceof Error ? e.message : typeof e === 'string' ? e : '未知错误'
    ElMessage.error(`加载分类树失败：${msg}`)
  } finally {
    if (jobId === latestRenderJobId) loading.value = false
  }
}

async function showReadableView(g: Graph): Promise<void> {
  await g.zoomTo(1, false)
  const nodes = g.getNodeData()
  const root =
    nodes.find((n) => n.id === 'ecosystem-root') ||
    nodes.find((n) => (n.data as { kind?: string } | undefined)?.kind === 'source') ||
    nodes[0]
  if (!root?.id) return
  let bounds: { min: number[]; max: number[] } | undefined
  try {
    bounds = g.getElementRenderBounds(root.id) as { min: number[]; max: number[] }
  } catch {
    return
  }
  if (!bounds?.min || !bounds?.max) return
  const viewH = containerRef.value?.clientHeight || 640
  const midY = (bounds.min[1] + bounds.max[1]) / 2
  await g.translateBy([48 - bounds.min[0], viewH * 0.46 - midY], false)
}

function showOverview(): void {
  const g = graphRef.value
  const el = containerRef.value
  if (!g) return
  if (el) {
    const width = el.clientWidth || 1200
    const height = Math.max(240, el.clientHeight || el.offsetHeight || 0)
    g.setSize(width, height)
  }
  void showReadableView(g).then(() => {
    placeMinimap()
    return syncGraphPanelShift(!!selectedConcrete.value)
  })
}

async function exportTreeImage(): Promise<void> {
  const g = graphRef.value
  if (!g) {
    ElMessage.warning('分类树尚未加载完成，无法导出')
    return
  }
  exportingImage.value = true
  try {
    const dataUrl = await g.toDataURL({
      mode: 'overall',
      type: 'image/png',
      encoderOptions: 1,
    })
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    const link = document.createElement('a')
    link.href = dataUrl
    link.download = `capability-tree-${stamp}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    ElMessage.success('分类树图片已导出')
  } catch (e) {
    console.error(e)
    ElMessage.error('导出失败，请重试')
  } finally {
    exportingImage.value = false
  }
}

function onResize(): void {
  const g = graphRef.value
  const el = containerRef.value
  if (!g || !el) return
  const width = el.clientWidth || 1200
  const height = Math.max(240, el.clientHeight || el.offsetHeight || 0)
  g.setSize(width, height)
  placeMinimap()
}

function onExternalFormChange(ev: Event): void {
  if (treeFormChoice.value === FORM_UNMATCHED) return
  const id = String((ev as CustomEvent).detail || '')
  if (id && id !== treeFormChoice.value) {
    treeFormChoice.value = id
    currentFormId.value = id
    void loadAndRender()
  }
}

onMounted(() => {
  void loadAndRender()
  window.addEventListener('resize', onResize)
  window.addEventListener('resize', syncEnvTagCollapse)
  window.addEventListener(HOME_FORM_CHANGED_EVENT, onExternalFormChange as EventListener)
})

watch(
  () => !!selectedConcrete.value,
  (open) => {
    if (panelShiftTimer) {
      window.clearTimeout(panelShiftTimer)
      panelShiftTimer = undefined
    }
    // 与侧栏展开/收起同一帧启动，避免“先出菜单再平移”的割裂感
    void syncGraphPanelShift(open)
    trackMinimap(340)
  },
)

watch(domainOptions, (opts) => {
  if (selectedDomainId.value != null && !opts.some((x) => x.value === selectedDomainId.value)) {
    selectedDomainId.value = null
  }
})

watch(objectOptions, (opts) => {
  if (selectedObjectId.value != null && !opts.some((x) => x.value === selectedObjectId.value)) {
    selectedObjectId.value = null
  }
})

watch(effectOptions, (opts) => {
  if (selectedEffectId.value != null && !opts.some((x) => x.value === selectedEffectId.value)) {
    selectedEffectId.value = null
  }
})

watch(abstractTypeOptions, (opts) => {
  if (selectedAbstractType.value && !opts.includes(selectedAbstractType.value)) {
    selectedAbstractType.value = ''
  }
})

watch(selectedEnvFilters, () => {
  syncEnvTagCollapse()
  void loadAndRender()
})

watch(envFilterMode, () => {
  void loadAndRender()
})

watch(selectedDomainId, () => {
  void loadAndRender()
})

watch(selectedObjectId, () => {
  void loadAndRender()
})

watch(selectedEffectId, () => {
  void loadAndRender()
})

watch(selectedAbstractType, () => {
  void loadAndRender()
})

watch(selectedSources, () => {
  clearSelectionUi()
  void loadAndRender()
})

watch(hideAbstractLayer, () => {
  clearSelectionUi()
  void loadAndRender()
})

watch(mergeViewMode, () => {
  clearSelectionUi()
  void loadAndRender()
})

watch(treeLayoutMode, () => {
  clearSelectionUi()
  void loadAndRender()
})

onUnmounted(() => {
  latestRenderJobId += 1
  window.removeEventListener('resize', onResize)
  window.removeEventListener('resize', syncEnvTagCollapse)
  window.removeEventListener(HOME_FORM_CHANGED_EVENT, onExternalFormChange as EventListener)
  if (panelShiftTimer) window.clearTimeout(panelShiftTimer)
  detachGraphSelection?.()
  detachGraphSelection = undefined
  destroyGraphSafely()
})
</script>

<style scoped>
.cap-tree-page {
  min-height: 0;
}

.cap-tree-canvas {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cap-tree-side {
  overflow: auto;
}

.cap-tree-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px 16px;
}

.cap-tree-fields :deep(.el-select),
.cap-tree-fields :deep(.el-radio-group) {
  width: 100%;
}

.layout-mode-group {
  width: 100%;
}

.title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.layout-mode-group {
  margin-right: 4px;
  flex-shrink: 0;
}

.merge-view-switch {
  margin-right: 4px;
}

.source-legend-dropdown {
  margin-right: 4px;
}

.source-legend-dropdown__caret {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.75;
}

.retrieval-mode-switch {
  margin-right: 4px;
}

.abstract-layer-switch {
  margin-right: 4px;
}

.empty-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 260px;
}

.tree-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100%;
  align-items: stretch;
  gap: 0;
  overflow: hidden;
}

.tree-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
  overflow: hidden;
}

.tree-main .g6-container {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  border-radius: 0;
  background: #fff;
  overflow: hidden;
}

.tree-main :deep(.cap-tree-minimap) {
  z-index: 4;
  box-shadow: none;
}

.api-panel {
  flex: 0 0 0;
  width: 0;
  max-width: 0;
  overflow: hidden;
  opacity: 0;
  position: relative;
  z-index: 3;
  transition:
    flex-basis 0.28s ease,
    max-width 0.28s ease,
    width 0.28s ease,
    opacity 0.18s ease;
}

.api-panel--open {
  flex: 0 0 min(360px, 40vw);
  width: min(360px, 40vw);
  max-width: min(360px, 40vw);
  height: 100%;
  min-height: 0;
  opacity: 1;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #111;
  background: #fff;
  border-radius: 0;
}

.api-panel--open .api-panel__inner {
  min-width: 260px;
}

.api-panel__inner {
  box-sizing: border-box;
  flex: 1;
  height: 100%;
  min-height: 0;
  max-height: none;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.api-panel__head {
  flex-shrink: 0;
  margin-bottom: 8px;
}

.api-panel__title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
}

.api-panel__sub {
  margin: 0 0 2px;
  font-size: 12px;
  color: #303133;
  word-break: break-all;
  line-height: 1.4;
}

.api-panel__meta {
  margin: 0;
  font-size: 11px;
  color: #909399;
}

.api-panel__path {
  margin: 4px 0 2px;
  font-size: 11px;
  line-height: 1.45;
  color: #606266;
  word-break: break-all;
}

.api-panel__path-node {
  color: #409eff;
  text-decoration: underline;
  text-decoration-style: dotted;
  cursor: help;
}

.api-panel__controls {
  margin-top: 8px;
}

.api-panel__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
  scrollbar-gutter: stable;
}

.api-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.api-card {
  border: 0;
  border-bottom: 1px solid #cfcfcb;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: hidden;
  padding: 8px 0 12px;
}

.api-card__head {
  padding: 0 0 6px;
  border-bottom: 0;
  background: transparent;
}

.api-card__title {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.api-card--parameter,
.api-card--strategy {
  border-style: solid;
  border-color: #cfcfcb;
}

.api-card__param {
  color: #e6a23c;
}

.api-card__strategy {
  color: #67c23a;
}

.strategy-side-collapse {
  margin-top: 10px;
}

.api-card__aux {
  color: #909399;
}

.api-card__kind {
  font-weight: 500;
}

.api-card__desc {
  padding: 6px 10px 0;
  font-size: 12px;
  line-height: 1.55;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

.api-card__effect {
  color: #409eff;
  text-decoration: underline;
  text-decoration-style: dotted;
  cursor: help;
}

:deep(.cap-tooltip-wrap) {
  max-width: 280px;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.45;
}

.api-card__uid {
  margin-top: 4px;
  font-size: 11px;
  color: #909399;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.api-card__meta {
  padding: 6px 10px;
  font-size: 11px;
  line-height: 1.35;
  border-bottom: 1px dashed #ebeef5;
  background: #fafafa;
}

.api-card__meta-key {
  color: #909399;
}

.api-card__meta-value {
  color: #606266;
}

.api-panel__json-wrap {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
  background: #fafafa;
}

.api-panel__json-title {
  padding: 5px 8px;
  font-size: 11px;
  color: #909399;
  border-bottom: 1px solid #ebeef5;
  background: #f5f7fa;
}

.api-panel__json {
  margin: 0;
  padding: 8px;
  font-size: 10px;
  line-height: 1.35;
  max-height: min(46vh, 360px);
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.api-panel__json--copyable {
  cursor: pointer;
}
</style>

<!-- 下拉挂载到 body，需非 scoped 样式 -->
<style>
.source-legend-menu .el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: default;
  color: #606266;
}

.source-legend-menu .el-dropdown-menu__item.is-disabled {
  opacity: 1;
  cursor: default;
  color: #606266;
}

.source-legend-menu__swatch {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 2px;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
}

.source-legend-menu__label {
  font-weight: 600;
  min-width: 88px;
}

.source-legend-menu__sub {
  color: #909399;
  font-size: 12px;
}
</style>
