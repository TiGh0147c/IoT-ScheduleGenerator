<template>
  <div class="page-dock kb">
    <aside class="pane-tree" :class="{ 'pane-tree--wide': activeTab === 'capability' }">
      <button type="button" class="tree-item" :class="{ 'is-on': activeTab === 'capability' }" @click="handleTabChange('capability')">
        能力
      </button>
      <button type="button" class="tree-item" :class="{ 'is-on': activeTab === 'env' }" @click="handleTabChange('env')">
        环境
      </button>

      <template v-if="activeTab === 'capability'">
        <div class="tree-group">领域</div>
        <el-tree
          class="kb-tree"
          :data="knowledgeTree"
          :props="defaultProps"
          node-key="uniqueId"
          highlight-current
          default-expand-all
          @node-click="handleNodeClick"
        >
          <template #default="{ node }">
            <span class="custom-tree-node">
              <span class="kb-tree-label">{{ node.label }}</span>
            </span>
          </template>
        </el-tree>
      </template>

    </aside>

    <section class="pane-inspect">
      <template v-if="activeTab === 'capability'">
        <div class="pane-h">
          <h1>能力</h1>
        </div>
        <div class="board-scroll kb-detail">
          <div v-if="selectedNode">
            <p class="kb-path">
              <span
                v-for="(item, index) in selectedNodePathParts"
                :key="`${item.node.level}-${item.node.uniqueId}`"
              >
                <el-link
                  v-if="index < selectedNodePathParts.length - 1"
                  class="detail-path-link"
                  type="primary"
                  :underline="false"
                  @click="jumpToNode(item.node)"
                >
                  {{ item.node.label }}
                </el-link>
                <span v-else class="detail-path-text">{{ item.node.label }}</span>
                <span v-if="index < selectedNodePathParts.length - 1" class="detail-path-sep"> / </span>
              </span>
            </p>
            <el-form label-position="top">
              <el-form-item label="名称">
                <el-input v-model="selectedNode.label" readonly />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="selectedNode.desc" type="textarea" rows="5" readonly />
              </el-form-item>
              <el-form-item label="环境对应组">
                <div class="env-combo">
                  <p v-if="selectedEnvCombo.note" class="env-hint env-combo-note">{{ selectedEnvCombo.note }}</p>
                  <p v-else-if="!selectedEnvComboItems.length" class="env-hint env-combo-note">暂无对应环境属性</p>
                  <div
                    v-for="group in selectedEnvComboGroups"
                    :key="group.role"
                    class="env-combo-group"
                  >
                    <div class="env-combo-role">{{ envRoleLabel(group.role) }}</div>
                    <div class="env-combo-tags">
                      <span
                        v-for="item in group.items"
                        :key="`${item.role}-${item.match_key}`"
                        class="mark"
                      >
                        {{ item.env_name }}
                        <template v-if="item.polarity"> · {{ envPolarityLabel(item.polarity) }}</template>
                      </span>
                    </div>
                  </div>
                </div>
              </el-form-item>
            </el-form>
          </div>
          <el-empty v-else description="在左侧点一个节点" />
        </div>
      </template>



      <template v-else-if="activeTab === 'env'">
        <div class="pane-h">
          <h1>环境</h1>
          <div class="seg">
            <button type="button" :class="{ 'is-on': envKindFilter === 'all' }" @click="envKindFilter = 'all'">全部</button>
            <button
              v-for="item in envKindOptions"
              :key="item.value"
              type="button"
              :class="{ 'is-on': envKindFilter === item.value }"
              @click="envKindFilter = item.value"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div class="board-scroll">
          <el-table :data="displayedEnvList" style="width: 100%" size="small" v-loading="envListLoading">
            <el-table-column prop="env_id" label="ID" width="70" />
            <el-table-column prop="env_name" label="名称" min-width="110" />
            <el-table-column label="构型" width="120">
              <template #default="scope">
                {{ envKindLabel(scope.row.env_kind) }}
              </template>
            </el-table-column>
            <el-table-column prop="match_key" label="匹配键" width="130">
              <template #default="scope">
                <span>{{ scope.row.match_key || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="解释" min-width="180">
              <template #default="scope">
                <span class="env-desc-cell" :title="scope.row.env_desc || ''">
                  {{ scope.row.env_desc || '—' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="别名" min-width="160">
              <template #default="scope">
                <span class="env-desc-cell">{{ (scope.row.aliases || []).join('、') || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="关联对象" min-width="160">
              <template #default="scope">
                <el-tooltip
                  placement="left"
                  effect="dark"
                  :disabled="!relatedObjectNames(scope.row).length"
                >
                  <template #content>
                    <div class="effect-lines">
                      <div
                        v-for="(name, idx) in relatedObjectNames(scope.row)"
                        :key="`${scope.row.env_id}-o-${idx}`"
                      >
                        {{ name }}
                      </div>
                    </div>
                  </template>
                  <span v-if="relatedObjectNames(scope.row).length" class="env-desc-cell">
                    {{ relatedObjectNames(scope.row).join('、') }}
                  </span>
                  <span v-else class="env-desc-cell">—</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="关联效果" min-width="220">
              <template #default="scope">
                <el-tooltip
                  placement="left"
                  effect="dark"
                  :disabled="!relatedEffectLabels(scope.row).length"
                >
                  <template #content>
                    <div class="effect-lines">
                      <div
                        v-for="(name, idx) in relatedEffectLabels(scope.row)"
                        :key="`${scope.row.env_id}-e-${idx}`"
                      >
                        {{ name }}
                      </div>
                    </div>
                  </template>
                  <span v-if="relatedEffectLabels(scope.row).length" class="env-desc-cell">
                    {{ relatedEffectLabels(scope.row).join('、') }}
                  </span>
                  <span v-else class="env-desc-cell">—</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="scope">
                <span class="mark">{{ scope.row.is_active === false ? '停用' : '启用' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </section>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import request from '../api/request'
import { ElMessage } from 'element-plus'

interface EnvComboItem {
  env_id?: number | null
  env_name: string
  match_key: string
  role: string
  polarity?: string
}

interface EnvComboView {
  empty?: boolean
  note?: string
  items?: EnvComboItem[]
}

interface EnvRelatedNode {
  id: number
  name: string
  role?: string | null
}

interface TreeNode {
  id: number
  label: string
  desc: string
  level: number
  uniqueId: string
  d_id?: number
  o_id?: number
  children?: TreeNode[]
  env_combo?: EnvComboView
}

interface EffectItem {
  e_id: number
  e_name: string
  e_desc: string
  o_id: number
  env_combo?: EnvComboView
}

interface ObjectItem {
  o_id: number
  o_name: string
  o_desc?: string
  d_id: number
  env_combo?: EnvComboView
}





interface EnvAttribute {
  env_id: number
  env_name: string
  env_desc?: string | null
  match_key?: string | null
  env_kind?: string | null
  aliases?: string[]
  units?: string[]
  related_o_ids?: number[]
  related_e_ids?: number[]
  related_objects?: EnvRelatedNode[]
  related_effects?: EnvRelatedNode[]
  is_active?: boolean
}



const envKindOptions = [
  { value: 'ambient', label: '处境量' },
  { value: 'workpiece_id', label: '对象身份' },
  { value: 'workpiece_state', label: '对象状态量' },
  { value: 'provision', label: '供给能力' },
  { value: 'process', label: '过程状态' },
]

function envKindLabel(kind?: string | null): string {
  const hit = envKindOptions.find((item) => item.value === kind)
  return hit ? hit.label : kind || '—'
}





const activeTab = ref<'capability' | 'abstract' | 'guidance' | 'env'>('capability')





const knowledgeTree = ref<TreeNode[]>([])
const selectedNode = ref<TreeNode | null>(null)



const defaultProps = { children: 'children', label: 'label' }


const allEffects = ref<EffectItem[]>([])
const allObjects = ref<ObjectItem[]>([])



















const envList = ref<EnvAttribute[]>([])
const envListLoading = ref(false)
const envKindFilter = ref('all')
const displayedEnvList = computed(() => {
  if (envKindFilter.value === 'all') return envList.value
  return envList.value.filter((row) => (row.env_kind || 'ambient') === envKindFilter.value)
})




const fetchKnowledgeData = async () => {
  try {
    const [domains, objects, effects] = await Promise.all([
      request.get('/api/domains/'),
      request.get('/api/objects/'),
      request.get('/api/effects/'),
    ])

    allEffects.value = effects.data
    allObjects.value = objects.data
    knowledgeTree.value = domains.data.map((d: any) => ({
      id: d.d_id,
      label: d.d_name,
      desc: d.d_desc,
      level: 1,
            uniqueId: `d-${d.d_id}`,
            env_combo: d.env_combo,
            children: objects.data
              .filter((o: any) => o.d_id === d.d_id)
              .map((o: any) => ({
                id: o.o_id,
                label: o.o_name,
                desc: o.o_desc,
                level: 2,
                uniqueId: `o-${o.o_id}`,
                env_combo: o.env_combo,
                children: effects.data
                  .filter((e: any) => e.o_id === o.o_id)
                  .map((e: any) => ({
                    id: e.e_id,
                    label: e.e_name,
                    desc: e.e_desc,
                    level: 3,
                    uniqueId: `e-${e.e_id}`,
                    env_combo: e.env_combo,
                  })),
              })),
    }))
  } catch (_error) {
    ElMessage.error('获取能力数据失败，请确保后端已启动')
  }
}





const fetchEnvAttributes = async () => {
  envListLoading.value = true
  try {
    const res = await request.get('/api/env-attributes/')
    envList.value = res.data
  } catch (_error) {
    ElMessage.error('获取环境属性列表失败，请确保后端已启动')
  } finally {
    envListLoading.value = false
  }
}

const getEffectNamesByIds = (effectIds: number[]) => {
  if (!effectIds?.length) return ['暂无关联能力']
  const idSet = new Set(effectIds)
  const names = allEffects.value
    .filter((item) => idSet.has(item.e_id))
    .map((item) => item.e_name)
  return names.length ? names : effectIds.map((id) => `未知能力(ID: ${id})`)
}

const ENV_ROLE_LABELS: Record<string, string> = {
  primary: '执行主签名',
  side: '连带',
  observe: '观察',
  forbid: '禁标',
}

const ENV_POLARITY_LABELS: Record<string, string> = {
  lower: '降低',
  raise: '升高',
  set: '设定',
  start: '开始',
  change: '改变',
  observe: '读取',
  process: '作用',
}

function envRoleLabel(role?: string | null): string {
  if (!role) return '关联'
  return ENV_ROLE_LABELS[role] || role
}



function envPolarityLabel(raw?: string): string {
  if (!raw) return ''
  return raw
    .split('/')
    .map((part) => ENV_POLARITY_LABELS[part] || part)
    .join('/')
}

const selectedEnvCombo = computed<EnvComboView>(() => selectedNode.value?.env_combo || {})
const selectedEnvComboItems = computed(() => selectedEnvCombo.value.items || [])

const selectedEnvComboGroups = computed(() => {
  const order = ['primary', 'side', 'observe', 'forbid']
  const grouped = new Map<string, EnvComboItem[]>()
  for (const item of selectedEnvComboItems.value) {
    const role = item.role || 'related'
    const list = grouped.get(role) || []
    list.push(item)
    grouped.set(role, list)
  }
  return order
    .filter((role) => grouped.has(role))
    .map((role) => ({ role, items: grouped.get(role) || [] }))
})

function relatedObjectNames(row: EnvAttribute): string[] {
  if (row.related_objects?.length) return row.related_objects.map((item) => item.name)
  return getObjectNamesByIds(row.related_o_ids || [])
}

function relatedEffectLabels(row: EnvAttribute): string[] {
  if (row.related_effects?.length) {
    return row.related_effects.map((item) => {
      const role = envRoleLabel(item.role)
      return item.role ? `${item.name}（${role}）` : item.name
    })
  }
  return getEffectNamesByIds(row.related_e_ids || []).filter((name) => name !== '暂无关联能力')
}

const getObjectNamesByIds = (objectIds: number[]) => {
  if (!objectIds?.length) return []
  const idSet = new Set(objectIds)
  const names = allObjects.value.filter((item) => idSet.has(item.o_id)).map((item) => item.o_name)
  return names.length ? names : objectIds.map((id) => `未知对象(ID: ${id})`)
}

const initData = async () => {
  await Promise.all([fetchKnowledgeData(), fetchEnvAttributes()])
}

onMounted(initData)

const findNodePathByUniqueId = (
  nodes: TreeNode[],
  uniqueId: string,
  parents: TreeNode[] = [],
): TreeNode[] | null => {
  for (const node of nodes) {
    const nextParents = [...parents, node]
    if (node.uniqueId === uniqueId) {
      return nextParents
    }
    if (node.children?.length) {
      const childResult = findNodePathByUniqueId(node.children, uniqueId, nextParents)
      if (childResult) {
        return childResult
      }
    }
  }
  return null
}

const selectedNodePathParts = computed(() => {
  if (!selectedNode.value) return []
  const path = findNodePathByUniqueId(knowledgeTree.value, selectedNode.value.uniqueId) || []
  return path.map((node) => ({ node }))
})

const handleTabChange = (index: string) => {
  if (index === 'capability' || index === 'env') {
    activeTab.value = index
    if (index === 'env') {
      fetchEnvAttributes()
    }
  }
}

const handleNodeClick = (data: TreeNode) => {
  selectedNode.value = data
}

const jumpToNode = (node: TreeNode) => {
  selectedNode.value = node
}






























</script>

<style scoped>
.kb {
  min-height: 0;
}

.kb > .pane-tree {
  overflow: hidden;
}

.kb-tree {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: transparent;
  padding: 4px 0 16px;
}

.kb-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 32px;
  align-items: flex-start;
  padding: 4px 8px 4px 0;
}

.kb-tree-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-detail {
  padding: 16px 20px 28px;
  max-width: 560px;
}

.kb-path {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--ui-muted);
}

.env-hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

.pack-members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pack-member-tag {
  margin: 0;
}

.env-combo {
  width: 100%;
}

.env-combo-note {
  margin: 0 0 8px;
}

.env-combo-group {
  margin-bottom: 10px;
}

.env-combo-role {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.env-combo-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.env-combo-tag {
  margin: 0;
}

.env-combo-polarity {
  color: #909399;
}

.env-desc-cell {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #606266;
  font-size: 13px;
  line-height: 1.45;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}

.node-ops {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  opacity: 0;
}

.custom-tree-node:hover .node-ops {
  opacity: 1;
}

.detail-path-link,
.detail-path-text,
.detail-path-sep {
  font-size: 14px;
  line-height: 1.4;
}

.template-preview {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.template-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.template-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.template-scroll-box {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 8px;
}

:global(.effect-desc-tooltip) {
  max-width: min(420px, calc(100vw - 24px)) !important;
}

:global(.effect-desc-tooltip .el-popper__content) {
  white-space: normal !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
  line-height: 1.5;
}

:global(.effect-count-tooltip) {
  max-width: min(320px, calc(100vw - 24px)) !important;
}

.effect-lines {
  white-space: normal;
  line-height: 1.5;
}
</style>