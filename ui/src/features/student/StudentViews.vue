<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, formatDate } from '../../shared/api'
import { nearestDeadline, orderAssignments } from '../../shared/student'
import MarkdownText from '../../shared/ui/MarkdownText.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'

const props = defineProps({ active: String, sub: { type: Array, default: () => [] } })
const emit = defineEmits(['navigate'])
// студенту незачем видеть внутреннюю кухню распределения
const studentLabels = { proposed: 'На проверке', assigned: 'На проверке' }
const loading = ref(true)
const error = ref('')
const assignments = ref([])
const submittedCount = computed(() => assignments.value.filter(a => a.submission).length)
// Доля для кольца. Без заданий делить не на что — кольцо остаётся пустым, а не NaN.
const submittedRatio = computed(() => (assignments.value.length ? submittedCount.value / assignments.value.length : 0))
// Наверх — то, что ещё требует действия: несданное, потом непроверенное.
const orderedAssignments = computed(() => orderAssignments(assignments.value))
// Момент, от которого считается «осталось столько-то дней». Берётся при
// загрузке списка, а не на каждую перерисовку: иначе счётчик менялся бы от
// любого клика по соседней кнопке.
const now = ref(Date.now())
const deadline = computed(() => nearestDeadline(assignments.value, now.value))
const detail = ref(null)
const result = ref(null)
const blitz = ref([])
const sourceUrl = ref('https://github.com/student/mlflow-homework')
const answers = ref({})

const ROOT = 'student-assignments'
// Открытое задание живёт в адресе, а не во внутреннем флаге: иначе «назад» из
// карточки уводит из кабинета, а F5 на ней открывает список.
const openedId = computed(() => (props.active === ROOT ? props.sub[0] || '' : ''))
const mode = computed(() => {
  if (!openedId.value) return 'list'
  return result.value ? 'result' : detail.value ? 'detail' : 'loading'
})

async function loadAssignments() {
  loading.value = true
  try {
    assignments.value = await api('/student/assignments')
    now.value = Date.now()
  }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

const openAssignment = (item) => emit('navigate', `${ROOT}/${item.id}`)

// Что показать по адресу, решает сама работа, а не список: по прямой ссылке
// список может быть ещё не загружен, а ответ по заданию уже говорит, сдано оно
// или проверено.
async function openRoute(id) {
  detail.value = null
  result.value = null
  if (!id) return
  error.value = ''
  try {
    const assignment = await api(`/student/assignments/${id}`)
    if (assignment.submission?.status === 'completed') {
      result.value = await api(`/student/submissions/${assignment.submission.id}/result`)
    } else {
      detail.value = assignment
    }
  } catch (e) { error.value = e.message }
}

// Отправка идёт через состояние кнопки, а не молча: работа сдаётся один раз, и
// студенту нужно видеть, что нажатие поймано, дошло и закончилось успехом.
// Заодно это защита от второго клика, пока запрос в пути.
const submitState = ref('idle')
let submitTimer = null

async function submit() {
  if (submitState.value !== 'idle') return
  error.value = ''
  submitState.value = 'sending'
  try {
    await api(`/student/assignments/${detail.value.id}/submissions`, { method: 'POST', body: JSON.stringify({ source_url: sourceUrl.value }) })
    submitState.value = 'sent'
    await loadAssignments()
    // Уходим в список не сразу: без этой паузы галочка не успевает доиграть, и
    // отправка выглядит как ничем не объяснённый прыжок на другой экран.
    submitTimer = setTimeout(() => { submitState.value = 'idle'; emit('navigate', ROOT) }, 900)
  } catch (e) {
    error.value = e.message
    submitState.value = 'idle'
  }
}

// Сбор поведения при ответе на блиц. Объявлен студенту в telemetry_notice —
// скрытым он не бывает. Наружу уходят вид события, вопрос, смещение от открытия
// формы и ДЛИНА вставленного или набранного: ни текста вставки, ни содержимого
// буфера обмена здесь нет и появиться не должно.
const events = ref({})
const typed = {}
let openedAt = 0
let flushTimer = null

function record(sessionId, kind, questionId = null, size = 0) {
  if (!openedAt) return
  const bucket = events.value[sessionId] || (events.value[sessionId] = [])
  // Потолок совпадает с серверным: заклинивший обработчик не должен уметь
  // отправить мегабайт событий.
  if (bucket.length >= 5000) return
  bucket.push({ kind, question_id: questionId, offset_ms: Date.now() - openedAt, size })
}

function recordEverywhere(kind) {
  blitz.value.forEach(session => record(session.id, kind))
}

// Alt-Tab в другое приложение обычно даёт только blur, переключение вкладки —
// только visibilitychange. Слушаем оба и схлопываем на сервере, иначе половина
// уходов просто не наблюдается.
const onBlur = () => recordEverywhere('blur')
const onFocus = () => recordEverywhere('focus')
const onVisibility = () => recordEverywhere(document.hidden ? 'hidden' : 'visible')

function onBeforeInput(session, question, event) {
  // Вставка и перетаскивание считаются отдельно — иначе один и тот же текст
  // попал бы и в набранное, и во вставленное.
  if (event.inputType && (event.inputType.startsWith('insertFromPaste') || event.inputType.startsWith('insertFromDrop'))) return
  const key = `${session.id}:${question.id}`
  typed[key] = (typed[key] || 0) + (event.data ? event.data.length : 0)
}

function flushTyping() {
  Object.entries(typed).forEach(([key, size]) => {
    if (!size) return
    const [sessionId, questionId] = key.split(':')
    record(sessionId, 'input_batch', questionId, size)
    typed[key] = 0
  })
}

async function loadBlitz() {
  try {
    blitz.value = await api('/student/blitz')
    openedAt = Date.now()
    events.value = {}
  } catch (e) { error.value = e.message }
}

async function sendAnswers(session) {
  const payload = session.questions.map(q => ({ question_id: q.id, text: answers.value[q.id] || '' }))
  if (payload.some(x => !x.text.trim())) { error.value = 'Ответьте на все вопросы'; return }
  flushTyping()
  try {
    await api(`/student/blitz/${session.id}/answer`, {
      method: 'POST',
      body: JSON.stringify({ answers: payload, events: events.value[session.id] || [] }),
    })
    await loadBlitz()
  } catch (e) { error.value = e.message }
}

watch(() => props.active, value => {
  error.value = ''
  if (value === ROOT) loadAssignments()
  if (value === 'student-blitz') loadBlitz()
})
// Смена раздела и переход внутри раздела — разные события: возврат из карточки
// в список не меняет раздел, и перезагружать список ради него незачем.
watch(openedId, id => openRoute(id))

onMounted(() => {
  window.addEventListener('blur', onBlur)
  window.addEventListener('focus', onFocus)
  document.addEventListener('visibilitychange', onVisibility)
  flushTimer = setInterval(flushTyping, 1000)
  if (props.active === 'student-blitz') return loadBlitz()
  loadAssignments()
  return openRoute(openedId.value)
})

onUnmounted(() => {
  window.removeEventListener('blur', onBlur)
  window.removeEventListener('focus', onFocus)
  document.removeEventListener('visibilitychange', onVisibility)
  clearInterval(flushTimer)
  clearTimeout(submitTimer)
})
</script>

<template>
  <section v-if="active === 'student-assignments'">
    <template v-if="mode === 'list'">
      <div class="page-heading"><div><h1>Мои задания</h1></div><div class="progress-ring" :style="{ '--done': submittedRatio }" :title="`Сдано ${submittedCount} из ${assignments.length}`"><b>{{ submittedCount }}/{{ assignments.length }}</b><small>сдано</small></div></div>
      <!-- Ближайший срок наверху: список отсортирован по действию, а не по дате,
           и без этой строки «когда сгорит» пришлось бы вычитать из карточек. -->
      <button v-if="!loading && deadline" class="deadline-banner" :class="deadline.state" @click="openAssignment(deadline.assignment)">
        <span class="deadline-mark">⏳</span>
        <span><b>{{ deadline.text }}</b><small>{{ deadline.assignment.title }} · до {{ formatDate(deadline.assignment.deadline_at, true) }}</small></span>
        <strong class="row-arrow">→</strong>
      </button>
      <div v-if="loading" class="skeleton-list"><i v-for="x in 3" :key="x" /></div>
      <div v-else class="assignment-list">
        <button v-for="item in orderedAssignments" :key="item.id" class="assignment-row" @click="openAssignment(item)">
          <span class="assignment-icon">⌁</span>
          <span class="assignment-main"><small>{{ item.course }}</small><b>{{ item.title }}</b><em>Дедлайн {{ formatDate(item.deadline_at) }}</em></span>
          <StatusBadge v-if="item.submission" :status="item.submission.status" :labels="studentLabels" />
          <span v-else class="status status--new"><i />Не сдана</span>
          <span class="assignment-score"><b>{{ item.score ?? '—' }}</b><small v-if="item.max_score != null">из {{ item.max_score }}</small></span><strong class="row-arrow">→</strong>
        </button>
      </div>
    </template>

    <template v-else-if="mode === 'detail' && detail">
      <button class="back" @click="emit('navigate', 'student-assignments')">← Все задания</button>
      <div class="page-heading compact"><div><h1>{{ detail.title }}</h1><p>{{ detail.course }} · дедлайн {{ formatDate(detail.deadline_at, true) }}</p></div></div>
      <div class="two-columns">
        <article class="card prose-card"><h2>Условие</h2><MarkdownText :text="detail.statement" /><h2>Критерии оценки</h2><div v-for="criterion in detail.rubric" :key="criterion.key" class="criterion-short"><span>✓</span><b><MarkdownText inline :text="criterion.title" /></b><em>{{ criterion.max_score }} б.</em></div></article>
        <!-- Работа сдаётся один раз. По «назад» сюда можно вернуться уже после
             отправки — тогда вместо формы показываем, что с работой сейчас. -->
        <aside v-if="detail.submission" class="card submit-card"><span class="card-icon blue">✓</span><h2>Работа отправлена</h2><p>Отправлена {{ formatDate(detail.submission.submitted_at, true) }}. Повторная сдача по заданию не предусмотрена.</p><StatusBadge :status="detail.submission.status" :labels="studentLabels" /><small>Результат появится в списке заданий, когда ревьюер опубликует его</small></aside>
        <aside v-else class="card submit-card"><span class="card-icon blue">↗</span><h2>Сдать работу</h2><p>Укажите ссылку на публичный GitHub-репозиторий. После отправки мы сохраним снапшот.</p><label>Ссылка на репозиторий<input v-model="sourceUrl" placeholder="https://github.com/..." /></label><button class="primary full submit-button" :class="`is-${submitState}`" :disabled="submitState !== 'idle'" @click="submit"><span class="submit-face">Отправить на проверку</span><span class="submit-face" aria-hidden="true"><i class="submit-spinner" />Отправляем…</span><span class="submit-face" aria-hidden="true"><i class="submit-check">✓</i>Отправлено</span></button><small>После отправки ссылка будет зафиксирована</small></aside>
      </div>
    </template>

    <template v-else-if="mode === 'result' && result">
      <button class="back" @click="emit('navigate', 'student-assignments')">← Все задания</button>
      <div class="result-hero"><div><span class="eyebrow">РАБОТА ПРОВЕРЕНА</span><h1>{{ result.submission.assignment }}</h1><p>Ревьюер подтвердил результат и опубликовал обратную связь</p></div><div class="big-score"><b>{{ result.review.final_score }}</b><small v-if="result.review.max_score != null">из {{ result.review.max_score }}</small></div></div>
      <p v-if="result.review.late_penalty" class="penalty-note">⏱ {{ result.review.late_penalty_note }}. Балл по критериям — {{ Math.round((result.review.final_score + result.review.late_penalty) * 100) / 100 }}, за вычетом штрафа — {{ result.review.final_score }}.</p>
      <div class="two-columns result-grid"><article class="card"><h2>Результат по критериям</h2><div v-for="criterion in result.criteria" :key="criterion.title" class="result-item"><div><b><MarkdownText inline :text="criterion.title" /></b><MarkdownText :text="criterion.comment" /></div><strong>{{ criterion.score }} / {{ criterion.max_score }}</strong></div></article><aside class="card feedback-card"><span class="quote">“</span><h2>Обратная связь</h2><MarkdownText :text="result.review.final_feedback" /><div class="human-note"><span>✓</span>Подтверждено ревьюером</div></aside></div>
    </template>

    <!-- Работа по адресу ещё грузится. Кнопка «назад» здесь не для красоты:
         по битой ссылке загрузка кончится ошибкой, и из этого экрана нужен
         выход. -->
    <template v-else-if="mode === 'loading'">
      <button class="back" @click="emit('navigate', 'student-assignments')">← Все задания</button>
      <div v-if="!error" class="skeleton-list"><i v-for="x in 2" :key="x" /></div>
    </template>
    <p v-if="error" class="form-error floating">{{ error }}</p>
  </section>

  <section v-else-if="active === 'student-blitz'">
    <div class="page-heading"><div><h1>Вопросы от ревьюера</h1></div></div>
    <div v-if="!blitz.length" class="empty-state"><span>✓</span><h2>Сейчас вопросов нет</h2><p>Если ревьюеру понадобится уточнение, оно появится здесь.</p></div>
    <article v-for="session in blitz" :key="session.id" class="card blitz-card">
      <div class="blitz-head"><div><span class="eyebrow">{{ session.assignment }}</span><h2>Вопросы от ревьюера по работе</h2></div><span class="deadline-chip">До {{ formatDate(session.due_at, true) }}</span></div>
      <p class="neutral-note">Это обычная часть проверки: ответьте своими словами, опираясь на решение.</p>
      <details class="telemetry-notice"><summary>Что фиксируется, пока вы отвечаете</summary><p>{{ session.telemetry_notice }}</p></details>
      <label v-for="(question, index) in session.questions" :key="question.id" class="question-field">
        <b>{{ index + 1 }}. <MarkdownText inline :text="question.text" /></b>
        <textarea
          v-model="answers[question.id]"
          rows="3"
          placeholder="Ваш ответ"
          @focus="record(session.id, 'question_focus', question.id)"
          @blur="record(session.id, 'question_blur', question.id)"
          @beforeinput="onBeforeInput(session, question, $event)"
          @paste="record(session.id, 'paste', question.id, ($event.clipboardData && $event.clipboardData.getData('text') || '').length)"
          @drop="record(session.id, 'drop', question.id, ($event.dataTransfer && $event.dataTransfer.getData('text') || '').length)"
        />
      </label>
      <button class="primary" @click="sendAnswers(session)">Отправить ответы</button>
    </article>
    <p v-if="error" class="form-error floating">{{ error }}</p>
  </section>
</template>
