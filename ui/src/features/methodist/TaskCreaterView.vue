<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, taskCreater } from '../../shared/api'

// --- навигация экрана переживает выход в меню --------------------------------
const NAV_KEY = 'taskcreater:nav'
const loadNav = () => { try { return JSON.parse(localStorage.getItem(NAV_KEY)) || { mode: 'list' } } catch { return { mode: 'list' } } }
const saveNav = () => { try { localStorage.setItem(NAV_KEY, JSON.stringify({ mode: mode.value, taskId: taskId.value })) } catch { /* */ } }

const mode = ref('list')      // list | new | import | detail
const taskId = ref(null)
const error = ref('')
const notice = ref('')

// список
const items = ref([])
const statusFilter = ref('')
const loadingList = ref(false)

// генерация
const form = ref({
  idea: 'Кейс на разбор бизнес-проблемы: студент в роли продуктового аналитика вертикали. За год упал ROMI маркетинга. Нужно верифицировать проблему, сгенерировать и приоритизировать гипотезы, выбрать способы валидации, предложить решения, оценить их потенциал и выбрать метрики/дизайн теста.',
  track: 'Аналитика данных',
  task_format: 'case_study',
  total_points: 10,
  constraints: 'Кейс с ролью и вводными цифрами. Оптимально 6–8 гипотез. Оценка по этапам, сумма 10.',
})
const generating = ref(false)

// импорт готового задания
const imp = ref({
  title: '', track: 'Аналитика данных', context_md: '', statement_md: '',
  deliverables: '', public_rubric_note: '', total_points: 10, reference_solution_md: '',
  criteria: [{ key: 'c1', title: '', max_points: 5, student_hint: '', description: '', check_kind: 'subjective', evidence_hint: '', expected_signals: '', rubric_levels: '' }],
})
const importing = ref(false)

// деталь
const task = ref(null)
const runs = ref([])
const activeRun = ref(null)
const shownResult = ref(null)
const validating = ref(false)
const applying = ref(false)
const showHidden = ref(false)
const showSolvers = ref(false)
const editing = ref(false)
const edit = ref(null)

// демо-проверка решения
const grading = ref(false)
const gradeInput = ref('')
const gradeResult = ref(null)

const STATUS = {
  generating: ['генерируется', '#7c3aed'], generation_failed: ['ошибка генерации', '#b91c1c'],
  draft: ['черновик', '#6b7280'], validating: ['на проверке', '#7c3aed'],
  needs_review: ['есть замечания', '#b45309'], checked: ['проверено', '#047857'],
  revised: ['уточнено', '#1d4ed8'], failed: ['ошибка прогона', '#b91c1c'],
}
const PERSONA_RU = {
  diligent_strong: 'добросовестный студент', minimalist_weak: 'слабый студент',
  rule_lawyer: 'формалист (ищет лазейки)', ambiguity_prober: 'ищет двусмысленности',
  provided: 'присланное решение', demo: 'демо',
}
const KIND_PLAIN = {
  ambiguous: ['Критерий читается двояко', 'Разные студенты и ревьюеры поймут его по-разному — баллы будут несправедливыми.'],
  underspecified: ['Не хватает деталей для оценки', 'Ревьюер не сможет поставить балл однозначно.'],
  gameable: ['Можно выполнить формально', 'Слабое решение наберёт максимум, обойдя смысл критерия.'],
  overlapping: ['Критерии пересекаются', 'Один и тот же аспект оценивается дважды.'],
  unmeasurable: ['Субъективная формулировка', '«Хорошо / качественно» без порогов — каждый ревьюер понимает по-своему.'],
  missing_criterion: ['Аспект задания не покрыт', 'Важную часть работы никто не оценит.'],
  inconsistent_scoring: ['Критерий не различает уровни', 'Сильная и слабая работа получают одинаковый балл.'],
  weight_imbalance: ['Вес не по важности', 'Второстепенное весит больше ключевого (или наоборот).'],
  scope_creep: ['Требует того, чего нет в условии', 'Студент не мог знать об этом требовании.'],
  unfair_hidden: ['Скрытое ожидание нельзя вывести из брифа', 'Рубрика тайно требует то, чего студенту не сказали — нечестно.'],
  leaky_public: ['Публичная часть раскрывает грейдинг', 'Студент видит, что именно нужно написать, — можно подогнать без реальной работы.'],
}

const criteria = computed(() => task.value?.data?.criteria || [])
const openEdits = computed(() => shownResult.value?.proposed_edits || [])
const exportBase = computed(() => (task.value ? `/task-creater/tasks/${task.value.id}/export` : ''))
const anyBusy = computed(() => items.value.some(x => x.status === 'validating' || x.status === 'generating'))

// свод находок по всем раундам (последнее вхождение по id)
const allFindings = computed(() => {
  const m = new Map()
  for (const rd of shownResult.value?.rounds || []) for (const f of rd.findings) m.set(f.id, f)
  return [...m.values()].sort((a, b) => ({ high: 0, medium: 1, low: 2 }[a.severity] - { high: 0, medium: 1, low: 2 }[b.severity]))
})
const briefFindings = computed(() => allFindings.value.filter(f => f.target === 'brief'))
const verdict = computed(() => {
  const r = shownResult.value
  if (!r) return null
  const high = allFindings.value.filter(f => f.severity === 'high').length
  if (r.converged && !openEdits.value.length && !allFindings.value.length)
    return { tone: 'ok', text: 'Рубрика рабочая — агенты не нашли, за что зацепиться. Можно публиковать задание.' }
  if (!openEdits.value.length && allFindings.value.length)
    return { tone: 'warn', text: `${allFindings.value.length} замечани(й) по формулировкам. Автоправок нет — поправьте вручную в редакторе.` }
  return { tone: 'warn', text: `Рубрику стоит доработать: ${openEdits.value.length} предложенны(х) правк(и)${high ? `, важных: ${high}` : ''}.` }
})

function fmtDate(v) {
  if (!v) return '—'
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(v))
}
const personasOf = m => [...new Set(Object.values(m || {}).flatMap(r => Object.keys(r)))]
function spread(row) { const v = Object.values(row || {}); return v.length > 1 ? (Math.max(...v) - Math.min(...v)).toFixed(2) : '0.00' }

// --- поллинг переживает перемонтирование ------------------------------------
const registry = (window.__tcPoll ||= { runId: null, stop: false })
async function pollRun(runId) {
  registry.runId = runId; registry.stop = false; validating.value = true
  for (let i = 0; i < 400; i++) {
    if (registry.stop || registry.runId !== runId) return
    try { activeRun.value = await taskCreater(`/validation-runs/${runId}`) } catch (e) { error.value = e.message; break }
    if (['succeeded', 'failed'].includes(activeRun.value.status)) {
      if (activeRun.value.status === 'failed') error.value = activeRun.value.error || 'Прогон валидации упал'
      shownResult.value = activeRun.value.result
      await refreshDetailMeta(); break
    }
    await new Promise(r => setTimeout(r, 1500))
  }
  validating.value = false
  if (registry.runId === runId) registry.runId = null
}

// --- список ---------------------------------------------------------------
let listTimer = null
async function loadList() {
  loadingList.value = true; error.value = ''
  try { items.value = await taskCreater(`/tasks${statusFilter.value ? `?status=${statusFilter.value}` : ''}`) }
  catch (e) { error.value = e.message } finally { loadingList.value = false }
}
function scheduleRefresh() {
  clearInterval(listTimer)
  listTimer = setInterval(() => { if (mode.value === 'list' && anyBusy.value) loadList() }, 3000)
}

// --- деталь -------------------------------------------------------------
let genTimer = null
async function openTask(id) {
  mode.value = 'detail'; taskId.value = id; saveNav()
  task.value = null; runs.value = []; activeRun.value = null; shownResult.value = null
  editing.value = false; gradeResult.value = null; gradeInput.value = ''; error.value = ''
  clearInterval(genTimer)
  try {
    task.value = await taskCreater(`/tasks/${id}`)
    if (task.value.gen_status === 'generating') {
      genTimer = setInterval(async () => {
        task.value = await taskCreater(`/tasks/${id}`)
        if (task.value.gen_status !== 'generating') { clearInterval(genTimer); openTask(id) }
      }, 2000)
      return
    }
    runs.value = await taskCreater(`/tasks/${task.value.root_id}/runs`)
    const running = runs.value.find(r => ['pending', 'running'].includes(r.status))
    if (running) pollRun(running.id)
    else if (runs.value[0]?.status === 'succeeded') showRun(runs.value[0])
  } catch (e) { error.value = e.message }
}
async function refreshDetailMeta() {
  if (!task.value) return
  try {
    task.value = await taskCreater(`/tasks/${task.value.root_id}/versions/${task.value.version}`).catch(() => task.value)
    runs.value = await taskCreater(`/tasks/${task.value.root_id}/runs`)
  } catch { /* */ }
}
async function showRun(rb) {
  if (['pending', 'running'].includes(rb.status)) { pollRun(rb.id); return }
  try { const full = await taskCreater(`/validation-runs/${rb.id}`); shownResult.value = full.result; activeRun.value = full }
  catch (e) { error.value = e.message }
}

// --- действия --------------------------------------------------------------
async function generate() {
  generating.value = true; error.value = ''; notice.value = ''
  try {
    const res = await taskCreater('/tasks/generate', {
      method: 'POST',
      body: JSON.stringify({ background: true, idea: { ...form.value, delivery_channel: 'stepik', language: 'ru' } }),
    })
    notice.value = 'Задание поставлено в очередь на генерацию'
    mode.value = 'list'; taskId.value = null; saveNav()
    await loadList()
    // подсветим: откроем деталь новой задачи (покажет «генерируется…»)
    setTimeout(() => openTask(res.id), 300)
  } catch (e) { error.value = e.message } finally { generating.value = false }
}

async function importTask() {
  importing.value = true; error.value = ''
  try {
    const body = {
      title: imp.value.title, track: imp.value.track, context_md: imp.value.context_md,
      statement_md: imp.value.statement_md,
      deliverables: imp.value.deliverables.split('\n').map(s => s.trim()).filter(Boolean),
      public_rubric_note: imp.value.public_rubric_note,
      reference_solution_md: imp.value.reference_solution_md,
      total_points: imp.value.total_points || null,
      criteria: imp.value.criteria.map(c => ({
        key: c.key || c.title.toLowerCase().replace(/[^a-zа-я0-9]+/gi, '-').slice(0, 30) || 'c',
        title: c.title, max_points: Number(c.max_points) || 1, student_hint: c.student_hint,
        description: c.description || c.title, check_kind: c.check_kind,
        evidence_hint: c.evidence_hint || '—',
        expected_signals: c.expected_signals.split('\n').map(s => s.trim()).filter(Boolean),
        rubric_levels: parseLevels(c.rubric_levels),
      })),
    }
    const res = await taskCreater('/tasks/import', { method: 'POST', body: JSON.stringify(body) })
    notice.value = 'Задание импортировано'
    await openTask(res.id)
  } catch (e) { error.value = e.message } finally { importing.value = false }
}
function parseLevels(text) {
  return (text || '').split('\n').map(s => s.trim()).filter(Boolean).map(line => {
    const [p, label, ...d] = line.split('—').map(x => x.trim())
    return { points: Number(p) || 0, label: label || '', descriptor: d.join(' — ') || '' }
  })
}
function levelsToText(levels) { return (levels || []).map(l => `${l.points} — ${l.label} — ${l.descriptor}`).join('\n') }
function addImpCriterion() {
  imp.value.criteria.push({ key: 'c' + (imp.value.criteria.length + 1), title: '', max_points: 5, student_hint: '', description: '', check_kind: 'subjective', evidence_hint: '', expected_signals: '', rubric_levels: '' })
}

async function validate() {
  error.value = ''
  try {
    const started = await taskCreater(`/tasks/${task.value.id}/validate`, { method: 'POST', body: JSON.stringify({ max_rounds: 2 }) })
    shownResult.value = null; await refreshDetailMeta(); pollRun(started.id)
  } catch (e) { error.value = e.message }
}
async function applyEdits() {
  applying.value = true; error.value = ''
  try {
    const decisions = openEdits.value.map(e => ({ edit_id: e.id, accept: true }))
    const revised = await taskCreater(`/validation-runs/${activeRun.value.id}/decisions`, {
      method: 'POST', body: JSON.stringify({ decisions, author: 'кабинет методиста' }),
    })
    notice.value = `Правки применены — версия v${revised.version}`
    await openTask(revised.id)
  } catch (e) { error.value = e.message } finally { applying.value = false }
}

// --- ручное редактирование ---------------------------------------------
function startEdit() {
  const d = task.value.data
  edit.value = {
    title: d.title, context_md: d.context_md, statement_md: d.statement_md,
    deliverables: (d.deliverables || []).join('\n'), public_rubric_note: d.public_rubric_note,
    reference_solution_md: d.reference_solution_md, common_mistakes: (d.common_mistakes || []).join('\n'),
    reviewer_notes: d.reviewer_notes,
    criteria: (d.criteria || []).map(c => ({
      key: c.key, title: c.title, max_points: c.max_points, student_hint: c.student_hint,
      description: c.description, check_kind: c.check_kind, evidence_hint: c.evidence_hint,
      expected_signals: (c.expected_signals || []).join('\n'), rubric_levels: levelsToText(c.rubric_levels),
    })),
  }
  editing.value = true
}
async function saveEdit() {
  error.value = ''
  try {
    const patch = {
      title: edit.value.title, context_md: edit.value.context_md, statement_md: edit.value.statement_md,
      deliverables: edit.value.deliverables.split('\n').map(s => s.trim()).filter(Boolean),
      public_rubric_note: edit.value.public_rubric_note,
      reference_solution_md: edit.value.reference_solution_md,
      common_mistakes: edit.value.common_mistakes.split('\n').map(s => s.trim()).filter(Boolean),
      reviewer_notes: edit.value.reviewer_notes,
      criteria: edit.value.criteria.map(c => ({
        key: c.key, title: c.title, max_points: Number(c.max_points) || 1, student_hint: c.student_hint,
        description: c.description || c.title, check_kind: c.check_kind, evidence_hint: c.evidence_hint || '—',
        expected_signals: c.expected_signals.split('\n').map(s => s.trim()).filter(Boolean),
        rubric_levels: parseLevels(c.rubric_levels),
      })),
    }
    const res = await taskCreater(`/tasks/${task.value.id}`, { method: 'PATCH', body: JSON.stringify(patch) })
    notice.value = `Сохранено — версия v${res.version}`
    editing.value = false
    await openTask(res.id)
  } catch (e) { error.value = e.message }
}

// --- демо-проверка решения -------------------------------------------
function fillReference() { gradeInput.value = task.value.data.reference_solution_md || '' }
async function gradeSolution() {
  grading.value = true; error.value = ''; gradeResult.value = null
  try {
    gradeResult.value = await taskCreater(`/tasks/${task.value.id}/grade`, {
      method: 'POST', body: JSON.stringify({ solution_md: gradeInput.value, persona: 'demo' }),
    })
  } catch (e) { error.value = e.message } finally { grading.value = false }
}

// --- отправка готового задания в «Банк заданий и критериев» -------------
const sendingToAssignments = ref(false)
async function sendToAssignments() {
  const d = task.value?.data
  if (!d) return
  sendingToAssignments.value = true; error.value = ''; notice.value = ''
  try {
    const criteria = (d.criteria || []).map(c => ({
      key: c.key || '', title: c.title,
      max_score: Number(c.max_points) || 1, student_hint: c.student_hint || '',
    }))
    if (!criteria.length) throw new Error('В задании нет критериев')
    const statement = [
      d.context_md,
      d.statement_md,
      (d.deliverables || []).length ? 'Что сдать:\n' + d.deliverables.map(x => `• ${x}`).join('\n') : '',
      d.public_rubric_note,
    ].filter(Boolean).join('\n\n')
    await api('/methodist/assignments', {
      method: 'POST',
      body: JSON.stringify({
        title: d.title, statement, submission_channel: 'stepik', criteria,
        pass_score: Math.round((task.value.total_points || 0) * 0.6),
      }),
    })
    notice.value = 'Задание отправлено в «Банк заданий и критериев»'
  } catch (e) { error.value = e.message } finally { sendingToAssignments.value = false }
}

function backToList() { editing.value = false; mode.value = 'list'; taskId.value = null; saveNav(); loadList() }

onMounted(() => {
  const nav = loadNav()
  if (nav.mode === 'detail' && nav.taskId) openTask(nav.taskId)
  else if (['new', 'import'].includes(nav.mode)) mode.value = nav.mode
  else mode.value = 'list'
  loadList(); scheduleRefresh()
})
onUnmounted(() => { clearInterval(listTimer); clearInterval(genTimer); registry.stop = true })
</script>

<template>
  <div v-if="notice" class="toast-success global-toast">✓ {{ notice }}<button @click="notice = ''">×</button></div>
  <div v-if="error" class="toast-error global-toast">{{ error }}<button @click="error = ''">×</button></div>

  <!-- ═══════════════ СПИСОК ═══════════════ -->
  <template v-if="mode === 'list'">
    <div class="page-heading">
      <div>
        <h1>AI-конструктор заданий и критериев</h1>
      </div>
      <div class="tc-head-actions">
        <button class="secondary" @click="mode = 'import'; saveNav()">Добавить готовое</button>
        <button class="primary" @click="mode = 'new'; saveNav()">＋ Из идеи</button>
      </div>
    </div>

    <div class="registry-tools">
      <select v-model="statusFilter" @change="loadList">
        <option value="">Все статусы</option>
        <option v-for="(v, k) in STATUS" :key="k" :value="k">{{ v[0] }}</option>
      </select>
      <button class="text-button" @click="loadList">{{ loadingList ? 'Обновляю…' : 'Обновить' }}</button>
      <span v-if="anyBusy" class="tc-live">● есть активные задачи — список обновляется сам</span>
    </div>

    <div class="table-card">
      <div class="table-row table-head"><span>Задание</span><span>Статус</span><span>Версия</span><span>Последняя проверка</span><span /></div>
      <div v-for="it in items" :key="it.root_id" class="table-row tc-row" @click="openTask(it.id)">
        <span class="tc-title-cell">
          <b>{{ it.title }}</b>
          <small>{{ it.track || '—' }} · {{ it.criteria_count }} критериев · {{ it.total_points }} б.</small>
        </span>
        <span><em class="tc-status" :class="{ 'tc-pulse': ['validating', 'generating'].includes(it.status) }" :style="`--c:${STATUS[it.status][1]}`">{{ STATUS[it.status][0] }}</em></span>
        <span>v{{ it.version }} <small>{{ it.source }}</small></span>
        <span class="tc-runcell">
          <template v-if="it.last_run">
            <b :class="it.last_run.status === 'failed' ? 'danger' : ''">{{ it.last_run.status === 'succeeded' ? `${it.last_run.rounds} р. · правок ${it.last_run.proposed_edits} · ${it.last_run.cost_rub} ₽` : it.last_run.status }}</b>
            <small>{{ fmtDate(it.last_run.updated_at) }}</small>
          </template>
          <small v-else>не запускалась</small>
        </span>
        <span class="tc-go">→</span>
      </div>
      <div v-if="!items.length && !loadingList" class="empty-state in-table"><span>✦</span><h2>Пока нет заданий</h2><p>«＋ Из идеи» или «Добавить готовое».</p></div>
    </div>
  </template>

  <!-- ═══════════════ НОВОЕ ИЗ ИДЕИ ═══════════════ -->
  <template v-else-if="mode === 'new'">
    <div class="page-heading">
      <div><h1>Новое задание из идеи</h1></div>
      <button class="secondary tc-back" @click="backToList">← К списку</button>
    </div>
    <article class="card tc-form">
      <label>Идея задания<textarea v-model="form.idea" rows="4" /></label>
      <div class="tc-form-row">
        <label>Направление<input v-model="form.track" /></label>
        <label>Формат<select v-model="form.task_format">
          <option value="auto">авто</option><option value="case_study">бизнес-кейс</option>
          <option value="metrics_design">подбор метрик</option><option value="coding">задача с кодом</option><option value="open">свободный</option>
        </select></label>
        <label>Баллов<input v-model.number="form.total_points" type="number" min="1" max="100" /></label>
      </div>
      <label>Доп. требования<input v-model="form.constraints" /></label>
      <button class="primary" :disabled="generating" @click="generate">
        {{ generating ? 'Ставлю в очередь…' : 'Сгенерировать (появится в списке сразу)' }}
      </button>
      <p class="tc-hintline">Генерация идёт в фоне ~1–2 мин — задание сразу видно в списке со статусом «генерируется».</p>
    </article>
  </template>

  <!-- ═══════════════ ИМПОРТ ГОТОВОГО ═══════════════ -->
  <template v-else-if="mode === 'import'">
    <div class="page-heading">
      <div><h1>Добавить готовое задание</h1></div>
      <button class="secondary tc-back" @click="backToList">← К списку</button>
    </div>
    <article class="card tc-form">
      <div class="tc-form-row">
        <label>Заголовок<input v-model="imp.title" /></label>
        <label>Направление<input v-model="imp.track" /></label>
        <label>Сумма баллов<input v-model.number="imp.total_points" type="number" min="1" /></label>
      </div>
      <label>Контекст / роль (что видит студент)<textarea v-model="imp.context_md" rows="3" /></label>
      <label>Условие / постановка задачи<textarea v-model="imp.statement_md" rows="4" /></label>
      <label>Пункты сдачи (по одному в строке)<textarea v-model="imp.deliverables" rows="3" /></label>
      <label>Публичная разбалловка (обобщённо)<textarea v-model="imp.public_rubric_note" rows="2" /></label>
      <label>Эталонное решение (опционально — для демо-проверки)<textarea v-model="imp.reference_solution_md" rows="3" /></label>

      <h3 class="tc-sub">Критерии</h3>
      <div v-for="(c, i) in imp.criteria" :key="i" class="tc-crit-edit">
        <div class="tc-form-row">
          <label>Название<input v-model="c.title" /></label>
          <label>Баллов (макс)<input v-model.number="c.max_points" type="number" min="0.5" step="0.5" /></label>
          <label>Тип<select v-model="c.check_kind"><option value="objective">объективный</option><option value="subjective">субъективный</option></select></label>
        </div>
        <label>Подсказка студенту (одна фраза, без раскрытия ожиданий)<input v-model="c.student_hint" /></label>
        <label>Что проверяет ревьюер (скрыто от студента)<textarea v-model="c.description" rows="2" /></label>
        <label>Признаки сильного ответа (скрыто; по одному в строке)<textarea v-model="c.expected_signals" rows="2" /></label>
        <label>Уровни (по строке: «баллы — метка — описание»)<textarea v-model="c.rubric_levels" rows="2" /></label>
        <button v-if="imp.criteria.length > 1" class="text-button" @click="imp.criteria.splice(i, 1)">удалить критерий</button>
      </div>
      <button class="secondary" @click="addImpCriterion">＋ Ещё критерий</button>
      <div style="margin-top:14px"><button class="primary" :disabled="importing || !imp.title || !imp.statement_md" @click="importTask">{{ importing ? 'Импортирую…' : 'Импортировать задание' }}</button></div>
    </article>
  </template>

  <!-- ═══════════════ ДЕТАЛЬ ═══════════════ -->
  <template v-else-if="mode === 'detail'">
    <div class="page-heading">
      <div>
        <h1>{{ task?.data?.title || 'Загрузка…' }}</h1>
        <p v-if="task">v{{ task.version }} · {{ task.source }} · {{ task.data.criteria.length }} критериев · {{ task.total_points }} б.</p>
      </div>
      <button class="secondary tc-back" @click="backToList">← К списку</button>
    </div>

    <article v-if="task && task.gen_status === 'generating'" class="card tc-progress">
      <span class="spinner" /> Задание генерируется агентом… <small>можно уйти в меню — не прервётся</small>
    </article>
    <article v-else-if="task && task.gen_status === 'generation_failed'" class="card">
      <h2 class="danger">Генерация не удалась</h2>
      <pre class="tc-err">{{ task.gen_error }}</pre>
    </article>

    <!-- ── просмотр ── -->
    <template v-else-if="task && !editing">
      <article class="card">
        <div class="rubric-head">
          <div><h2>Что видит студент</h2><p>{{ task.data.summary }}</p></div>
          <button class="text-button" @click="startEdit">✎ Редактировать</button>
        </div>
        <p v-if="task.data.context_md" class="tc-block">{{ task.data.context_md }}</p>
        <p class="tc-block"><b>Задача.</b> {{ task.data.statement_md }}</p>
        <ol v-if="task.data.deliverables?.length" class="tc-deliverables"><li v-for="(d, i) in task.data.deliverables" :key="i">{{ d }}</li></ol>
        <p v-if="task.data.public_rubric_note" class="tc-note">{{ task.data.public_rubric_note }}</p>
        <div class="criteria-table">
          <div v-for="(c, i) in criteria" :key="c.key"><span>{{ i + 1 }}</span><b>{{ c.title }}</b><em>0–{{ c.max_points }} б.</em><small class="tc-hint">{{ c.student_hint || '—' }}</small></div>
        </div>
        <div class="rubric-actions">
          <button class="text-button" @click="showHidden = !showHidden">{{ showHidden ? 'Скрыть' : 'Показать' }} рубрику ревьюера</button>
          <a class="secondary" :href="`${exportBase}?format=markdown&view=student`" target="_blank">Бриф студента ↗</a>
          <a class="secondary" :href="`${exportBase}?format=markdown&view=reviewer`" target="_blank">Экспорт ревьюера ↗</a>
          <button class="secondary" :disabled="sendingToAssignments" @click="sendToAssignments">{{ sendingToAssignments ? 'Отправляю…' : '→ В «Банк заданий и критериев»' }}</button>
          <button class="primary" :disabled="validating" @click="validate">{{ validating ? 'Проверяю…' : 'Проверить критерии агентами' }}</button>
        </div>
        <div v-if="showHidden" class="tc-hidden">
          <article v-for="c in criteria" :key="c.key">
            <h4>{{ c.title }} <em>0–{{ c.max_points }} · {{ c.check_kind === 'objective' ? 'объективный' : 'субъективный' }}</em></h4>
            <p>{{ c.description }}</p>
            <ul v-if="c.expected_signals?.length"><li v-for="(s, i) in c.expected_signals" :key="i">{{ s }}</li></ul>
            <div v-if="c.rubric_levels?.length" class="tc-levels"><span v-for="(lv, i) in c.rubric_levels" :key="i">{{ lv.points }} — {{ lv.label }}</span></div>
          </article>
        </div>
      </article>

      <!-- ── демо-проверка решения ── -->
      <article class="card tc-grade">
        <div class="card-title"><div><h2>Демо-проверка решения</h2><p>Как AI-ревьюер оценит конкретное решение по этой рубрике</p></div></div>
        <label>Текст решения студента
          <textarea v-model="gradeInput" rows="4" placeholder="Вставьте решение…" />
        </label>
        <div class="rubric-actions">
          <button v-if="task.data.reference_solution_md" class="text-button" @click="fillReference">подставить эталон</button>
          <button class="primary" :disabled="grading || !gradeInput.trim()" @click="gradeSolution">{{ grading ? 'Оцениваю…' : 'Проверить решение' }}</button>
        </div>
        <div v-if="gradeResult" class="tc-grade-res">
          <p class="tc-block"><b>Итого {{ gradeResult.total_points }} б.</b> — {{ gradeResult.overall_comment }}</p>
          <div v-for="s in gradeResult.scores" :key="s.criterion_key" class="tc-finding">
            <b>{{ s.criterion_key }}: {{ s.points }} / {{ s.max_points }}</b>
            <span v-if="!s.decidable" class="tc-target">рубрики не хватило</span>
            <p>{{ s.rationale }}</p>
            <p class="tc-why">основание: «{{ s.evidence_quote }}»</p>
            <p v-if="s.ambiguity_note" class="tc-fix">не хватило: {{ s.ambiguity_note }}</p>
          </div>
        </div>
      </article>

      <article v-if="validating && !activeRun?.result" class="card tc-progress">
        <span class="spinner" /> {{ activeRun?.progress || 'старт валидации…' }}
        <small>прогон идёт на сервере — можно уйти в меню и вернуться</small>
      </article>

      <!-- ── ИТОГИ ВАЛИДАЦИИ (объяснённые) ── -->
      <template v-if="shownResult">
        <article class="card" :class="verdict.tone === 'ok' ? 'tc-ok' : 'tc-warn'">
          <h2>{{ verdict.tone === 'ok' ? '✓ ' : '⚠ ' }}{{ verdict.text }}</h2>
          <p class="tc-what">Что проверяли: {{ shownResult.rounds[0] ? shownResult.rounds[0].solutions.length : 0 }} профил(я) «студентов» независимо решили задание, видя только бриф. AI-ревьюер оценил каждое решение по полной (скрытой) рубрике. AI-методист сравнил оценки и формулировки и нашёл слабые места. Расход: {{ shownResult.metrics.total_tokens }} токенов ≈ {{ shownResult.metrics.cost_rub }} ₽.</p>

          <template v-if="allFindings.length">
            <h3 class="tc-sub">Что не так и что делать</h3>
            <div v-for="f in allFindings" :key="f.id" class="tc-rec">
              <span :class="`tc-sev tc-sev--${f.severity}`">{{ f.severity === 'high' ? 'важно' : f.severity === 'medium' ? 'средне' : 'мелочь' }}</span>
              <b>{{ (KIND_PLAIN[f.kind] || [f.kind])[0] }}</b>
              <span class="tc-where">{{ f.criterion_key ? `критерий «${f.criterion_key}»` : 'уровень задания' }}<template v-if="f.target === 'brief'"> · чинится в брифе</template></span>
              <p class="tc-why">{{ (KIND_PLAIN[f.kind] || ['', ''])[1] }} {{ f.explanation }}</p>
              <p v-if="f.fix_suggestion" class="tc-fix">→ {{ f.fix_suggestion }}</p>
            </div>
          </template>

          <div class="tc-next">
            <b>Что дальше:</b>
            <span v-if="openEdits.length">примите правки рубрики кнопкой ниже — или откройте «✎ Редактировать» и поправьте формулировки сами.</span>
            <span v-else-if="briefFindings.length">откройте «✎ Редактировать» и поправьте условие / пункты сдачи по рекомендациям.</span>
            <span v-else-if="verdict.tone === 'ok'">рубрика в порядке — экспортируйте бриф студента.</span>
            <span v-else>поправьте формулировки вручную через «✎ Редактировать».</span>
          </div>
        </article>

        <article v-if="openEdits.length" class="card">
          <div class="card-title">
            <div><h2>Правки рубрики ({{ openEdits.length }})</h2><p>Применятся все сразу, создав новую версию задания</p></div>
            <button class="primary" :disabled="applying" @click="applyEdits">{{ applying ? 'Применяю…' : 'Принять все' }}</button>
          </div>
          <div v-for="e in openEdits" :key="e.id" class="tc-edit">
            <div class="tc-edit-head"><b>{{ { modify: 'изменить', add: 'добавить', remove: 'убрать' }[e.operation] }} «{{ e.criterion_key }}»</b><span :class="`tc-sev tc-sev--${e.severity}`">{{ e.severity }}</span></div>
            <p v-if="e.before_snapshot" class="tc-was">было: {{ e.before_snapshot }}</p>
            <p v-if="e.proposed_criterion" class="tc-now">стало: {{ e.proposed_criterion.description }}</p>
            <p class="tc-why">{{ e.rationale }}</p>
          </div>
        </article>

        <article class="card">
          <button class="text-button" @click="showSolvers = !showSolvers">{{ showSolvers ? 'Скрыть' : 'Показать' }} детали: как студенты решили и как оценены</button>
          <template v-if="showSolvers">
            <p class="tc-what">Каждый профиль-студент получил баллы по критериям. Если один критерий даёт всем одинаковый балл при разном качестве работ — он не различает уровни. Если баллы сильно разнятся (spread ≥ 1) — критерий читается неоднозначно.</p>
            <div v-for="rd in shownResult.rounds" :key="rd.round_no" class="tc-round">
              <h4>Раунд {{ rd.round_no }}</h4>
              <div class="tc-matrix">
                <div class="tc-matrix-head"><span>критерий</span><span v-for="p in personasOf(rd.score_matrix)" :key="p">{{ PERSONA_RU[p] || p }}</span><span>разброс</span></div>
                <div v-for="(row, key) in rd.score_matrix" :key="key" class="tc-matrix-row">
                  <span>{{ key }}</span><span v-for="p in personasOf(rd.score_matrix)" :key="p">{{ row[p] ?? '—' }}</span>
                  <span :class="{ 'tc-wide': Number(spread(row)) >= 1 }">{{ spread(row) }}</span>
                </div>
              </div>
            </div>
          </template>
        </article>
      </template>

      <article v-if="runs.length" class="card">
        <div class="card-title"><div><h2>История прогонов</h2><p>{{ runs.length }} шт. — нажмите, чтобы открыть</p></div></div>
        <div v-for="r in runs" :key="r.id" class="tc-runrow" @click="showRun(r)">
          <span :class="`tc-sev tc-sev--${r.status === 'succeeded' ? 'low' : r.status === 'failed' ? 'high' : 'medium'}`">{{ r.status }}</span>
          <b v-if="r.status === 'succeeded'">{{ r.rounds }} раунд(ов) · находок {{ r.open_findings }} · правок {{ r.proposed_edits }} · {{ r.cost_rub }} ₽</b>
          <b v-else>{{ r.progress }}</b>
          <small>{{ fmtDate(r.created_at) }}</small>
        </div>
      </article>
    </template>

    <!-- ── редактор ── -->
    <template v-else-if="task && editing">
      <article class="card tc-form">
        <div class="card-title"><div><h2>Ручное редактирование</h2><p>Сохранение создаёт новую версию (source=edited)</p></div>
          <div class="tc-head-actions"><button class="secondary" @click="editing = false">Отмена</button><button class="primary" @click="saveEdit">Сохранить</button></div>
        </div>
        <label>Заголовок<input v-model="edit.title" /></label>
        <label>Контекст (виден студенту)<textarea v-model="edit.context_md" rows="3" /></label>
        <label>Условие<textarea v-model="edit.statement_md" rows="4" /></label>
        <label>Пункты сдачи (по строке)<textarea v-model="edit.deliverables" rows="3" /></label>
        <label>Публичная разбалловка<textarea v-model="edit.public_rubric_note" rows="2" /></label>

        <h3 class="tc-sub">Критерии</h3>
        <div v-for="(c, i) in edit.criteria" :key="i" class="tc-crit-edit">
          <div class="tc-form-row">
            <label>Название<input v-model="c.title" /></label>
            <label>Баллов<input v-model.number="c.max_points" type="number" min="0.5" step="0.5" /></label>
            <label>Тип<select v-model="c.check_kind"><option value="objective">объективный</option><option value="subjective">субъективный</option></select></label>
          </div>
          <label>Подсказка студенту<input v-model="c.student_hint" /></label>
          <label>Что проверяет ревьюер (скрыто)<textarea v-model="c.description" rows="2" /></label>
          <label>Признаки сильного ответа (скрыто, по строке)<textarea v-model="c.expected_signals" rows="2" /></label>
          <label>Уровни («баллы — метка — описание»)<textarea v-model="c.rubric_levels" rows="2" /></label>
          <button v-if="edit.criteria.length > 1" class="text-button" @click="edit.criteria.splice(i, 1)">удалить критерий</button>
        </div>
        <button class="secondary" @click="edit.criteria.push({ key: 'c' + (edit.criteria.length + 1), title: '', max_points: 5, student_hint: '', description: '', check_kind: 'subjective', evidence_hint: '', expected_signals: '', rubric_levels: '' })">＋ Ещё критерий</button>

        <h3 class="tc-sub">Скрытое от студента</h3>
        <label>Эталонное решение<textarea v-model="edit.reference_solution_md" rows="3" /></label>
        <label>Типичные ошибки (по строке)<textarea v-model="edit.common_mistakes" rows="2" /></label>
        <label>Заметки для калибровки<textarea v-model="edit.reviewer_notes" rows="2" /></label>
      </article>
    </template>
  </template>
</template>

<style scoped>
.tc-head-actions { display: flex; gap: 8px; }
.tc-back { white-space: nowrap; min-width: 110px; padding: 8px 16px; }
.registry-tools { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.registry-tools select { padding: 7px 10px; border: 1px solid #d7d7e0; border-radius: 8px; }
.tc-live { color: #7c3aed; font-size: 12px; }
.table-card .table-row { grid-template-columns: 2.4fr 1fr 0.8fr 1.6fr 24px; }
.tc-row { cursor: pointer; } .tc-row:hover { background: #faf9ff; }
.tc-title-cell b { display: block; }
.tc-title-cell small, .tc-runcell small { color: #8a8a9c; font-size: 12px; }
.tc-go { color: #b7b7c6; text-align: right; }
.tc-status { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 700;
  color: var(--c); background: color-mix(in srgb, var(--c) 14%, white); }
.tc-pulse { animation: tc-pulse 1.4s ease-in-out infinite; }
@keyframes tc-pulse { 50% { opacity: .5; } }

.tc-form label { display: block; margin-bottom: 12px; font-weight: 600; font-size: 13px; }
.tc-form input, .tc-form select, .tc-form textarea { display: block; width: 100%; margin-top: 6px;
  padding: 9px 11px; font: inherit; font-weight: 400; color: #1f1f28;
  border: 1px solid #d7d7e0; border-radius: 8px; background: #fff; }
.tc-form textarea { resize: vertical; }
.tc-form-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; }
.tc-hintline { color: #8a8a9c; font-size: 12px; margin-top: 8px; }
.tc-sub { margin: 18px 0 8px; font-size: 15px; }
.tc-crit-edit { border: 1px solid #eee; border-radius: 10px; padding: 12px; margin-bottom: 12px; background: #fcfcff; }

.tc-block { margin: 8px 0; white-space: pre-line; }
.tc-note { margin: 10px 0; padding: 10px 12px; background: #f5f4ff; border-radius: 8px; font-size: 13px; white-space: pre-line; }
.tc-deliverables { margin: 8px 0 8px 18px; font-size: 14px; }
.criteria-table .tc-hint { grid-column: 1 / -1; color: #6b6b80; font-size: 12px; margin-top: 2px; }
.rubric-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 14px; }
.rubric-actions .primary { margin-left: auto; }
.tc-hidden { margin-top: 14px; border-top: 1px dashed #d7d7e0; padding-top: 12px; }
.tc-hidden article { margin-bottom: 12px; }
.tc-hidden h4 { margin: 0 0 4px; font-size: 14px; } .tc-hidden h4 em { font-weight: 400; color: #8a8a9c; }
.tc-hidden ul { margin: 4px 0 4px 18px; font-size: 13px; color: #444; }
.tc-levels { display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; color: #6b6b80; }

.tc-progress { display: flex; align-items: center; gap: 10px; color: #6b6b80; flex-wrap: wrap; }
.tc-progress small { color: #b7b7c6; width: 100%; }
.spinner { width: 14px; height: 14px; border: 2px solid #cfcfe0; border-top-color: #8b5cf6; border-radius: 50%; animation: tc-spin .8s linear infinite; }
@keyframes tc-spin { to { transform: rotate(360deg); } }
.tc-err { white-space: pre-wrap; font-size: 12px; color: #b91c1c; background: #fef2f2; padding: 10px; border-radius: 8px; }

.tc-ok { border-left: 4px solid #047857; } .tc-warn { border-left: 4px solid #b45309; }
.tc-ok h2, .tc-warn h2 { margin: 0 0 8px; }
.tc-what { color: #555; font-size: 13px; margin: 6px 0 4px; }
.tc-rec { margin: 10px 0; padding: 9px 11px; background: #faf9ff; border-radius: 8px; font-size: 13px; }
.tc-rec b { margin: 0 8px; }
.tc-where { color: #8a8a9c; font-size: 12px; }
.tc-rec .tc-why { margin: 5px 0 0; color: #444; }
.tc-rec .tc-fix { margin: 4px 0 0; color: #6d28d9; font-weight: 600; }
.tc-next { margin-top: 14px; padding: 10px 12px; background: #eef2ff; border-radius: 8px; font-size: 13px; }

.tc-grade label { display: block; font-weight: 600; font-size: 13px; }
.tc-grade textarea { display: block; width: 100%; margin-top: 6px; padding: 9px 11px; font: inherit; font-weight: 400;
  border: 1px solid #d7d7e0; border-radius: 8px; resize: vertical; }
.tc-grade-res { margin-top: 12px; }

.tc-round h4 { margin: 14px 0 6px; font-size: 14px; }
.tc-matrix { font-size: 12px; overflow-x: auto; }
.tc-matrix-head, .tc-matrix-row { display: grid; grid-template-columns: 1.6fr repeat(5, 1fr); gap: 6px; padding: 4px 0; }
.tc-matrix-head { color: #8a8a9c; border-bottom: 1px solid #eee; }
.tc-matrix-row span:first-child { font-weight: 600; }
.tc-matrix .tc-wide { color: #dc2626; font-weight: 700; }
.tc-finding { margin: 8px 0; padding: 8px 10px; background: #faf9ff; border-radius: 8px; font-size: 13px; }
.tc-finding p { margin: 4px 0 0; } .tc-finding .tc-fix { color: #6d28d9; }
.tc-sev { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.tc-sev--high { background: #fee2e2; color: #b91c1c; }
.tc-sev--medium { background: #fef3c7; color: #92400e; }
.tc-sev--low { background: #dcfce7; color: #166534; }
.tc-target { background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 999px; font-size: 11px; font-weight: 700; margin-left: 6px; }
.tc-edit { margin: 10px 0; padding: 10px 12px; border: 1px solid #eee; border-radius: 8px; font-size: 13px; }
.tc-edit-head { display: flex; gap: 8px; align-items: center; }
.tc-was { color: #9ca3af; text-decoration: line-through; margin: 6px 0 2px; }
.tc-now { color: #065f46; margin: 2px 0; }
.tc-why { color: #6b6b80; margin-top: 4px; }
.tc-runrow { display: grid; grid-template-columns: 90px 1fr auto; gap: 10px; align-items: center;
  padding: 8px 0; border-top: 1px solid #f0f0f4; cursor: pointer; font-size: 13px; }
.tc-runrow:hover { background: #faf9ff; } .tc-runrow small { color: #8a8a9c; }
.danger { color: #b91c1c; }
</style>
