<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, formatDate, statusNames } from '../../shared/api'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import TaskCreaterView from './TaskCreaterView.vue'

const props = defineProps({ active: String })
const report = ref(null)            // объединённый дашборд: обзор + качество проверки
const dashTab = ref('overview')
const showAllCriteria = ref(false)
const performance = ref(null)       // матрица «студент × задание»
const perfSearch = ref('')
const perfSort = ref('name')
const distribution = ref([])        // работы, ожидающие распределения
const assignedRows = ref([])        // распределённые работы — можно передать другому
const reviewerLoads = ref([])
const autoAssign = ref(false)
const registry = ref([])
const registrySearch = ref('')
const assignments = ref([])
const courses = ref([])
const course = ref(null)
const error = ref('')
const notice = ref('')
const statusFilter = ref('')

async function load(active = props.active) {
  error.value = ''
  try {
    if (active === 'methodist-dashboard') {
      report.value = await api('/methodist/analytics')
      if (!report.value.quality) dashTab.value = 'overview'   // вкладка выключена фиче-флагом
    }
    if (active === 'methodist-performance') performance.value = await api('/methodist/performance')
    if (active === 'methodist-distribution') {
      const s = await api('/methodist/distribution')
      autoAssign.value = s.auto_assign
      reviewerLoads.value = s.reviewers
      distribution.value = s.waiting.map(r => ({ ...r, chosen: r.reviewer?.id || '' }))
      assignedRows.value = s.assigned.map(r => ({ ...r, chosen: r.reviewer.id }))
    }
    if (active === 'methodist-registry') {
      registry.value = await api('/methodist/submissions')
      if (registry.value.length && !openGroups.value.size) openGroups.value.add(registry.value[0].assignment.id)
    }
    if (active === 'methodist-rubrics') {
      ;[assignments.value, courses.value] = await Promise.all([api('/methodist/assignments'), api('/methodist/courses')])
    }
    if (active === 'methodist-settings') course.value = await api('/methodist/course')
  } catch (e) { error.value = e.message }
}

const isFull = (p) => p.slots_left <= 0
const initials = (s) => s.split(' ').map(x => x[0]).join('').slice(0, 2)
const waitingReady = computed(() => distribution.value.filter(x => x.chosen).length)

// --- дашборд курса --------------------------------------------------------
// Все цифры приходят посчитанными с сервера; здесь только формат и геометрия.
const isNil = (v) => v === null || v === undefined
const nf = (v) => (isNil(v) ? '—' : v)
const pct = (v) => (isNil(v) ? '—' : `${Math.round(v)}%`)
const hours = (v) => (isNil(v) ? '—' : v >= 24 ? `${(v / 24).toFixed(1)} дн` : `${v} ч`)
const score = (v) => (isNil(v) ? '—' : String(Number(v).toFixed(1)).replace(/\.0$/, ''))

const ov = computed(() => report.value?.overview || {})
const quality = computed(() => report.value?.quality || null)
const funnelMax = computed(() => Math.max(1, ...(report.value?.funnel || []).map(r => r.count)))
const funnelWidth = (row) => `width:${Math.max(4, Math.round(row.count / funnelMax.value * 100))}%`

const completedTrend = computed(() => {
  const delta = ov.value.completed_delta
  if (isNil(delta)) return { text: '—', good: false }
  if (delta === 0) return { text: 'как неделей раньше', good: false }
  return { text: `${delta > 0 ? '+' : '−'}${Math.abs(delta)} за неделю`, good: delta > 0 }
})
const leadTrend = computed(() => {
  const delta = ov.value.lead_delta_pct
  if (isNil(delta)) return { text: 'прошлую неделю не с чем сравнить', good: false }
  if (!delta) return { text: 'без изменений к прошлой неделе', good: false }
  // Меньше часов — лучше, поэтому «хорошо» это отрицательная дельта.
  return { text: `${delta > 0 ? '+' : '−'}${Math.abs(Math.round(delta))}% к прошлой неделе`, good: delta < 0 }
})
const loadHint = computed(() => {
  const rows = report.value?.reviewers || []
  if (!rows.length) return 'Ревьюеры на курсе не заведены.'
  const busiest = rows.reduce((a, b) => (b.load > a.load ? b : a))
  const free = rows.reduce((sum, r) => sum + (r.available ? Math.max(0, r.slots_left) : 0), 0)
  const off = rows.filter(r => !r.available).length
  return `Свободный лимит на потоке — ${score(free)} работ. Самый загруженный: ${busiest.name} (${busiest.load}/${busiest.capacity}).`
    + (off ? ` Снято с распределения: ${off}.` : '')
})

const CHART_W = 600
const CHART_H = 180
const weeks = computed(() => quality.value?.weekly || [])
const agreementPoints = computed(() => {
  const rows = weeks.value
  const span = Math.max(1, rows.length - 1)
  return rows
    .map((row, index) => ({ row, index }))
    .filter(p => !isNil(p.row.agreement))
    .map(p => ({
      x: Math.round(p.index / span * CHART_W),
      y: Math.round(CHART_H - Math.min(100, Math.max(0, p.row.agreement)) / 100 * CHART_H),
      value: p.row.agreement,
    }))
})
const agreementLine = computed(() => agreementPoints.value.map(p => `${p.x},${p.y}`).join(' '))
const agreementArea = computed(() => {
  const points = agreementPoints.value
  if (points.length < 2) return ''
  return `${points[0].x},${CHART_H} ${agreementLine.value} ${points[points.length - 1].x},${CHART_H}`
})
const leadMax = computed(() => Math.max(1, ...weeks.value.map(r => r.avg_lead_hours || 0)))
const barHeight = (row) => `height:${Math.max(2, Math.round((row.avg_lead_hours || 0) / leadMax.value * 140))}px`
const criteriaRows = computed(() => {
  const rows = quality.value?.criteria || []
  return showAllCriteria.value ? rows : rows.slice(0, 8)
})

// --- успеваемость ---------------------------------------------------------
const openStudents = ref(new Set())
const toggleStudent = (id) => { openStudents.value.has(id) ? openStudents.value.delete(id) : openStudents.value.add(id) }
const isStudentOpen = (id) => openStudents.value.has(id)
const perfColumns = computed(() => {
  // repeat(0, ...) — невалидный CSS, поэтому без заданий колонок просто нет.
  const count = performance.value?.assignments?.length || 0
  return `minmax(170px,1.4fr)${count ? ` repeat(${count}, minmax(92px,1fr))` : ''} 168px`
})
const perfRows = computed(() => {
  const query = perfSearch.value.trim().toLowerCase()
  const rows = (performance.value?.rows || []).filter(r => !query || r.student.toLowerCase().includes(query))
  const sorted = [...rows]
  if (perfSort.value === 'best') sorted.sort((a, b) => (b.totals.avg_percent ?? -1) - (a.totals.avg_percent ?? -1))
  if (perfSort.value === 'risk') sorted.sort((a, b) => (a.totals.avg_percent ?? 101) - (b.totals.avg_percent ?? 101))
  if (perfSort.value === 'gaps') sorted.sort((a, b) =>
    (b.totals.expected - b.totals.submitted) - (a.totals.expected - a.totals.submitted))
  return sorted
})
const cellText = (cell) => (cell.status === 'not_submitted' ? '×' : isNil(cell.score) ? '·' : score(cell.score))
const cellClass = (cell) => {
  if (cell.status === 'not_submitted') return 'miss'
  if (isNil(cell.score)) return 'wip'
  return cell.passed ? 'pass' : 'fail'
}
const cellTitle = (cell, column) => {
  if (cell.status === 'not_submitted') return `${column.title}: не сдано`
  const state = statusNames[cell.status] || cell.status
  return isNil(cell.score)
    ? `${column.title}: ${state}`
    : `${column.title}: ${cell.score} из ${cell.max_score} (${state})`
}

const openGroups = ref(new Set())
const toggleGroup = (id) => { openGroups.value.has(id) ? openGroups.value.delete(id) : openGroups.value.add(id) }
const isGroupOpen = (id) => openGroups.value.has(id)
const openCards = ref(new Set())
const toggleCard = (id) => { openCards.value.has(id) ? openCards.value.delete(id) : openCards.value.add(id) }
const isCardOpen = (id) => openCards.value.has(id)
const filteredRegistry = computed(() => {
  const q = registrySearch.value.trim().toLowerCase()
  const sf = statusFilter.value
  return registry.value
    .map(g => {
      const titleHit = q && g.assignment.title.toLowerCase().includes(q)
      const rows = g.rows.filter(r => (!sf || r.status === sf) && (!q || titleHit || r.student.toLowerCase().includes(q)))
      return { ...g, rows }
    })
    .filter(g => g.rows.length)
})
const courseGroups = computed(() => {
  const map = {}
  for (const a of assignments.value) (map[a.course] ||= []).push(a)
  return map
})

async function toggleAuto() {
  try {
    const res = await api('/methodist/distribution/auto', { method: 'POST', body: JSON.stringify({ enabled: !autoAssign.value }) })
    notice.value = res.auto_assign
      ? `Автораспределение включено${res.assigned ? ` · распределено работ: ${res.assigned}` : ''}`
      : 'Автораспределение выключено'
    await load()
  } catch (e) { error.value = e.message }
}

async function applyDistribution() {
  const selected = distribution.value.filter(x => x.chosen).map(x => ({ submission_id: x.submission.id, reviewer_id: x.chosen, explanation: x.explanation }))
  if (!selected.length) return
  try { await api('/methodist/distribution/apply', { method: 'POST', body: JSON.stringify({ assignments: selected }) }); notice.value = `Распределено работ: ${selected.length}`; await load() }
  catch (e) { error.value = e.message }
}

async function assignRow(row) {
  if (!row.chosen) return
  try {
    await api('/methodist/distribution/apply', { method: 'POST', body: JSON.stringify({ assignments: [{ submission_id: row.submission.id, reviewer_id: row.chosen, explanation: row.explanation }] }) })
    notice.value = 'Работа назначена'; await load()
  } catch (e) { error.value = e.message }
}

async function reassignAssigned(row) {
  if (!row.chosen || row.chosen === row.reviewer.id) return
  if (row.status === 'in_review' && !window.confirm(`Работа уже на проверке у ${row.reviewer.name}. Передать другому — проверка начнётся заново. Продолжить?`)) return
  const target = reviewerLoads.value.find(p => p.id === row.chosen)
  let force = false
  if (target && isFull(target)) {
    if (!window.confirm(`У ревьюера ${target.name} нет свободного лимита (${target.load}/${target.capacity}). Всё равно передать?`)) return
    force = true
  }
  try { await api(`/methodist/submissions/${row.submission.id}/reviewer`, { method: 'PATCH', body: JSON.stringify({ reviewer_id: row.chosen, force }) }); notice.value = 'Работа передана другому ревьюеру'; await load() }
  catch (e) { error.value = e.message }
}

async function toggleAvailability(person) {
  try {
    const res = await api(`/methodist/reviewers/${person.id}`, { method: 'PATCH', body: JSON.stringify({ is_available: !person.available }) })
    if (res.proposals && res.proposals.length) {
      const seen = new Set(distribution.value.map(x => x.submission.id))
      distribution.value = [
        ...res.proposals.filter(r => !seen.has(r.submission.id)).map(r => ({ ...r, chosen: r.reviewer?.id || '' })),
        ...distribution.value,
      ]
      reviewerLoads.value = await api('/methodist/reviewers')
      notice.value = `${person.name}: снят с распределения. Предложено переназначений — ${res.proposals.length}, проверьте и подтвердите.`
    } else {
      notice.value = res.reassigned
        ? `${person.name}: снят с распределения, работ перераспределено — ${res.reassigned}`
        : (person.available ? `${person.name}: снят с распределения` : `${person.name}: снова в распределении`)
      await load()
    }
  } catch (e) { error.value = e.message }
}

// --- задания и критерии ---------------------------------------------------
const emptyCriterion = () => ({ key: '', title: '', max_score: 5, student_hint: '' })
const showNewAssignment = ref(false)
const draft = ref(null)
const editAssignmentId = ref('')
const assignmentEdit = ref(null)
const criteriaEditId = ref('')
const criteriaDraft = ref([])

function toggleNewAssignment() {
  if (showNewAssignment.value) { showNewAssignment.value = false; return }
  draft.value = {
    course_id: courses.value[0]?.id || '',
    title: '', statement: '', deadline_at: '', effort_weight: 1, submission_channel: 'github',
    pass_score: 6, criteria: [emptyCriterion()],
  }
  showNewAssignment.value = true
}
async function createAssignment() {
  const d = draft.value
  try {
    await api('/methodist/assignments', { method: 'POST', body: JSON.stringify({
      course_id: d.course_id || null, title: d.title, statement: d.statement,
      deadline_at: d.deadline_at ? new Date(d.deadline_at).toISOString() : null,
      effort_weight: Number(d.effort_weight) || 1, submission_channel: d.submission_channel,
      pass_score: Number(d.pass_score) || 0,
      criteria: d.criteria.filter(c => c.title.trim()).map(c => ({ key: c.key, title: c.title, max_score: Number(c.max_score) || 1, student_hint: c.student_hint })),
    }) })
    showNewAssignment.value = false; notice.value = 'Задание создано'; await load()
  } catch (e) { error.value = e.message }
}

function startEditAssignment(item) {
  editAssignmentId.value = item.id
  assignmentEdit.value = {
    title: item.title, statement: item.statement,
    deadline_at: item.deadline_at ? item.deadline_at.slice(0, 16) : '',
    effort_weight: item.effort_weight, submission_channel: item.submission_channel,
  }
}
async function saveAssignment(id) {
  const e = assignmentEdit.value
  try {
    const res = await api(`/methodist/assignments/${id}`, { method: 'PATCH', body: JSON.stringify({
      title: e.title, statement: e.statement,
      deadline_at: e.deadline_at ? new Date(e.deadline_at).toISOString() : null,
      effort_weight: Number(e.effort_weight) || 1, submission_channel: e.submission_channel,
    }) })
    editAssignmentId.value = ''
    notice.value = res.versioned ? `Задание обновлено — версия рубрики v${res.rubric_version}` : 'Задание обновлено'
    if (versionsOpenId.value === id) rubricVersions.value = await api(`/methodist/assignments/${id}/rubrics`)
    await load()
  } catch (err) { error.value = err.message }
}

function startCriteria(item) {
  criteriaEditId.value = item.id
  criteriaDraft.value = item.rubric.map(c => ({ key: c.key, title: c.title, max_score: c.max_score, student_hint: c.student_hint || '' }))
  if (!criteriaDraft.value.length) criteriaDraft.value = [emptyCriterion()]
}
async function saveCriteria(item) {
  try {
    await api(`/methodist/assignments/${item.id}/rubrics`, { method: 'POST', body: JSON.stringify({
      criteria: criteriaDraft.value.filter(c => c.title.trim()).map(c => ({ key: c.key || '', title: c.title, max_score: Number(c.max_score) || 1, student_hint: c.student_hint })),
      pass_score: item.pass_score ?? 0, note: 'Правка критериев',
    }) })
    criteriaEditId.value = ''; notice.value = `Опубликована рубрика v${(item.rubric_version || 0) + 1}`; await load()
  } catch (e) { error.value = e.message }
}

async function publishAssignment(item, published) {
  try {
    await api(`/methodist/assignments/${item.id}/publish`, { method: 'POST', body: JSON.stringify({ published }) })
    notice.value = published ? 'Задание опубликовано — видно студентам курса и в реестре работ' : 'Задание снято с публикации'
    await load()
  } catch (e) { error.value = e.message }
}

// --- история версий рубрики (откат «как в гите») -------------------------
const versionsOpenId = ref('')
const rubricVersions = ref([])
async function toggleVersions(item) {
  if (versionsOpenId.value === item.id) { versionsOpenId.value = ''; return }
  try {
    rubricVersions.value = await api(`/methodist/assignments/${item.id}/rubrics`)
    versionsOpenId.value = item.id
  } catch (e) { error.value = e.message }
}
async function restoreVersion(item, v) {
  if (!window.confirm(`Вернуть версию рубрики v${v.version}? Её содержимое станет новой версией — история сохранится, старые оценки не изменятся.`)) return
  try {
    const res = await api(`/methodist/assignments/${item.id}/rubrics/${v.version}/restore`, { method: 'POST' })
    notice.value = `Активна версия рубрики v${res.version} — копия v${res.restored_from}`
    rubricVersions.value = await api(`/methodist/assignments/${item.id}/rubrics`)
    await load()
  } catch (e) { error.value = e.message }
}

async function saveCourse() {
  try { await api('/methodist/course', { method: 'PATCH', body: JSON.stringify({ reviewer_capacity: course.value.reviewer_capacity, tone_of_voice: course.value.tone_of_voice }) }); notice.value = 'Настройки курса сохранены' }
  catch (e) { error.value = e.message }
}

watch(() => props.active, load)
onMounted(load)
</script>

<template>
  <div v-if="notice" class="toast-success global-toast">✓ {{ notice }}<button @click="notice = ''">×</button></div>
  <div v-if="error" class="toast-error global-toast">{{ error }}<button @click="error = ''">×</button></div>

  <section v-if="active === 'methodist-dashboard' && report">
    <div class="page-heading">
      <div><span class="eyebrow">ОБЗОР КУРСА</span><h1>Дашборд курса</h1><p>{{ report.course ? report.course.title : 'Курс' }} · посчитано по живым записям: {{ report.live_records }} работ, {{ ov.assignments }} опубликованных заданий</p></div>
      <div class="dash-tabs"><button :class="{ active: dashTab === 'overview' }" @click="dashTab = 'overview'">Обзор</button><button v-if="report.quality" :class="{ active: dashTab === 'quality' }" @click="dashTab = 'quality'">Качество проверки</button></div>
    </div>

    <template v-if="dashTab === 'overview'">
      <div class="metric-grid">
        <article><span class="metric-icon blue">▦</span><div><small>Сдано работ</small><b>{{ ov.submitted }}</b><em>{{ pct(ov.submission_rate) }} от ожидаемых · всего {{ ov.expected }}</em></div></article>
        <article><span class="metric-icon green">✓</span><div><small>Проверено</small><b>{{ ov.completed }}</b><em :class="{ positive: completedTrend.good }">{{ completedTrend.text }}</em></div></article>
        <article><span class="metric-icon red">!</span><div><small>Просрочено</small><b>{{ ov.overdue }}</b><em>{{ ov.overdue ? 'сданы после дедлайна' : 'дедлайны соблюдены' }}</em></div></article>
        <article><span class="metric-icon purple">◷</span><div><small>Сдача → результат</small><b>{{ hours(ov.avg_lead_hours) }}</b><em :class="{ positive: leadTrend.good }">{{ leadTrend.text }}</em></div></article>
      </div>

      <div class="mini-metrics">
        <span><b>{{ score(ov.avg_score) }}</b><small>средний балл</small></span>
        <span><b>{{ pct(ov.pass_rate) }}</b><small>зачётов</small></span>
        <span><b>{{ pct(ov.ai_agreement) }}</b><small>согласие с AI</small></span>
        <span><b>{{ nf(ov.in_progress) }}</b><small>у ревьюеров</small></span>
        <span><b>{{ nf(ov.waiting) }}</b><small>ждут распределения</small></span>
        <span><b>{{ nf(ov.not_submitted) }}</b><small>не сдано</small></span>
      </div>

      <div class="dashboard-grid">
        <article class="card">
          <div class="card-title"><div><h2>Воронка проверки</h2><p>Где сейчас находятся сданные работы</p></div></div>
          <div class="funnel"><div v-for="(row, index) in report.funnel" :key="row.status"><span>{{ statusNames[row.status] }}</span><div><i :style="funnelWidth(row)" :class="`bar-${index}`" /></div><b>{{ row.count }}</b></div></div>
        </article>
        <article class="card">
          <div class="card-title"><div><h2>Нагрузка ревьюеров</h2><p>Активные работы и свободный лимит</p></div></div>
          <div v-for="person in report.reviewers" :key="person.id" class="reviewer-load"><span class="avatar purple">{{ initials(person.name) }}</span><div><b>{{ person.name }}</b><span><i :style="`width:${Math.min(100, person.load / person.capacity * 100)}%`" /></span></div><em>{{ person.load }} / {{ person.capacity }}</em></div>
          <div class="insight"><span>▲</span><p><b>Что видно по данным</b>{{ loadHint }}</p></div>
        </article>
      </div>
    </template>

    <template v-else-if="report.quality">
      <div class="analytics-grid">
        <article class="card">
          <div class="card-title"><div><h2>Согласие AI и ревьюера</h2><p>Доля критериев, принятых без правки</p></div><strong class="large-positive">{{ pct(report.quality.agreement.rate) }}</strong></div>
          <div class="line-chart">
            <div class="chart-y"><span>100%</span><span>50%</span><span>0%</span></div>
            <svg viewBox="0 0 600 180" preserveAspectRatio="none">
              <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8b5cf6" stop-opacity=".25" /><stop offset="1" stop-color="#8b5cf6" stop-opacity="0" /></linearGradient></defs>
              <polygon v-if="agreementArea" :points="agreementArea" fill="url(#area)" />
              <polyline v-if="agreementLine" :points="agreementLine" fill="none" stroke="#8b5cf6" stroke-width="4" />
              <circle v-for="point in agreementPoints" :key="point.x" :cx="point.x" :cy="point.y" r="5" fill="#8b5cf6" />
            </svg>
            <div class="chart-x"><span v-for="row in weeks" :key="row.week_start">{{ formatDate(row.week_start) }}</span></div>
          </div>
          <div class="agree-legend"><span><b>{{ report.quality.agreement.accepted }}</b> принято</span><span><b>{{ report.quality.agreement.changed }}</b> исправлено</span><span><b>{{ report.quality.agreement.rejected }}</b> отклонено</span><span>из <b>{{ report.quality.agreement.decided }}</b> решений</span></div>
        </article>
        <article class="card">
          <div class="card-title"><div><h2>Сдача → результат</h2><p>Среднее время по неделям, часы</p></div><strong>{{ hours(ov.avg_lead_hours) }}</strong></div>
          <div class="time-bars"><div v-for="row in weeks" :key="row.week_start"><i :style="barHeight(row)" /><span>{{ nf(row.avg_lead_hours) }}</span><small>{{ formatDate(row.week_start) }}</small></div></div>
        </article>
      </div>

      <article class="card corrections">
        <div class="card-title"><div><h2>Критерии с частыми правками</h2><p>Ревьюер меняет или отклоняет оценку AI — кандидаты на уточнение формулировки</p></div><span v-if="criteriaRows.length" class="warning-chip">! максимум {{ pct(criteriaRows[0].correction_rate) }}</span></div>
        <div v-for="row in criteriaRows" :key="row.key" class="correction-row">
          <b>{{ row.title }}</b>
          <div><i :style="`width:${Math.max(2, row.correction_rate)}%`" /></div>
          <strong>{{ pct(row.correction_rate) }}</strong>
          <small>{{ row.reviews }} ревью · AI {{ score(row.avg_ai) }} → {{ score(row.avg_final) }}</small>
        </div>
        <div v-if="!criteriaRows.length" class="empty-mini">Ревьюеры ещё не приняли ни одного решения по критериям.</div>
        <button v-if="report.quality.criteria.length > 8" class="text-button" @click="showAllCriteria = !showAllCriteria">{{ showAllCriteria ? 'свернуть' : `показать все · ${report.quality.criteria.length}` }}</button>
      </article>

      <article class="card">
        <div class="card-title"><div><h2>Ревьюеры</h2><p>Производительность за всё время и текущая загрузка</p></div></div>
        <div class="rev-stats">
          <div class="rev-stats-head"><span>Ревьюер</span><span>Проверено</span><span>Время проверки</span><span>Согласие с AI</span><span>Средний результат</span><span>Сейчас в работе</span></div>
          <div v-for="person in report.reviewers" :key="person.id">
            <span class="student-cell"><i>{{ initials(person.name) }}</i><span><b>{{ person.name }}</b><small>{{ person.available ? 'в распределении' : 'снят с распределения' }}</small></span></span>
            <span>{{ person.completed }}</span>
            <span>{{ hours(person.avg_review_hours) }}</span>
            <span>{{ pct(person.agreement) }}<small>{{ person.decided }} решений</small></span>
            <span>{{ pct(person.avg_percent) }}</span>
            <span>{{ person.load }} / {{ person.capacity }}</span>
          </div>
        </div>
      </article>

      <p class="data-note">AI-прогоны: {{ report.quality.ai_runs.ready }} готово · {{ report.quality.ai_runs.failed }} с ошибкой · {{ report.quality.ai_runs.pending }} в очереди.<template v-if="report.demo_reviews"> Из {{ report.live_records }} работ {{ report.demo_reviews }} проверены демо-фикстурами курса.</template></p>
    </template>
  </section>

  <section v-else-if="active === 'methodist-performance' && performance">
    <div class="page-heading"><div><span class="eyebrow">УСПЕВАЕМОСТЬ</span><h1>Таблица успеваемости</h1><p>{{ performance.course ? performance.course.title : 'Курс' }} · опубликованные задания. В ячейке — итоговый балл после ревью</p></div></div>
    <div class="metric-grid">
      <article><span class="metric-icon blue">▦</span><div><small>Студентов</small><b>{{ performance.summary.students }}</b><em>{{ performance.summary.assignments }} заданий в зачёте</em></div></article>
      <article><span class="metric-icon green">✓</span><div><small>Сдано</small><b>{{ performance.summary.submitted }} / {{ performance.summary.expected }}</b><em>{{ pct(performance.summary.submission_rate) }} ожидаемых работ</em></div></article>
      <article><span class="metric-icon purple">◷</span><div><small>Средний результат</small><b>{{ pct(performance.summary.avg_percent) }}</b><em>от максимума по рубрике · зачётов {{ pct(performance.summary.pass_rate) }}</em></div></article>
      <article><span class="metric-icon red">!</span><div><small>В зоне риска</small><b>{{ performance.summary.at_risk }}</b><em>средний результат ниже 60%</em></div></article>
    </div>
    <div class="registry-tools"><label class="search">⌕<input v-model="perfSearch" placeholder="Студент" /></label><select v-model="perfSort"><option value="name">По алфавиту</option><option value="best">Сначала сильные</option><option value="risk">Сначала отстающие</option><option value="gaps">Больше всего пропусков</option></select></div>

    <div v-if="perfRows.length && performance.assignments.length" class="table-card perf-table">
      <div class="table-row table-head" :style="{ gridTemplateColumns: perfColumns }"><span>Студент</span><span v-for="column in performance.assignments" :key="column.id" :title="column.title">{{ column.title }}</span><span>Итог</span></div>
      <template v-for="row in perfRows" :key="row.student_id">
        <button class="table-row perf-row" :style="{ gridTemplateColumns: perfColumns }" @click="toggleStudent(row.student_id)">
          <span class="student-cell"><i>{{ initials(row.student) }}</i><span><b>{{ row.student }}</b><small>{{ isStudentOpen(row.student_id) ? 'свернуть' : 'подробнее' }}</small></span></span>
          <span v-for="(cell, index) in row.cells" :key="cell.assignment_id" class="perf-cell" :class="cellClass(cell)" :title="cellTitle(cell, performance.assignments[index])">{{ cellText(cell) }}</span>
          <span class="perf-total"><b>{{ pct(row.totals.avg_percent) }}</b><small>сдано {{ row.totals.submitted }}/{{ row.totals.expected }} · зачётов {{ row.totals.passed }}</small></span>
        </button>
        <div v-if="isStudentOpen(row.student_id)" class="perf-detail">
          <div v-for="(cell, index) in row.cells" :key="cell.assignment_id">
            <b>{{ performance.assignments[index].title }}</b>
            <StatusBadge :status="cell.status" />
            <em>{{ isNil(cell.score) ? '—' : `${score(cell.score)} / ${cell.max_score}` }}</em>
            <small>{{ cell.reviewer || 'ревьюер не назначен' }}</small>
            <small :class="{ danger: cell.is_overdue }">{{ cell.submitted_at ? formatDate(cell.submitted_at, true) : 'не сдано' }}</small>
          </div>
        </div>
      </template>
      <div class="table-row perf-foot" :style="{ gridTemplateColumns: perfColumns }"><span>Итого по заданию</span><span v-for="column in performance.assignments" :key="column.id" class="perf-cell"><b>{{ pct(column.stats.avg_percent) }}</b><small>{{ column.stats.submitted }}/{{ column.stats.expected }}</small></span><span class="perf-total"><b>{{ pct(performance.summary.avg_percent) }}</b><small>зачётов {{ pct(performance.summary.pass_rate) }}</small></span></div>
    </div>
    <div v-else class="empty-state"><span>∅</span><h2>Показывать нечего</h2><p>Опубликуйте задание в «Задания и критерии» или измените поиск.</p></div>
  </section>

  <section v-else-if="active === 'methodist-distribution'">
    <div class="page-heading"><div><span class="eyebrow">УПРАВЛЕНИЕ ПОТОКОМ</span><h1>Распределение работ</h1><p>Специализация → минимальная нагрузка → round-robin при равенстве → кап курса</p></div><button v-if="!autoAssign" class="primary" :disabled="!waitingReady" @click="applyDistribution">Подтвердить всё · {{ waitingReady }}</button></div>
    <label class="auto-toggle">
      <input type="checkbox" :checked="autoAssign" @change="toggleAuto" />
      <span><b>Автоматическое распределение</b><small>Новые работы назначаются сразу при сдаче и при снятии ревьюера — без ручного подтверждения. Конкретную работу всё равно можно передать другому ревьюеру ниже.</small></span>
    </label>
    <div class="cap-strip">
      <div v-for="person in reviewerLoads" :key="person.id" class="cap-chip" :class="{ off: !person.available, full: isFull(person) }">
        <b>{{ person.name }}</b><em>{{ person.load }}/{{ person.capacity }}</em>
        <button class="text-button" @click="toggleAvailability(person)">{{ person.available ? 'снять' : 'вернуть' }}</button>
      </div>
    </div>

    <h2 class="dist-subhead">Ожидают распределения · {{ distribution.length }}</h2>
    <div class="table-card distribution-table">
      <div class="table-row table-head"><span>Работа</span><span>Ревьюер</span><span>Почему</span><span /></div>
      <div v-for="row in distribution" :key="row.submission.id" class="table-row" :class="{ 'over-cap': row.over_capacity }">
        <span class="student-cell"><i>{{ initials(row.submission.student) }}</i><span><b>{{ row.submission.student }}</b><small>{{ row.submission.assignment }}</small></span></span>
        <span><select v-model="row.chosen" class="rev-picker"><option value="">— не назначен —</option><option v-for="p in reviewerLoads" :key="p.id" :value="p.id" :disabled="!p.available">{{ p.name }} · {{ p.load }}/{{ p.capacity }}{{ p.available ? '' : ' · недоступен' }}</option></select></span>
        <span class="reason">{{ row.explanation }}</span>
        <button class="text-button" :disabled="!row.chosen" @click="assignRow(row)">назначить</button>
      </div>
      <div v-if="!distribution.length" class="empty-state in-table"><span>✓</span><h2>Все работы распределены</h2><p>Новых предложений пока нет.</p></div>
    </div>

    <template v-if="assignedRows.length">
      <h2 class="dist-subhead">Распределены — можно передать другому · {{ assignedRows.length }}</h2>
      <div class="table-card distribution-table">
        <div class="table-row table-head"><span>Работа</span><span>Ревьюер</span><span>Назначено</span><span /></div>
        <div v-for="row in assignedRows" :key="row.submission.id" class="table-row">
          <span class="student-cell"><i>{{ initials(row.submission.student) }}</i><span><b>{{ row.submission.student }}</b><small>{{ row.submission.assignment }}</small></span></span>
          <span><select v-model="row.chosen" class="rev-picker"><option v-for="p in reviewerLoads" :key="p.id" :value="p.id" :disabled="!p.available">{{ p.name }} · {{ p.load }}/{{ p.capacity }}{{ p.available ? '' : ' · недоступен' }}</option></select></span>
          <span class="reason">{{ row.status === 'in_review' ? 'на проверке — передача перезапустит ревью' : row.explanation }}</span>
          <button class="text-button" :disabled="row.chosen === row.reviewer.id" @click="reassignAssigned(row)">передать</button>
        </div>
      </div>
    </template>
  </section>

  <section v-else-if="active === 'methodist-registry'">
    <div class="page-heading"><div><span class="eyebrow">УПРАВЛЕНИЕ ПОТОКОМ</span><h1>Реестр работ</h1><p>Опубликованные задания. Строка на каждого студента курса, включая не сдавших. Переназначение — на экране «Распределение»</p></div></div>
    <div class="registry-tools"><label class="search">⌕<input v-model="registrySearch" placeholder="Студент или задание" /></label><select v-model="statusFilter"><option value="">Все статусы</option><option v-for="(name, key) in statusNames" :key="key" :value="key">{{ name }}</option></select></div>

    <div v-for="g in filteredRegistry" :key="g.assignment.id" class="reg-group">
      <button class="reg-group-head" @click="toggleGroup(g.assignment.id)">
        <span class="reg-caret">{{ isGroupOpen(g.assignment.id) ? '▾' : '▸' }}</span>
        <span class="reg-group-title"><b>{{ g.assignment.title }}</b><small>{{ g.assignment.course }}</small></span>
        <span class="reg-stats"><em>сдали {{ g.stats.submitted }}/{{ g.stats.students }}</em><em>проверено {{ g.stats.completed }}</em><em v-if="g.stats.overdue" class="danger">просрочка {{ g.stats.overdue }}</em></span>
      </button>
      <div v-if="isGroupOpen(g.assignment.id)" class="table-card registry-table">
        <div class="table-row table-head"><span>Студент</span><span>Статус</span><span>Ревьюер</span><span>Сдано</span><span>AI</span></div>
        <div v-for="row in g.rows" :key="row.student_id" class="table-row">
          <span class="student-cell"><i>{{ initials(row.student) }}</i><span><b>{{ row.student }}</b></span></span>
          <StatusBadge :status="row.status" />
          <span class="registry-reviewer"><b>{{ row.reviewer || '—' }}</b></span>
          <span :class="{ danger: row.is_overdue }"><b>{{ row.submitted_at ? formatDate(row.submitted_at, true) : '—' }}</b><small v-if="row.is_overdue">После срока</small></span>
          <span v-if="row.ai_status" class="ai-ready ready"><i>✦</i>{{ row.ai_status === 'ready' ? 'Готов' : row.ai_status }}</span><span v-else>—</span>
        </div>
      </div>
    </div>
    <div v-if="!filteredRegistry.length" class="empty-state"><span>∅</span><h2>Ничего не найдено</h2><p>Опубликуйте задание в «Задания и критерии» или измените фильтр.</p></div>
  </section>

  <section v-else-if="active === 'methodist-rubrics'">
    <div class="page-heading"><div><span class="eyebrow">КОНТЕНТ КУРСА</span><h1>Задания и критерии</h1><p>Любая правка — критериев или самого задания — создаёт новую версию рубрики; через «Историю версий» можно откатиться на любую</p></div><button class="primary" @click="toggleNewAssignment">{{ showNewAssignment ? 'Отмена' : '＋ Новое задание' }}</button></div>

    <article v-if="showNewAssignment && draft" class="card rubric-card assign-form">
      <h2>Новое задание</h2>
      <div class="af-row">
        <label>Название<input v-model="draft.title" /></label>
        <label>Курс<select v-model="draft.course_id"><option v-for="c in courses" :key="c.id" :value="c.id">{{ c.title }}</option></select></label>
      </div>
      <label>Условие<textarea v-model="draft.statement" rows="4" /></label>
      <div class="af-row">
        <label>Дедлайн<input v-model="draft.deadline_at" type="datetime-local" /></label>
        <label>Трудоёмкость<input v-model.number="draft.effort_weight" type="number" min="0.5" step="0.5" /></label>
        <label>Канал сдачи<select v-model="draft.submission_channel"><option value="github">GitHub</option><option value="stepik">Stepik</option><option value="gdocs">Google Docs</option></select></label>
        <label>Проходной балл<input v-model.number="draft.pass_score" type="number" min="0" /></label>
      </div>
      <h3 class="dist-subhead">Критерии</h3>
      <div v-for="(c, i) in draft.criteria" :key="i" class="af-crit">
        <input v-model="c.title" placeholder="Название критерия" />
        <input v-model.number="c.max_score" type="number" min="0.5" step="0.5" />
        <input v-model="c.student_hint" placeholder="Подсказка студенту (необязательно)" />
        <button v-if="draft.criteria.length > 1" class="text-button" @click="draft.criteria.splice(i, 1)">×</button>
      </div>
      <button class="text-button" @click="draft.criteria.push(emptyCriterion())">＋ ещё критерий</button>
      <div class="af-actions"><button class="primary" :disabled="!draft.title.trim() || !draft.criteria.some(c => c.title.trim())" @click="createAssignment">Создать задание</button></div>
    </article>

    <template v-for="(list, courseName) in courseGroups" :key="courseName">
      <h2 class="dist-subhead">{{ courseName }}</h2>
      <article v-for="item in list" :key="item.id" class="card rubric-card">
        <button class="rubric-card-head" @click="toggleCard(item.id)">
          <span class="reg-caret">{{ isCardOpen(item.id) || editAssignmentId === item.id || criteriaEditId === item.id ? '▾' : '▸' }}</span>
          <span class="rubric-card-title"><b>{{ item.title }}</b><small>{{ item.rubric.length }} критериев · трудоёмкость {{ item.effort_weight }}</small></span>
          <span class="version-pill" :class="item.published ? 'pub' : 'draft'">{{ item.published ? 'Опубликовано' : 'Черновик' }} · v{{ item.rubric_version || '—' }}</span>
        </button>

        <div v-if="isCardOpen(item.id) || editAssignmentId === item.id || criteriaEditId === item.id" class="rubric-card-body">
          <template v-if="editAssignmentId === item.id && assignmentEdit">
            <div class="card-title"><div><h2>Редактирование задания</h2></div><div class="tc-head-actions"><button class="secondary" @click="editAssignmentId = ''">Отмена</button><button class="primary" @click="saveAssignment(item.id)">Сохранить</button></div></div>
            <label>Название<input v-model="assignmentEdit.title" /></label>
            <label>Условие<textarea v-model="assignmentEdit.statement" rows="4" /></label>
            <div class="af-row">
              <label>Дедлайн<input v-model="assignmentEdit.deadline_at" type="datetime-local" /></label>
              <label>Трудоёмкость<input v-model.number="assignmentEdit.effort_weight" type="number" min="0.5" step="0.5" /></label>
              <label>Канал<select v-model="assignmentEdit.submission_channel"><option value="github">GitHub</option><option value="stepik">Stepik</option><option value="gdocs">Google Docs</option></select></label>
            </div>
          </template>
          <template v-else-if="criteriaEditId === item.id">
            <div class="card-title"><div><h2>Критерии · {{ item.title }}</h2><p>Сохранение публикует новую версию рубрики</p></div><div class="tc-head-actions"><button class="secondary" @click="criteriaEditId = ''">Отмена</button><button class="primary" @click="saveCriteria(item)">Опубликовать v{{ (item.rubric_version || 0) + 1 }}</button></div></div>
            <div v-for="(c, i) in criteriaDraft" :key="i" class="af-crit">
              <input v-model="c.title" placeholder="Название критерия" />
              <input v-model.number="c.max_score" type="number" min="0.5" step="0.5" />
              <input v-model="c.student_hint" placeholder="Подсказка студенту" />
              <button v-if="criteriaDraft.length > 1" class="text-button" @click="criteriaDraft.splice(i, 1)">×</button>
            </div>
            <button class="text-button" @click="criteriaDraft.push(emptyCriterion())">＋ ещё критерий</button>
          </template>
          <template v-else>
            <p class="rubric-statement">{{ item.statement || 'Условие не заполнено' }}</p>
            <div class="rubric-summary"><span><b>{{ item.max_score ?? '—' }}</b><small>макс. балл</small></span><span><b>{{ item.rubric.length }}</b><small>критериев</small></span><span><b>{{ item.effort_weight }}</b><small>трудоёмкость</small></span><span><b>{{ item.deadline_at ? formatDate(item.deadline_at, true) : '—' }}</b><small>дедлайн</small></span></div>
            <div class="criteria-table"><div v-for="(criterion, index) in item.rubric" :key="criterion.key"><span>{{ index + 1 }}</span><b>{{ criterion.title }}</b><em>{{ criterion.max_score }} б.</em></div></div>
            <div class="rubric-actions"><p>{{ item.rubric_note || '—' }}</p><button class="secondary" @click="toggleVersions(item)">{{ versionsOpenId === item.id ? 'Скрыть историю' : `История версий · ${item.rubric_versions || 1}` }}</button><button class="secondary" @click="startEditAssignment(item)">✎ Задание</button><button class="secondary" @click="startCriteria(item)">✎ Критерии</button><button v-if="!item.published" class="primary" @click="publishAssignment(item, true)">Опубликовать</button><button v-else class="secondary" @click="publishAssignment(item, false)">Снять с публикации</button></div>
            <div v-if="versionsOpenId === item.id" class="version-history">
              <div v-for="v in rubricVersions" :key="v.id" class="version-row" :class="{ current: v.is_current }">
                <span class="vh-tag">v{{ v.version }}</span>
                <span class="vh-main"><b>{{ v.note || '—' }}</b><small><template v-if="v.assignment_snapshot && v.assignment_snapshot.title !== item.title">«{{ v.assignment_snapshot.title }}» · </template>{{ v.criteria.length }} критериев · {{ v.max_score }} б. · проходной {{ v.pass_score }}<template v-if="v.author"> · {{ v.author }}</template><template v-if="v.published_at"> · {{ formatDate(v.published_at, true) }}</template></small></span>
                <span v-if="v.is_current" class="vh-current">текущая</span>
                <button v-else class="text-button" @click="restoreVersion(item, v)">Вернуть</button>
              </div>
              <p v-if="!rubricVersions.length" class="empty-mini">Версий пока нет.</p>
            </div>
          </template>
        </div>
      </article>
    </template>
    <div v-if="!assignments.length && !showNewAssignment" class="empty-state"><span>✦</span><h2>Пока нет заданий</h2><p>Создайте первое кнопкой «＋ Новое задание» или отправьте из AI-конструктора ДЗ.</p></div>
  </section>

  <TaskCreaterView v-else-if="active === 'methodist-taskcreater'" />

  <section v-else-if="active === 'methodist-settings' && course">
    <div class="page-heading"><div><span class="eyebrow">КУРС</span><h1>Настройки курса</h1><p>Правила коммуникации, нагрузки и дедлайнов</p></div><button class="primary" @click="saveCourse">Сохранить изменения</button></div>
    <div class="settings-grid"><article class="card form-card"><div class="setting-icon blue">Aa</div><div><h2>Tone of voice</h2><p>Этот стиль используется в черновиках обратной связи.</p><label>Стиль<input v-model="course.tone_of_voice.style" /></label><label>Обращение<select v-model="course.tone_of_voice.address"><option>на вы</option><option>на ты</option></select></label><label>Правила<textarea :value="course.tone_of_voice.rules.join('\n')" rows="4" @input="course.tone_of_voice.rules = $event.target.value.split('\n')" /></label></div></article><article class="card form-card"><div class="setting-icon purple">▦</div><div><h2>Нагрузка ревьюеров</h2><p>Жёсткий предел активных работ на одного человека.</p><label>Максимум работ<input v-model.number="course.reviewer_capacity" type="number" min="1" max="100" /></label><div class="setting-hint">Распределение не предложит ревьюера, если лимит исчерпан.</div></div></article><article class="card form-card"><div class="setting-icon green">◷</div><div><h2>Контрольные сроки</h2><p>Риск подсвечивается за 24 часа до дедлайна.</p><div class="setting-hint">Порог фиксированный и пока не настраивается.</div><label class="toggle-row disabled"><span><b>In-app уведомления</b><small>Всегда включены для всех ролей</small></span><input type="checkbox" checked disabled /></label><label class="toggle-row disabled"><span><b>Telegram</b><small>Выключено фиче-флагом</small></span><input type="checkbox" disabled /></label></div></article></div>
  </section>
</template>
