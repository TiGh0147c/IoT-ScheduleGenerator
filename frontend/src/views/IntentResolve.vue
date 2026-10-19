<template>
  <div class="intent-dock">
    <aside class="pane-tree">
      <button
        type="button"
        class="tree-item"
        :class="{ 'is-on': inspectView === 'intent' }"
        @click="inspectView = 'intent'"
      >
        解析
      </button>
      <button
        v-if="showResultNav"
        type="button"
        class="tree-item"
        :class="{ 'is-on': inspectView === 'result' }"
        @click="showResultInspect"
      >
        草案
      </button>
    </aside>

    <section class="pane-inspect">
      <div v-show="inspectView === 'intent'" class="home-board">
        <div class="pane-h">
          <h1>意图解析</h1>
        </div>
        <div class="board-scroll intent-console-body">
          <label class="field">
            <span>环境</span>
            <el-select
              v-model="currentFormId"
              filterable
              placeholder="选择要解析的环境"
              style="width: 100%"
              :disabled="resolving"
              @change="onFormSelect"
            >
              <el-option v-for="f in homeForms" :key="f.form_id" :label="f.name" :value="f.form_id" />
            </el-select>
          </label>
          <label class="field">
            <span>你想做什么</span>
            <el-input
              v-model="intentText"
              type="textarea"
              :rows="6"
              maxlength="1000"
              show-word-limit
              placeholder="例如：客厅太热，帮我凉快一点，并在洗完衣服后提醒我"
              :disabled="resolving"
            />
          </label>
          <div class="field">
            <span>解析模式</span>
            <div class="seg">
              <button type="button" :class="{ 'is-on': resolveMode === 'auto' }" :disabled="resolving" @click="resolveMode = 'auto'">自动</button>
              <button type="button" :class="{ 'is-on': resolveMode === 'interactive' }" :disabled="resolving" @click="resolveMode = 'interactive'">复杂</button>
            </div>
          </div>
          <div class="field">
            <span>生态来源</span>
            <el-select
              v-model="selectedSources"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :disabled="resolving"
              placeholder="参与实现的生态"
              style="width: 100%"
            >
              <el-option
                v-for="item in deviceSourceOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </div>
          <div class="intent-actions">
            <el-button type="primary" :loading="resolving" @click="runResolve">开始解析</el-button>
            <el-button :disabled="resolving" @click="resetResult">清空结果</el-button>
          </div>
          <div v-if="resolving" class="progress-list">
            <div
              v-for="(title, idx) in ['L1 领域', 'L2 对象', 'L3 效果', 'L4 设备', 'L5 指令']"
              :key="title"
              class="progress-list__item"
              :class="{ 'is-on': progressStep >= idx }"
            >
              {{ title }}
            </div>
            <p class="progress-hint">{{ progressHint }}</p>
          </div>
          <p v-else-if="jobAlert" class="console-alert">{{ jobAlert }}</p>
        </div>
      </div>
      <div v-show="inspectView === 'result'" class="result-board">
        <div class="pane-h">
          <h1>草案</h1>
          <span v-if="result?.trace_id" class="mark">{{ result.trace_id }}</span>
          <el-button
            v-if="result?.final_plan?.ordered_steps?.length"
            type="primary"
            :loading="packing"
            @click="runPack"
          >
            生成 API 指令集
          </el-button>
        </div>
        <div class="board-scroll result-scroll">
        <p v-if="resolving && !hasLayers && !result" class="muted">解析进行中，层级与草案会出现在这里。</p>
        <p v-if="result?.message || jobAlert" class="note" :class="{ 'note--warn': !!(result?.stopped_at || jobAlert) }">
          {{ result?.message || jobAlert }}
        </p>

        <section v-if="hasLayers">
          <section v-for="layerKey in layerKeys" :key="layerKey" class="doc-sec">
            <h2>{{ layerTitle(layerKey) }}</h2>
            <div v-if="displayLayers[layerKey]" class="layer-body">
              <p v-if="displayLayers[layerKey].error" class="layer-error">
                错误：{{ displayLayers[layerKey].error }}
              </p>
              <p v-if="displayLayers[layerKey].stop_reason" class="layer-stop">
                中止：{{ displayLayers[layerKey].stop_reason }}
              </p>
              <p class="layer-meta">候选数：{{ displayLayers[layerKey].candidate_count }}</p>
              <p v-if="displayLayers[layerKey].wanted_env?.length" class="layer-meta">
                主签名环境：{{ displayLayers[layerKey].wanted_env.join('、') }}
              </p>
              <div class="node-tags">
                <div
                  v-for="node in (displayLayers[layerKey].selected_nodes || [])"
                  :key="String(node.id)"
                  class="node-chip"
                >
                  <strong :title="node.reason || ''">{{ node.name || node.id }}</strong>
                  <span v-if="node.candidate_kind" class="node-meta">{{ kindLabel(node.candidate_kind) }}</span>
                  <span v-if="node.env_match_score" class="node-meta">匹配 {{ node.env_match_score }}</span>
                  <span v-if="node.env_hint" class="node-meta">{{ node.env_hint }}</span>
                </div>
                <span v-if="!displayLayers[layerKey].selected_nodes?.length" class="muted">无选中节点</span>
              </div>
              <div v-if="displayLayers[layerKey].relations?.length" class="relations">
                <div class="sub-title">节点关系</div>
                <ul>
                  <li v-for="(rel, idx) in displayLayers[layerKey].relations" :key="idx">
                    [{{ rel.type }}] {{ rel.from_id }} → {{ rel.to_id }}
                    <span v-if="rel.note">（{{ rel.note }}）</span>
                  </li>
                </ul>
              </div>
              <div v-if="displayLayers[layerKey].nl_guidance" class="guidance">
                <div class="sub-title">自然语言指导</div>
                <p>{{ displayLayers[layerKey].nl_guidance }}</p>
              </div>
              <div v-if="displayLayers[layerKey].invalid_ids?.length" class="invalid">
                已过滤幻觉 ID：{{ displayLayers[layerKey].invalid_ids.join(', ') }}
              </div>
            </div>
            <p v-else class="muted">本层未执行</p>
          </section>
        </section>

        <section v-if="result?.final_plan" class="final-plan">
          <h3>有序指令草案</h3>
          <p class="mark">{{ result.final_plan.resolve_mode === 'interactive' ? '复杂意图选择模式' : '自动意图选择模式' }}</p>
          <p class="plan-summary">{{ result.final_plan.plan_summary || '（无摘要）' }}</p>
          <p v-if="result.final_plan.nl_guidance" class="plan-guidance">{{ result.final_plan.nl_guidance }}</p>

          <article
            v-for="step in result.final_plan.ordered_steps"
            :key="`${step.step}-${step.selected_uid || step.payload_uid}`"
            class="plan-step"
          >
            <header class="plan-step__head">
              <span class="plan-step__no">步骤 {{ step.step }}</span>
              <span v-if="step.step_intent" class="plan-step__intent">{{ step.step_intent }}</span>
            </header>

            <div v-if="(step.options?.length ?? 0) > 1" class="step-options">
              <div class="sub-title">
                具体设备备选（{{ step.options?.length ?? 0 }}）
              </div>
              <div class="opt-list">
                <button
                  v-for="opt in (step.options ?? [])"
                  :key="opt.c_instance_id || opt.payload_uid"
                  type="button"
                  class="opt-row"
                  :class="{ 'is-on': isDeviceOptionActive(step, opt) }"
                  @click="selectStepDevice(step, opt)"
                >
                  <span class="opt-row__name">
                    {{ opt.c_brand || opt.c_instance_id }}
                    <i v-if="opt.is_recommended">推荐</i>
                  </span>
                  <span class="opt-row__w">{{ opt.device_weight ?? 0 }} / {{ opt.command_weight ?? 0 }}</span>
                  <span class="opt-row__nl">{{ opt.nl_step || opt.payload_uid }}{{ opt.e_name ? ` · ${opt.e_name}` : '' }}</span>
                </button>
              </div>
            </div>

            <div v-if="currentDeviceVariants(step).length > 1" class="step-variants">
              <div class="sub-title">
                同设备指令路径备选（{{ currentDeviceVariants(step).length }}）
              </div>
              <div class="opt-list">
                <button
                  v-for="variant in currentDeviceVariants(step)"
                  :key="variant.payload_uid"
                  type="button"
                  class="opt-row"
                  :class="{ 'is-on': (step.selected_uid || step.payload_uid) === variant.payload_uid }"
                  @click="selectStepCommandVariant(step, variant)"
                >
                  <span class="opt-row__name">
                    路径
                    <i v-if="variant.is_recommended">推荐</i>
                  </span>
                  <span class="opt-row__w">{{ variant.command_weight ?? 0 }}</span>
                  <span class="opt-row__nl">{{ variant.nl_step || variant.payload_uid }}</span>
                </button>
              </div>
            </div>

            <header v-else-if="(step.options?.length ?? 0) <= 1" class="plan-step__head plan-step__head--selected">
              <span class="plan-step__brand">{{ step.c_brand || step.c_instance_id }}</span>
              <span class="plan-step__effect">{{ step.e_name || (step.e_id != null ? `效果#${step.e_id}` : '') }}</span>
            </header>
            <p class="plan-step__nl">{{ step.nl_step || step.payload_uid }}</p>
            <div class="plan-step__uid">UID：{{ step.selected_uid || step.payload_uid }}</div>
            <div v-if="step.param_placeholders?.length" class="placeholders">
              <div class="sub-title">参数填写</div>
              <div v-for="(ph, i) in step.param_placeholders" :key="i" class="param-fill-row">
                <div class="param-fill-label">
                  <strong>{{ ph.label || ph.path }}</strong>
                  <span v-if="ph.required === false" class="mark">选填</span>
                </div>
                <div
                  v-if="ph.value_type !== 'enum' && (ph.nl_description || ph.hint)"
                  class="param-fill-desc"
                >
                  {{ ph.nl_description || ph.hint }}
                </div>
                <div v-else-if="ph.hint" class="param-fill-hint">{{ ph.hint }}</div>
                <el-select
                  v-if="(ph.value_type === 'enum' || ph.value_type === 'bool') && ph.options?.length"
                  v-model="userParamValues[`${step.step}-${ph.path}`]"
                  clearable
                  filterable
                  placeholder="选择参数值"
                  style="width: 100%; max-width: 360px"
                >
                  <el-option
                    v-for="opt in ph.options"
                    :key="String(opt.value)"
                    :label="`${opt.label_zh || opt.label_en || opt.value} (${opt.value})`"
                    :value="opt.value"
                  />
                </el-select>
                <el-input
                  v-else
                  v-model="userParamValues[`${step.step}-${ph.path}`]"
                  :placeholder="ph.value_range ? `输入数值（${ph.value_range.min ?? '?' }～${ph.value_range.max ?? '?' }）` : '输入具体数值'"
                  style="width: 100%; max-width: 360px"
                />
              </div>
            </div>
            <div class="api-block">
              <div class="api-block__title">
                api_set
                <el-button link type="primary" @click="copyApiSet(step.api_set)">复制</el-button>
              </div>
              <pre class="api-block__body">{{ formatJson(step.api_set) }}</pre>
            </div>
          </article>
        </section>

        <section v-if="result?.final_plan?.ordered_steps?.length" class="pack-section">
          <div class="pack-section__head">
            <h3>最后一步：API 指令集参数注入与打包</h3>
            <el-button type="primary" :loading="packing" @click="runPack">
              生成 API 指令集
            </el-button>
          </div>

          <p v-if="packResult && !packResult.success" class="note note--warn">
            {{ packResult.message }}
          </p>
          <ul v-if="packResult && !packResult.success && packResult.validation_errors?.length" class="pack-errors">
            <li v-for="(err, i) in packResult.validation_errors" :key="i">{{ err }}</li>
          </ul>

          <section v-if="packResult?.success" class="packed-result">
            <div class="packed-result__meta">
              <span class="mark">已生成</span>
              <span class="mark">{{ packResult.resolve_mode_label || (packResult.resolve_mode === 'interactive' ? '复杂模式' : '自动模式') }}</span>
              <span v-if="packResult.log_file" class="packed-log">日志：{{ packResult.log_file }}</span>
            </div>
            <p class="plan-summary">{{ packResult.plan_summary }}</p>

            <div class="packed-actions">
              <el-button type="primary" @click="copyPackedAll">复制完整 API 指令集</el-button>
            </div>

            <article
              v-for="ps in packResult.packed_steps"
              :key="`packed-${ps.step}-${ps.payload_uid}`"
              class="packed-step"
            >
              <header class="packed-step__head">
                <span class="plan-step__no">步骤 {{ ps.step }}</span>
                <span class="plan-step__brand">{{ ps.c_brand || ps.c_instance_id }}</span>
                <span class="plan-step__effect">{{ ps.e_name }}</span>
              </header>
              <p class="packed-step__desc">{{ ps.step_description || ps.nl_step }}</p>
              <div v-if="ps.user_params?.length" class="packed-step__params">
                <div class="sub-title">已注入参数</div>
                <ul>
                  <li v-for="(p, i) in ps.user_params" :key="i">
                    {{ p.label }} = {{ formatParamValue(p) }}
                  </li>
                </ul>
              </div>
              <div class="api-block">
                <div class="api-block__title">
                  注入后的 api_set
                  <el-button link type="primary" @click="copyApiSet(ps.api_set)">复制本步</el-button>
                </div>
                <pre class="api-block__body">{{ formatJson(ps.api_set) }}</pre>
              </div>
            </article>

            <div class="api-block packed-all">
              <div class="api-block__title">
                完整 API 指令集（JSON）
                <el-button link type="primary" @click="copyPackedAll">复制全部</el-button>
              </div>
              <pre class="api-block__body api-block__body--tall">{{ formatJson(packResult.packed_api_set) }}</pre>
            </div>
          </section>
        </section>
        </div>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onUnmounted, onMounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'

import request from '../api/request'
import { DEVICE_SOURCE_OPTIONS, defaultSelectedSources } from '../constants/deviceSources'
import {
  HOME_FORM_CHANGED_EVENT,
  readCurrentHomeFormId,
  writeCurrentHomeFormId,
} from '../constants/homeForm'



interface IntentNode {
  id: string | number
  name: string
  reason: string
  env_hint?: string
  env_match_score?: number
  candidate_kind?: string
}

interface IntentRelation {
  type: string
  from_id: string | number
  to_id: string | number
  note: string
}

interface IntentLayer {
  layer: string
  selected_nodes: IntentNode[]
  relations: IntentRelation[]
  nl_guidance: string
  invalid_ids?: Array<string | number>
  candidate_count: number
  stopped?: boolean
  stop_reason?: string | null
  error?: string | null
  wanted_env?: string[]
}

interface ParamOption {
  value: string | number | boolean
  label_zh?: string
  label_en?: string
}

interface ParamPlaceholder {
  path: string
  hint: string
  nl_description?: string
  user_value: unknown
  label?: string
  value_type?: string
  options?: ParamOption[]
  value_range?: { min?: number; max?: number; step?: number }
  siid?: number
  piid?: number
  unit?: string
  required?: boolean
}

interface PackedUserParam {
  path: string
  label: string
  value: unknown
  unit?: string
}

interface PackedStep {
  step: number
  payload_uid: string
  c_instance_id: string
  c_brand: string
  e_name: string
  nl_step: string
  step_description: string
  user_params: PackedUserParam[]
  api_set: unknown
}

interface PackResult {
  success: boolean
  message: string
  plan_summary: string
  resolve_mode?: string
  resolve_mode_label?: string
  packed_steps: PackedStep[]
  packed_api_set: unknown[]
  log_file?: string | null
  validation_errors?: string[]
}

interface CommandVariant {
  payload_uid: string
  nl_step: string
  is_recommended: boolean
  variant_reason: string
  goal_analysis?: string
  command_weight?: number
  api_set: unknown
  param_placeholders: ParamPlaceholder[]
}

interface StepOption {
  payload_uid: string
  c_instance_id: string
  c_brand: string
  e_id: number | null
  e_name: string
  nl_step: string
  is_recommended: boolean
  tie_group: string
  tie_reason: string
  device_weight?: number
  command_weight?: number
  goal_analysis?: string
  api_set: unknown
  param_placeholders: ParamPlaceholder[]
  command_variants?: CommandVariant[]
}

interface PlanStep {
  step: number
  payload_uid: string
  selected_uid?: string
  step_intent?: string
  c_instance_id: string
  c_brand: string
  e_id: number | null
  e_name: string
  api_set: unknown
  param_placeholders: ParamPlaceholder[]
  nl_step: string
  options?: StepOption[]
  selection_required?: boolean
}

interface IntentResult {
  trace_id: string
  intent_text: string
  layers: Record<string, IntentLayer>
  final_plan?: {
    plan_summary: string
    ordered_steps: PlanStep[]
    relations: IntentRelation[]
    nl_guidance: string
    resolve_mode?: string
  } | null
  stopped_at?: string | null
  message?: string | null
}

interface IntentJobSnapshot {
  job_id: string
  status: 'queued' | 'running' | 'success' | 'failed' | string
  phase: string
  phase_index: number
  phase_label?: string
  message?: string
  layers?: Record<string, IntentLayer>
  result?: IntentResult | null
  elapsed_ms?: number
}

interface HomeFormRow {
  form_id: string
  name: string
  note?: string
}

interface HomeRoomTypeRow {
  type_id: number
  name: string
  is_preset: boolean
  is_active: boolean
}

interface HomeRoomRow {
  room_id: number
  form_id: string
  type_id: number
  type_name: string
  label: string
}

interface HomePlacementRow {
  placement_id: string
  form_id: string
  catalog_c_instance_id: string
  c_brand: string
  a_ref?: string | null
  alias: string
  room_id?: number | null
  room_label: string
  weight: number
  preference_desc?: string | null
  display_name: string
}











interface CatalogDeviceRow {
  c_instance_id: string
  c_brand: string
  a_ref?: string | null
  env_set?: number[]
  source?: number
}





const INTENT_JOB_STORAGE_KEY = 'iot-intent-job-id'
const INTENT_POLL_MS = 800


const intentText = ref('')
const resolveMode = ref<'auto' | 'interactive'>('auto')
/** 参与本次寻址的生态来源；默认全选，选项见 constants/deviceSources */
const selectedSources = ref<number[]>(defaultSelectedSources())
const deviceSourceOptions = DEVICE_SOURCE_OPTIONS
const resolving = ref(false)
const result = ref<IntentResult | null>(null)
const liveLayers = ref<Record<string, IntentLayer>>({})
const jobAlert = ref('')
const openedLayers = ref<string[]>(['l1', 'l2', 'l3', 'l4', 'l5'])
const progressStep = ref(0)
const progressHint = ref('正在执行 L1 领域层推理…')
const userParamValues = ref<Record<string, unknown>>({})
const packing = ref(false)
const packResult = ref<PackResult | null>(null)


const homeForms = ref<HomeFormRow[]>([])
const currentFormId = ref('')

const roomTypes = ref<HomeRoomTypeRow[]>([])
const homeRooms = ref<HomeRoomRow[]>([])
const homePlacements = ref<HomePlacementRow[]>([])



const catalogDevices = ref<CatalogDeviceRow[]>([])













const cmdDrawerVisible = ref(false)
const inspectView = ref<'home' | 'intent' | 'commands' | 'result'>('intent')
const moduleMode = ref<'env' | 'intent'>('env')



























function showResultInspect(): void {
  cmdDrawerVisible.value = false
  moduleMode.value = 'intent'
  inspectView.value = 'result'
}



const showResultNav = computed(() => !!(result.value || packResult.value || resolving.value || jobAlert.value))























const layerKeys = ['l1', 'l2', 'l3', 'l4', 'l5'] as const

const progressLayerHints = [
  '正在执行 L1 领域层推理…',
  '正在执行 L2 对象层推理…',
  '正在执行 L3 效果层推理…',
  '正在执行 L4 设备层推理…',
  '正在执行 L5 指令层推理…',
] as const

const displayLayers = computed<Record<string, IntentLayer>>(() => {
  if (result.value?.layers) return result.value.layers
  return liveLayers.value
})

const hasLayers = computed(() => Object.keys(displayLayers.value || {}).length > 0)

let pollAborted = false

function stopPollTimer(): void {
  pollAborted = true
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function httpStatus(err: unknown): number | null {
  const status = (err as { response?: { status?: number } })?.response?.status
  return typeof status === 'number' ? status : null
}

function httpDetail(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : ''
}

function applyJobSnapshot(snap: IntentJobSnapshot): void {
  if (snap.layers && Object.keys(snap.layers).length) {
    liveLayers.value = snap.layers
  }
  const idx = Math.min(4, Math.max(0, Number(snap.phase_index) || 0))
  progressStep.value = snap.status === 'success' || snap.status === 'failed' ? 5 : idx
  progressHint.value = snap.message || snap.phase_label || progressLayerHints[idx] || progressLayerHints[0]
}

function applyResolveResult(data: IntentResult): void {
  result.value = data
  liveLayers.value = data.layers || {}
  userParamValues.value = {}
  packResult.value = null
  seedAllStepParams()
  openedLayers.value = layerKeys.filter((k) => !!data.layers?.[k])
  moduleMode.value = 'intent'
  inspectView.value = 'result'
  cmdDrawerVisible.value = false
}

onMounted(() => {
  void resumeIntentJobIfAny()
  void bootstrapHomeLibrary()
  window.addEventListener(HOME_FORM_CHANGED_EVENT, onExternalFormChange as EventListener)
})

onUnmounted(() => {
  stopPollTimer()
  window.removeEventListener(HOME_FORM_CHANGED_EVENT, onExternalFormChange as EventListener)
})

const layerTitleMap: Record<string, string> = {
  l1: 'L1 作用领域',
  l2: 'L2 作用对象',
  l3: 'L3 具体效果',
  l4: 'L4 具体设备',
  l5: 'L5 API 指令',
}

function layerTitle(key: string): string {
  const layer = displayLayers.value?.[key]
  const base = layerTitleMap[key] || key
  if (!layer) return base
  const n = layer.selected_nodes?.length ?? 0
  return `${base}（选中 ${n}）`
}

function kindLabel(kind: string): string {
  if (kind === 'recipe') return '配方'
  if (kind === 'atom') return '原子'
  if (kind === 'composed') return '组合'
  return kind
}



function onExternalFormChange(ev: Event): void {
  const id = String((ev as CustomEvent).detail || '')
  if (id && id !== currentFormId.value) {
    currentFormId.value = id
    void loadFormBundle(id)
  }
}

function persistCurrentForm(id: string): void {
  currentFormId.value = id
  writeCurrentHomeFormId(id)
}

async function bootstrapHomeLibrary(): Promise<void> {
  try {
    const [formsRes, typesRes, catalogRes] = await Promise.all([
      request.get<HomeFormRow[]>('/api/home/forms/'),
      request.get<HomeRoomTypeRow[]>('/api/home/room-types/'),
      request.get<CatalogDeviceRow[]>('/api/concrete-devices/', { timeout: 60000 }),
    ])
    homeForms.value = formsRes.data || []
    roomTypes.value = typesRes.data || []
    catalogDevices.value = catalogRes.data || []
    let formId = readCurrentHomeFormId()
    if (!formId || !homeForms.value.some((f) => f.form_id === formId)) {
      formId = homeForms.value[0]?.form_id || ''
    }
    if (formId) {
      persistCurrentForm(formId)
      await loadFormBundle(formId)
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('加载家居库失败')
  }
}

async function loadFormBundle(formId: string): Promise<void> {
  if (!formId) {
    homeRooms.value = []
    homePlacements.value = []
    return
  }
  const res = await request.get<{ rooms: HomeRoomRow[]; placements: HomePlacementRow[] }>(
    `/api/home/forms/${encodeURIComponent(formId)}`,
  )
  homeRooms.value = res.data.rooms || []
  homePlacements.value = res.data.placements || []
}

async function onFormSelect(id: string): Promise<void> {
  persistCurrentForm(id)
  try {
    await loadFormBundle(id)
  } catch (e) {
    console.error(e)
    ElMessage.error('加载环境表单失败')
  }
}



































































function resetResult(): void {
  result.value = null
  liveLayers.value = {}
  jobAlert.value = ''
  progressStep.value = 0
  progressHint.value = progressLayerHints[0]
  userParamValues.value = {}
  packResult.value = null
  sessionStorage.removeItem(INTENT_JOB_STORAGE_KEY)
  if (inspectView.value === 'result') {
    moduleMode.value = 'intent'
    inspectView.value = 'intent'
  }
}

function clearStepParams(stepNo: number): void {
  const prefix = `${stepNo}-`
  const next: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(userParamValues.value)) {
    if (!key.startsWith(prefix)) next[key] = val
  }
  userParamValues.value = next
  packResult.value = null
}

function seedPlaceholderValues(step: PlanStep): void {
  for (const ph of step.param_placeholders || []) {
    const key = `${step.step}-${ph.path}`
    if (ph.user_value == null || ph.user_value === '') continue
    if (userParamValues.value[key] == null || userParamValues.value[key] === '') {
      userParamValues.value[key] = ph.user_value
    }
  }
}

function seedAllStepParams(): void {
  for (const step of result.value?.final_plan?.ordered_steps || []) {
    seedPlaceholderValues(step)
  }
}

function selectedDeviceOption(step: PlanStep): StepOption | null {
  const opts = step.options ?? []
  if (!opts.length) return null
  const byDevice = opts.find((o) => o.c_instance_id && o.c_instance_id === step.c_instance_id)
  if (byDevice) return byDevice
  const selected = step.selected_uid || step.payload_uid
  const byUid = opts.find((o) => o.payload_uid === selected)
  if (byUid) return byUid
  for (const opt of opts) {
    if ((opt.command_variants ?? []).some((v) => v.payload_uid === selected)) return opt
  }
  return opts[0] ?? null
}

function currentDeviceVariants(step: PlanStep): CommandVariant[] {
  const opt = selectedDeviceOption(step)
  return opt?.command_variants?.length ? opt.command_variants : []
}

function isDeviceOptionActive(step: PlanStep, option: StepOption): boolean {
  if (step.c_instance_id && option.c_instance_id) {
    return step.c_instance_id === option.c_instance_id
  }
  const selected = step.selected_uid || step.payload_uid
  if (option.payload_uid === selected) return true
  return (option.command_variants ?? []).some((v) => v.payload_uid === selected)
}

function applyCommandFields(
  step: PlanStep,
  fields: {
    payload_uid: string
    nl_step?: string
    api_set?: unknown
    param_placeholders?: ParamPlaceholder[]
    c_instance_id?: string
    c_brand?: string
    e_id?: number | null
    e_name?: string
  },
): void {
  step.selected_uid = fields.payload_uid
  step.payload_uid = fields.payload_uid
  if (fields.c_instance_id != null) step.c_instance_id = fields.c_instance_id
  if (fields.c_brand != null) step.c_brand = fields.c_brand
  if (fields.e_id !== undefined) step.e_id = fields.e_id
  if (fields.e_name != null) step.e_name = fields.e_name
  step.nl_step = fields.nl_step || fields.payload_uid
  step.api_set = fields.api_set
  step.param_placeholders = fields.param_placeholders || []
  clearStepParams(step.step)
  seedPlaceholderValues(step)
}

function selectStepDevice(step: PlanStep, option: StepOption): void {
  const variants = option.command_variants ?? []
  const recommended =
    variants.find((v) => v.is_recommended) ||
    variants.find((v) => v.payload_uid === option.payload_uid) ||
    variants[0]
  if (recommended) {
    applyCommandFields(step, {
      payload_uid: recommended.payload_uid,
      nl_step: recommended.nl_step,
      api_set: recommended.api_set,
      param_placeholders: recommended.param_placeholders,
      c_instance_id: option.c_instance_id,
      c_brand: option.c_brand,
      e_id: option.e_id,
      e_name: option.e_name,
    })
    return
  }
  applyCommandFields(step, {
    payload_uid: option.payload_uid,
    nl_step: option.nl_step,
    api_set: option.api_set,
    param_placeholders: option.param_placeholders,
    c_instance_id: option.c_instance_id,
    c_brand: option.c_brand,
    e_id: option.e_id,
    e_name: option.e_name,
  })
}

function selectStepCommandVariant(step: PlanStep, variant: CommandVariant): void {
  const device = selectedDeviceOption(step)
  applyCommandFields(step, {
    payload_uid: variant.payload_uid,
    nl_step: variant.nl_step,
    api_set: variant.api_set,
    param_placeholders: variant.param_placeholders,
    c_instance_id: device?.c_instance_id ?? step.c_instance_id,
    c_brand: device?.c_brand ?? step.c_brand,
    e_id: device?.e_id ?? step.e_id,
    e_name: device?.e_name ?? step.e_name,
  })
}

function formatParamValue(p: PackedUserParam): string {
  const val = p.value
  if (val == null) return ''
  const unit = p.unit
  if (unit === 'celsius') return `${val}℃`
  if (unit === 'percentage') return `${val}%`
  return String(val)
}

function formatJson(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

async function copyApiSet(apiSet: unknown): Promise<void> {
  const text = formatJson(apiSet)
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('api_set 已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function copyPackedAll(): Promise<void> {
  if (!packResult.value?.packed_api_set) return
  const text = formatJson(packResult.value.packed_api_set)
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('完整 API 指令集已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function runPack(): Promise<void> {
  if (!result.value?.final_plan) {
    ElMessage.warning('请先完成意图解析')
    return
  }
  packing.value = true
  packResult.value = null
  try {
    const res = await request.post<PackResult>(
      '/api/intent/pack/',
      {
        trace_id: result.value.trace_id,
        intent_text: result.value.intent_text || intentText.value.trim(),
        final_plan: result.value.final_plan,
        user_param_values: userParamValues.value,
      },
      { timeout: 60000 },
    )
    packResult.value = res.data
    if (res.data.success) {
      ElMessage.success(res.data.message || 'API 指令集已生成')
    } else {
      ElMessage.warning(res.data.message || '请补全参数后重试')
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('指令打包失败')
  } finally {
    packing.value = false
  }
}

async function pollIntentJob(jobId: string): Promise<IntentJobSnapshot> {
  pollAborted = false
  while (!pollAborted) {
    const poll = await request.get<IntentJobSnapshot>(`/api/intent/jobs/${jobId}`, { timeout: 15000 })
    applyJobSnapshot(poll.data)
    if (poll.data.status !== 'queued' && poll.data.status !== 'running') {
      sessionStorage.removeItem(INTENT_JOB_STORAGE_KEY)
      return poll.data
    }
    await sleep(INTENT_POLL_MS)
  }
  throw new Error('作业轮询已取消')
}

async function resumeIntentJobIfAny(): Promise<void> {
  const jobId = sessionStorage.getItem(INTENT_JOB_STORAGE_KEY)
  if (!jobId) return
  resolving.value = true
  jobAlert.value = ''
  try {
    const snap = await pollIntentJob(jobId)
    if (snap.result) {
      applyResolveResult(snap.result)
    }
    if (snap.status === 'failed') {
      jobAlert.value = snap.message || '意图实现失败'
      ElMessage.error(jobAlert.value)
      return
    }
    if (snap.result?.stopped_at) {
      ElMessage.warning(snap.result.message || '推理中途停止')
    } else if (snap.result) {
      ElMessage.success(snap.result.message || '意图实现完成')
    }
  } catch (e) {
    sessionStorage.removeItem(INTENT_JOB_STORAGE_KEY)
    if (httpStatus(e) === 404) {
      jobAlert.value = '作业丢失，请重新解析'
      ElMessage.warning(jobAlert.value)
      return
    }
    ElMessage.error(httpDetail(e) || '恢复意图实现失败')
  } finally {
    resolving.value = false
  }
}

async function runResolve(): Promise<void> {
  const text = intentText.value.trim()
  if (!text) {
    ElMessage.warning('请先输入自然语言意图')
    return
  }
  if (!selectedSources.value.length) {
    ElMessage.warning('请至少选择一个参与实现的智能家居生态来源')
    return
  }
  if (!currentFormId.value) {
    ElMessage.warning('请先选择环境表单并实例化设备')
    return
  }
  if (!homePlacements.value.length) {
    ElMessage.warning('请先选择环境表单并实例化设备')
    return
  }
  resolving.value = true
  progressStep.value = 0
  progressHint.value = progressLayerHints[0]
  result.value = null
  liveLayers.value = {}
  jobAlert.value = ''
  packResult.value = null
  inspectView.value = 'result'
  moduleMode.value = 'intent'
  cmdDrawerVisible.value = false
  await nextTick()

  try {
    const created = await request.post<IntentJobSnapshot>(
      '/api/intent/jobs/',
      {
        intent_text: text,
        options: {
          filter_objects_by_l1: true,
          filter_effects_by_l2: true,
          filter_commands_by_l3: true,
          timeout_per_layer_ms: 180000,
          resolve_mode: resolveMode.value,
          max_options_per_step: 5,
          allowed_sources: [...selectedSources.value],
          home_form_id: currentFormId.value,
        },
      },
      { timeout: 15000 },
    )
    if (created.data?.job_id) {
      sessionStorage.setItem(INTENT_JOB_STORAGE_KEY, created.data.job_id)
    }
    applyJobSnapshot(created.data)
    const snap = await pollIntentJob(created.data.job_id)
    if (snap.result) {
      applyResolveResult(snap.result)
    }
    if (snap.status === 'failed') {
      jobAlert.value = snap.message || '意图实现失败'
      ElMessage.error(jobAlert.value)
      return
    }
    if (snap.result?.stopped_at) {
      ElMessage.warning(snap.result.message || '推理中途停止')
    } else {
      ElMessage.success(snap.result?.message || '意图实现完成')
    }
  } catch (e) {
    console.error(e)
    const status = httpStatus(e)
    if (status === 404) {
      sessionStorage.removeItem(INTENT_JOB_STORAGE_KEY)
      jobAlert.value = '作业丢失，请重新解析'
      ElMessage.warning(jobAlert.value)
    } else if (status === 409) {
      ElMessage.warning(httpDetail(e) || '已有意图实现作业在运行')
    } else {
      ElMessage.error(httpDetail(e) || '意图实现失败，请检查后端与模型配置')
    }
  } finally {
    resolving.value = false
  }
}
</script>

<style scoped>
.tree-item--mode {
  border-bottom: 1px solid var(--ui-line-soft);
  font-weight: 600;
  padding-top: 10px;
  padding-bottom: 10px;
}

.intent-dock {
  display: flex;
  flex: 1;
  min-height: 0;
  height: 100%;
  background: var(--ui-page);
}

.pane-console .intent-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
  border: 0;
}

.result-board {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.result-scroll {
  padding: 12px 16px 28px;
}

.intent-console-body {
  max-width: 640px;
  padding: 16px 20px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.progress-list {
  margin-top: 4px;
  border-top: 1px solid var(--ui-line-soft);
  padding-top: 8px;
}

.progress-list__item {
  padding: 6px 0;
  border-bottom: 1px solid var(--ui-line-soft);
  font-size: 12px;
  color: #8a8a8a;
}

.progress-list__item.is-on {
  color: #111;
  font-weight: 600;
}

.console-alert {
  margin: 8px 0 0;
  font-size: 12px;
  color: #7a5a1e;
  line-height: 1.45;
}

.cmd-inline {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.cmd-inline__h {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--ui-line);
}

.cmd-inline__back {
  font: inherit;
  font-size: 12px;
  padding: 4px 8px;
  cursor: pointer;
  background: #fff;
  color: #111;
  border: 1px solid #111;
}

.intent-layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: calc(100vh - 24px);
  padding: 12px;
  box-sizing: border-box;
}

.module-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.module-nav__btn {
  margin-left: 0;
}

.module-nav__btn.module-nav__btn--current,
.module-nav__btn.module-nav__btn--current:disabled {
  background: #303133;
  border-color: #303133;
  color: #fff;
}

.intent-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.home-lib-card {
  border: 0;
  height: 100%;
  overflow: auto;
}

.home-lib-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}

.home-lib-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.home-lib-tabs {
  margin-top: 4px;
}

.cmd-filter-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 8px 12px;
  background: #fff;
}

.cmd-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 14px 24px;
}

.cmd-editor__section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cmd-editor__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.cmd-card {
  border: 1px solid var(--ui-line-soft);
  border-radius: 0;
  padding: 10px 12px 12px;
  background: #fff;
}

.cmd-card--strategy {
  border-style: dashed;
  border-color: #67c23a;
}

.cmd-card--off {
  background: #fafafa;
  border-color: #fbc4c4;
}

.cmd-card--picked {
  border-color: #111;
  background: #ececec;
}

.cmd-card__check {
  margin-top: 4px;
  flex-shrink: 0;
}

.cmd-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.cmd-card__title-wrap {
  min-width: 0;
  flex: 1;
}

.cmd-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  word-break: break-all;
}

.cmd-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.cmd-card__weight {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.cmd-card__weight-label {
  font-size: 12px;
  color: #909399;
}

.cmd-card__desc,
.cmd-card__meta,
.cmd-card__warn {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
}

.cmd-card__desc {
  color: #303133;
  white-space: pre-wrap;
}

.cmd-card__warn {
  color: #e6a23c;
}

.cmd-card__desc-input {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.cmd-card__desc-input span {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.cmd-card__steps {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cmd-step {
  padding: 8px 0;
  border-bottom: 1px solid var(--ui-line-soft);
}

.cmd-step__main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.cmd-step__uid {
  font-size: 13px;
  color: #303133;
  word-break: break-all;
}

.cmd-step__effect {
  font-size: 12px;
  color: #5a5a5a;
}

.cmd-step__follow {
  font-size: 12px;
  color: #909399;
}

.cmd-step__desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.cmd-step__weight {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

.muted {
  color: #909399;
  font-size: 13px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.intent-input-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.intent-actions {
  display: flex;
  flex-direction: row;
  gap: 8px;
}

.intent-actions .el-button {
  margin-left: 0;
  width: auto;
  min-width: 96px;
}

.intent-console-body .seg {
  width: 100%;
}

.intent-console-body .seg button {
  flex: 1;
}

.resolve-mode-row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}

.resolve-mode-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.resolve-mode-group :deep(.el-radio) {
  margin-right: 0;
  height: auto;
  white-space: normal;
  align-items: flex-start;
}

.resolve-mode-label {
  font-size: 13px;
  color: #606266;
  font-weight: 600;
}

.mode-tag {
  margin-left: 8px;
  vertical-align: middle;
}

.step-options {
  margin: 8px 0 12px;
}

.step-options__hint {
  color: #e6a23c;
  font-weight: normal;
  margin-left: 6px;
}

.step-options__row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.step-option-card {
  min-width: 0;
  max-width: none;
  width: 100%;
  text-align: left;
  border: 1px solid var(--ui-line-soft);
  border-radius: 0;
  padding: 10px 12px;
  background: #fff;
  cursor: pointer;
  position: relative;
}

.step-option-card:hover {
  border-color: #111;
}

.step-option-card--active {
  border-color: #111;
  background: #ececec;
}

.step-option-card__badge {
  position: absolute;
  top: 6px;
  right: 8px;
  font-size: 11px;
  color: #111;
  font-weight: 600;
}

.step-option-card__brand {
  display: block;
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
  padding-right: 36px;
}

.step-option-card__weight {
  display: block;
  font-size: 12px;
  color: #5a5a5a;
  margin-bottom: 4px;
  font-weight: 600;
}

.step-option-card__effect {
  display: block;
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
}

.step-option-card__nl {
  display: block;
  font-size: 12px;
  color: #303133;
  line-height: 1.4;
}

.step-option-card__goal {
  display: block;
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f4f4f5;
  font-size: 11px;
  color: #606266;
  line-height: 1.45;
}

.step-option-card__reason {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  color: #909399;
}

.step-option-card__variants-hint {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  color: #67c23a;
}

.step-option-card--variant {
  min-width: 0;
  max-width: none;
  background: #fff;
}

.step-variants {
  margin: 10px 0 12px;
  padding: 10px;
  border: 1px dashed var(--ui-line-soft);
  border-radius: 0;
  background: #f7f7f5;
}

.plan-step__intent {
  color: #303133;
  font-size: 14px;
}

.plan-step__head--selected {
  margin-top: 4px;
}

.progress-bar {
  margin-top: 18px;
}

.progress-hint {
  margin: 10px 0 0;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.result-alert {
  margin-top: 16px;
}

.layer-collapse {
  margin-top: 14px;
}

.layer-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.layer-meta,
.muted {
  color: #909399;
  font-size: 13px;
}

.layer-error {
  color: #f56c6c;
}

.layer-stop {
  color: #e6a23c;
}

.node-tags {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.node-chip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.node-tag {
  max-width: 100%;
}

.node-meta {
  font-size: 12px;
  color: #909399;
}

.sub-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.param-fill-row {
  margin-bottom: 10px;
  padding: 8px 10px;
  border: 1px solid var(--ui-line-soft);
  border-radius: 0;
  background: #fff;
}

.param-fill-label {
  margin-bottom: 4px;
}

.param-fill-unit {
  color: #909399;
  font-size: 12px;
  margin-left: 4px;
}

.param-fill-hint,
.param-fill-desc {
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
  line-height: 1.5;
}

.param-fill-desc {
  color: #303133;
}

.relations ul,
.placeholders ul {
  margin: 0;
  padding-left: 18px;
}

.guidance p {
  margin: 0;
  white-space: pre-wrap;
}

.invalid {
  color: #909399;
  font-size: 12px;
}

.final-plan {
  margin-top: 20px;
  border-top: 1px solid #ebeef5;
  padding-top: 14px;
}

.final-plan h3 {
  margin: 0 0 8px;
}

.plan-summary {
  font-size: 15px;
  margin: 0 0 6px;
}

.plan-guidance {
  color: #606266;
  margin: 0 0 14px;
}

.plan-step {
  border: 0;
  border-bottom: 1px solid var(--ui-line-soft);
  padding: 14px 0;
  margin-bottom: 0;
  background: transparent;
}

.plan-step__head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
}

.plan-step__no {
  font-weight: 700;
}

.plan-step__brand {
  color: #303133;
}

.plan-step__effect {
  color: #606266;
  font-size: 13px;
}

.plan-step__nl {
  margin: 0 0 6px;
}

.plan-step__uid {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  word-break: break-all;
}

.api-block__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 4px;
}

.api-block__body {
  margin: 0;
  padding: 10px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  text-align: left;
}

.api-block__body--tall {
  max-height: 360px;
}

.pack-section {
  margin-top: 20px;
  border-top: 1px solid #ebeef5;
  padding-top: 14px;
}

.pack-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.pack-section__head h3 {
  margin: 0;
}

.pack-section__hint {
  margin: 8px 0 12px;
  color: #606266;
  font-size: 13px;
}

.pack-alert {
  margin-bottom: 12px;
}

.pack-errors {
  margin: 6px 0 0;
  padding-left: 18px;
}

.packed-result {
  margin-top: 12px;
}

.packed-result__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.packed-log {
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}

.packed-actions {
  margin-bottom: 12px;
}

.packed-step {
  border: 0;
  border-bottom: 1px solid var(--ui-line-soft);
  padding: 12px 0;
  margin-bottom: 0;
  background: transparent;
}

.packed-step__desc {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}

.packed-step__params ul {
  margin: 0 0 8px;
  padding-left: 18px;
  font-size: 13px;
}

.packed-all {
  margin-top: 12px;
}
</style>
