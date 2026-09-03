<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { taskCreater } from '../../shared/api'

// --- навигация экрана переживает выход в меню (localStorage) -----------------
const NAV_KEY = 'taskcreater:nav'
function loadNav() {
  try { return JSON.parse(localStorage.getItem(NAV_KEY)) || { mode: 'list' } } catch { return { mode: 'list' } }
}
function saveNav() {
  try { localStorage.setItem(NAV_KEY, JSON.stringify({ mode: mode.value, taskId: taskId.value })) } catch { /* ignore */ }
}

const mode = ref('list')      // list | new | detail
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

// деталь
const task = ref(null)
const runs = ref([])
const activeRun = ref(null)          // прогон, за которым сейчас следим (poll)
const shownResult = ref(null)        // какой result показываем (из активного или из истории)
const validating = ref(false)
const applying = ref(false)
const showHidden = ref(false)

const STATUS = {
  draft: ['черновик', '#6b7280'], validating: ['на проверке', '#7c3aed'],
  needs_review: ['есть замечания', '#b45309'], checked: ['проверено', '#047857'],
  revised: ['уточнено', '#1d4ed8'], failed: ['ошибка прогона', '#b91c1c'],
}
const KIND = {
  ambiguous: 'неоднозначно', underspecified: 'недоспецифицировано', gameable: 'geймабельно',
  overlapping: 'пересечение', unmeasurable: 'не измеримо', missing_criterion: 'нет критерия',
  inconsistent_scoring: 'несогласованность оценок', weight_imbalance: 'перекос весов',
  scope_creep: 'выход за условие', unfair_hidden: 'скрытое ожидание вне брифа', leaky_public: 'утечка грейдинга',
}

const criteria = computed(() => task.value?.data?.criteria || [])
const openEdits = computed(() => shownResult.value?.proposed_edits || [])
const exportBase = computed(() => (task.value ? `/task-creater/tasks/${task.value.id}/export` : ''))
const anyValidating = computed(() => items.value.some(x => x.status === 'validating'))

function fmtDate(v) {
  if (!v) return '—'
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(v))
}
function personasOf(m) { return [...new Set(Object.values(m || {}).flatMap(r => Object.keys(r)))] }
function spread(row) { const v = Object.values(row || {}); return v.length > 1 ? (Math.max(...v) - Math.min(...v)).toFixed(2) : '0.00' }

// --- модульный реестр поллинга: переживает перемонтирование компонента --------
const registry = (window.__tcPoll ||= { runId: null, stop: false })

async function pollRun(runId) {
  registry.runId = runId
  registry.stop = false
  validating.value = true
  for (let i = 0; i < 400; i++) {
    if (registry.stop || registry.runId !== runId) return
    try { activeRun.value = await taskCreater(`/validation-runs/${runId}`) }
    catch (e) { error.value = e.message; break }
    if (['succeeded', 'failed'].includes(activeRun.value.status)) {
      if (activeRun.value.status === 'failed') error.value = activeRun.value.error || 'Прогон валидации упал'
      shownResult.value = activeRun.value.result
      await refreshDetailMeta()
      break
    }
    await new Promise(r => setTimeout(r, 1500))
  }
  validating.value = false
  if (registry.runId === runId) registry.runId = null
}

// --- список -----------------------------------------------------------------
let listTimer = null
async function loadList() {
  loadingList.value = true; error.value = ''
  try { items.value = await taskCreater(`/tasks${statusFilter.value ? `?status=${statusFilter.value}` : ''}`) }
  catch (e) { error.value = e.message }
  finally { loadingList.value = false }
}
function scheduleListRefresh() {
  clearInterval(listTimer)
  listTimer = setInterval(() => { if (mode.value === 'list' && anyValidating.value) loadList() }, 3000)
}

// --- деталь ---------------------------------------------------------------
async function openTask(id) {
  mode.value = 'detail'; taskId.value = id; saveNav()
  task.value = null; runs.value = []; activeRun.value = null; shownResult.value = null; error.value = ''
  try {
    task.value = await taskCreater(`/tasks/${id}`)
    runs.value = await taskCreater(`/tasks/${task.value.root_id}/runs`)
    const running = runs.value.find(r => ['pending', 'running'].includes(r.status))
    if (running) pollRun(running.id)                      // возобновляем показ активного прогона
    else if (runs.value[0]?.status === 'succeeded') showRun(runs.value[0])
  } catch (e) { error.value = e.message }
}
async function refreshDetailMeta() {
  if (!task.value) return
  try {
    task.value = await taskCreater(`/tasks/${task.value.root_id}/versions/${task.value.version}`).catch(() => task.value)
    runs.value = await taskCreater(`/tasks/${task.value.root_id}/runs`)
  } catch { /* ignore */ }
}
async function showRun(runBrief) {
  if (['pending', 'running'].includes(runBrief.status)) { pollRun(runBrief.id); return }
  try { const full = await taskCreater(`/validation-runs/${runBrief.id}`); shownResult.value = full.result; activeRun.value = full }
  catch (e) { error.value = e.message }
}

async function generate() {
  generating.value = true; error.value = ''; notice.value = ''
  try {
    const res = await taskCreater('/tasks/generate', {
      method: 'POST',
      body: JSON.stringify({ idea: { ...form.value, delivery_channel: 'stepik', language: 'ru' } }),
    })
    notice.value = `Задание создано: «${res.data.title}»`
    await openTask(res.id)
  } catch (e) { error.value = e.message }
  finally { generating.value = false }
}

async function validate() {
  error.value = ''
  try {
    const started = await taskCreater(`/tasks/${task.value.id}/validate`, { method: 'POST', body: JSON.stringify({ max_rounds: 2 }) })
    shownResult.value = null
    await refreshDetailMeta()
    pollRun(started.id)
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
  } catch (e) { error.value = e.message }
  finally { applying.value = false }
}

function backToList() { mode.value = 'list'; taskId.value = null; saveNav(); loadList() }
function startNew() { mode.value = 'new'; taskId.value = null; saveNav() }

onMounted(() => {
  const nav = loadNav()
  if (nav.mode === 'detail' && nav.taskId) openTask(nav.taskId)
  else if (nav.mode === 'new') mode.value = 'new'
  else { mode.value = 'list' }
  loadList()
  scheduleListRefresh()
})
onUnmounted(() => {
  clearInterval(listTimer)
  registry.stop = true          // прекращаем ТОЛЬКО опрос из UI; серверный прогон продолжается
})
</script>

<template>
  <div v-if="notice" class="toast-success global-toast">✓ {{ notice }}<button @click="notice = ''">×</button></div>
  <div v-if="error" class="toast-error global-toast">{{ error }}<button @click="error = ''">×</button></div>

  <!-- ───────────────────────── СПИСОК ───────────────────────── -->
  <template v-if="mode === 'list'">
    <div class="page-heading">
      <div>
        <span class="eyebrow">КОНТЕНТ КУРСА</span>
        <h1>AI-конструктор ДЗ</h1>
        <p>Менеджер идей и заданий. Прогон валидации не прерывается при выходе в меню.</p>
      </div>
      <button class="primary" @click="startNew">＋ Новое задание</button>
    </div>

    <div class="registry-tools">
      <select v-model="statusFilter" @change="loadList">
        <option value="">Все статусы</option>
        <option v-for="(v, k) in STATUS" :key="k" :value="k">{{ v[0] }}</option>
      </select>
      <button class="text-button" @click="loadList">{{ loadingList ? 'Обновляю…' : 'Обновить' }}</button>
      <span v-if="anyValidating" class="tc-live">● есть активные прогоны — список обновляется автоматически</span>
    </div>

    <div class="table-card">
      <div class="table-row table-head"><span>Задание</span><span>Статус</span><span>Версия</span><span>Последняя проверка</span><span /></div>
      <div v-for="it in items" :key="it.root_id" class="table-row tc-row" @click="openTask(it.id)">
        <span class="tc-title-cell">
          <b>{{ it.title }}</b>
          <small>{{ it.track || '—' }} · {{ it.criteria_count }} критериев · {{ it.total_points }} б.</small>
        </span>
        <span><em class="tc-status" :style="`--c:${STATUS[it.status][1]}`">{{ STATUS[it.status][0] }}</em></span>
        <span>v{{ it.version }} <small>{{ it.source }}</small></span>
        <span class="tc-runcell">
          <template v-if="it.last_run">
            <b :class="it.last_run.status === 'failed' ? 'danger' : ''">
              {{ it.last_run.status === 'succeeded'
                ? `${it.last_run.rounds} р. · правок ${it.last_run.proposed_edits} · ${it.last_run.cost_rub} ₽`
                : it.last_run.status }}
            </b>
            <small>{{ fmtDate(it.last_run.updated_at) }}</small>
          </template>
          <small v-else>не запускалась</small>
        </span>
        <span class="tc-go">→</span>
      </div>
      <div v-if="!items.length && !loadingList" class="empty-state in-table">
        <span>✦</span><h2>Пока нет заданий</h2><p>Создайте первое — «＋ Новое задание».</p>
      </div>
    </div>
  </template>

  <!-- ───────────────────────── НОВОЕ ───────────────────────── -->
  <template v-else-if="mode === 'new'">
    <div class="page-heading">
      <div><span class="eyebrow">КОНТЕНТ КУРСА</span><h1>Новое задание из идеи</h1></div>
      <button class="secondary" @click="backToList">← К списку</button>
    </div>
    <article class="card tc-form">
      <label>Идея задания<textarea v-model="form.idea" rows="4" /></label>
      <div class="tc-form-row">
        <label>Направление<input v-model="form.track" /></label>
        <label>Формат
          <select v-model="form.task_format">
            <option value="auto">авто</option>
            <option value="case_study">бизнес-кейс</option>
            <option value="metrics_design">подбор метрик</option>
            <option value="coding">задача с кодом</option>
            <option value="open">свободный</option>
          </select>
        </label>
        <label>Баллов<input v-model.number="form.total_points" type="number" min="1" max="100" /></label>
      </div>
      <label>Доп. требования<input v-model="form.constraints" /></label>
      <button class="primary" :disabled="generating" @click="generate">
        {{ generating ? 'Генерирую…' : 'Сгенерировать задание' }}
      </button>
    </article>
  </template>

  <!-- ───────────────────────── ДЕТАЛЬ ───────────────────────── -->
  <template v-else-if="mode === 'detail'">
    <div class="page-heading">
      <div>
        <span class="eyebrow">ЗАДАНИЕ</span>
        <h1>{{ task?.data?.title || 'Загрузка…' }}</h1>
        <p v-if="task">v{{ task.version }} · {{ task.source }} · {{ task.data.criteria.length }} критериев · {{ task.total_points }} б.</p>
      </div>
      <button class="secondary" @click="backToList">← К списку</button>
    </div>

    <template v-if="task">
      <article class="card">
        <div class="rubric-head">
          <div><h2>Что видит студент</h2><p>{{ task.data.summary }}</p></div>
        </div>
        <p v-if="task.data.context_md" class="tc-block">{{ task.data.context_md }}</p>
        <p class="tc-block"><b>Задача.</b> {{ task.data.statement_md }}</p>
        <ol v-if="task.data.deliverables?.length" class="tc-deliverables">
          <li v-for="(d, i) in task.data.deliverables" :key="i">{{ d }}</li>
        </ol>
        <p v-if="task.data.public_rubric_note" class="tc-note">{{ task.data.public_rubric_note }}</p>
        <div class="criteria-table">
          <div v-for="(c, i) in criteria" :key="c.key">
            <span>{{ i + 1 }}</span><b>{{ c.title }}</b><em>0–{{ c.max_points }} б.</em>
            <small class="tc-hint">{{ c.student_hint || '—' }}</small>
          </div>
        </div>

        <div class="rubric-actions">
          <button class="text-button" @click="showHidden = !showHidden">
            {{ showHidden ? 'Скрыть' : 'Показать' }} рубрику ревьюера
          </button>
          <a class="secondary" :href="`${exportBase}?format=markdown&view=student`" target="_blank">Бриф студента ↗</a>
          <a class="secondary" :href="`${exportBase}?format=markdown&view=reviewer`" target="_blank">Экспорт ревьюера ↗</a>
          <button class="primary" :disabled="validating" @click="validate">
            {{ validating ? 'Проверяю…' : 'Проверить критерии агентами' }}
          </button>
        </div>

        <div v-if="showHidden" class="tc-hidden">
          <article v-for="c in criteria" :key="c.key">
            <h4>{{ c.title }} <em>0–{{ c.max_points }} · {{ c.check_kind === 'objective' ? 'объективный' : 'субъективный' }}</em></h4>
            <p>{{ c.description }}</p>
            <ul v-if="c.expected_signals?.length"><li v-for="(s, i) in c.expected_signals" :key="i">{{ s }}</li></ul>
            <div v-if="c.rubric_levels?.length" class="tc-levels">
              <span v-for="(lv, i) in c.rubric_levels" :key="i">{{ lv.points }} — {{ lv.label }}</span>
            </div>
          </article>
        </div>
      </article>

      <article v-if="validating && (!activeRun?.result)" class="card tc-progress">
        <span class="spinner" /> {{ activeRun?.progress || 'старт валидации…' }}
        <small>прогон идёт на сервере — можно уйти в меню и вернуться</small>
      </article>

      <template v-if="shownResult">
        <article class="card">
          <div class="card-title">
            <div><h2>Итог валидации</h2><p>{{ shownResult.summary }}</p></div>
            <strong :class="shownResult.converged ? 'large-positive' : ''">
              {{ shownResult.converged ? 'сошлось' : 'нужно решение' }}
            </strong>
          </div>
          <div class="tc-metrics">
            <span>вызовов LLM <b>{{ shownResult.metrics.llm_calls }}</b></span>
            <span>токенов <b>{{ shownResult.metrics.total_tokens }}</b></span>
            <span>≈ <b>{{ shownResult.metrics.cost_rub }} ₽</b></span>
            <span><b>{{ shownResult.metrics.duration_s }} c</b></span>
          </div>

          <div v-for="rd in shownResult.rounds" :key="rd.round_no" class="tc-round">
            <h4>Раунд {{ rd.round_no }} — оценки по критериям × профиль</h4>
            <div class="tc-matrix">
              <div class="tc-matrix-head">
                <span>критерий</span><span v-for="p in personasOf(rd.score_matrix)" :key="p">{{ p }}</span><span>spread</span>
              </div>
              <div v-for="(row, key) in rd.score_matrix" :key="key" class="tc-matrix-row">
                <span>{{ key }}</span>
                <span v-for="p in personasOf(rd.score_matrix)" :key="p">{{ row[p] ?? '—' }}</span>
                <span :class="{ 'tc-wide': Number(spread(row)) >= 1 }">{{ spread(row) }}</span>
              </div>
            </div>
            <div v-for="f in rd.findings" :key="f.id" class="tc-finding">
              <span :class="`tc-sev tc-sev--${f.severity}`">{{ f.severity }}</span>
              <span class="tc-kind">{{ KIND[f.kind] || f.kind }}</span>
              <span v-if="f.target === 'brief'" class="tc-target">бриф</span>
              <span class="tc-crit">{{ f.criterion_key || 'уровень задания' }}</span>
              <p>{{ f.explanation }}</p>
              <p v-if="f.fix_suggestion" class="tc-fix">Как чинить: {{ f.fix_suggestion }}</p>
            </div>
          </div>
        </article>

        <article v-if="openEdits.length" class="card">
          <div class="card-title">
            <div><h2>Предложенные правки критериев</h2><p>Применяются к рубрике; brief-правки — вручную через экспорт</p></div>
            <button class="primary" :disabled="applying" @click="applyEdits">
              {{ applying ? 'Применяю…' : `Принять все · ${openEdits.length}` }}
            </button>
          </div>
          <div v-for="e in openEdits" :key="e.id" class="tc-edit">
            <div class="tc-edit-head"><b>{{ e.operation.toUpperCase() }} {{ e.criterion_key }}</b><span :class="`tc-sev tc-sev--${e.severity}`">{{ e.severity }}</span></div>
            <p v-if="e.before_snapshot" class="tc-was">было: {{ e.before_snapshot }}</p>
            <p v-if="e.proposed_criterion" class="tc-now">стало: {{ e.proposed_criterion.description }}</p>
            <p class="tc-why">{{ e.rationale }}</p>
          </div>
        </article>
      </template>

      <article v-if="runs.length" class="card">
        <div class="card-title"><div><h2>История прогонов</h2><p>{{ runs.length }} шт.</p></div></div>
        <div v-for="r in runs" :key="r.id" class="tc-runrow" @click="showRun(r)">
          <span :class="`tc-sev tc-sev--${r.status === 'succeeded' ? 'low' : r.status === 'failed' ? 'high' : 'medium'}`">{{ r.status }}</span>
          <b v-if="r.status === 'succeeded'">{{ r.rounds }} раунд(ов) · находок {{ r.open_findings }} · правок {{ r.proposed_edits }} · {{ r.cost_rub }} ₽</b>
          <b v-else>{{ r.progress }}</b>
          <small>{{ fmtDate(r.created_at) }}</small>
        </div>
      </article>
    </template>
  </template>
</template>

<style scoped>
.registry-tools { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.registry-tools select { padding: 7px 10px; border: 1px solid #d7d7e0; border-radius: 8px; }
.tc-live { color: #7c3aed; font-size: 12px; }
.table-head span, .tc-row span { padding: 4px 0; }
.table-card .table-row { grid-template-columns: 2.4fr 1fr 0.8fr 1.6fr 24px; }
.tc-row { cursor: pointer; }
.tc-row:hover { background: #faf9ff; }
.tc-title-cell b { display: block; }
.tc-title-cell small, .tc-runcell small { color: #8a8a9c; font-size: 12px; }
.tc-go { color: #b7b7c6; text-align: right; }
.tc-status { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 700;
  color: var(--c); background: color-mix(in srgb, var(--c) 14%, white); }
.tc-form label { display: block; margin-bottom: 12px; font-weight: 600; font-size: 13px; }
.tc-form input, .tc-form select, .tc-form textarea { display: block; width: 100%; margin-top: 6px;
  padding: 9px 11px; font: inherit; border: 1px solid #d7d7e0; border-radius: 8px; background: #fff; }
.tc-form-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; }
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
.tc-metrics { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: #555; margin: 6px 0 14px; }
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
.tc-kind { font-weight: 600; margin: 0 6px; }
.tc-target { background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.tc-crit { color: #8a8a9c; margin-left: 6px; font-family: ui-monospace, monospace; font-size: 12px; }
.tc-edit { margin: 10px 0; padding: 10px 12px; border: 1px solid #eee; border-radius: 8px; font-size: 13px; }
.tc-edit-head { display: flex; gap: 8px; align-items: center; }
.tc-was { color: #9ca3af; text-decoration: line-through; margin: 6px 0 2px; }
.tc-now { color: #065f46; margin: 2px 0; }
.tc-why { color: #6b6b80; margin-top: 4px; }
.tc-runrow { display: grid; grid-template-columns: 90px 1fr auto; gap: 10px; align-items: center;
  padding: 8px 0; border-top: 1px solid #f0f0f4; cursor: pointer; font-size: 13px; }
.tc-runrow:hover { background: #faf9ff; }
.tc-runrow small { color: #8a8a9c; }
.danger { color: #b91c1c; }
</style>
