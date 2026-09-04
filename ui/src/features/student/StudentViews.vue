<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { api, formatDate } from '../../shared/api'
import StatusBadge from '../../shared/ui/StatusBadge.vue'

const props = defineProps({ active: String })
const loading = ref(true)
const error = ref('')
const assignments = ref([])
const detail = ref(null)
const result = ref(null)
const blitz = ref([])
const mode = ref('list')
const sourceUrl = ref('https://github.com/student/mlflow-homework')
const answers = ref({})

async function loadAssignments() {
  loading.value = true
  try { assignments.value = await api('/student/assignments') }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function openAssignment(item) {
  error.value = ''
  if (item.submission?.status === 'completed') {
    result.value = await api(`/student/submissions/${item.submission.id}/result`)
    mode.value = 'result'
  } else {
    detail.value = await api(`/student/assignments/${item.id}`)
    mode.value = 'detail'
  }
}

async function submit() {
  try {
    await api(`/student/assignments/${detail.value.id}/submissions`, { method: 'POST', body: JSON.stringify({ source_url: sourceUrl.value }) })
    await loadAssignments()
    mode.value = 'list'
  } catch (e) { error.value = e.message }
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
  if (value === 'student-assignments') { mode.value = 'list'; loadAssignments() }
  if (value === 'student-blitz') loadBlitz()
})
onMounted(() => {
  window.addEventListener('blur', onBlur)
  window.addEventListener('focus', onFocus)
  document.addEventListener('visibilitychange', onVisibility)
  flushTimer = setInterval(flushTyping, 1000)
  return props.active === 'student-blitz' ? loadBlitz() : loadAssignments()
})

onUnmounted(() => {
  window.removeEventListener('blur', onBlur)
  window.removeEventListener('focus', onFocus)
  document.removeEventListener('visibilitychange', onVisibility)
  clearInterval(flushTimer)
})
</script>

<template>
  <section v-if="active === 'student-assignments'">
    <template v-if="mode === 'list'">
      <div class="page-heading"><div><span class="eyebrow">МОЁ ОБУЧЕНИЕ</span><h1>Мои задания</h1><p>Здесь собраны задания, статусы проверки и обратная связь</p></div><div class="progress-ring"><b>1/1</b><small>сдано</small></div></div>
      <div v-if="loading" class="skeleton-list"><i v-for="x in 3" :key="x" /></div>
      <div v-else class="assignment-list">
        <button v-for="item in assignments" :key="item.id" class="assignment-row" @click="openAssignment(item)">
          <span class="assignment-icon">⌁</span>
          <span class="assignment-main"><small>{{ item.course }}</small><b>{{ item.title }}</b><em>Дедлайн {{ formatDate(item.deadline_at) }}</em></span>
          <StatusBadge v-if="item.submission" :status="item.submission.status" />
          <span v-else class="status status--new"><i />Не сдана</span>
          <span class="assignment-score"><b>{{ item.score ?? '—' }}</b><small>из 10</small></span><strong class="row-arrow">→</strong>
        </button>
      </div>
    </template>

    <template v-else-if="mode === 'detail' && detail">
      <button class="back" @click="mode = 'list'">← Все задания</button>
      <div class="page-heading compact"><div><span class="eyebrow">ЗАДАНИЕ</span><h1>{{ detail.title }}</h1><p>{{ detail.course }} · дедлайн {{ formatDate(detail.deadline_at, true) }}</p></div></div>
      <div class="two-columns">
        <article class="card prose-card"><h2>Условие</h2><p>{{ detail.statement }}</p><h2>Критерии оценки</h2><div v-for="criterion in detail.rubric" :key="criterion.key" class="criterion-short"><span>✓</span><b>{{ criterion.title }}</b><em>{{ criterion.max_score }} б.</em></div></article>
        <aside class="card submit-card"><span class="card-icon blue">↗</span><h2>Сдать работу</h2><p>Укажите ссылку на публичный GitHub-репозиторий. После отправки мы сохраним снапшот.</p><label>Ссылка на репозиторий<input v-model="sourceUrl" placeholder="https://github.com/..." /></label><button class="primary full" @click="submit">Отправить на проверку</button><small>После отправки ссылка будет зафиксирована</small></aside>
      </div>
    </template>

    <template v-else-if="mode === 'result' && result">
      <button class="back" @click="mode = 'list'">← Все задания</button>
      <div class="result-hero"><div><span class="eyebrow">РАБОТА ПРОВЕРЕНА</span><h1>{{ result.submission.assignment }}</h1><p>Ревьюер подтвердил результат и опубликовал обратную связь</p></div><div class="big-score"><b>{{ result.review.final_score }}</b><small>из 10</small></div></div>
      <div class="two-columns result-grid"><article class="card"><h2>Результат по критериям</h2><div v-for="criterion in result.criteria" :key="criterion.title" class="result-item"><div><b>{{ criterion.title }}</b><p>{{ criterion.comment }}</p></div><strong>{{ criterion.score }} / {{ criterion.max_score }}</strong></div></article><aside class="card feedback-card"><span class="quote">“</span><h2>Обратная связь</h2><p>{{ result.review.final_feedback }}</p><div class="human-note"><span>✓</span>Подтверждено ревьюером</div></aside></div>
    </template>
    <p v-if="error" class="form-error floating">{{ error }}</p>
  </section>

  <section v-else-if="active === 'student-blitz'">
    <div class="page-heading"><div><span class="eyebrow">МОЁ ОБУЧЕНИЕ</span><h1>Дополнительные вопросы</h1><p>Вопросы помогают уточнить детали вашей работы и не влияют на оценку автоматически</p></div></div>
    <div v-if="!blitz.length" class="empty-state"><span>✓</span><h2>Сейчас вопросов нет</h2><p>Если ревьюеру понадобится уточнение, оно появится здесь.</p></div>
    <article v-for="session in blitz" :key="session.id" class="card blitz-card">
      <div class="blitz-head"><div><span class="eyebrow">{{ session.assignment }}</span><h2>Дополнительные вопросы по работе</h2></div><span class="deadline-chip">До {{ formatDate(session.due_at, true) }}</span></div>
      <p class="neutral-note">Это обычная часть проверки: ответьте своими словами, опираясь на решение.</p>
      <details class="telemetry-notice"><summary>Что фиксируется, пока вы отвечаете</summary><p>{{ session.telemetry_notice }}</p></details>
      <label v-for="(question, index) in session.questions" :key="question.id" class="question-field">
        <b>{{ index + 1 }}. {{ question.text }}</b>
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
