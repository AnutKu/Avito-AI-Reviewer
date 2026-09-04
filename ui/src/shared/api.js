const TOKEN_KEY = 'avito-ai-reviewer-token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export async function api(path, options = {}) {
  const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`/api${path}`, { ...options, headers })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `Ошибка ${response.status}`)
  }
  if (response.status === 204) return null
  return response.json()
}

// AI-помощник лектора (services/task-creater). Отдельный сервис без авторизации,
// проксируется единым кабинетом на /task-creater/.
export async function taskCreater(path, options = {}) {
  const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers }
  const response = await fetch(`/task-creater${path}`, { ...options, headers })
  const isJson = (response.headers.get('content-type') || '').includes('json')
  if (!response.ok) {
    const data = isJson ? await response.json().catch(() => ({})) : {}
    throw new Error(data.detail || `Ошибка ${response.status}`)
  }
  if (response.status === 204) return null
  return isJson ? response.json() : response.text()
}

export function formatDate(value, withTime = false) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric', month: 'short', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(new Date(value))
}

export const statusNames = {
  not_submitted: 'Не сдал', submitted: 'Принята', proposed: 'Ждёт распределения', assigned: 'Назначена',
  in_review: 'На проверке', blitz_sent: 'Ждёт ответа', blitz_answered: 'Ответ получен',
  completed: 'Проверена',
}
