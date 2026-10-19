/**
 * 智能家居生态来源（与后端 concrete_devices.source 对齐）。
 * 新增来源时只改本文件，各模块筛选下拉自动同步。
 */
export const DEVICE_SOURCE_MIOT = 1
export const DEVICE_SOURCE_GOOGLE_HOME = 2
export const DEVICE_SOURCE_OPENHARMONY = 3

export type DeviceSourceCode = number

export interface DeviceSourceOption {
  value: DeviceSourceCode
  label: string
  shortLabel: string
}

export const DEVICE_SOURCE_OPTIONS: readonly DeviceSourceOption[] = [
  { value: DEVICE_SOURCE_MIOT, label: 'miot', shortLabel: 'MIoT' },
  { value: DEVICE_SOURCE_GOOGLE_HOME, label: 'google home', shortLabel: 'Google Home' },
  { value: DEVICE_SOURCE_OPENHARMONY, label: 'openharmony', shortLabel: 'OpenHarmony' },
] as const

export const ALL_DEVICE_SOURCE_CODES: DeviceSourceCode[] = DEVICE_SOURCE_OPTIONS.map((x) => x.value)

export function defaultSelectedSources(): DeviceSourceCode[] {
  return [...ALL_DEVICE_SOURCE_CODES]
}

export function normalizeDeviceSource(source?: number | null): DeviceSourceCode {
  const code = Number(source)
  if (code === DEVICE_SOURCE_GOOGLE_HOME) return DEVICE_SOURCE_GOOGLE_HOME
  if (code === DEVICE_SOURCE_OPENHARMONY) return DEVICE_SOURCE_OPENHARMONY
  return DEVICE_SOURCE_MIOT
}

export function deviceSourceLabel(
  source?: number | null,
  sourceLabel?: string | null,
): string {
  if (sourceLabel && String(sourceLabel).trim()) return String(sourceLabel).trim()
  const code = normalizeDeviceSource(source)
  return DEVICE_SOURCE_OPTIONS.find((x) => x.value === code)?.shortLabel || 'miot'
}

/** 分类树中的生态节点 id（稳定可读；新增来源用 source-<code>） */
export function deviceSourceTreeNodeId(source?: number | null): string {
  const code = normalizeDeviceSource(source)
  if (code === DEVICE_SOURCE_MIOT) return 'source-miot'
  if (code === DEVICE_SOURCE_GOOGLE_HOME) return 'source-google-home'
  if (code === DEVICE_SOURCE_OPENHARMONY) return 'source-openharmony'
  return `source-${code}`
}

/**
 * 合并视图下生态标识色（图例 / 书签条）。
 * 新增生态时在此与 DEVICE_SOURCE_OPTIONS 一并维护即可。
 */
export function deviceSourceNodeColor(source?: number | null): string {
  const code = normalizeDeviceSource(source)
  if (code === DEVICE_SOURCE_GOOGLE_HOME) return '#E6A23C'
  if (code === DEVICE_SOURCE_OPENHARMONY) return '#F56C6C'
  return '#409EFF'
}

/**
 * 合并视图叶子：左侧书签条染色 + 主体沿用能力树 concrete 底色。
 * 使用 CSS linear-gradient（G6 v5 支持）。
 */
export function deviceSourceBookmarkFill(
  source?: number | null,
  bodyColor = '#78D3F8',
  stripeRatio = 0.12,
): string {
  const stripe = deviceSourceNodeColor(source)
  const stop = Math.max(0.06, Math.min(0.22, stripeRatio))
  const pct = `${(stop * 100).toFixed(1)}%`
  return `linear-gradient(90deg, ${stripe} 0%, ${stripe} ${pct}, ${bodyColor} ${pct}, ${bodyColor} 100%)`
}

/** 是否已按生态筛选（未全选或选空）——分类树此时省略总根节点 */
export function isPartialSourceSelection(selected: DeviceSourceCode[]): boolean {
  if (!selected.length) return true
  if (selected.length < ALL_DEVICE_SOURCE_CODES.length) return true
  const set = new Set(selected)
  return ALL_DEVICE_SOURCE_CODES.some((code) => !set.has(code))
}
