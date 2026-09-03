<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, formatDate, statusNames } from '../../shared/api'
import DemoBadge from '../../shared/ui/DemoBadge.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import TaskCreaterView from './TaskCreaterView.vue'

const props = defineProps({ active: String })
const dashboard = ref(null)
const distribution = ref([])
const registry = ref([])
const reviewers = ref([])
const assignments = ref([])
const analytics = ref(null)
const course = ref(null)
const error = ref('')
const notice = ref('')
const statusFilter = ref('')

async function load(active = props.active) {
  error.value = ''
  try {
    if (active === 'methodist-dashboard') dashboard.value = await api('/methodist/dashboard')
    if (active === 'methodist-distribution') distribution.value = await api('/methodist/distribution')
    if (active === 'methodist-registry') {
      ;[registry.value, reviewers.value] = await Promise.all([api(`/methodist/submissions${statusFilter.value ? `?status=${statusFilter.value}` : ''}`), api('/methodist/reviewers')])
    }
    if (active === 'methodist-rubrics') assignments.value = await api('/methodist/assignments')
    if (active === 'methodist-analytics') analytics.value = await api('/methodist/analytics')
    if (active === 'methodist-settings') course.value = await api('/methodist/course')
  } catch (e) { error.value = e.message }
}

async function applyDistribution() {
  const selected = distribution.value.filter(x => x.reviewer).map(x => ({ submission_id: x.submission.id, reviewer_id: x.reviewer.id, explanation: x.explanation }))
  try { await api('/methodist/distribution/apply', { method: 'POST', body: JSON.stringify({ assignments: selected }) }); notice.value = `Распределено работ: ${selected.length}`; await load() }
  catch (e) { error.value = e.message }
}

async function reassign(row) {
  if (!row.newReviewer) return
  try { await api(`/methodist/submissions/${row.id}/reviewer`, { method: 'PATCH', body: JSON.stringify({ reviewer_id: row.newReviewer }) }); notice.value = 'Ревьюер изменён'; await load() }
  catch (e) { error.value = e.message }
}

async function publishRubric(item) {
  try {
    const criteria = item.rubric.map(x => ({ ...x }))
    await api(`/methodist/assignments/${item.id}/rubrics`, { method: 'POST', body: JSON.stringify({ criteria, pass_score: 6, note: 'Новая версия из кабинета' }) })
    notice.value = 'Новая неизменяемая версия опубликована'; await load()
  } catch (e) { error.value = e.message }
}

async function saveCourse() {
  try { await api('/methodist/course', { method: 'PATCH', body: JSON.stringify({ reviewer_capacity: course.value.reviewer_capacity, tone_of_voice: course.value.tone_of_voice }) }); notice.value = 'Настройки курса сохранены' }
  catch (e) { error.value = e.message }
}

watch(() => props.active, load)
watch(statusFilter, () => props.active === 'methodist-registry' && load())
onMounted(load)
</script>

<template>
  <div v-if="notice" class="toast-success global-toast">✓ {{ notice }}<button @click="notice = ''">×</button></div>
  <div v-if="error" class="toast-error global-toast">{{ error }}<button @click="error = ''">×</button></div>

  <section v-if="active === 'methodist-dashboard' && dashboard">
    <div class="page-heading"><div><span class="eyebrow">ОБЗОР КУРСА</span><h1>Добрый день, Анна</h1><p>Главное по потоку на сегодня, 3 сентября</p></div><DemoBadge /></div>
    <div class="metric-grid"><article><span class="metric-icon blue">▦</span><div><small>Всего работ</small><b>{{ dashboard.metrics.total }}</b><em>в потоке</em></div></article><article><span class="metric-icon green">✓</span><div><small>Проверено</small><b>{{ dashboard.metrics.completed }}</b><em class="positive">+8 за неделю</em></div></article><article><span class="metric-icon red">!</span><div><small>Просрочено</small><b>{{ dashboard.metrics.overdue }}</b><em>нужны действия</em></div></article><article><span class="metric-icon purple">◷</span><div><small>Среднее время</small><b>{{ dashboard.metrics.average_hours }} ч</b><em class="positive">−21% к прошлой неделе</em></div></article></div>
    <div class="dashboard-grid"><article class="card"><div class="card-title"><div><h2>Воронка проверки</h2><p>Живые записи демо-БД: {{ dashboard.live_records }}</p></div><span>Последние 7 дней⌄</span></div><div class="funnel"><div v-for="(row, index) in dashboard.funnel" :key="row.status"><span>{{ statusNames[row.status] }}</span><div><i :style="`width:${Math.max(4, row.count * 25)}%`" :class="`bar-${index}`" /></div><b>{{ row.count }}</b></div></div></article><article class="card"><div class="card-title"><div><h2>Нагрузка ревьюеров</h2><p>Активные работы и доступность</p></div><button class="text-button">Все →</button></div><div v-for="person in dashboard.reviewers" :key="person.id" class="reviewer-load"><span class="avatar purple">{{ person.name.split(' ').map(x => x[0]).join('') }}</span><div><b>{{ person.name }}</b><span><i :style="`width:${person.active / person.capacity * 100}%`" /></span></div><em>{{ person.active }} / {{ person.capacity }}</em></div><div class="insight"><span>✦</span><p><b>AI-подсказка</b>Распределение сбалансировано. У всех ревьюеров есть свободный кап.</p></div></article></div>
  </section>

  <section v-else-if="active === 'methodist-distribution'">
    <div class="page-heading"><div><span class="eyebrow">УПРАВЛЕНИЕ ПОТОКОМ</span><h1>Распределение работ</h1><p>Система предлагает ревьюеров по специализации и текущей загрузке</p></div><button class="primary" :disabled="!distribution.length" @click="applyDistribution">Подтвердить всё · {{ distribution.length }}</button></div>
    <div class="explain-banner"><span>✦</span><div><b>Как работает распределение</b><p>Сначала совпадение специализации, затем минимальная загрузка. Назначение станет видимым ревьюеру только после вашего подтверждения.</p></div></div>
    <div class="table-card distribution-table"><div class="table-row table-head"><span>Работа</span><span>Предложенный ревьюер</span><span>Почему</span><span /></div><div v-for="row in distribution" :key="row.submission.id" class="table-row"><span class="student-cell"><i>{{ row.submission.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ row.submission.student }}</b><small>{{ row.submission.assignment }}</small></span></span><span v-if="row.reviewer" class="reviewer-choice"><span class="avatar blue">{{ row.reviewer.name.split(' ').map(x => x[0]).join('') }}</span><b>{{ row.reviewer.name }}</b></span><span v-else class="danger">Нет кандидата</span><span class="reason">{{ row.explanation }}</span><button class="icon-more">•••</button></div><div v-if="!distribution.length" class="empty-state in-table"><span>✓</span><h2>Все работы распределены</h2><p>Новых предложений пока нет.</p></div></div>
  </section>

  <section v-else-if="active === 'methodist-registry'">
    <div class="page-heading"><div><span class="eyebrow">УПРАВЛЕНИЕ ПОТОКОМ</span><h1>Реестр работ</h1><p>Статусы, сроки и ответственные в одном списке</p></div><button class="secondary">Экспорт CSV</button></div>
    <div class="registry-tools"><label class="search">⌕<input placeholder="Студент или задание" /></label><select v-model="statusFilter"><option value="">Все статусы</option><option v-for="(name, key) in statusNames" :key="key" :value="key">{{ name }}</option></select></div>
    <div class="table-card registry-table"><div class="table-row table-head"><span>Студент</span><span>Статус</span><span>Ревьюер</span><span>Сдано</span><span>AI</span></div><div v-for="row in registry" :key="row.id" class="table-row"><span class="student-cell"><i>{{ row.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ row.student }}</b><small>{{ row.assignment }}</small></span></span><StatusBadge :status="row.status" /><span class="registry-reviewer"><b>{{ row.reviewer || 'Не назначен' }}</b><span class="reassign-controls"><select v-model="row.newReviewer"><option value="">Переназначить</option><option v-for="person in reviewers" :key="person.id" :value="person.id">{{ person.name }}</option></select><button v-if="row.newReviewer" @click="reassign(row)">✓</button></span></span><span :class="{ danger: row.is_overdue }"><b>{{ formatDate(row.submitted_at, true) }}</b><small v-if="row.is_overdue">После срока</small></span><span class="ai-ready ready"><i>✦</i>{{ row.ai_status === 'ready' ? 'Готов' : row.ai_status }}</span></div></div>
  </section>

  <section v-else-if="active === 'methodist-rubrics'">
    <div class="page-heading"><div><span class="eyebrow">КОНТЕНТ КУРСА</span><h1>Задания и критерии</h1><p>Опубликованные рубрики неизменяемы — каждая правка создаёт новую версию</p></div><span class="mock-chip">✦ AI-конструктор · mock</span></div>
    <article v-for="item in assignments" :key="item.id" class="card rubric-card"><div class="rubric-head"><div><small>{{ item.course }}</small><h2>{{ item.title }}</h2><p>{{ item.statement }}</p></div><div class="version-pill">Версия {{ item.rubric_version }}</div></div><div class="rubric-summary"><span><b>{{ item.max_score }}</b><small>макс. балл</small></span><span><b>{{ item.rubric.length }}</b><small>критериев</small></span><span><b>3</b><small>golden set</small></span></div><div class="criteria-table"><div v-for="(criterion, index) in item.rubric" :key="criterion.key"><span>{{ index + 1 }}</span><b>{{ criterion.title }}</b><em>{{ criterion.max_score }} б.</em></div></div><div class="rubric-actions"><p>Последнее изменение: {{ item.rubric_note }}</p><button class="secondary">Посмотреть golden set</button><button class="primary" @click="publishRubric(item)">Опубликовать новую версию</button></div></article>
  </section>

  <TaskCreaterView v-else-if="active === 'methodist-taskcreater'" />

  <section v-else-if="active === 'methodist-analytics' && analytics">
    <div class="page-heading"><div><span class="eyebrow">КАЧЕСТВО ПРОВЕРКИ</span><h1>Аналитика</h1><p>Где AI и ревьюеры расходятся и как меняется скорость проверки</p></div><DemoBadge /></div>
    <div class="analytics-grid"><article class="card"><div class="card-title"><div><h2>Согласие AI и ревьюера</h2><p>Доля принятых рекомендаций</p></div><strong class="large-positive">84%</strong></div><div class="line-chart"><div class="chart-y"><span>100%</span><span>75%</span><span>50%</span></div><svg viewBox="0 0 600 180" preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8b5cf6" stop-opacity=".25"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient></defs><path d="M0 120 C100 110 130 90 200 95 S320 65 400 60 S510 38 600 30 L600 180 L0 180Z" fill="url(#area)"/><path d="M0 120 C100 110 130 90 200 95 S320 65 400 60 S510 38 600 30" fill="none" stroke="#8b5cf6" stroke-width="4"/></svg><div class="chart-x"><span v-for="point in analytics.weekly" :key="point.week">{{ point.week }}</span></div></div></article><article class="card"><div class="card-title"><div><h2>Время ревью</h2><p>Медиана на одну работу</p></div><strong>16 мин</strong></div><div class="time-bars"><div v-for="point in analytics.weekly" :key="point.week"><i :style="`height:${point.review_time * 4}px`" /><span>{{ point.review_time }}</span><small>{{ point.week }}</small></div></div></article></div>
    <article class="card corrections"><div class="card-title"><div><h2>Критерии с частыми правками</h2><p>Кандидаты на уточнение формулировок</p></div><span class="warning-chip">! Требуют внимания</span></div><div v-for="row in analytics.criteria" :key="row.title" class="correction-row"><b>{{ row.title }}</b><div><i :style="`width:${row.correction_rate}%`" /></div><strong>{{ row.correction_rate }}%</strong><small>{{ row.reviews }} ревью</small></div></article>
  </section>

  <section v-else-if="active === 'methodist-settings' && course">
    <div class="page-heading"><div><span class="eyebrow">КУРС</span><h1>Настройки курса</h1><p>Правила коммуникации, нагрузки и дедлайнов</p></div><button class="primary" @click="saveCourse">Сохранить изменения</button></div>
    <div class="settings-grid"><article class="card form-card"><div class="setting-icon blue">Aa</div><div><h2>Tone of voice</h2><p>Этот стиль используется в черновиках обратной связи.</p><label>Стиль<input v-model="course.tone_of_voice.style" /></label><label>Обращение<select v-model="course.tone_of_voice.address"><option>на вы</option><option>на ты</option></select></label><label>Правила<textarea :value="course.tone_of_voice.rules.join('\n')" rows="4" @input="course.tone_of_voice.rules = $event.target.value.split('\n')" /></label></div></article><article class="card form-card"><div class="setting-icon purple">▦</div><div><h2>Нагрузка ревьюеров</h2><p>Жёсткий предел активных работ на одного человека.</p><label>Максимум работ<input v-model.number="course.reviewer_capacity" type="number" min="1" max="100" /></label><div class="setting-hint">Распределение не предложит ревьюера, если лимит исчерпан.</div></div></article><article class="card form-card"><div class="setting-icon green">◷</div><div><h2>Контрольные сроки</h2><p>Риск подсвечивается за 24 часа до дедлайна.</p><label>Порог риска<select><option>24 часа</option><option>48 часов</option></select></label><label class="toggle-row"><span><b>In-app уведомления</b><small>Для всех ролей</small></span><input type="checkbox" checked /></label><label class="toggle-row disabled"><span><b>Telegram</b><small>Выключено фиче-флагом</small></span><input type="checkbox" disabled /></label></div></article></div>
  </section>
</template>
