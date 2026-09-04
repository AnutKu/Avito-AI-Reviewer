<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, formatDate, statusNames } from '../../shared/api'
import DemoBadge from '../../shared/ui/DemoBadge.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import TaskCreaterView from './TaskCreaterView.vue'

const props = defineProps({ active: String })
const dashboard = ref(null)
const distribution = ref([])        // работы, ожидающие распределения
const assignedRows = ref([])        // распределённые работы — можно передать другому
const reviewerLoads = ref([])
const autoAssign = ref(false)
const registry = ref([])
const registrySearch = ref('')
const assignments = ref([])
const courses = ref([])
const analytics = ref(null)
const course = ref(null)
const error = ref('')
const notice = ref('')
const statusFilter = ref('')

async function load(active = props.active) {
  error.value = ''
  try {
    if (active === 'methodist-dashboard') dashboard.value = await api('/methodist/dashboard')
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
    if (active === 'methodist-analytics') analytics.value = await api('/methodist/analytics')
    if (active === 'methodist-settings') course.value = await api('/methodist/course')
  } catch (e) { error.value = e.message }
}

const isFull = (p) => p.slots_left <= 0
const initials = (s) => s.split(' ').map(x => x[0]).join('').slice(0, 2)
const waitingReady = computed(() => distribution.value.filter(x => x.chosen).length)

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
    await api(`/methodist/assignments/${id}`, { method: 'PATCH', body: JSON.stringify({
      title: e.title, statement: e.statement,
      deadline_at: e.deadline_at ? new Date(e.deadline_at).toISOString() : null,
      effort_weight: Number(e.effort_weight) || 1, submission_channel: e.submission_channel,
    }) })
    editAssignmentId.value = ''; notice.value = 'Задание обновлено'; await load()
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
      pass_score: item.pass_score ?? 0, note: 'Обновлено в кабинете',
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

  <section v-if="active === 'methodist-dashboard' && dashboard">
    <div class="page-heading"><div><span class="eyebrow">ОБЗОР КУРСА</span><h1>Добрый день, Анна</h1><p>Главное по потоку на сегодня, 3 сентября</p></div><DemoBadge /></div>
    <div class="metric-grid"><article><span class="metric-icon blue">▦</span><div><small>Всего работ</small><b>{{ dashboard.metrics.total }}</b><em>в потоке</em></div></article><article><span class="metric-icon green">✓</span><div><small>Проверено</small><b>{{ dashboard.metrics.completed }}</b><em class="positive">+8 за неделю</em></div></article><article><span class="metric-icon red">!</span><div><small>Просрочено</small><b>{{ dashboard.metrics.overdue }}</b><em>нужны действия</em></div></article><article><span class="metric-icon purple">◷</span><div><small>Среднее время</small><b>{{ dashboard.metrics.average_hours }} ч</b><em class="positive">−21% к прошлой неделе</em></div></article></div>
    <div class="dashboard-grid"><article class="card"><div class="card-title"><div><h2>Воронка проверки</h2><p>Живые записи демо-БД: {{ dashboard.live_records }}</p></div><span>Последние 7 дней⌄</span></div><div class="funnel"><div v-for="(row, index) in dashboard.funnel" :key="row.status"><span>{{ statusNames[row.status] }}</span><div><i :style="`width:${Math.max(4, row.count * 25)}%`" :class="`bar-${index}`" /></div><b>{{ row.count }}</b></div></div></article><article class="card"><div class="card-title"><div><h2>Нагрузка ревьюеров</h2><p>Активные работы и доступность</p></div></div><div v-for="person in dashboard.reviewers" :key="person.id" class="reviewer-load"><span class="avatar purple">{{ person.name.split(' ').map(x => x[0]).join('') }}</span><div><b>{{ person.name }}</b><span><i :style="`width:${person.active / person.capacity * 100}%`" /></span></div><em>{{ person.active }} / {{ person.capacity }}</em></div><div class="insight"><span>✦</span><p><b>AI-подсказка</b>Распределение сбалансировано. У всех ревьюеров есть свободный кап.</p></div></article></div>
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
    <div class="page-heading"><div><span class="eyebrow">КОНТЕНТ КУРСА</span><h1>Задания и критерии</h1><p>Список заданий по курсам. Опубликованные рубрики неизменяемы — правка создаёт новую версию</p></div><button class="primary" @click="toggleNewAssignment">{{ showNewAssignment ? 'Отмена' : '＋ Новое задание' }}</button></div>

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
            <div class="rubric-actions"><p>{{ item.rubric_note || '—' }}</p><button class="secondary" @click="startEditAssignment(item)">✎ Задание</button><button class="secondary" @click="startCriteria(item)">✎ Критерии</button><button v-if="!item.published" class="primary" @click="publishAssignment(item, true)">Опубликовать</button><button v-else class="secondary" @click="publishAssignment(item, false)">Снять с публикации</button></div>
          </template>
        </div>
      </article>
    </template>
    <div v-if="!assignments.length && !showNewAssignment" class="empty-state"><span>✦</span><h2>Пока нет заданий</h2><p>Создайте первое кнопкой «＋ Новое задание» или отправьте из AI-конструктора ДЗ.</p></div>
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
