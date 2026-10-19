/** 当前环境表单：意图实现与分类树共用。 */
export const HOME_FORM_STORAGE_KEY = 'iot-current-home-form-id'
export const HOME_FORM_CHANGED_EVENT = 'iot-home-form-changed'

export function readCurrentHomeFormId(): string {
  try {
    return localStorage.getItem(HOME_FORM_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export function writeCurrentHomeFormId(formId: string): void {
  const id = (formId || '').trim()
  try {
    if (id) localStorage.setItem(HOME_FORM_STORAGE_KEY, id)
    else localStorage.removeItem(HOME_FORM_STORAGE_KEY)
  } catch {
    /* ignore quota / private mode */
  }
  window.dispatchEvent(new CustomEvent(HOME_FORM_CHANGED_EVENT, { detail: id }))
}
