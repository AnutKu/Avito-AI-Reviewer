<script setup>
import { computed, ref } from 'vue'
import { taskCreater } from '../../shared/api'

const error = ref('')
const notice = ref('')

const form = ref({
  idea: 'Кейс на разбор бизнес-проблемы: студент в роли продуктового аналитика вертикали. За год упал ROMI маркетинга. Нужно верифицировать проблему, сгенерировать и приоритизировать гипотезы, выбрать способы валидации, предложить решения, оценить их потенциал и выбрать метрики/дизайн теста.',
  track: 'Аналитика данных',
  task_format: 'case_study',
  total_points: 10,
  constraints: 'Кейс с ролью и вводными цифрами. Оптимально 6–8 гипотез. Оценка по этапам, сумма 10.',
})

const task = ref(null)
const run = ref(null)
const generating = ref(false)
const validating = ref(false)
const applying = ref(false)
const showHidden = ref(false)

const criteria = computed(() => task.value?.data?.criteria || [])
const result = computed(() => run.value?.result || null)
const openEdits = computed(() => result.value?.proposed_edits || [])
const exportBase = computed(() => (task.value ? `/task-creater/tasks/${task.value.id}/export` : ''))

const kinds = {
  ambiguous: 'неоднозначно', underspecified: 'недоспецифицировано', gameable: 'geймабельно',
  overlapping: 'пересечение', unmeasurable: 'не измеримо', missing_criterion: 'нет критерия',
  inconsistent_scoring: 'несогласованность оценок', weight_imbalance: 'перекос весов',
  scope_creep: 'выход за условие', unfair_hidden: 'скрытое ожидание вне брифа',
  leaky_public: 'утечка грейдинга',
}

async function generate() {
  error.value = ''; notice.value = ''; run.value = null; generating.value = true
  try {
    task.value = await taskCreater('/tasks/generate', {
      method: 'POST',
      body: JSON.stringify({ idea: { ...form.value, delivery_channel: 'stepik', language: 'ru' } }),
    })
    notice.value = `Задание сгенерировано: v${task.value.version}`
  } catch (e) { error.value = e.message }
  finally { generating.value = false }
}

async function validate() {
  error.value = ''; validating.value = true; run.value = null
  try {
    const started = await taskCreater(`/tasks/${task.value.id}/validate`, {
      method: 'POST', body: JSON.stringify({ max_rounds: 2 }),
    })
    for (let i = 0; i < 200; i++) {
      run.value = await taskCreater(`/validation-runs/${started.id}`)
      if (run.value.status === 'succeeded' || run.value.status === 'failed') break
      await new Promise(r => setTimeout(r, 1500))
    }
    if (run.value?.status === 'failed') error.value = run.value.error || 'Прогон валидации упал'
  } catch (e) { error.value = e.message }
  finally { validating.value = false }
}

async function applyEdits() {
  applying.value = true; error.value = ''
  try {
    const decisions = openEdits.value.map(e => ({ edit_id: e.id, accept: true }))
    task.value = await taskCreater(`/validation-runs/${run.value.id}/decisions`, {
      method: 'POST', body: JSON.stringify({ decisions, author: 'кабинет методиста' }),
    })
    run.value = null
    notice.value = `Правки применены — новая версия v${task.value.version}`
  } catch (e) { error.value = e.message }
  finally { applying.value = false }
}

function personasOf(matrix) {
  return [...new Set(Object.values(matrix || {}).flatMap(row => Object.keys(row)))]
}
function spread(row) {
  const v = Object.values(row || {})
  return v.length > 1 ? (Math.max(...v) - Math.min(...v)).toFixed(2) : '0.00'
}
</script>

<template>
  <div v-if="notice" class="toast-success global-toast">✓ {{ notice }}<button @click="notice = ''">×</button></div>
  <div v-if="error" class="toast-error global-toast">{{ error }}<button @click="error = ''">×</button></div>

  <div class="page-heading">
    <div>
      <span class="eyebrow">КОНТЕНТ КУРСА</span>
      <h1>AI-конструктор ДЗ</h1>
      <p>Из идеи — задание с критериями. Агенты решают его глазами студента и находят слабые места рубрики.</p>
    </div>
    <a v-if="task" class="secondary" :href="`${exportBase}?format=markdown&view=reviewer`" target="_blank">Экспорт (ревьюер) ↗</a>
  </div>

  <article class="card tc-form">
    <label>Идея задания
      <textarea v-model="form.idea" rows="4" />
    </label>
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

  <template v-if="task">
    <article class="card">
      <div class="rubric-head">
        <div>
          <small>{{ task.data.title }}</small>
          <h2>Что видит студент</h2>
          <p>{{ task.data.summary }}</p>
        </div>
        <div class="version-pill">v{{ task.version }} · {{ task.source }}</div>
      </div>

      <p v-if="task.data.context_md" class="tc-block">{{ task.data.context_md }}</p>
      <p class="tc-block"><b>Задача.</b> {{ task.data.statement_md }}</p>

      <ol v-if="task.data.deliverables?.length" class="tc-deliverables">
        <li v-for="(d, i) in task.data.deliverables" :key="i">{{ d }}</li>
      </ol>

      <p v-if="task.data.public_rubric_note" class="tc-note">{{ task.data.public_rubric_note }}</p>

      <div class="criteria-table">
        <div v-for="(c, i) in criteria" :key="c.key">
          <span>{{ i + 1 }}</span>
          <b>{{ c.title }}</b>
          <em>0–{{ c.max_points }} б.</em>
          <small class="tc-hint">{{ c.student_hint || '—' }}</small>
        </div>
      </div>

      <div class="rubric-actions">
        <button class="text-button" @click="showHidden = !showHidden">
          {{ showHidden ? 'Скрыть' : 'Показать' }} рубрику ревьюера (скрыта от студента)
        </button>
        <a class="secondary" :href="`${exportBase}?format=markdown&view=student`" target="_blank">Бриф студента ↗</a>
        <button class="primary" :disabled="validating" @click="validate">
          {{ validating ? 'Проверяю…' : 'Проверить критерии агентами' }}
        </button>
      </div>

      <div v-if="showHidden" class="tc-hidden">
        <article v-for="c in criteria" :key="c.key">
          <h4>{{ c.title }} <em>0–{{ c.max_points }} · {{ c.check_kind === 'objective' ? 'объективный' : 'субъективный' }}</em></h4>
          <p>{{ c.description }}</p>
          <ul v-if="c.expected_signals?.length">
            <li v-for="(s, i) in c.expected_signals" :key="i">{{ s }}</li>
          </ul>
          <div v-if="c.rubric_levels?.length" class="tc-levels">
            <span v-for="(lv, i) in c.rubric_levels" :key="i">{{ lv.points }} — {{ lv.label }}</span>
          </div>
        </article>
      </div>
    </article>

    <article v-if="validating && !result" class="card tc-progress">
      <span class="spinner" /> {{ run?.progress || 'старт валидации…' }}
    </article>

    <template v-if="result">
      <article class="card">
        <div class="card-title">
          <div><h2>Итог валидации</h2><p>{{ result.summary }}</p></div>
          <strong :class="result.converged ? 'large-positive' : ''">
            {{ result.converged ? 'сошлось' : 'нужно решение' }}
          </strong>
        </div>
        <div class="tc-metrics">
          <span>вызовов LLM <b>{{ result.metrics.llm_calls }}</b></span>
          <span>токенов <b>{{ result.metrics.total_tokens }}</b></span>
          <span>≈ <b>{{ result.metrics.cost_rub }} ₽</b></span>
          <span><b>{{ result.metrics.duration_s }} c</b></span>
        </div>

        <div v-for="rd in result.rounds" :key="rd.round_no" class="tc-round">
          <h4>Раунд {{ rd.round_no }} — оценки по критериям × профиль</h4>
          <div class="tc-matrix">
            <div class="tc-matrix-head">
              <span>критерий</span>
              <span v-for="p in personasOf(rd.score_matrix)" :key="p">{{ p }}</span>
              <span>spread</span>
            </div>
            <div v-for="(row, key) in rd.score_matrix" :key="key" class="tc-matrix-row">
              <span>{{ key }}</span>
              <span v-for="p in personasOf(rd.score_matrix)" :key="p">{{ row[p] ?? '—' }}</span>
              <span :class="{ 'tc-wide': Number(spread(row)) >= 1 }">{{ spread(row) }}</span>
            </div>
          </div>

          <div v-for="f in rd.findings" :key="f.id" class="tc-finding">
            <span :class="`tc-sev tc-sev--${f.severity}`">{{ f.severity }}</span>
            <span class="tc-kind">{{ kinds[f.kind] || f.kind }}</span>
            <span v-if="f.target === 'brief'" class="tc-target">бриф</span>
            <span class="tc-crit">{{ f.criterion_key || 'уровень задания' }}</span>
            <p>{{ f.explanation }}</p>
            <p v-if="f.fix_suggestion" class="tc-fix">Как чинить: {{ f.fix_suggestion }}</p>
          </div>
        </div>
      </article>

      <article v-if="openEdits.length" class="card">
        <div class="card-title">
          <div><h2>Предложенные правки критериев</h2><p>Применяются к исходной рубрике; brief-правки — вручную через экспорт</p></div>
          <button class="primary" :disabled="applying" @click="applyEdits">
            {{ applying ? 'Применяю…' : `Принять все · ${openEdits.length}` }}
          </button>
        </div>
        <div v-for="e in openEdits" :key="e.id" class="tc-edit">
          <div class="tc-edit-head">
            <b>{{ e.operation.toUpperCase() }} {{ e.criterion_key }}</b>
            <span :class="`tc-sev tc-sev--${e.severity}`">{{ e.severity }}</span>
          </div>
          <p v-if="e.before_snapshot" class="tc-was">было: {{ e.before_snapshot }}</p>
          <p v-if="e.proposed_criterion" class="tc-now">стало: {{ e.proposed_criterion.description }}</p>
          <p class="tc-why">{{ e.rationale }}</p>
        </div>
      </article>
    </template>
  </template>
</template>

<style scoped>
.tc-form label { display: block; margin-bottom: 12px; font-weight: 600; font-size: 13px; }
.tc-form input, .tc-form select, .tc-form textarea {
  display: block; width: 100%; margin-top: 6px; padding: 9px 11px; font: inherit;
  border: 1px solid #d7d7e0; border-radius: 8px; background: #fff;
}
.tc-form-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; }
.tc-block { margin: 8px 0; white-space: pre-line; }
.tc-note { margin: 10px 0; padding: 10px 12px; background: #f5f4ff; border-radius: 8px; font-size: 13px; white-space: pre-line; }
.tc-deliverables { margin: 8px 0 8px 18px; font-size: 14px; }
.tc-deliverables li { margin: 3px 0; }
.criteria-table .tc-hint { grid-column: 1 / -1; color: #6b6b80; font-size: 12px; margin-top: 2px; }
.rubric-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 14px; }
.rubric-actions .primary { margin-left: auto; }
.tc-hidden { margin-top: 14px; border-top: 1px dashed #d7d7e0; padding-top: 12px; }
.tc-hidden article { margin-bottom: 12px; }
.tc-hidden h4 { margin: 0 0 4px; font-size: 14px; }
.tc-hidden h4 em { font-weight: 400; color: #8a8a9c; }
.tc-hidden ul { margin: 4px 0 4px 18px; font-size: 13px; color: #444; }
.tc-levels { display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; color: #6b6b80; }
.tc-progress { display: flex; align-items: center; gap: 10px; color: #6b6b80; }
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
.tc-finding p { margin: 4px 0 0; }
.tc-finding .tc-fix { color: #6d28d9; }
.tc-sev { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.tc-sev--high { background: #fee2e2; color: #b91c1c; }
.tc-sev--medium { background: #fef3c7; color: #92400e; }
.tc-sev--low { background: #e5e7eb; color: #374151; }
.tc-kind { font-weight: 600; margin: 0 6px; }
.tc-target { background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.tc-crit { color: #8a8a9c; margin-left: 6px; font-family: ui-monospace, monospace; font-size: 12px; }
.tc-edit { margin: 10px 0; padding: 10px 12px; border: 1px solid #eee; border-radius: 8px; font-size: 13px; }
.tc-edit-head { display: flex; gap: 8px; align-items: center; }
.tc-was { color: #9ca3af; text-decoration: line-through; margin: 6px 0 2px; }
.tc-now { color: #065f46; margin: 2px 0; }
.tc-why { color: #6b6b80; margin-top: 4px; }
</style>
