<script setup>
// Банк заданий и критериев: один раздел на весь жизненный цикл задания —
// список → создание или правка → проверка на AI-персонах → рекомендации →
// публикация. AI здесь не отдельный продукт и не отдельное хранилище, а
// инструменты внутри редактора: ни один ответ агента не попадает в задание,
// пока человек его не подтвердил.
import { computed, onUnmounted, ref, watch } from 'vue'
import { api, formatDate } from '../../shared/api'
import MarkdownText from '../../shared/ui/MarkdownText.vue'
import {
  AI_BLOCKS, PERSONA_TYPE, RUN_STATE, SEVERITY, criteriaTotal, decidedRecommendations,
  fieldTitle, filterAssignments, isDirty, kindLabel, kindWhy, openRecommendations,
  publishBlockers, runIntro, runTitle, scoreWarning, sortAssignments, splitByPublication,
} from '../../shared/taskbank'

const props = defineProps({ sub: { type: Array, default: () => [] } })
const emit = defineEmits(['navigate'])

const ROOT = 'methodist-rubrics'
const go = (path = '') => emit('navigate', path ? `${ROOT}/${path}` : ROOT)

const rows = ref([])
const courses = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

// --- список ---------------------------------------------------------------
const tab = ref('published')
const search = ref('')
const sort = ref('recent')

const buckets = computed(() => splitByPublication(rows.value))
const visible = computed(() =>
  sortAssignments(filterAssignments(buckets.value[tab.value === 'published' ? 'published' : 'drafts'], search.value), sort.value))

// --- маршрут --------------------------------------------------------------
// Экран выводится из хеша, а не из внутреннего флага: прямая ссылка, F5 и
// кнопки «назад/вперёд» обязаны показывать то же, что и клик по интерфейсу.
const view = computed(() => {
  const [first] = props.sub
  if (!first) return 'list'
  if (first === 'run') return 'run'
  return 'editor'
})
const editedId = computed(() => (view.value === 'editor' && props.sub[0] !== 'new' ? props.sub[0] : null))

// --- редактор -------------------------------------------------------------
const emptyCriterion = () => ({ key: '', title: '', max_score: 5, student_hint: '', description: '', expected_signals: [] })
const draft = ref(null)
const saved = ref(null)
const saving = ref(false)
const openCriterion = ref(-1)

const dirty = computed(() => !!draft.value && isDirty(draft.value, saved.value))
const total = computed(() => criteriaTotal(draft.value?.criteria))
const warning = computed(() => (draft.value ? scoreWarning(draft.value.criteria, draft.value.pass_score) : ''))
const blockers = computed(() => (draft.value ? publishBlockers(draft.value) : []))

function blankDraft() {
  return {
    id: null, course_id: courses.value[0]?.id || '', title: '', statement: '',
    deadline_at: '', effort_weight: 1, submission_channel: 'github', pass_score: 0,
    published: false, revision: 0,
    authoring: { topic: '', difficulty: '', estimated_minutes: '', learning_objectives: '', context: '', expected_result: '', constraints: '', submission_format: '', reviewer_notes: '', reference_solution: '' },
    criteria: [emptyCriterion()],
  }
}

function toDraft(row) {
  const a = row.authoring || {}
  return {
    id: row.id, course_id: row.course_id, title: row.title, statement: row.statement,
    deadline_at: row.deadline_at ? row.deadline_at.slice(0, 16) : '',
    effort_weight: row.effort_weight, submission_channel: row.submission_channel,
    pass_score: row.pass_score ?? 0, published: row.published, revision: row.revision || 0,
    authoring: {
      topic: a.topic || '', difficulty: a.difficulty || '', estimated_minutes: a.estimated_minutes || '',
      learning_objectives: Array.isArray(a.learning_objectives) ? a.learning_objectives.join('\n') : (a.learning_objectives || ''),
      context: a.context || '', expected_result: a.expected_result || '', constraints: a.constraints || '',
      submission_format: a.submission_format || '', reviewer_notes: a.reviewer_notes || '',
      reference_solution: a.reference_solution || '',
    },
    criteria: (row.rubric || []).map(c => ({
      key: c.key || '', title: c.title || '', max_score: c.max_score ?? 1, student_hint: c.student_hint || '',
      description: c.description || '', expected_signals: c.expected_signals || [],
    })),
  }
}

function authoringPayload(a) {
  return {
    ...a,
    learning_objectives: (a.learning_objectives || '').split('\n').map(s => s.trim()).filter(Boolean),
    estimated_minutes: Number(a.estimated_minutes) || null,
  }
}

const criteriaPayload = () => draft.value.criteria
  .filter(c => (c.title || '').trim())
  .map(c => ({
    key: c.key || '', title: c.title, max_score: Number(c.max_score) || 1,
    student_hint: c.student_hint || '', description: c.description || '',
    expected_signals: c.expected_signals || [],
  }))

// --- AI-инструменты -------------------------------------------------------
const aiBusy = ref('')
const preview = ref(null)     // { field, mode, current, proposed, note, editing }
const ideaOpen = ref(false)
const idea = ref({ idea: '', track: 'Аналитика данных', task_format: 'auto', total_points: 10, constraints: '' })
const generating = ref(false)

// --- прогон ---------------------------------------------------------------
const runChoice = ref(false)
const runType = ref('student')
const starting = ref(false)
const run = ref(null)
const runs = ref([])
const recEdit = ref(null)     // { id, value }
const deciding = ref('')
let timer = null

const openRecs = computed(() => openRecommendations(run.value))
const decidedRecs = computed(() => decidedRecommendations(run.value))

// --------------------------------------------------------------------------

async function loadList() {
  loading.value = true; error.value = ''
  try {
    ;[rows.value, courses.value] = await Promise.all([api('/methodist/assignments'), api('/methodist/courses')])
  } catch (e) { error.value = e.message } finally { loading.value = false }
}

async function openEditor() {
  if (!rows.value.length) await loadList()
  if (props.sub[0] === 'new') { draft.value = blankDraft(); saved.value = JSON.parse(JSON.stringify(draft.value)); runs.value = []; return }
  const row = rows.value.find(r => r.id === editedId.value)
  if (!row) { error.value = 'Задание не найдено'; go(); return }
  draft.value = toDraft(row)
  saved.value = JSON.parse(JSON.stringify(draft.value))
  try { runs.value = await api(`/methodist/assignments/${row.id}/ai-runs`) } catch { runs.value = [] }
}

async function openRun() {
  const id = props.sub[1]
  if (!id) { go(); return }
  try {
    run.value = await api(`/methodist/ai-runs/${id}`)
    schedulePoll(id)
  } catch (e) { error.value = e.message }
}

function schedulePoll(id) {
  clearTimeout(timer)
  // Опрос идёт только пока есть что ждать: завершённый прогон дальше не
  // меняется, а лишние запросы — это только шум в логах.
  if (!['queued', 'running'].includes(run.value?.status)) return
  timer = setTimeout(async () => {
    try { run.value = await api(`/methodist/ai-runs/${id}`) } catch { /* сеть моргнула — попробуем ещё */ }
    schedulePoll(id)
  }, 2000)
}

watch(() => props.sub.join('/'), () => {
  clearTimeout(timer)
  error.value = ''
  if (view.value === 'list') loadList()
  if (view.value === 'editor') openEditor()
  if (view.value === 'run') openRun()
}, { immediate: true })

onUnmounted(() => clearTimeout(timer))

// --- действия списка ------------------------------------------------------

function leaveEditor() {
  if (dirty.value && !window.confirm('Изменения не сохранены. Выйти и потерять их?')) return
  go()
}

async function save({ silent = false } = {}) {
  const d = draft.value
  if (!(d.title || '').trim()) { error.value = 'Заполните название'; return null }
  saving.value = true; error.value = ''
  try {
    const authoring = authoringPayload(d.authoring)
    if (!d.id) {
      const created = await api('/methodist/assignments', { method: 'POST', body: JSON.stringify({
        course_id: d.course_id || null, title: d.title, statement: d.statement,
        deadline_at: d.deadline_at ? new Date(d.deadline_at).toISOString() : null,
        effort_weight: Number(d.effort_weight) || 1, submission_channel: d.submission_channel,
        pass_score: Number(d.pass_score) || 0, authoring, criteria: criteriaPayload(),
      }) })
      d.id = created.id
      await loadList()
      if (!silent) notice.value = 'Черновик сохранён'
      go(d.id)
      return d.id
    }
    const base = saved.value
    const fieldsChanged = ['title', 'statement', 'deadline_at', 'effort_weight', 'submission_channel'].some(f => d[f] !== base[f])
      || JSON.stringify(d.authoring) !== JSON.stringify(base.authoring)
    if (fieldsChanged) {
      await api(`/methodist/assignments/${d.id}`, { method: 'PATCH', body: JSON.stringify({
        title: d.title, statement: d.statement,
        deadline_at: d.deadline_at ? new Date(d.deadline_at).toISOString() : null,
        effort_weight: Number(d.effort_weight) || 1, submission_channel: d.submission_channel,
        authoring,
      }) })
    }
    if (JSON.stringify(d.criteria) !== JSON.stringify(base.criteria) || d.pass_score !== base.pass_score) {
      await api(`/methodist/assignments/${d.id}/rubrics`, { method: 'POST', body: JSON.stringify({
        criteria: criteriaPayload(), pass_score: Number(d.pass_score) || 0, note: 'Правка в редакторе',
      }) })
    }
    await loadList()
    const fresh = rows.value.find(r => r.id === d.id)
    if (fresh) { draft.value = toDraft(fresh); saved.value = JSON.parse(JSON.stringify(draft.value)) }
    if (!silent) notice.value = 'Изменения сохранены'
    return d.id
  } catch (e) { error.value = e.message; return null } finally { saving.value = false }
}

async function publish(flag) {
  if (flag && blockers.value.length) { error.value = `Перед публикацией заполните: ${blockers.value.join(', ')}`; return }
  if (dirty.value && !(await save({ silent: true }))) return
  try {
    await api(`/methodist/assignments/${draft.value.id}/publish`, { method: 'POST', body: JSON.stringify({ published: flag }) })
    notice.value = flag ? 'Задание опубликовано — оно видно студентам курса' : 'Задание снято с публикации'
    await loadList()
    const fresh = rows.value.find(r => r.id === draft.value.id)
    if (fresh) { draft.value = toDraft(fresh); saved.value = JSON.parse(JSON.stringify(draft.value)) }
  } catch (e) { error.value = e.message }
}

async function duplicate(row) {
  // Копия всегда черновик, даже если исходник опубликован: публикация — это
  // решение по конкретному заданию, наследовать её молча нельзя.
  try {
    const created = await api('/methodist/assignments', { method: 'POST', body: JSON.stringify({
      course_id: row.course_id, title: `${row.title} (копия)`, statement: row.statement,
      effort_weight: row.effort_weight, submission_channel: row.submission_channel,
      pass_score: row.pass_score ?? 0, authoring: row.authoring || {},
      criteria: (row.rubric || []).map(c => ({ ...c, key: '' })),
    }) })
    notice.value = 'Создана копия — она лежит в черновиках'
    await loadList()
    go(created.id)
  } catch (e) { error.value = e.message }
}

async function remove(row) {
  const works = row.submissions || 0
  const toll = works ? ` Вместе с ним будут удалены сданные работы (${works}) и все оценки по ним.` : ''
  if (!window.confirm(`Удалить задание «${row.title}»?${toll} Это действие необратимо.`)) return
  try {
    const res = await api(`/methodist/assignments/${row.id}`, { method: 'DELETE' })
    notice.value = res.submissions ? `Задание удалено вместе с работами (${res.submissions})` : 'Задание удалено'
    await loadList()
    if (view.value === 'editor') go()
  } catch (e) { error.value = e.message }
}

// --- AI: заполнение блока -------------------------------------------------

function blockValue(field) {
  return field === 'statement' ? draft.value.statement : (draft.value.authoring[field] || '')
}
function setBlock(field, value) {
  if (field === 'statement') draft.value.statement = value
  else draft.value.authoring[field] = value
}

// Контекст берём из редактора, а не с сервера: помощник должен видеть то, что
// методист набрал прямо сейчас, включая несохранённое. Поэтому же ручка не
// привязана к заданию — она работает и на ещё не созданном черновике.
function aiContext(exclude) {
  const d = draft.value
  const all = { title: d.title, statement: d.statement, ...d.authoring }
  return Object.fromEntries(
    Object.entries(all).filter(([key, value]) => key !== exclude && typeof value === 'string' && value.trim()))
}

async function askAi(field) {
  const current = blockValue(field)
  aiBusy.value = field
  try {
    const out = await api('/methodist/ai-fill', {
      method: 'POST',
      body: JSON.stringify({
        field, mode: current.trim() ? 'improve' : 'fill', current, instruction: '', context: aiContext(field),
      }),
    })
    preview.value = { field, current, proposed: out.proposed, note: out.note, editing: false }
  } catch (e) { error.value = e.message } finally { aiBusy.value = '' }
}

function acceptPreview() {
  setBlock(preview.value.field, preview.value.proposed)
  notice.value = `${fieldTitle(preview.value.field)}: предложение вставлено`
  preview.value = null
}

// Сборка черновика идёт на сервере одну-две минуты, поэтому здесь опрос, а не
// один длинный запрос: иначе любой прокси по дороге рвёт соединение по таймауту.
async function waitForDraft(jobId) {
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const state = await api(`/methodist/assignments/draft-from-idea/${jobId}?track=${encodeURIComponent(idea.value.track)}&total_points=${idea.value.total_points}`)
    if (state.status === 'ready') return state.draft
    if (state.status === 'failed') throw new Error(state.error)
  }
  throw new Error('Черновик собирается дольше обычного. Попробуйте ещё раз.')
}

async function generateDraft() {
  generating.value = true; error.value = ''
  try {
    const job = await api('/methodist/assignments/draft-from-idea', { method: 'POST', body: JSON.stringify(idea.value) })
    const out = await waitForDraft(job.job_id)
    // Ничего не перезаписываем молча: заполняем только пустые блоки, всё
    // остальное показываем как предложение и оставляем решение человеку.
    const d = draft.value
    if (!d.title.trim()) d.title = out.title
    if (!d.statement.trim()) d.statement = out.statement
    for (const [key, value] of Object.entries(out.authoring || {})) {
      if (!d.authoring[key] && typeof value === 'string') d.authoring[key] = value
    }
    const hasCriteria = d.criteria.some(c => (c.title || '').trim())
    if (!hasCriteria && out.criteria?.length) {
      d.criteria = out.criteria.map(c => ({ ...c, max_score: c.max_score, expected_signals: c.expected_signals || [] }))
      d.pass_score = out.pass_score
    } else if (out.criteria?.length) {
      notice.value = 'Критерии уже заполнены — предложенные не подставлены. Очистите их, если хотите заменить.'
    }
    ideaOpen.value = false
  } catch (e) { error.value = e.message } finally { generating.value = false }
}

// --- AI: прогон -----------------------------------------------------------

async function startRun() {
  starting.value = true; error.value = ''
  try {
    if (!draft.value.id || dirty.value) {
      const id = await save({ silent: true })
      if (!id) return
    }
    const started = await api(`/methodist/assignments/${draft.value.id}/ai-runs`, {
      method: 'POST',
      body: JSON.stringify({ persona_type: runType.value, idempotency_key: `${draft.value.id}-${runType.value}-${Date.now()}` }),
    })
    runChoice.value = false
    go(`run/${started.id}`)
  } catch (e) { error.value = e.message } finally { starting.value = false }
}

async function skipAndSave() {
  runChoice.value = false
  if (await save()) notice.value = 'Черновик сохранён. Проверку можно запустить позже.'
}

async function decide(rec, action, value = '') {
  deciding.value = rec.id
  try {
    await api(`/methodist/ai-recommendations/${rec.id}/${action}`, {
      method: 'POST',
      body: JSON.stringify({ expected_revision: run.value.assignment_revision, value, reason: value }),
    })
    notice.value = { apply: 'Рекомендация применена', edit: 'Ваш вариант применён', reject: 'Рекомендация отклонена' }[action]
    recEdit.value = null
    run.value = await api(`/methodist/ai-runs/${run.value.id}`)
  } catch (e) { error.value = e.message } finally { deciding.value = '' }
}

const runRow = computed(() => rows.value.find(r => r.id === run.value?.assignment_id))
</script>

<template>
  <div v-if="notice" class="toast-success global-toast">✓ {{ notice }}<button @click="notice = ''">×</button></div>
  <div v-if="error" class="toast-error global-toast">{{ error }}<button @click="error = ''">×</button></div>

  <!-- ═════════════ СПИСОК ═════════════ -->
  <section v-if="view === 'list'">
    <div class="page-heading">
      <div><h1>Банк заданий и критериев</h1></div>
      <button class="primary" @click="go('new')">＋ Добавить задание</button>
    </div>

    <div class="page-heading tb-tabbar">
      <div class="dash-tabs">
        <button :class="{ active: tab === 'published' }" @click="tab = 'published'">Опубликованные · {{ buckets.published.length }}</button>
        <button :class="{ active: tab === 'drafts' }" @click="tab = 'drafts'">Черновики · {{ buckets.drafts.length }}</button>
      </div>
    </div>

    <div class="registry-tools">
      <label class="search"><input v-model="search" placeholder="Поиск по названию или курсу" /></label>
      <select v-model="sort"><option value="recent">Сначала новые</option><option value="title">По названию</option><option value="checked">Давно не проверяли</option></select>
      <button class="text-button" @click="loadList">{{ loading ? 'Обновляю…' : 'Обновить' }}</button>
    </div>

    <div v-if="loading && !rows.length" class="skeleton-list"><i /><i /><i /></div>

    <div v-else-if="visible.length" class="table-card tb-table">
      <div class="table-row table-head"><span>Задание</span><span>Критерии</span><span>Статус</span><span>Проверка агентами</span><span /></div>
      <div v-for="item in visible" :key="item.id" class="table-row tb-row">
        <button class="tb-open" @click="go(item.id)"><b>{{ item.title }}</b><small>{{ item.course }}</small></button>
        <span><b>{{ item.rubric.length }}</b><small>максимум {{ item.max_score ?? '—' }} б.</small></span>
        <span><em class="version-pill" :class="item.published ? 'pub' : 'draft'">{{ item.published ? 'Опубликовано' : 'Черновик' }}</em></span>
        <span class="tb-runcell">
          <template v-if="item.last_run">
            <b :class="RUN_STATE[item.last_run.status]?.[1]">{{ runTitle(item.last_run) }}</b>
            <small>{{ item.last_run.completed_at ? formatDate(item.last_run.completed_at, true) : 'идёт' }}</small>
          </template>
          <small v-else>не запускалась</small>
        </span>
        <span class="tb-actions">
          <button class="text-button" @click="go(item.id)">открыть</button>
          <button class="text-button" @click="duplicate(item)">копия</button>
          <button v-if="!item.published" class="text-button danger" @click="remove(item)">удалить</button>
        </span>
      </div>
    </div>

    <div v-else-if="search.trim()" class="empty-state"><span>⌕</span><h2>Ничего не найдено</h2><p>Измените запрос или загляните в соседнюю вкладку.</p></div>
    <div v-else-if="error" class="empty-state"><span>!</span><h2>Не удалось загрузить банк</h2><p>{{ error }}</p><button class="secondary" @click="loadList">Повторить</button></div>
    <div v-else class="empty-state"><span>✦</span><h2>{{ tab === 'published' ? 'Опубликованных заданий нет' : 'Черновиков нет' }}</h2><p>Соберите задание вручную или из идеи — AI поможет с формулировками и проверит их на персонах.</p><button class="primary" @click="go('new')">Добавить первое задание</button></div>
  </section>

  <!-- ═════════════ РЕДАКТОР ═════════════ -->
  <section v-else-if="view === 'editor' && draft">
    <div class="page-heading">
      <div>
        <p class="tb-crumbs"><button class="text-button" @click="leaveEditor">Банк заданий</button> / {{ draft.title || 'Новое задание' }}</p>
        <h1>{{ draft.title || 'Новое задание' }}</h1>
      </div>
      <div class="tb-head-actions">
        <button class="secondary" @click="leaveEditor">← В банк</button>
        <button class="primary" :disabled="saving || !dirty" @click="save()">{{ saving ? 'Сохраняю…' : 'Сохранить изменения' }}</button>
      </div>
    </div>

    <div class="two-columns">
      <div class="tb-form">
        <article v-if="!draft.id" class="card tb-idea">
          <div class="card-title"><div><h2>Собрать черновик из идеи</h2><p>AI предложит структуру: условие, критерии, эталон. Заполнятся только пустые блоки.</p></div><button class="secondary" @click="ideaOpen = !ideaOpen">{{ ideaOpen ? 'Свернуть' : '✦ Открыть' }}</button></div>
          <template v-if="ideaOpen">
            <label>Идея задания<textarea v-model="idea.idea" rows="3" placeholder="Например: студент в роли аналитика разбирает падение ROMI…" /></label>
            <div class="af-row">
              <label>Направление<input v-model="idea.track" /></label>
              <label>Формат<select v-model="idea.task_format"><option value="auto">авто</option><option value="case_study">бизнес-кейс</option><option value="metrics_design">подбор метрик</option><option value="coding">задача с кодом</option><option value="open">свободный</option></select></label>
              <label>Баллов<input v-model.number="idea.total_points" type="number" min="1" /></label>
            </div>
            <label>Доп. требования<input v-model="idea.constraints" /></label>
            <button class="primary" :disabled="generating || idea.idea.trim().length < 10" @click="generateDraft">{{ generating ? 'Формирую…' : 'Сформировать черновик' }}</button>
            <p v-if="generating" class="tb-side-note"><span class="tb-spinner" /> Сборка идёт на сервере, обычно 1–2 минуты. Заполнятся только пустые блоки.</p>
          </template>
        </article>

        <article class="card">
          <h2 class="tb-block-title">Основная информация</h2>
          <div class="af-row">
            <label>Название<input v-model="draft.title" /></label>
            <label>Курс<select v-model="draft.course_id"><option v-for="c in courses" :key="c.id" :value="c.id">{{ c.title }}</option></select></label>
          </div>
          <div class="af-row">
            <label>Тема<input v-model="draft.authoring.topic" /></label>
            <label>Уровень<select v-model="draft.authoring.difficulty"><option value="">—</option><option value="basic">базовый</option><option value="medium">средний</option><option value="advanced">продвинутый</option></select></label>
            <label>Время, мин<input v-model="draft.authoring.estimated_minutes" type="number" min="0" /></label>
            <label>Трудоёмкость<input v-model.number="draft.effort_weight" type="number" min="0.5" step="0.5" /></label>
          </div>
          <div class="af-row">
            <label>Дедлайн<input v-model="draft.deadline_at" type="datetime-local" /></label>
            <label>Канал сдачи<select v-model="draft.submission_channel"><option value="github">GitHub</option><option value="stepik">Stepik</option><option value="gdocs">Google Docs</option></select></label>
            <label>Проходной балл<input v-model.number="draft.pass_score" type="number" min="0" /></label>
          </div>
          <label>Формат сдачи — что именно и как студент присылает<input v-model="draft.authoring.submission_format" /></label>
          <label>Образовательная цель — чему научится студент (по строке)<textarea v-model="draft.authoring.learning_objectives" rows="3" /></label>
        </article>

        <article v-for="block in AI_BLOCKS" :key="block.field" class="card">
          <div class="tb-block-head">
            <h2 class="tb-block-title">{{ block.title }}</h2>
            <button class="text-button" :disabled="aiBusy === block.field" @click="askAi(block.field)">
              {{ aiBusy === block.field ? '…' : (blockValue(block.field).trim() ? '✦ Улучшить с AI' : '✦ Заполнить с AI') }}
            </button>
          </div>
          <textarea class="tb-area" :value="blockValue(block.field)" rows="5" @input="setBlock(block.field, $event.target.value)" />
        </article>

        <article class="card">
          <div class="tb-block-head">
            <h2 class="tb-block-title">Критерии оценки</h2>
            <span class="tb-total" :class="{ bad: warning }">сумма {{ total }} б.<template v-if="draft.pass_score"> · зачёт от {{ draft.pass_score }}</template></span>
          </div>
          <p v-if="warning" class="tb-warn">⚠ {{ warning }}</p>
          <div v-for="(c, i) in draft.criteria" :key="i" class="tb-crit">
            <div class="af-crit">
              <input v-model="c.title" placeholder="Название критерия" />
              <input v-model.number="c.max_score" type="number" min="0.5" step="0.5" />
              <input v-model="c.student_hint" placeholder="Подсказка студенту" />
              <button class="text-button" :title="openCriterion === i ? 'свернуть' : 'подробнее'" @click="openCriterion = openCriterion === i ? -1 : i">{{ openCriterion === i ? '▾' : '▸' }}</button>
            </div>
            <div v-if="openCriterion === i" class="tb-crit-more">
              <label>Что проверяет ревьюер — скрыто от студента<textarea v-model="c.description" rows="2" /></label>
              <div class="tb-crit-actions">
                <button class="text-button danger" @click="draft.criteria.length > 1 ? draft.criteria.splice(i, 1) : null" :disabled="draft.criteria.length < 2">удалить критерий</button>
                <button class="text-button" :disabled="i === 0" @click="draft.criteria.splice(i - 1, 0, draft.criteria.splice(i, 1)[0]); openCriterion = i - 1">↑ выше</button>
                <button class="text-button" :disabled="i === draft.criteria.length - 1" @click="draft.criteria.splice(i + 1, 0, draft.criteria.splice(i, 1)[0]); openCriterion = i + 1">↓ ниже</button>
              </div>
            </div>
          </div>
          <button class="text-button" @click="draft.criteria.push(emptyCriterion())">＋ ещё критерий</button>
        </article>

        <article class="card">
          <h2 class="tb-block-title">Эталон и ориентиры</h2>
          <label>Эталонное решение — скрыто от студента<textarea v-model="draft.authoring.reference_solution" rows="4" /></label>
          <label>Заметки для ревьюеров<textarea v-model="draft.authoring.reviewer_notes" rows="3" /></label>
        </article>
      </div>

      <!-- правая панель: статус, AI-проверка, публикация -->
      <div class="tb-side">
        <article class="card">
          <div class="tb-status"><em class="version-pill" :class="draft.published ? 'pub' : 'draft'">{{ draft.published ? 'Опубликовано' : 'Черновик' }}</em><small v-if="dirty" class="tb-dirty">есть несохранённые изменения</small></div>
          <button class="primary tb-wide" :disabled="saving || !dirty" @click="save()">{{ saving ? 'Сохраняю…' : 'Сохранить изменения' }}</button>
          <p class="tb-side-note">Черновик можно сохранять с незаполненными блоками — публикация проверит остальное.</p>
        </article>

        <article class="card">
          <h2 class="tb-block-title">Проверка на AI-персонах</h2>
          <p class="tb-side-note">За один запуск проверяется что-то одно: либо постановка задания, либо критерии. Второй тип можно запустить следом.</p>
          <button class="secondary tb-wide" @click="runChoice = true">Проверить на AI-персонах</button>
          <div v-if="runs.length" class="tb-runs">
            <button v-for="r in runs" :key="r.id" class="tb-runrow" @click="go(`run/${r.id}`)">
              <span :class="RUN_STATE[r.status]?.[1]">{{ PERSONA_TYPE[r.persona_type] }}</span>
              <b>{{ RUN_STATE[r.status]?.[0] || r.status }}</b>
              <small>{{ formatDate(r.created_at, true) }}</small>
            </button>
          </div>
          <p v-else class="tb-side-note">Проверка ещё не запускалась.</p>
        </article>

        <article class="card">
          <h2 class="tb-block-title">Публикация</h2>
          <p v-if="blockers.length" class="tb-warn">Не заполнено: {{ blockers.join(', ') }}</p>
          <button v-if="!draft.published" class="primary tb-wide" :disabled="!draft.id && !draft.title.trim()" @click="publish(true)">Опубликовать</button>
          <button v-else class="secondary tb-wide" @click="publish(false)">Снять с публикации</button>
          <p class="tb-side-note">Опубликованное задание видно студентам курса и попадает в успеваемость.</p>
        </article>
      </div>
    </div>
  </section>

  <!-- ═════════════ ПРОГОН И РЕЗУЛЬТАТЫ ═════════════ -->
  <section v-else-if="view === 'run' && run">
    <div class="page-heading">
      <div>
        <p class="tb-crumbs"><button class="text-button" @click="go()">Банк заданий</button> / {{ runRow?.title || 'Задание' }}</p>
        <h1>{{ PERSONA_TYPE[run.persona_type] }}</h1>
      </div>
      <div class="tb-head-actions">
        <button class="secondary" @click="go(run.assignment_id)">← К заданию</button>
        <button v-if="run.status === 'completed'" class="secondary" @click="go(run.assignment_id)">Запустить другой тип</button>
      </div>
    </div>

    <p v-if="run.stale" class="cap-hint">ⓘ Результаты относятся к версии задания №{{ run.revision }}. Черновик с тех пор изменён — часть выводов может быть неактуальна.</p>

    <article v-if="['queued', 'running'].includes(run.status)" class="card tb-progress">
      <span class="tb-spinner" />
      <div>
        <b>{{ run.progress || 'прогон идёт' }}</b>
        <small>Запущено {{ formatDate(run.created_at, true) }} · версия задания №{{ run.revision }}. Страницу можно закрыть — прогон продолжается на сервере.</small>
      </div>
      <button class="secondary" @click="go()">Вернуться в банк</button>
    </article>

    <article v-else-if="run.status === 'failed'" class="card tb-failed">
      <h2>Проверка не удалась</h2>
      <p>{{ run.error }}</p>
      <p class="tb-side-note">Черновик сохранён и не изменился.</p>
      <div class="tb-head-actions"><button class="secondary" @click="go(run.assignment_id)">Вернуться к редактированию</button></div>
    </article>

    <template v-else>
      <article class="card" :class="run.summary?.verdict === 'ok' ? 'tb-ok' : 'tb-attention'">
        <h2>{{ run.summary?.verdict === 'ok' ? '✓ ' : '⚠ ' }}{{ run.summary?.headline }}</h2>
        <p class="tb-what">{{ runIntro(run.persona_type) }}</p>
        <div class="tb-counts">
          <span><b>{{ run.summary?.good }}</b></span>
          <span v-if="run.summary?.counts?.critical"><em class="tb-sev high">критично</em> {{ run.summary.counts.critical }}</span>
          <span v-if="run.summary?.counts?.important"><em class="tb-sev medium">важно</em> {{ run.summary.counts.important }}</span>
          <span v-if="run.summary?.counts?.improvement"><em class="tb-sev low">улучшение</em> {{ run.summary.counts.improvement }}</span>
          <span>рекомендаций: <b>{{ run.summary?.recommendations }}</b></span>
        </div>
      </article>

      <article v-if="run.personas.length" class="card">
        <div class="card-title"><div><h2>{{ run.persona_type === 'student' ? 'Как персоны поняли задание' : 'Как персоны применили критерии' }}</h2></div></div>
        <div class="tb-personas">
          <div v-for="p in run.personas" :key="p.key" class="tb-persona">
            <b>{{ p.key }}</b>
            <template v-if="run.persona_type === 'student'">
              <em :class="p.understood ? 'ok' : 'bad'">{{ p.understood ? 'понял без догадок' : 'пришлось догадываться' }}</em>
              <p>{{ p.approach }}</p>
              <ul v-if="p.troubles.length"><li v-for="(t, i) in p.troubles" :key="i">{{ t }}</li></ul>
            </template>
            <template v-else>
              <em>{{ p.total_points }} б.</em>
              <p>{{ p.comment }}</p>
              <ul v-if="p.undecidable.length"><li v-for="(t, i) in p.undecidable" :key="i">не хватило рубрики: {{ t }}</li></ul>
            </template>
          </div>
        </div>
      </article>

      <article v-if="openRecs.length" class="card">
        <div class="card-title"><div><h2>Рекомендации · {{ openRecs.length }}</h2><p>Каждую вы применяете, правите или отклоняете. Ничего не применяется само.</p></div></div>
        <div v-for="rec in openRecs" :key="rec.id" class="tb-rec">
          <div class="tb-rec-head">
            <em class="tb-sev" :class="SEVERITY[rec.severity]?.[1]">{{ SEVERITY[rec.severity]?.[0] }}</em>
            <b>{{ rec.kind ? kindLabel(rec.kind) : 'Правка критерия' }}</b>
            <span class="tb-where">{{ rec.target_type === 'criterion' ? `критерий «${rec.target_id}»` : fieldTitle(rec.target_field) }}</span>
          </div>
          <p class="tb-why">{{ rec.problem || kindWhy(rec.kind) }}</p>
          <p v-if="rec.expected_effect" class="tb-effect">→ {{ rec.expected_effect }}</p>
          <details v-if="rec.evidence.length" class="tb-evidence"><summary>на чём основано</summary><p v-for="(e, i) in rec.evidence" :key="i">{{ e }}</p></details>
          <div v-if="rec.original_value" class="tb-diff"><span class="was">{{ rec.original_value }}</span><span v-if="rec.proposed_value" class="now">{{ rec.proposed_value }}</span></div>
          <div v-else-if="rec.proposed_value" class="tb-diff"><span class="now">{{ rec.proposed_value }}</span></div>

          <div v-if="recEdit?.id === rec.id" class="tb-rec-edit">
            <textarea v-model="recEdit.value" rows="5" />
            <div class="tb-rec-actions">
              <button class="text-button" @click="recEdit = null">Отмена</button>
              <button class="primary" :disabled="!recEdit.value.trim() || deciding === rec.id" @click="decide(rec, 'edit', recEdit.value)">Применить мой вариант</button>
            </div>
          </div>
          <div v-else class="tb-rec-actions">
            <button class="text-button danger" :disabled="deciding === rec.id" @click="decide(rec, 'reject')">Отклонить</button>
            <button class="secondary" :disabled="deciding === rec.id" @click="recEdit = { id: rec.id, value: rec.proposed_value || rec.expected_effect }">Редактировать</button>
            <button class="primary" :disabled="!rec.proposed_value || deciding === rec.id" @click="decide(rec, 'apply')">Применить</button>
          </div>
        </div>
      </article>

      <article v-if="decidedRecs.length" class="card">
        <div class="card-title"><div><h2>Решённые · {{ decidedRecs.length }}</h2><p>История решений — в том числе отклонённых</p></div></div>
        <div v-for="rec in decidedRecs" :key="rec.id" class="tb-decided">
          <em class="tb-sev" :class="rec.status === 'rejected' ? 'low' : 'ok'">{{ { applied: 'применена', edited: 'применена с правкой', rejected: 'отклонена' }[rec.status] }}</em>
          <b>{{ rec.target_type === 'criterion' ? `критерий «${rec.target_id}»` : fieldTitle(rec.target_field) }}</b>
          <small>{{ rec.rejection_reason || rec.problem }}</small>
        </div>
      </article>

      <p class="tb-meta" v-if="run.metrics?.total_tokens">Расход прогона: {{ run.metrics.total_tokens }} токенов ≈ {{ run.metrics.cost_rub }} ₽.</p>
    </template>
  </section>

  <!-- ═════════════ МОДАЛКИ ═════════════ -->
  <div v-if="preview" class="tb-modal" @click.self="preview = null">
    <article class="card tb-modal-card">
      <h2>{{ fieldTitle(preview.field) }}: предложение AI</h2>
      <p class="tb-side-note">{{ preview.note }}</p>
      <div class="tb-preview">
        <div v-if="preview.current"><small>сейчас</small><MarkdownText :text="preview.current" /></div>
        <div><small>предложение</small><textarea v-if="preview.editing" v-model="preview.proposed" rows="10" /><MarkdownText v-else :text="preview.proposed" /></div>
      </div>
      <div class="tb-rec-actions">
        <button class="text-button" @click="preview = null">Отмена</button>
        <button class="secondary" @click="preview.editing = !preview.editing">{{ preview.editing ? 'Скрыть правку' : 'Отредактировать' }}</button>
        <button class="primary" @click="acceptPreview">Вставить в задание</button>
      </div>
    </article>
  </div>

  <div v-if="runChoice" class="tb-modal" @click.self="runChoice = false">
    <article class="card tb-modal-card">
      <h2>Что проверяем в этот раз</h2>
      <p class="tb-side-note">За один запуск — один тип персон. Второй можно запустить сразу после.</p>
      <label class="tb-choice" :class="{ active: runType === 'student' }">
        <input v-model="runType" type="radio" value="student" />
        <span><b>Проверить задание на AI-студентах</b><small>Студенты разного уровня попробуют выполнить задание и покажут, где формулировка неоднозначна, слишком сложна или не содержит нужных данных.</small></span>
      </label>
      <label class="tb-choice" :class="{ active: runType === 'reviewer' }">
        <input v-model="runType" type="radio" value="reviewer" />
        <span><b>Проверить критерии на AI-ревьюерах</b><small>Ревьюеры применят критерии к решениям разного качества и покажут расхождения в оценках, дублирование и неоднозначные формулировки.</small></span>
      </label>
      <div class="tb-rec-actions">
        <button class="text-button" @click="runChoice = false">Отмена</button>
        <button class="secondary" @click="skipAndSave">Пропустить и сохранить черновик</button>
        <button class="primary" :disabled="starting" @click="startRun">{{ starting ? 'Запускаю…' : 'Запустить проверку' }}</button>
      </div>
    </article>
  </div>
</template>

<style scoped>
.tb-tabbar { margin-top: -6px; }
.tb-head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.tb-crumbs { color: var(--muted); font-size: 11px; margin: 0 0 4px; }
.tb-crumbs .text-button { font-size: 11px; }

.tb-table .table-row { grid-template-columns: minmax(220px, 2fr) .7fr .8fr 1.1fr 150px; }
.tb-open { border: 0; background: none; padding: 0; text-align: left; cursor: pointer; font: inherit; }
.tb-open b { display: block; font-size: 12px; }
.tb-open small { display: block; color: var(--muted); font-size: 9px; margin-top: 4px; }
.tb-runcell b.ok { color: #087448; } .tb-runcell b.bad { color: var(--red); } .tb-runcell b.wait { color: #7c3aed; }
.tb-actions { display: flex; gap: 10px; justify-content: flex-end; }

.tb-side > .card { margin-bottom: 12px; position: relative; }
.tb-side > .card:first-child { position: sticky; top: 95px; }
.tb-block-title { font-size: 14px; margin: 0 0 10px; }
/* Кабинет стилизует поля только внутри .form-card, а редактор задания собран из
   обычных карточек — поэтому форма одевается здесь, а не наследует ничего. */
.tb-form label { display: block; margin-bottom: 12px; font-size: 12px; font-weight: 600; }
.tb-form input, .tb-form select, .tb-form textarea { display: block; width: 100%; margin-top: 6px;
  padding: 10px 12px; font: inherit; font-weight: 400; color: var(--ink);
  border: 1px solid #dcdde3; border-radius: 10px; background: #fff; }
.tb-form textarea { resize: vertical; }
.tb-form input:focus, .tb-form select:focus, .tb-form textarea:focus { outline: none; border-color: var(--blue); box-shadow: 0 0 0 3px #e7f4fe; }
.tb-form .af-crit input { margin-top: 0; }
.tb-block-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.tb-area { display: block; width: 100%; margin-top: 8px; padding: 11px 12px; font: inherit; font-size: 13px;
  border: 1px solid #dcdde3; border-radius: 10px; resize: vertical; }
.tb-status { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.tb-dirty { color: #9a6810; font-size: 10px; }
.tb-wide { width: 100%; }
.tb-side-note { color: var(--muted); font-size: 11px; line-height: 1.5; margin-top: 10px; }
.tb-side-note .tb-spinner { display: inline-block; vertical-align: -3px; width: 12px; height: 12px; margin-right: 6px; }
.tb-total { color: var(--muted); font-size: 11px; } .tb-total.bad { color: #9a6810; }
.tb-warn { color: #9a6810; background: #fff8ec; border-radius: 8px; padding: 8px 10px; font-size: 11px; margin: 8px 0; }
.tb-crit { border-bottom: 1px solid #f1f1f4; padding-bottom: 6px; }
.tb-crit-more { padding: 4px 0 10px; }
.tb-crit-more textarea { display: block; width: 100%; margin-top: 6px; padding: 9px 11px; font: inherit; font-size: 12px;
  border: 1px solid #dcdde3; border-radius: 8px; resize: vertical; }
.tb-crit-actions { display: flex; gap: 12px; margin-top: 8px; }

.tb-runs { margin-top: 10px; }
.tb-runrow { display: grid; grid-template-columns: 1fr auto; gap: 4px 8px; width: 100%; text-align: left;
  border: 0; border-top: 1px solid #f0f0f4; background: none; padding: 8px 0; cursor: pointer; font: inherit; font-size: 11px; }
.tb-runrow span { font-weight: 700; } .tb-runrow span.ok { color: #087448; } .tb-runrow span.bad { color: var(--red); } .tb-runrow span.wait { color: #7c3aed; }
.tb-runrow small { grid-column: 1 / -1; color: var(--muted); font-size: 10px; }

.tb-progress { display: flex; align-items: center; gap: 14px; }
.tb-progress small { display: block; color: var(--muted); font-size: 11px; margin-top: 4px; line-height: 1.5; }
.tb-progress button { margin-left: auto; }
.tb-spinner { width: 18px; height: 18px; flex: none; border: 2px solid #cfcfe0; border-top-color: #8b5cf6;
  border-radius: 50%; animation: tb-spin .8s linear infinite; }
@keyframes tb-spin { to { transform: rotate(360deg); } }
.tb-failed { border-left: 4px solid var(--red); }
.tb-ok { border-left: 4px solid #047857; } .tb-attention { border-left: 4px solid #b45309; }
.tb-what { color: #555; font-size: 12px; line-height: 1.6; margin: 6px 0; }
.tb-counts { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-top: 10px; font-size: 12px; }
.tb-sev { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; font-style: normal; }
.tb-sev.high { background: #fee2e2; color: #b91c1c; } .tb-sev.medium { background: #fef3c7; color: #92400e; }
.tb-sev.low { background: #eef0f3; color: #4b5563; } .tb-sev.ok { background: #dcfce7; color: #166534; }

.tb-personas { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
.tb-persona { border: 1px solid var(--line); border-radius: 12px; padding: 12px; font-size: 12px; }
.tb-persona b { display: block; } .tb-persona em { font-style: normal; font-size: 11px; color: var(--muted); }
.tb-persona em.ok { color: #087448; } .tb-persona em.bad { color: #9a6810; }
.tb-persona p { color: #555; margin: 6px 0 0; line-height: 1.5; }
.tb-persona ul { margin: 6px 0 0 16px; color: #6b6b80; }

.tb-rec { border-top: 1px solid #f0f0f4; padding: 14px 0; font-size: 12px; }
.tb-rec-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tb-where { color: var(--muted); font-size: 11px; }
.tb-why { color: #444; margin: 6px 0 0; line-height: 1.55; }
.tb-effect { color: #6d28d9; font-weight: 600; margin: 4px 0 0; }
.tb-evidence { margin-top: 6px; color: var(--muted); font-size: 11px; }
.tb-diff { display: grid; gap: 6px; margin-top: 8px; }
.tb-diff .was { color: #9ca3af; text-decoration: line-through; white-space: pre-wrap; }
.tb-diff .now { color: #065f46; background: #f0fdf7; border-radius: 8px; padding: 8px 10px; white-space: pre-wrap; }
.tb-rec-actions { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 12px; flex-wrap: wrap; }
.tb-rec-edit textarea { display: block; width: 100%; margin-top: 8px; padding: 10px 12px; font: inherit; font-size: 12px;
  border: 1px solid #dcdde3; border-radius: 10px; resize: vertical; }
.tb-decided { display: grid; grid-template-columns: auto auto 1fr; gap: 10px; align-items: center;
  border-top: 1px solid #f0f0f4; padding: 10px 0; font-size: 12px; }
.tb-decided small { color: var(--muted); }
.tb-meta { color: var(--muted); font-size: 11px; margin-top: 12px; }

.tb-modal { position: fixed; inset: 0; z-index: 40; display: grid; place-items: center; padding: 20px; background: rgba(20,22,30,.45); }
.tb-modal-card { width: min(760px, 100%); max-height: 86vh; overflow: auto; }
.tb-preview { display: grid; gap: 12px; margin-top: 12px; }
.tb-preview small { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
.tb-preview textarea { display: block; width: 100%; padding: 10px 12px; font: inherit; font-size: 12px;
  border: 1px solid #dcdde3; border-radius: 10px; resize: vertical; }
.tb-choice { display: flex; gap: 10px; align-items: flex-start; border: 1px solid var(--line); border-radius: 12px;
  padding: 12px; margin-top: 10px; cursor: pointer; }
.tb-choice.active { border-color: var(--blue); background: #f6fbff; }
.tb-choice b { display: block; font-size: 13px; }
.tb-choice small { display: block; color: var(--muted); font-size: 11px; line-height: 1.5; margin-top: 4px; }

@media (max-width: 980px) {
  .two-columns { grid-template-columns: 1fr; }
  .tb-side > .card:first-child { position: static; }
  .tb-table .table-row { min-width: 760px; }
}
</style>
