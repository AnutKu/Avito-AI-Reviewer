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

// Клиента к task-creater здесь больше нет намеренно: конструктор заданий —
// счётная машина, а задание хранит кабинет. В движок ходит только api, иначе у
// заданий было бы два хранилища и два разных ответа на вопрос «где правда».
// Прокси /task-creater/ в nginx оставлен ради Swagger'а сервиса.

export function formatDate(value, withTime = false) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric', month: 'short', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(new Date(value))
}

// Статус AI-ревью виден ревьюеру в очереди: ревью запускается назначением
// и идёт в фоне, так что «ещё не считали» и «считается прямо сейчас» — разные
// сообщения. Раньше сюда протекали сырые значения перечисления.
export const aiStatusNames = {
  pending: 'Ожидает ревью', running: 'Ревью идёт', ready: 'Готово', failed: 'Ошибка ревью',
}

export const statusNames = {
  not_submitted: 'Не сдал', submitted: 'Принята', proposed: 'Ждёт распределения', assigned: 'Назначена',
  in_review: 'На проверке', blitz_sent: 'Ждёт ответа', blitz_answered: 'Ответ получен',
  completed: 'Проверена',
}
