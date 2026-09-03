<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, getToken, setToken } from '../shared/api'
import AppShell from './AppShell.vue'
import LoginView from '../features/auth/LoginView.vue'
import StudentViews from '../features/student/StudentViews.vue'
import ReviewerViews from '../features/reviewer/ReviewerViews.vue'
import MethodistViews from '../features/methodist/MethodistViews.vue'

const user = ref(null)
const config = ref({ features: {}, demo_data_sections: [] })
const notifications = ref([])
const active = ref('')
const loading = ref(false)
const error = ref('')

const allNav = {
  student: [
    { id: 'student-assignments', label: 'Мои задания', icon: '▦' },
    { id: 'student-blitz', label: 'Доп. вопросы', icon: '?' },
  ],
  reviewer: [
    { id: 'reviewer-queue', label: 'Моя очередь', icon: '≡' },
    { id: 'reviewer-review', label: 'Ревью', icon: '✓' },
  ],
  methodist: [
    { id: 'methodist-dashboard', label: 'Дашборд курса', icon: '◫', demo: true },
    { id: 'methodist-distribution', label: 'Распределение', icon: '⌁', feature: 'distribution' },
    { id: 'methodist-registry', label: 'Реестр работ', icon: '▤' },
    { id: 'methodist-rubrics', label: 'Задания и критерии', icon: '◇', feature: 'rubric_builder' },
    { id: 'methodist-analytics', label: 'Аналитика', icon: '↗', demo: true, feature: 'analytics' },
    { id: 'methodist-settings', label: 'Настройки курса', icon: '⚙' },
  ],
}

const nav = computed(() => (allNav[user.value?.role] || []).filter(item => !item.feature || config.value.features[item.feature]))

function defaultPage(role) { return { student: 'student-assignments', reviewer: 'reviewer-queue', methodist: 'methodist-dashboard' }[role] }

async function bootstrap() {
  if (!getToken()) return
  try {
    ;[user.value, config.value] = await Promise.all([api('/auth/me'), api('/config')])
    active.value = window.location.hash.slice(1) || defaultPage(user.value.role)
    notifications.value = await api('/notifications')
  } catch { logout() }
}

async function login(role) {
  loading.value = true; error.value = ''
  try {
    const response = await api(`/auth/demo/${role}`, { method: 'POST' })
    setToken(response.access_token); user.value = response.user
    config.value = await api('/config'); active.value = defaultPage(role)
    window.location.hash = active.value
    notifications.value = await api('/notifications')
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

function navigate(page) { active.value = page; window.location.hash = page }
function logout() { setToken(null); user.value = null; notifications.value = []; active.value = ''; window.location.hash = '' }
async function readNotification(note) {
  if (!note.read) { await api(`/notifications/${note.id}/read`, { method: 'POST' }); note.read = true }
  const route = note.payload?.route?.split('/').filter(Boolean).join('-')
  if (route && nav.value.some(item => item.id === route)) navigate(route)
}

onMounted(bootstrap)
</script>

<template>
  <LoginView v-if="!user" :loading="loading" :error="error" @login="login" />
  <AppShell v-else :user="user" :nav="nav" :active="active" :notifications="notifications" @navigate="navigate" @logout="logout" @read="readNotification">
    <StudentViews v-if="user.role === 'student'" :active="active" />
    <ReviewerViews v-else-if="user.role === 'reviewer'" :active="active" @navigate="navigate" />
    <MethodistViews v-else :active="active" />
  </AppShell>
</template>
