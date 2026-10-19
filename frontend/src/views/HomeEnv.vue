<template>
  <div class="intent-dock">
    <aside class="pane-tree">
      <div class="pane-h">
        <el-select
          v-model="currentFormId"
          filterable
          placeholder="环境表单"
          style="width: 100%"
          :disabled="resolving"
          @change="onFormSelect"
        >
          <el-option v-for="f in homeForms" :key="f.form_id" :label="f.name" :value="f.form_id" />
        </el-select>
      </div>
      <div class="pane-h">
        <el-input v-model="newFormName" placeholder="新表单" :disabled="resolving" />
        <el-button :disabled="resolving" @click="createHomeForm">新建</el-button>
        <el-button :disabled="resolving || !currentFormId" @click="renameHomeForm">改名</el-button>
        <el-button type="danger" plain :disabled="resolving || homeForms.length <= 1" @click="deleteHomeForm">
          删除
        </el-button>
      </div>
      <button type="button" class="tree-item" :class="{ 'is-on': inspectView === 'home' }" @click="showHomeInspect">
        家居库
      </button>
      <div v-for="room in treeRooms" :key="room.room_id">
        <div class="tree-group">{{ room.label }}</div>
        <button
          v-for="p in room.items"
          :key="p.placement_id"
          type="button"
          class="tree-item"
          :class="{ 'is-on': inspectView === 'commands' && cmdDrawerPlacementId === p.placement_id }"
          @click="openPlacementCommands(p)"
        >
          <span>{{ p.display_name }}</span>
          <b>{{ p.weight }}</b>
        </button>
      </div>
      <div v-if="unplacedPlacements.length" class="tree-group">未挂房间</div>
      <button
        v-for="p in unplacedPlacements"
       
        :key="p.placement_id"
        type="button"
        class="tree-item"
        :class="{ 'is-on': inspectView === 'commands' && cmdDrawerPlacementId === p.placement_id }"
        @click="openPlacementCommands(p)"
      >
        <span>{{ p.display_name }}</span>
        <b>{{ p.weight }}</b>
      </button>
      <div class="pane-h">
        <el-button type="primary" :disabled="!currentFormId" @click="openAddPlacement">实例化</el-button>
      </div>
    </aside>

    <section class="pane-inspect">
      <div v-show="inspectView === 'home'" class="home-board">
        <div class="pane-h">
          <h1>家居库</h1>
          <div class="seg">
            <button type="button" :class="{ 'is-on': homeLibTab === 'types' }" @click="homeLibTab = 'types'">种类</button>
            <button type="button" :class="{ 'is-on': homeLibTab === 'rooms' }" @click="homeLibTab = 'rooms'">房间</button>
            <button type="button" :class="{ 'is-on': homeLibTab === 'devices' }" @click="homeLibTab = 'devices'">设备</button>
          </div>
        </div>
        <div class="board-scroll home-lib-body">
          <template v-if="homeLibTab === 'types'">
            <div class="home-lib-toolbar">
              <el-input v-model="newRoomTypeName" placeholder="自定义种类名，如影音室" style="width: 220px" />
              <el-button type="primary" @click="createRoomType">登记种类</el-button>
            </div>
            <el-table :data="roomTypes" size="small" empty-text="暂无房间种类">
              <el-table-column prop="name" label="种类名" min-width="140" />
              <el-table-column label="来源" width="90">
                <template #default="scope">
                  <span class="mark">{{ scope.row.is_preset ? '预设' : '自定义' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="scope">
                  {{ scope.row.is_active ? '启用' : '停用' }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180">
                <template #default="scope">
                  <el-button
                    v-if="!scope.row.is_preset"
                    link
                    type="primary"
                    @click="renameRoomType(scope.row)"
                  >
                    改名
                  </el-button>
                  <el-button link @click="toggleRoomType(scope.row)">
                    {{ scope.row.is_active ? '停用' : '启用' }}
                  </el-button>
                  <el-button
                    v-if="!scope.row.is_preset"
                    link
                    type="danger"
                    @click="deleteRoomType(scope.row)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template v-else-if="homeLibTab === 'rooms'">
            <div class="home-lib-toolbar">
              <el-select v-model="newRoomTypeId" placeholder="选择种类" filterable style="width: 180px">
                <el-option
                  v-for="t in activeRoomTypes"
                  :key="t.type_id"
                  :label="t.name"
                  :value="t.type_id"
                />
              </el-select>
              <el-input v-model="newRoomLabel" placeholder="实例名，如主卧（可空则用种类名）" style="width: 240px" />
              <el-button type="primary" :disabled="!currentFormId" @click="createRoom">添加房间</el-button>
            </div>
            <el-table :data="homeRooms" size="small" empty-text="当前表单还没有房间；设备可不挂房间">
              <el-table-column prop="label" label="房间名" min-width="140" />
              <el-table-column prop="type_name" label="种类" width="120" />
              <el-table-column label="操作" width="160">
                <template #default="scope">
                  <el-button link type="primary" @click="renameRoom(scope.row)">改名</el-button>
                  <el-button link type="danger" @click="deleteRoom(scope.row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template v-else>
            <div class="home-lib-toolbar">
              <el-button type="primary" :disabled="!currentFormId" @click="openAddPlacement">从设备库实例化</el-button>
              <span v-if="selectedPlacements.length" class="mark">已选 {{ selectedPlacements.length }} 台</span>
              <el-input-number v-model="bulkDeviceWeight" :min="1" :max="5" size="small" :disabled="!selectedPlacements.length" />
              <el-button :disabled="!selectedPlacements.length" :loading="bulkApplying" @click="applySelectedDeviceWeight">
                批量设设备权重
              </el-button>
              <el-button :disabled="!selectedPlacements.length" :loading="bulkApplying" @click="applySelectedCommandWeight(1)">
                指令全部参与
              </el-button>
              <el-button :disabled="!selectedPlacements.length" :loading="bulkApplying" @click="applySelectedCommandWeight(0)">
                指令全部不参与
              </el-button>
            </div>
            <el-table
              :data="homePlacements"
              size="small"
              empty-text="请从能力库挑选设备，实例化进当前表单"
              row-key="placement_id"
              @selection-change="onPlacementSelection"
            >
              <el-table-column type="selection" width="48" />
              <el-table-column prop="display_name" label="实例名称" min-width="180" />
              <el-table-column prop="c_brand" label="能力库型号" min-width="140" show-overflow-tooltip />
              <el-table-column label="房间" width="140">
                <template #default="scope">
                  <el-select
                    :model-value="scope.row.room_id ?? undefined"
                    clearable
                    placeholder="不挂房间"
                    size="small"
                    @change="(v: number | undefined) => updatePlacementRoom(scope.row, v)"
                  >
                    <el-option v-for="r in homeRooms" :key="r.room_id" :label="r.label" :value="r.room_id" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="别名" min-width="140">
                <template #default="scope">
                  <el-input
                    :model-value="scope.row.alias"
                    size="small"
                    @change="(v: string) => updatePlacementAlias(scope.row, v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="权重" width="120">
                <template #default="scope">
                  <el-input-number
                    :model-value="scope.row.weight"
                    :min="1"
                    :max="5"
                    size="small"
                    controls-position="right"
                    @change="(v: number | undefined) => updatePlacementWeight(scope.row, v ?? 1)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="偏好描述" min-width="160">
                <template #default="scope">
                  <el-input
                    :model-value="scope.row.preference_desc || ''"
                    size="small"
                    placeholder="可选"
                    @change="(v: string) => updatePlacementDesc(scope.row, v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="160" fixed="right">
                <template #default="scope">
                  <el-button link type="primary" @click="openPlacementCommands(scope.row)">指令权重</el-button>
                  <el-button link type="danger" @click="removePlacement(scope.row)">移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </div>
      </div>
      <el-dialog v-model="addPlacementVisible" title="从设备库实例化" width="960px" destroy-on-close>
        <div class="device-filters catalog-filters">
          <label class="field">
            <span>名称或实例 ID</span>
            <el-input v-model="catalogKeyword" clearable placeholder="设备名称或实例 ID" />
          </label>
          <label class="field">
            <span>生态</span>
            <el-select v-model="catalogSources" multiple collapse-tags collapse-tags-tooltip placeholder="生态来源">
              <el-option
                v-for="item in deviceSourceOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </label>
          <label class="field">
            <span>抽象设备</span>
            <el-select v-model="catalogARef" clearable filterable placeholder="抽象设备类型">
              <el-option
                v-for="item in catalogAbstractOptions"
                :key="item"
                :label="item === CATALOG_PENDING_A_REF ? '待确认类目' : item"
                :value="item"
              />
            </el-select>
          </label>
          <label class="field">
            <span>环境属性</span>
            <el-select
              v-model="catalogEnvFilters"
              multiple
              :collapse-tags="catalogCollapseEnvTags"
              collapse-tags-tooltip
              filterable
              placeholder="环境属性"
              class="catalog-env-filter-select"
            >
              <el-option
                v-for="env in catalogEnvAttributes"
                :key="env.env_id"
                :label="env.env_name"
                :value="env.env_id"
              />
            </el-select>
          </label>
          <div class="field">
            <span>环境匹配</span>
            <div class="seg">
              <button type="button" :class="{ 'is-on': catalogEnvMode === 'union' }" @click="catalogEnvMode = 'union'">并集</button>
              <button type="button" :class="{ 'is-on': catalogEnvMode === 'intersection' }" @click="catalogEnvMode = 'intersection'">交集</button>
            </div>
          </div>
          <div class="field">
            <span>筛选</span>
            <el-button @click="clearCatalogFilters">清空筛选</el-button>
          </div>
        </div>
        <div class="home-lib-toolbar">
          <el-select v-model="addPlacementRoomId" clearable placeholder="可选：挂到房间" style="width: 200px">
            <el-option v-for="r in homeRooms" :key="r.room_id" :label="r.label" :value="r.room_id" />
          </el-select>
          <el-input-number v-model="addPlacementWeight" :min="1" :max="5" size="small" />
        </div>
        <el-table
          :key="catalogPickerKey"
          :data="filteredCatalogDevices"
          size="small"
          max-height="360"
          row-key="c_instance_id"
          empty-text="没有符合筛选的设备"
          @selection-change="onCatalogSelection"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="c_brand" label="设备名称" min-width="180" />
          <el-table-column prop="c_instance_id" label="实例 ID" min-width="200" show-overflow-tooltip />
          <el-table-column label="类目" width="140">
            <template #default="scope">
              {{ scope.row.a_ref || '待确认类目' }}
            </template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button @click="addPlacementVisible = false">取消</el-button>
          <el-button type="primary" :loading="addingPlacements" @click="confirmAddPlacements">实例化到当前表单</el-button>
        </template>
      </el-dialog>
      <div v-show="inspectView === 'commands'" class="cmd-inline">
        <header class="cmd-inline__h">
          <button type="button" class="cmd-inline__back" @click="closeCommandInspect">返回家居库</button>
          <strong>{{ cmdDrawerTitle }}</strong>
        </header>
        <div class="pane-h cmd-filter-bar" v-loading="cmdDrawerLoading">
          <div class="seg">
            <button type="button" :class="{ 'is-on': cmdKindFilter === 'all' }" @click="cmdKindFilter = 'all'">全部</button>
            <button type="button" :class="{ 'is-on': cmdKindFilter === 'recipe' }" @click="cmdKindFilter = 'recipe'">配方</button>
            <button type="button" :class="{ 'is-on': cmdKindFilter === 'effect' }" @click="cmdKindFilter = 'effect'">效果</button>
            <button type="button" :class="{ 'is-on': cmdKindFilter === 'strategy' }" @click="cmdKindFilter = 'strategy'">策略</button>
          </div>
          <span v-if="selectedCmdKeys.length" class="mark">已选 {{ selectedCmdKeys.length }}</span>
          <el-button size="small" :disabled="!visibleCmdKeys.length" @click="selectVisibleCmds">全选当前</el-button>
          <el-button size="small" :disabled="!selectedCmdKeys.length" @click="clearCmdSelection">取消选择</el-button>
          <el-input-number v-model="cmdBatchWeight" :min="0" :max="5" size="small" />
          <el-button size="small" :disabled="!selectedCmdKeys.length" @click="applySelectedCardWeight(cmdBatchWeight)">
            设为该权
          </el-button>
          <el-button size="small" :disabled="!selectedCmdKeys.length" @click="applySelectedCardWeight(1)">
            参与
          </el-button>
          <el-button size="small" :disabled="!selectedCmdKeys.length" @click="applySelectedCardWeight(0)">
            不参与
          </el-button>
        </div>

        <div v-loading="cmdDrawerLoading" class="cmd-editor">
          <section v-if="visibleRecipeCards.length" class="cmd-editor__section">
            <h4 class="cmd-editor__title">可执行配方（{{ visibleRecipeCards.length }}）</h4>
            <article
              v-for="recipe in visibleRecipeCards"
              :key="recipe.recipe_uid"
              class="cmd-row"
              :class="{
                'is-on': isCmdSelected(recipeKey(recipe.recipe_uid)),
                'is-off': recipe.effective_weight <= 0,
              }"
            >
              <el-checkbox
                :model-value="isCmdSelected(recipeKey(recipe.recipe_uid))"
                @change="(v: boolean | string | number) => toggleCmdKey(recipeKey(recipe.recipe_uid), Boolean(v))"
              />
              <div>
                <div class="cmd-row__name">{{ recipe.recipe_name }}</div>
                <p class="cmd-row__meta">
                  {{ recipe.is_strategy ? '场景策略' : '效果配方' }}
                  <template v-if="recipe.effective_weight <= 0"> · 不参与</template>
                  <template v-if="recipe.cover_effect_names?.length"> · {{ recipe.cover_effect_names.join('、') }}</template>
                </p>
                <p v-if="recipe.recipe_desc" class="cmd-row__desc">{{ recipe.recipe_desc }}</p>
                <p v-if="recipe.daily_use" class="cmd-row__meta">日常：{{ recipe.daily_use }}</p>
                <ul class="cmd-card__steps">
                  <li v-for="step in recipe.steps" :key="`${recipe.recipe_uid}-${step.uid}`" class="cmd-step">
                    <div class="cmd-step__main">
                      <span class="mark">{{ step.kind_label || step.role_label }}</span>
                      <span class="cmd-step__uid" :title="step.uid">{{ step.uid }}</span>
                      <span v-if="step.e_name" class="cmd-step__effect">{{ step.e_name }}</span>
                    </div>
                    <p v-if="step.capability_desc" class="cmd-step__desc">{{ step.capability_desc }}</p>
                    <p v-if="step.param_labels?.length" class="cmd-step__desc">参数槽：{{ step.param_labels.join('、') }}</p>
                    <div v-if="step.weight_editable" class="cmd-step__weight">
                      <span>步骤权重</span>
                      <el-input-number
                        :model-value="step.weight ?? 1"
                        :min="0"
                        :max="5"
                        size="small"
                        controls-position="right"
                        @change="(v: number | undefined) => saveCommandUid(step.uid, v ?? 0)"
                      />
                    </div>
                  </li>
                </ul>
              </div>
              <el-input-number
                :model-value="recipe.effective_weight"
                :min="0"
                :max="5"
                size="small"
                controls-position="right"
                :disabled="!recipe.weight_payload_uids.length"
                @change="(v: number | undefined) => saveRecipeWeight(recipe, v ?? 0)"
              />
            </article>
          </section>

          <section v-if="visibleUncoveredCommands.length" class="cmd-editor__section">
            <h4 class="cmd-editor__title">未被配方覆盖的效果 / 策略（{{ visibleUncoveredCommands.length }}）</h4>
            <article
              v-for="cmd in visibleUncoveredCommands"
              :key="cmd.payload_uid"
              class="cmd-row"
              :class="{
                'is-on': isCmdSelected(atomKey(cmd.payload_uid)),
                'is-off': cmd.weight <= 0,
              }"
            >
              <el-checkbox
                :model-value="isCmdSelected(atomKey(cmd.payload_uid))"
                @change="(v: boolean | string | number) => toggleCmdKey(atomKey(cmd.payload_uid), Boolean(v))"
              />
              <div>
                <div class="cmd-row__name" :title="cmd.payload_uid">{{ cmd.payload_uid }}</div>
                <p class="cmd-row__meta">
                  {{ cmd.kind_label || cmd.capability_kind }}
                  <template v-if="cmd.weight <= 0"> · 不参与</template>
                  <template v-if="cmd.e_name || cmd.e_id != null"> · {{ cmd.e_name || `效果#${cmd.e_id}` }}</template>
                </p>
                <p v-if="cmd.capability_desc" class="cmd-row__desc">{{ cmd.capability_desc }}</p>
                <p v-if="cmd.supports_effect_names?.length" class="cmd-row__meta">
                  {{ cmd.capability_kind === 'strategy' ? '可能有关：' : '可被引用：' }}{{ cmd.supports_effect_names.join('、') }}
                </p>
                <p v-if="cmd.env_names?.length" class="cmd-row__meta">影响环境：{{ cmd.env_names.join('、') }}</p>
                <div class="cmd-card__desc-input">
                  <span>偏好描述</span>
                  <el-input
                    :model-value="cmd.preference_desc || ''"
                    size="small"
                    placeholder="可选"
                    @change="(v: string) => saveCommandUid(cmd.payload_uid, cmd.weight, v)"
                  />
                </div>
              </div>
              <el-input-number
                :model-value="cmd.weight"
                :min="0"
                :max="5"
                size="small"
                controls-position="right"
                @change="(v: number | undefined) => saveCommandUid(cmd.payload_uid, v ?? 0, cmd.preference_desc)"
              />
            </article>
          </section>

          <el-empty
            v-if="!cmdDrawerLoading && !visibleRecipeCards.length && !visibleUncoveredCommands.length"
            description="当前筛选下没有可设权的配方或效果/策略"
          />
        </div>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onUnmounted, onMounted, nextTick, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import request from '../api/request'
import { DEVICE_SOURCE_OPTIONS, defaultSelectedSources, normalizeDeviceSource } from '../constants/deviceSources'
import {
  HOME_FORM_CHANGED_EVENT,
  readCurrentHomeFormId,
  writeCurrentHomeFormId,
} from '../constants/homeForm'





























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

interface HomeCommandRow {
  placement_id: string
  payload_uid: string
  weight: number
  preference_desc?: string | null
  e_id?: number | null
  e_name?: string
  capability_kind?: string | null
  kind_label?: string
  capability_desc?: string | null
  env_impact?: number[]
  env_names?: string[]
  supports_e_ids?: number[]
  supports_effect_names?: string[]
  covered_by_recipes?: string[]
  param_labels?: string[]
}

interface HomeRecipeStepCard {
  uid: string
  role: string
  role_label: string
  capability_kind: string
  kind_label: string
  capability_desc?: string | null
  e_id?: number | null
  e_name: string
  weight_editable: boolean
  weight?: number | null
  shared_recipe_names: string[]
  param_labels: string[]
}

interface HomeRecipeWeightCard {
  recipe_uid: string
  recipe_name: string
  recipe_desc?: string | null
  daily_use?: string | null
  is_strategy: boolean
  shadowed: boolean
  shadowed_by: string[]
  cover_effect_names: string[]
  steps: HomeRecipeStepCard[]
  effective_weight: number
  weight_payload_uids: string[]
}

interface HomeCommandEditor {
  placement_id: string
  commands: HomeCommandRow[]
  recipes: HomeRecipeWeightCard[]
  uncovered_payload_uids: string[]
}

type CmdKindFilter = 'all' | 'recipe' | 'effect' | 'strategy'

interface CatalogDeviceRow {
  c_instance_id: string
  c_brand: string
  a_ref?: string | null
  env_set?: number[]
  source?: number
}

interface CatalogEnvAttribute {
  env_id: number
  env_name: string
}

const CATALOG_PENDING_A_REF = '__pending_class__'







/** 参与本次寻址的生态来源；默认全选，选项见 constants/deviceSources */

const deviceSourceOptions = DEVICE_SOURCE_OPTIONS
const resolving = ref(false)










const homeLibTab = ref('devices')
const homeForms = ref<HomeFormRow[]>([])
const currentFormId = ref('')
const newFormName = ref('')
const roomTypes = ref<HomeRoomTypeRow[]>([])
const homeRooms = ref<HomeRoomRow[]>([])
const homePlacements = ref<HomePlacementRow[]>([])
const newRoomTypeName = ref('')
const newRoomTypeId = ref<number | undefined>()
const newRoomLabel = ref('')
const catalogDevices = ref<CatalogDeviceRow[]>([])
const catalogKeyword = ref('')
const catalogSources = ref<number[]>(defaultSelectedSources())
const catalogARef = ref('')
const catalogEnvFilters = ref<number[]>([])
const catalogEnvMode = ref<'union' | 'intersection'>('union')
const catalogEnvAttributes = ref<CatalogEnvAttribute[]>([])
const catalogCollapseEnvTags = ref(false)
const addPlacementVisible = ref(false)
const catalogPickerKey = ref(0)
const addPlacementRoomId = ref<number | undefined>()
const addPlacementWeight = ref(1)
const addingPlacements = ref(false)
const selectedCatalogIds = ref<string[]>([])
const cmdDrawerVisible = ref(false)
const inspectView = ref<'home' | 'intent' | 'commands' | 'result'>('home')
const moduleMode = ref<'env' | 'intent'>('env')
const cmdDrawerLoading = ref(false)
const cmdDrawerTitle = ref('指令权重')
const cmdDrawerPlacementId = ref('')
const commandEditor = ref<HomeCommandEditor | null>(null)
const cmdKindFilter = ref<CmdKindFilter>('all')
const cmdBatchWeight = ref(1)
const selectedCmdKeys = ref<string[]>([])
const selectedPlacements = ref<HomePlacementRow[]>([])
const bulkDeviceWeight = ref(1)
const bulkApplying = ref(false)

const activeRoomTypes = computed(() => roomTypes.value.filter((t) => t.is_active))

const catalogAbstractOptions = computed(() => {
  const sourceRows = catalogDevices.value.filter((row) =>
    catalogSources.value.includes(normalizeDeviceSource(row.source)),
  )
  const names = Array.from(new Set(sourceRows.map((row) => row.a_ref).filter((name): name is string => !!name))).sort(
    (a, b) => a.localeCompare(b),
  )
  const hasPending = sourceRows.some((row) => !row.a_ref)
  return hasPending ? [CATALOG_PENDING_A_REF, ...names] : names
})

const filteredCatalogDevices = computed(() =>
  catalogDevices.value.filter((row) => {
    const keyword = catalogKeyword.value.trim().toLowerCase()
    if (keyword) {
      const name = (row.c_brand || '').toLowerCase()
      const id = (row.c_instance_id || '').toLowerCase()
      if (!name.includes(keyword) && !id.includes(keyword)) return false
    }
    if (!catalogSources.value.includes(normalizeDeviceSource(row.source))) return false
    if (catalogARef.value === CATALOG_PENDING_A_REF) {
      if (row.a_ref) return false
    } else if (catalogARef.value && row.a_ref !== catalogARef.value) {
      return false
    }
    if (catalogEnvFilters.value.length > 0) {
      const envSet = row.env_set || []
      const match =
        catalogEnvMode.value === 'intersection'
          ? catalogEnvFilters.value.every((envId) => envSet.includes(envId))
          : catalogEnvFilters.value.some((envId) => envSet.includes(envId))
      if (!match) return false
    }
    return true
  }),
)

const treeRooms = computed(() =>
  homeRooms.value.map((room) => ({
    ...room,
    items: homePlacements.value.filter((p) => p.room_id === room.room_id),
  })),
)

const unplacedPlacements = computed(() => homePlacements.value.filter((p) => !p.room_id))

function showHomeInspect(): void {
  cmdDrawerVisible.value = false
  moduleMode.value = 'env'
  inspectView.value = 'home'
}







function closeCommandInspect(): void {
  showHomeInspect()
}



const commandByUid = computed(() => {
  const map: Record<string, HomeCommandRow> = {}
  for (const cmd of commandEditor.value?.commands || []) {
    map[cmd.payload_uid] = cmd
  }
  return map
})

const visibleRecipeCards = computed(() => {
  const recipes = commandEditor.value?.recipes || []
  const kind = cmdKindFilter.value
  return recipes.filter((recipe) => {
    if (kind === 'all' || kind === 'recipe') return true
    if (kind === 'strategy') return recipe.is_strategy
    return !recipe.is_strategy
  })
})

const visibleUncoveredCommands = computed(() => {
  if (cmdKindFilter.value === 'recipe') return []
  const uncovered = commandEditor.value?.uncovered_payload_uids || []
  return uncovered
    .map((uid) => commandByUid.value[uid])
    .filter((cmd): cmd is HomeCommandRow => {
      if (!cmd) return false
      if (cmdKindFilter.value === 'effect') return cmd.capability_kind === 'effect'
      if (cmdKindFilter.value === 'strategy') return cmd.capability_kind === 'strategy'
      return true
    })
})

const visibleCmdKeys = computed(() => [
  ...visibleRecipeCards.value.map((recipe) => recipeKey(recipe.recipe_uid)),
  ...visibleUncoveredCommands.value.map((cmd) => atomKey(cmd.payload_uid)),
])

function recipeKey(uid: string): string {
  return `r:${uid}`
}

function atomKey(uid: string): string {
  return `a:${uid}`
}

function isCmdSelected(key: string): boolean {
  return selectedCmdKeys.value.includes(key)
}

function toggleCmdKey(key: string, on: boolean): void {
  if (on) {
    if (!selectedCmdKeys.value.includes(key)) selectedCmdKeys.value = [...selectedCmdKeys.value, key]
    return
  }
  selectedCmdKeys.value = selectedCmdKeys.value.filter((item) => item !== key)
}

function selectVisibleCmds(): void {
  selectedCmdKeys.value = [...new Set([...selectedCmdKeys.value, ...visibleCmdKeys.value])]
}

function clearCmdSelection(): void {
  selectedCmdKeys.value = []
}

function selectedWeightUids(): string[] {
  const uids = new Set<string>()
  const recipesById = Object.fromEntries(
    (commandEditor.value?.recipes || []).map((recipe) => [recipe.recipe_uid, recipe]),
  )
  for (const key of selectedCmdKeys.value) {
    if (key.startsWith('r:')) {
      const recipe = recipesById[key.slice(2)]
      for (const uid of recipe?.weight_payload_uids || []) uids.add(uid)
      continue
    }
    if (key.startsWith('a:')) uids.add(key.slice(2))
  }
  return [...uids]
}
















function httpDetail(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : ''
}





onMounted(() => {
  void bootstrapHomeLibrary()
  void loadCatalogEnvAttributes()
  window.addEventListener(HOME_FORM_CHANGED_EVENT, onExternalFormChange as EventListener)
})

watch(cmdDrawerVisible, (open) => {
  if (!open) selectedCmdKeys.value = []
})

watch(catalogEnvFilters, () => {
  syncCatalogEnvTagCollapse()
})

onUnmounted(() => {
  window.removeEventListener(HOME_FORM_CHANGED_EVENT, onExternalFormChange as EventListener)
})









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

async function refreshForms(selectId?: string): Promise<void> {
  const res = await request.get<HomeFormRow[]>('/api/home/forms/')
  homeForms.value = res.data || []
  const next = selectId || currentFormId.value
  if (next && homeForms.value.some((f) => f.form_id === next)) {
    persistCurrentForm(next)
    await loadFormBundle(next)
    return
  }
  const fallback = homeForms.value[0]?.form_id || ''
  persistCurrentForm(fallback)
  await loadFormBundle(fallback)
}

async function createHomeForm(): Promise<void> {
  const name = newFormName.value.trim()
  if (!name) {
    ElMessage.warning('请填写表单名称')
    return
  }
  try {
    const res = await request.post<HomeFormRow>('/api/home/forms/', { name })
    newFormName.value = ''
    ElMessage.success('已新建环境表单')
    await refreshForms(res.data.form_id)
  } catch (e) {
    console.error(e)
    ElMessage.error(httpDetail(e) || '新建表单失败')
  }
}

async function renameHomeForm(): Promise<void> {
  const current = homeForms.value.find((f) => f.form_id === currentFormId.value)
  if (!current) return
  try {
    const { value } = await ElMessageBox.prompt('新的表单名称', '重命名环境表单', {
      inputValue: current.name,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    const name = String(value || '').trim()
    if (!name) return
    await request.put(`/api/home/forms/${encodeURIComponent(current.form_id)}`, { name })
    ElMessage.success('已重命名')
    await refreshForms(current.form_id)
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(httpDetail(e) || '重命名失败')
  }
}

async function deleteHomeForm(): Promise<void> {
  if (!currentFormId.value) return
  try {
    await ElMessageBox.confirm('删除后该表单的房间与设备实例一并清除。', '删除环境表单', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await request.delete(`/api/home/forms/${encodeURIComponent(currentFormId.value)}`)
    ElMessage.success('已删除表单')
    persistCurrentForm('')
    await refreshForms()
  } catch (e) {
    console.error(e)
    ElMessage.error(httpDetail(e) || '删除表单失败')
  }
}

async function createRoomType(): Promise<void> {
  const name = newRoomTypeName.value.trim()
  if (!name) {
    ElMessage.warning('请填写种类名')
    return
  }
  try {
    await request.post('/api/home/room-types/', { name })
    newRoomTypeName.value = ''
    roomTypes.value = (await request.get<HomeRoomTypeRow[]>('/api/home/room-types/')).data || []
    ElMessage.success('已登记房间种类，可在房间实例中引用')
  } catch (e) {
    console.error(e)
    ElMessage.error(httpDetail(e) || '登记种类失败')
  }
}

async function renameRoomType(row: HomeRoomTypeRow): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('新的种类名', '改名', {
      inputValue: row.name,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    const name = String(value || '').trim()
    if (!name) return
    await request.put(`/api/home/room-types/${row.type_id}`, { name })
    roomTypes.value = (await request.get<HomeRoomTypeRow[]>('/api/home/room-types/')).data || []
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(httpDetail(e) || '改名失败')
  }
}

async function toggleRoomType(row: HomeRoomTypeRow): Promise<void> {
  try {
    await request.put(`/api/home/room-types/${row.type_id}`, { is_active: !row.is_active })
    roomTypes.value = (await request.get<HomeRoomTypeRow[]>('/api/home/room-types/')).data || []
  } catch (e) {
    ElMessage.error(httpDetail(e) || '更新种类失败')
  }
}

async function deleteRoomType(row: HomeRoomTypeRow): Promise<void> {
  try {
    await request.delete(`/api/home/room-types/${row.type_id}`)
    roomTypes.value = (await request.get<HomeRoomTypeRow[]>('/api/home/room-types/')).data || []
  } catch (e) {
    ElMessage.error(httpDetail(e) || '删除种类失败')
  }
}

async function createRoom(): Promise<void> {
  if (!currentFormId.value || newRoomTypeId.value == null) {
    ElMessage.warning('请选择房间种类')
    return
  }
  try {
    await request.post(`/api/home/forms/${encodeURIComponent(currentFormId.value)}/rooms/`, {
      type_id: newRoomTypeId.value,
      label: newRoomLabel.value.trim() || null,
    })
    newRoomLabel.value = ''
    await loadFormBundle(currentFormId.value)
    ElMessage.success('已添加房间')
  } catch (e) {
    ElMessage.error(httpDetail(e) || '添加房间失败')
  }
}

async function renameRoom(row: HomeRoomRow): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('房间实例名', '改名', {
      inputValue: row.label,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    const label = String(value || '').trim()
    if (!label) return
    await request.put(
      `/api/home/forms/${encodeURIComponent(currentFormId.value)}/rooms/${row.room_id}`,
      { label },
    )
    await loadFormBundle(currentFormId.value)
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(httpDetail(e) || '改名失败')
  }
}

async function deleteRoom(row: HomeRoomRow): Promise<void> {
  try {
    await request.delete(`/api/home/forms/${encodeURIComponent(currentFormId.value)}/rooms/${row.room_id}`)
    await loadFormBundle(currentFormId.value)
  } catch (e) {
    ElMessage.error(httpDetail(e) || '删除房间失败')
  }
}

function clearCatalogFilters(): void {
  catalogKeyword.value = ''
  catalogSources.value = defaultSelectedSources()
  catalogARef.value = ''
  catalogEnvFilters.value = []
  catalogEnvMode.value = 'union'
  catalogCollapseEnvTags.value = false
}

function syncCatalogEnvTagCollapse(): void {
  if (catalogEnvFilters.value.length <= 1) {
    catalogCollapseEnvTags.value = false
    return
  }
  catalogCollapseEnvTags.value = false
  void nextTick(() => {
    const selection = document.querySelector('.catalog-env-filter-select .el-select__selection') as HTMLElement | null
    if (!selection) return
    catalogCollapseEnvTags.value = selection.scrollWidth > selection.clientWidth || selection.clientHeight > 34
  })
}

async function loadCatalogEnvAttributes(): Promise<void> {
  try {
    const res = await request.get<CatalogEnvAttribute[]>('/api/env-attributes/', { timeout: 60000 })
    catalogEnvAttributes.value = res.data || []
  } catch (e) {
    console.error(e)
  }
}

function openAddPlacement(): void {
  selectedCatalogIds.value = []
  addPlacementRoomId.value = undefined
  addPlacementWeight.value = 1
  catalogPickerKey.value += 1
  addPlacementVisible.value = true
}

function onCatalogSelection(rows: CatalogDeviceRow[]): void {
  selectedCatalogIds.value = (rows || []).map((r) => r.c_instance_id)
}

async function confirmAddPlacements(): Promise<void> {
  if (!currentFormId.value) return
  if (!selectedCatalogIds.value.length) {
    ElMessage.warning('请勾选至少一台设备')
    return
  }
  addingPlacements.value = true
  try {
    await request.post(`/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements/`, {
      catalog_c_instance_ids: selectedCatalogIds.value,
      room_id: addPlacementRoomId.value ?? null,
      weight: addPlacementWeight.value,
    })
    addPlacementVisible.value = false
    await loadFormBundle(currentFormId.value)
    ElMessage.success('已实例化到当前表单')
  } catch (e) {
    ElMessage.error(httpDetail(e) || '实例化失败')
  } finally {
    addingPlacements.value = false
  }
}

async function patchPlacement(row: HomePlacementRow, body: Record<string, unknown>): Promise<void> {
  await request.put(
    `/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements/${encodeURIComponent(row.placement_id)}`,
    body,
  )
  await loadFormBundle(currentFormId.value)
}

async function updatePlacementRoom(row: HomePlacementRow, roomId: number | undefined): Promise<void> {
  try {
    if (roomId == null) await patchPlacement(row, { clear_room: true })
    else await patchPlacement(row, { room_id: roomId })
  } catch (e) {
    ElMessage.error(httpDetail(e) || '更新房间失败')
  }
}

async function updatePlacementAlias(row: HomePlacementRow, alias: string): Promise<void> {
  try {
    await patchPlacement(row, { alias })
  } catch (e) {
    ElMessage.error(httpDetail(e) || '更新别名失败')
  }
}

async function updatePlacementWeight(row: HomePlacementRow, weight: number): Promise<void> {
  try {
    await patchPlacement(row, { weight })
  } catch (e) {
    ElMessage.error(httpDetail(e) || '更新权重失败')
  }
}

async function updatePlacementDesc(row: HomePlacementRow, preference_desc: string): Promise<void> {
  try {
    await patchPlacement(row, { preference_desc })
  } catch (e) {
    ElMessage.error(httpDetail(e) || '更新偏好描述失败')
  }
}

async function removePlacement(row: HomePlacementRow): Promise<void> {
  try {
    await request.delete(
      `/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements/${encodeURIComponent(row.placement_id)}`,
    )
    await loadFormBundle(currentFormId.value)
  } catch (e) {
    ElMessage.error(httpDetail(e) || '移除失败')
  }
}

function onPlacementSelection(rows: HomePlacementRow[]): void {
  selectedPlacements.value = rows || []
}

async function applySelectedDeviceWeight(): Promise<void> {
  if (!currentFormId.value || !selectedPlacements.value.length) return
  bulkApplying.value = true
  try {
    await request.put(`/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements-batch`, {
      placement_ids: selectedPlacements.value.map((p) => p.placement_id),
      weight: bulkDeviceWeight.value,
    })
    await loadFormBundle(currentFormId.value)
    ElMessage.success('已更新所选设备权重')
  } catch (e) {
    ElMessage.error(httpDetail(e) || '批量更新设备权重失败')
  } finally {
    bulkApplying.value = false
  }
}

async function applySelectedCommandWeight(weight: number): Promise<void> {
  if (!currentFormId.value || !selectedPlacements.value.length) return
  if (weight <= 0) {
    try {
      await ElMessageBox.confirm('确定将所选设备的指令设为不参与？', '不参与', { type: 'warning' })
    } catch {
      return
    }
  }
  bulkApplying.value = true
  try {
    await request.put(`/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements-batch`, {
      placement_ids: selectedPlacements.value.map((p) => p.placement_id),
      command_weight: weight,
    })
    await loadFormBundle(currentFormId.value)
    if (cmdDrawerVisible.value && cmdDrawerPlacementId.value) {
      await reloadCommandEditor()
    }
    ElMessage.success(weight > 0 ? '所选设备指令已全部参与' : '所选设备指令已全部不参与')
  } catch (e) {
    ElMessage.error(httpDetail(e) || '批量更新指令权重失败')
  } finally {
    bulkApplying.value = false
  }
}

async function openPlacementCommands(row: HomePlacementRow): Promise<void> {
  cmdDrawerPlacementId.value = row.placement_id
  cmdDrawerTitle.value = `指令权重 · ${row.display_name}`
  cmdKindFilter.value = 'all'
  selectedCmdKeys.value = []
  cmdDrawerVisible.value = true
  inspectView.value = 'commands'
  await reloadCommandEditor()
}

async function reloadCommandEditor(): Promise<void> {
  if (!currentFormId.value || !cmdDrawerPlacementId.value) return
  cmdDrawerLoading.value = true
  try {
    const res = await request.get<HomeCommandEditor>(
      `/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements/${encodeURIComponent(cmdDrawerPlacementId.value)}/commands`,
    )
    commandEditor.value = res.data || { placement_id: cmdDrawerPlacementId.value, commands: [], recipes: [], uncovered_payload_uids: [] }
  } catch (e) {
    ElMessage.error(httpDetail(e) || '加载指令权重失败')
    commandEditor.value = { placement_id: cmdDrawerPlacementId.value, commands: [], recipes: [], uncovered_payload_uids: [] }
  } finally {
    cmdDrawerLoading.value = false
  }
}



async function saveCommandBatch(
  items: Array<{ payload_uid: string; weight: number; preference_desc?: string | null }>,
): Promise<void> {
  if (!currentFormId.value || !cmdDrawerPlacementId.value || !items.length) return
  const res = await request.put<HomeCommandEditor>(
    `/api/home/forms/${encodeURIComponent(currentFormId.value)}/placements/${encodeURIComponent(cmdDrawerPlacementId.value)}/commands`,
    { items },
  )
  commandEditor.value = res.data
}

async function saveCommandUid(uid: string, weight: number, preferenceDesc?: string | null): Promise<void> {
  const current = commandByUid.value[uid]
  try {
    await saveCommandBatch([
      {
        payload_uid: uid,
        weight,
        preference_desc: preferenceDesc !== undefined ? preferenceDesc : current?.preference_desc,
      },
    ])
  } catch (e) {
    ElMessage.error(httpDetail(e) || '保存指令权重失败')
  }
}

async function saveRecipeWeight(recipe: HomeRecipeWeightCard, weight: number): Promise<void> {
  const uids = recipe.weight_payload_uids || []
  if (!uids.length) {
    ElMessage.warning('该配方没有可设权的步骤')
    return
  }
  try {
    await saveCommandBatch(uids.map((uid) => ({ payload_uid: uid, weight })))
  } catch (e) {
    ElMessage.error(httpDetail(e) || '保存配方权重失败')
  }
}

async function applySelectedCardWeight(weight: number): Promise<void> {
  const uids = selectedWeightUids()
  if (!uids.length) {
    ElMessage.warning('请先勾选指令')
    return
  }
  if (weight <= 0) {
    try {
      await ElMessageBox.confirm('确定将所选指令设为不参与？', '不参与', { type: 'warning' })
    } catch {
      return
    }
  }
  try {
    await saveCommandBatch(uids.map((uid) => ({ payload_uid: uid, weight })))
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(httpDetail(e) || '保存指令权重失败')
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
