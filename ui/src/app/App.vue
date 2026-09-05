<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, getToken, setToken } from '../shared/api'
import { HUMAN_TICK, useLiveRefresh } from '../shared/live'
import { parseHash } from '../shared/route'
import { markSeen, shouldShow } from '../shared/onboarding'
import AppShell from './AppShell.vue'
import Onboarding from './Onboarding.vue'
import LoginView from '../features/auth/LoginView.vue'
import StudentViews from '../features/student/StudentViews.vue'
import ReviewerViews from '../features/reviewer/ReviewerViews.vue'
import MethodistViews from '../features/methodist/MethodistViews.vue'

const user = ref(null)
const config = ref({ features: {}, demo_data_sections: [] })
const notifications = ref([])
const active = ref('')
const sub = ref([])
const loading = ref(false)
const error = ref('')
const onboarding = ref(false)

const allNav = {
  student: [
    { id: 'student-assignments', label: 'Мои задания', icon: '▦' },
    { id: 'student-blitz', label: 'Вопросы от ревьюера', icon: '?' },
  ],
  reviewer: [
    // Разбор работы — не отдельный раздел, а страница внутри очереди: открывают
    // его всегда из списка, и пункт меню остаётся подсвеченным (`pages`).
    { id: 'reviewer-queue', label: 'Моя очередь', icon: '≡', pages: ['reviewer-review'] },
    { id: 'reviewer-history', label: 'История', icon: '⟲' },
  ],
  // Порядок — это маршрут рабочего дня методиста, а не алфавит: сначала
  // задание, потом кто его проверит, потом что сдали, и только потом выводы.
  // Первый пункт заодно становится экраном входа (см. defaultPage).
  methodist: [
    // AI-конструктор больше не отдельный пункт: создание, правка и проверка
    // задания живут внутри банка — это один процесс над одной сущностью.
    { id: 'methodist-rubrics', label: 'Банк заданий и критериев', icon: '◇', feature: 'rubric_builder' },
    { id: 'methodist-distribution', label: 'Распределение ревьюеров', icon: '👥', feature: 'distribution' },
    { id: 'methodist-performance', label: 'Успеваемость', icon: '↗' },
    { id: 'methodist-dashboard', label: 'Аналитика курса', icon: '◫' },
    { id: 'methodist-settings', label: 'Настройки курса', icon: '⚙' },
  ],
}


const nav = computed(() => (allNav[user.value?.role] || []).filter(item => !item.feature || config.value.features[item.feature]))

// Экран входа — первый пункт меню роли. Именно меню, а не отдельный список:
// иначе при выключенном флаге методист попадал бы в раздел, которого у него в
// навигации нет, и не понимал, как вернуться.
function defaultPage() { return nav.value[0]?.id || '' }

// Хеш — единственный источник правды о том, какой экран открыт. Раздел берётся
// из первого сегмента, остальное отдаётся самому разделу: так прямая ссылка,
// перезагрузка и кнопки «назад/вперёд» показывают одно и то же.
function applyHash() {
  const route = parseHash(window.location.hash)
  // Устаревший адрес заменяем, а не добавляем: «назад» должен вести туда,
  // откуда пришли, а не обратно на мёртвую ссылку.
  if (route.redirectTo) { window.location.replace(`#${route.redirectTo}`); return }
  active.value = route.page || defaultPage()
  sub.value = route.sub
}

async function bootstrap() {
  if (!getToken()) return
  try {
    ;[user.value, config.value] = await Promise.all([api('/auth/me'), api('/config')])
    applyHash()
    onboarding.value = shouldShow(user.value.role)
    notifications.value = await api('/notifications')
  } catch { logout() }
}

async function login(role) {
  loading.value = true; error.value = ''
  try {
    const response = await api(`/auth/demo/${role}`, { method: 'POST' })
    setToken(response.access_token); user.value = response.user
    config.value = await api('/config')
    navigate(defaultPage())
    onboarding.value = shouldShow(role)
    notifications.value = await api('/notifications')
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

// Закрыли — значит показали: второй раз при входе знакомство не всплывёт, но
// остаётся доступным из «Нужна помощь?» в меню.
function closeOnboarding() { markSeen(user.value?.role); onboarding.value = false }

function navigate(path) {
  const target = `#${path}`
  // Тот же адрес события hashchange не породит — применяем сразу сами.
  if (window.location.hash === target) applyHash()
  else window.location.hash = target
}
function logout() { setToken(null); user.value = null; onboarding.value = false; notifications.value = []; active.value = ''; sub.value = []; window.location.hash = '' }

// Колокольчик грузился один раз за сессию: работа проверена, вопрос задан,
// ревью назначено — а счётчик до перезагрузки показывал вчерашнее число.
// Опрос идёт, пока в кабинете кто-то есть, и не идёт на экране логина.
useLiveRefresh(
  () => Boolean(user.value),
  async () => { notifications.value = await api('/notifications') },
  { interval: HUMAN_TICK },
)
async function readNotification(note) {
  if (!note.read) { await api(`/notifications/${note.id}/read`, { method: 'POST' }); note.read = true }
  const route = note.payload?.route?.split('/').filter(Boolean).join('-')
  if (route && nav.value.some(item => item.id === route)) navigate(route)
}

onMounted(() => { window.addEventListener('hashchange', applyHash); bootstrap() })
onUnmounted(() => window.removeEventListener('hashchange', applyHash))
</script>

<template>
  <LoginView v-if="!user" :loading="loading" :error="error" @login="login" />
  <AppShell v-else :user="user" :nav="nav" :active="active" :notifications="notifications" @navigate="navigate" @logout="logout" @read="readNotification" @help="onboarding = true">
    <StudentViews v-if="user.role === 'student'" :active="active" :sub="sub" @navigate="navigate" />
    <ReviewerViews v-else-if="user.role === 'reviewer'" :active="active" :sub="sub" @navigate="navigate" />
    <MethodistViews v-else :active="active" :sub="sub" @navigate="navigate" />
    <Onboarding v-if="onboarding" :role="user.role" @close="closeOnboarding" />
  </AppShell>
</template>
