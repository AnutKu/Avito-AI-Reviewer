<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { aiStatusNames, api, formatDate } from '../../shared/api'
import MarkdownText from '../../shared/ui/MarkdownText.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'

const props = defineProps({ active: String })
const emit = defineEmits(['navigate'])
const queue = ref([])
const history = ref([])
const current = ref(null)
const error = ref('')
const notice = ref('')
const feedback = ref('')
const loading = ref(true)
const showAllQueue = ref(false)

// По умолчанию в очереди — работы, которые ждут действия ревьюера.
// «blitz_sent» = ждём ответа студента, взять в работу нельзя.
const ACTIONABLE = ['assigned', 'in_review', 'blitz_answered']
const visibleQueue = computed(() =>
  showAllQueue.value ? queue.value : queue.value.filter(i => ACTIONABLE.includes(i.status)),
)

async function loadQueue() {
  loading.value = true
  try { queue.value = await api('/reviewer/queue') }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function loadHistory() {
  try { history.value = await api('/reviewer/history') }
  catch (e) { error.value = e.message }
}

async function openReview(id) {
  try {
    current.value = await api(`/reviewer/submissions/${id}/review`)
    feedback.value = current.value.review.draft_feedback
    current.value.review.items.forEach(item => { item.editScore = item.final_score ?? item.ai_score; item.editComment = item.reviewer_comment })
    // Черновик мог остаться с прошлого захода: без этого он бы показался с
    // пустыми галочками, и «Отправить» ругалось бы на пустой выбор.
    picked.value = Object.fromEntries((current.value.blitz_draft?.questions || []).map(q => [q.id, true]))
    fraudVerdict.value = ''
    fraudRationale.value = ''
    emit('navigate', 'reviewer-review')
  } catch (e) { error.value = e.message }
}

async function decideItem(item, action) {
  try {
    await api(`/reviewer/review-items/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ action, final_score: action === 'changed' ? Number(item.editScore) : null, comment: item.editComment || '' }),
    })
    item.reviewer_action = action
    item.final_score = action === 'accepted' ? item.ai_score : action === 'rejected' ? 0 : Number(item.editScore)
    notice.value = 'Решение сохранено'
  } catch (e) { error.value = e.message }
}

async function decideSignal(signal, decision) {
  try { await api(`/reviewer/signals/${signal.id}`, { method: 'PATCH', body: JSON.stringify({ decision }) }); signal.reviewer_decision = decision }
  catch (e) { error.value = e.message }
}

async function rewrite() {
  try {
    const result = await api(`/reviewer/reviews/${current.value.review.id}/rewrite-feedback`, { method: 'POST', body: JSON.stringify({ text: feedback.value }) })
    feedback.value = result.suggestion
    notice.value = `Z.AI ${result.model} предложил новый вариант — проверьте его перед публикацией`
  } catch (e) { error.value = e.message }
}

async function rerun() {
  try {
    await api(`/reviewer/reviews/${current.value.review.id}/rerun`, { method: 'POST' })
    current.value.review.ai_status = 'running'
    notice.value = 'Z.AI начал повторную проверку'
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 2000))
      const updated = await api(`/reviewer/submissions/${current.value.submission.id}/review`)
      current.value = updated
      if (updated.review.ai_status !== 'running' && updated.review.ai_status !== 'pending') {
        feedback.value = updated.review.draft_feedback
        updated.review.items.forEach(item => { item.editScore = item.final_score ?? item.ai_score; item.editComment = item.reviewer_comment })
        notice.value = updated.review.ai_status === 'ready' ? 'Проверка Z.AI готова' : ''
        if (updated.review.ai_status === 'failed') error.value = updated.review.ai_error || 'Проверка Z.AI завершилась ошибкой'
        break
      }
    }
  } catch (e) { error.value = e.message }
}

const CATEGORY_TITLES = {
  no_signs: 'Признаков не наблюдается',
  tool_assisted: 'Похоже на использование AI как инструмента',
  likely_generated: 'Похоже на сгенерированное решение',
}

const CONFIDENCE_TITLES = {
  high: 'Высокая — было что наблюдать',
  medium: 'Средняя — часть признаков недоступна',
  low: 'Низкая — наблюдать почти нечего',
}

async function rerunDetection() {
  try {
    await api(`/reviewer/reviews/${current.value.review.id}/detect`, { method: 'POST' })
    current.value.detection = { ...(current.value.detection || {}), status: 'running' }
    notice.value = 'Проверка на признаки AI перезапущена'
  } catch (e) { error.value = e.message }
}

const QUESTION_TYPES = {
  explain_choice: 'обоснование выбора',
  what_if: 'что изменится, если',
  change_solution: 'доработка решения',
  trace_output: 'что окажется в выводе',
}

const ANSWER_VERDICTS = {
  consistent: 'Согласуется с решением',
  partial: 'Частично, поверхностно',
  inconsistent: 'Расходится с решением',
  empty: 'Ответа нет',
}

const FRAUD_VERDICTS = {
  no_signs: 'Признаков нет',
  tool_assisted: 'AI как инструмент — допустимо',
  misconduct: 'Недобросовестность',
  inconclusive: 'Данных недостаточно',
}

const blitzCount = ref(5)
const picked = ref({})
const busyBlitz = ref(false)
const fraudVerdict = ref('')
const fraudRationale = ref('')

function seconds(ms) { return Math.round((ms || 0) / 100) / 10 }

function answerText(questionId) {
  const found = (current.value.blitz?.answers || []).find(a => a.question_id === questionId)
  return found ? found.text : ''
}

function assessmentFor(questionId) {
  return (current.value.blitz?.ai_analysis?.assessments || []).find(a => a.question_id === questionId)
}

function statsFor(questionId) {
  return (current.value.blitz?.telemetry?.questions || []).find(q => q.question_id === questionId)
}

async function suggestBlitz() {
  busyBlitz.value = true
  try {
    const draft = await api(`/reviewer/reviews/${current.value.review.id}/blitz/suggest`, { method: 'POST', body: JSON.stringify({ count: Number(blitzCount.value) }) })
    current.value.blitz_draft = { ...draft, telemetry: null }
    picked.value = Object.fromEntries(draft.questions.map(q => [q.id, true]))
    notice.value = `Z.AI составил вопросы по этой работе: ${draft.questions.length}`
  } catch (e) { error.value = e.message }
  finally { busyBlitz.value = false }
}

async function sendBlitz() {
  const questionIds = current.value.blitz_draft.questions.map(q => q.id).filter(id => picked.value[id])
  if (!questionIds.length) { error.value = 'Выберите хотя бы один вопрос'; return }
  try {
    await api(`/reviewer/reviews/${current.value.review.id}/blitz`, {
      method: 'POST',
      body: JSON.stringify({ session_id: current.value.blitz_draft.id, question_ids: questionIds }),
    })
    notice.value = 'Вопросы отправлены студенту на 48 часов'
    current.value = await api(`/reviewer/submissions/${current.value.submission.id}/review`)
  } catch (e) { error.value = e.message }
}

async function saveFraudDecision() {
  try {
    await api(`/reviewer/reviews/${current.value.review.id}/fraud-decision`, {
      method: 'POST',
      body: JSON.stringify({ verdict: fraudVerdict.value, rationale: fraudRationale.value, blitz_id: current.value.blitz?.id || null }),
    })
    notice.value = 'Решение зафиксировано. На балл оно не влияет.'
    fraudRationale.value = ''
    fraudVerdict.value = ''
    current.value = await api(`/reviewer/submissions/${current.value.submission.id}/review`)
  } catch (e) { error.value = e.message }
}

async function complete() {
  try {
    const result = await api(`/reviewer/reviews/${current.value.review.id}/complete`, { method: 'POST', body: JSON.stringify({ feedback: feedback.value }) })
    notice.value = `Ревью опубликовано · ${result.score}${result.max_score != null ? ` из ${result.max_score}` : ''}`
    current.value.submission.status = 'completed'
  } catch (e) { error.value = e.message }
}

// Что действительно требует внимания на этой работе. Раньше блок висел всегда
// с постоянным текстом и советовал проверить то, чего в работе могло не быть.
const snapshotFiles = computed(() => current.value?.snapshot?.parsed_facts?.files || [])
const needsAttention = computed(() => {
  const items = current.value?.review?.items || []
  const unsure = items.filter(i => i.confidence === 'low' && i.reviewer_action === 'pending')
  const signals = (current.value?.review?.signals || []).filter(s => s.reviewer_decision === 'pending')
  const notes = []
  if (unsure.length) notes.push(`критериев с низкой уверенностью: ${unsure.length}`)
  if (signals.length) notes.push(`нерешённых AI-сигналов: ${signals.length}`)
  if (current.value?.review?.ai_status === 'failed') notes.push('AI-разбор не выполнен')
  return notes
})

watch(() => props.active, value => {
  error.value = ''
  if (value === 'reviewer-queue') loadQueue()
  if (value === 'reviewer-history') loadHistory()
})
onMounted(() => { props.active === 'reviewer-history' ? loadHistory() : loadQueue() })
</script>

<template>
  <section v-if="active === 'reviewer-queue'">
    <div class="page-heading"><div><h1>Моя очередь</h1></div><div class="queue-summary"><b>{{ visibleQueue.length }}</b><small>ждут действия</small></div></div>
    <div class="filter-row">
      <label class="chk"><input type="checkbox" v-model="showAllQueue" /> Показывать все актуальные работы</label>
      <span />
      <small v-if="!showAllQueue && queue.length > visibleQueue.length">скрыто «ждёт ответа студента»: {{ queue.length - visibleQueue.length }}</small>
    </div>
    <div class="table-card">
      <div class="table-row table-head"><span>Студент и работа</span><span>Статус</span><span>AI-разбор</span><span>Срок</span><span /></div>
      <button v-for="item in visibleQueue" :key="item.id" class="table-row" :disabled="item.status === 'blitz_sent'" @click="item.status !== 'blitz_sent' && openReview(item.id)">
        <span class="student-cell"><i>{{ item.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ item.student }}</b><small>{{ item.assignment }}</small></span></span>
        <StatusBadge :status="item.status" />
        <span class="ai-ready" :class="[item.ai_status, { demo: item.is_demo }]"><i>✦</i>{{ item.is_demo ? 'Демо-фикстура' : aiStatusNames[item.ai_status] || item.ai_status }}</span>
        <span :class="{ danger: item.deadline_risk }"><b>{{ formatDate(item.deadline_at, true) }}</b><small v-if="item.deadline_risk">Риск просрочки</small></span>
        <strong class="row-arrow">{{ item.status === 'blitz_sent' ? '⏳' : '→' }}</strong>
      </button>
      <div v-if="!loading && !visibleQueue.length" class="empty-mini padded">{{ queue.length ? 'Все работы в очереди ждут ответа студента — включите «показывать все актуальные»' : 'Очередь пуста' }}</div>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-history'">
    <div class="page-heading"><div><h1>История</h1></div><div class="queue-summary"><b>{{ history.length }}</b><small>всего работ</small></div></div>
    <div class="table-card">
      <div class="table-row table-head"><span>Студент и работа</span><span>Статус</span><span>Балл</span><span>Сдано</span><span /></div>
      <button v-for="item in history" :key="item.id" class="table-row" :disabled="!item.is_current || item.status === 'completed'" @click="item.is_current && item.status !== 'completed' && openReview(item.id)">
        <span class="student-cell"><i>{{ item.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ item.student }}</b><small>{{ item.assignment }}</small></span></span>
        <StatusBadge :status="item.status" />
        <span><b>{{ item.final_score ?? '—' }}</b><small v-if="item.final_score != null && item.max_score != null">из {{ item.max_score }}</small></span>
        <span><b>{{ formatDate(item.submitted_at, true) }}</b><small v-if="item.completed_at">проверено {{ formatDate(item.completed_at, true) }}</small></span>
        <strong class="row-arrow">{{ item.is_current && item.status !== 'completed' ? '→' : '' }}</strong>
      </button>
      <div v-if="!history.length" class="empty-mini padded">Здесь появятся все проверенные вами работы</div>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-review' && current" class="review-page">
    <button class="back" @click="emit('navigate', 'reviewer-queue')">← Вернуться в очередь</button>
    <div class="review-title"><div><h1>{{ current.submission.student }}</h1><p>{{ current.submission.assignment }} · сдано {{ formatDate(current.submission.submitted_at, true) }}</p></div><StatusBadge :status="current.submission.status" /></div>
    <div v-if="notice" class="toast-success">✓ {{ notice }}<button @click="notice = ''">×</button></div>
    <div v-if="error" class="toast-error">{{ error }}<button @click="error = ''">×</button></div>
    <div class="review-workspace">
      <article class="notebook-panel"><header><div class="file-tab" :title="snapshotFiles.join('\n')"><span>◇</span>{{ snapshotFiles[0] || 'Снапшот решения' }}<i v-if="snapshotFiles.length > 1">+{{ snapshotFiles.length - 1 }}</i></div><a :href="current.submission.source_url" target="_blank">GitHub ↗</a></header><pre>{{ current.snapshot.content }}</pre><footer><span>Снапшот сохранён {{ formatDate(current.snapshot.fetched_at, true) }}</span><span>Повторных запросов к GitHub нет</span></footer></article>
      <aside class="review-panel">
        <div class="ai-summary"><span class="spark">✦</span><div><span class="eyebrow">AI-РАЗБОР · {{ current.review.is_demo ? 'ДЕМО-ФИКСТУРА' : 'Z.AI' }}</span><b><MarkdownText v-if="current.review.summary" inline :text="current.review.summary" /><template v-else>{{ current.review.ai_status === 'running' ? 'Проверка выполняется…' : 'Результат пока не сформирован' }}</template></b><small>Модель {{ current.review.model }}</small></div><button class="ai-rerun" :disabled="current.review.is_demo || current.review.ai_status === 'running' || current.submission.status === 'completed'" @click="rerun">↻ Перезапустить</button></div>
        <div v-if="current.review.is_demo" class="fixture-note">Эта карточка — неизменяемый демонстрационный пример. Новые сдачи проверяются реальной моделью Z.AI.</div>
        <div v-if="current.review.ai_status === 'failed'" class="toast-error">Z.AI: {{ current.review.ai_error }}</div>
        <section v-if="needsAttention.length" class="attention-panel"><h3><span>!</span> Панель внимания</h3><p>{{ needsAttention.join(' · ') }}</p></section>

        <section v-if="current.detection" class="review-section detection-panel">
          <div class="section-title"><h2>Признаки использования AI</h2><span>На балл не влияет</span></div>
          <p v-if="current.detection.status === 'running'" class="muted">Проверка выполняется…</p>
          <p v-else-if="current.detection.status === 'failed'" class="toast-error">Проверка не выполнена: {{ current.detection.error }}</p>
          <template v-else>
            <div class="detection-head">
              <div class="detection-score" :class="current.detection.reportable ? current.detection.category : 'unknown'">
                <b>{{ current.detection.reportable ? current.detection.score : '—' }}</b><small>{{ current.detection.reportable ? 'из 100' : 'нет данных' }}</small>
              </div>
              <div class="detection-meta">
                <b>{{ current.detection.reportable ? CATEGORY_TITLES[current.detection.category] : 'Признаков недостаточно для оценки' }}</b>
                <span class="confidence" :class="current.detection.confidence">{{ CONFIDENCE_TITLES[current.detection.confidence] }}</span>
                <small v-if="current.detection.reportable">Индекс признаков, а не вероятность: 30 — ничего не наблюдали, ниже — следы ручной работы, выше — следы генерации. Считается детерминированно, раскладку видно ниже.</small>
                <small v-else>Покрытие {{ Math.round(current.detection.coverage * 100) }}% — короткая работа или обрезанный снапшот. Число не показываем: «мало данных» и «мало признаков» дают одинаково низкую отметку.</small>
              </div>
              <button class="ai-rerun" :disabled="current.submission.status === 'completed'" @click="rerunDetection">↻ Перепроверить</button>
            </div>
            <MarkdownText v-if="current.detection.summary" class="detection-summary" :text="current.detection.summary" />
            <div v-for="item in current.detection.contributions" :key="item.key" class="detection-row" :class="item.direction > 0 ? 'up' : 'down'">
              <span class="detection-points">{{ item.points > 0 ? '+' : '' }}{{ item.points }}</span>
              <span class="detection-body">
                <b>{{ item.title }}</b>
                <small>вес {{ item.weight }} × величина {{ item.magnitude }}{{ item.direction > 0 ? '' : ' · свидетельство ручной работы' }}</small>
                <em v-for="proof in item.evidence" :key="proof.quote">«{{ proof.quote }}» <i>{{ proof.anchor }}</i></em>
              </span>
            </div>
            <div v-if="current.detection.reportable && current.detection.score >= current.detection.blitz_threshold" class="attention-panel">
              <h3><span>?</span> Стоит задать вопросы по работе</h3>
              <p>Индекс выше порога {{ current.detection.blitz_threshold }}. Это повод проверить понимание, а не снизить балл: решение о баллах принимаете вы и только по критериям.</p>
            </div>
            <details v-if="current.detection.limitations"><summary>Ограничения метода</summary><MarkdownText :text="current.detection.limitations" /></details>
          </template>
        </section>
        <section class="review-section"><div class="section-title"><h2>Критерии</h2><span>{{ current.review.items.filter(i => i.reviewer_action !== 'pending').length }} / {{ current.review.items.length }} решено</span></div>
          <article v-for="item in current.review.items" :key="item.id" class="review-item" :class="`decision-${item.reviewer_action}`">
            <header><div><span class="confidence" :class="item.confidence">{{ item.confidence === 'high' ? 'Высокая' : item.confidence === 'medium' ? 'Средняя' : 'Низкая' }}</span><h3>{{ item.criterion_title }}</h3></div><strong>{{ item.ai_score }} <small>/ {{ item.max_score }}</small></strong></header>
            <MarkdownText :text="item.recommendation" /><div class="evidence" v-for="proof in item.evidence" :key="proof.quote"><span>“</span><code>{{ proof.quote }}</code><small>{{ proof.anchor }}</small></div>
            <div v-if="item.reviewer_action === 'pending'" class="decision-box"><div class="edit-inline"><label>Ваш балл<input v-model="item.editScore" type="number" min="0" :max="item.max_score" step="0.5" /></label><label>Комментарий<input v-model="item.editComment" placeholder="Необязательно" /></label></div><div class="decision-actions"><button class="accept" @click="decideItem(item, 'accepted')">✓ Принять</button><button @click="decideItem(item, 'changed')">Изменить</button><button class="reject" @click="decideItem(item, 'rejected')">Отклонить</button></div></div>
            <div v-else class="decision-done">✓ Решение: {{ { accepted: 'принято', changed: 'изменено', rejected: 'отклонено' }[item.reviewer_action] }} <button @click="item.reviewer_action = 'pending'">Изменить</button></div>
          </article>
        </section>
        <section class="review-section"><div class="section-title"><h2>AI-сигнал</h2><span>Не влияет на балл</span></div><article v-for="signal in current.review.signals" :key="signal.id" class="signal-card"><header><span class="signal-icon">⌁</span><div><small>{{ signal.kind === 'ai_use' ? 'ВОЗМОЖНОЕ ИСПОЛЬЗОВАНИЕ AI' : 'РИСК ПОНИМАНИЯ' }}</small><h3><MarkdownText inline :text="signal.summary" /></h3></div><span class="confidence" :class="signal.level">{{ signal.level }}</span></header><ul><li v-for="ground in signal.grounds" :key="ground"><MarkdownText inline :text="ground" /></li></ul><details><summary>Ограничения метода</summary><MarkdownText :text="signal.limitations" /></details><div v-if="signal.reviewer_decision === 'pending'" class="decision-actions"><button class="accept" @click="decideSignal(signal, 'confirmed')">Подтвердить сигнал</button><button @click="decideSignal(signal, 'dismissed')">Отклонить</button></div><div v-else class="decision-done">Решение сохранено: {{ signal.reviewer_decision }}</div></article></section>
        <section v-if="current.submission.status === 'in_review'" class="review-section">
          <div class="section-title"><h2>Дополнительные вопросы</h2><span>До 48 часов на ответ</span></div>
          <p class="muted">Вопросы составляются по этому решению — на них нельзя ответить, не открыв работу. Студент не увидит упоминаний AI-сигнала.</p>
          <div class="blitz-generate">
            <label>Сколько вопросов<input v-model="blitzCount" type="number" min="1" max="8" /></label>
            <button class="secondary" :disabled="busyBlitz" @click="suggestBlitz">{{ busyBlitz ? 'Z.AI составляет…' : '✦ Составить вопросы' }}</button>
          </div>
          <template v-if="current.blitz_draft">
            <label v-for="question in current.blitz_draft.questions" :key="question.id" class="question-check">
              <input v-model="picked[question.id]" type="checkbox" />
              <span>
                <b><MarkdownText inline :text="question.text" /></b>
                <small>{{ QUESTION_TYPES[question.type] || question.type }} · {{ question.anchor }}</small>
                <em class="expected">Понимающий ответ покажет: {{ question.expected_points.join('; ') }}</em>
              </span>
            </label>
            <p class="muted small">Подсказки «понимающий ответ покажет» студенту не отправляются.</p>
            <button class="secondary full" @click="sendBlitz">Отправить выбранные вопросы</button>
          </template>
        </section>

        <section v-if="current.blitz && current.blitz.status !== 'draft'" class="review-section blitz-review">
          <div class="section-title"><h2>Блиц-опрос</h2><span>{{ current.blitz.status === 'sent' ? 'Ожидаем ответа' : current.blitz.status === 'expired' ? 'Срок истёк' : 'Ответ получен' }}</span></div>
          <p v-if="current.blitz.status === 'sent'" class="muted">Отправлено {{ formatDate(current.blitz.sent_at, true) }}, срок до {{ formatDate(current.blitz.due_at, true) }}.</p>
          <p v-else-if="current.blitz.status === 'expired'" class="muted">Студент не ответил до {{ formatDate(current.blitz.due_at, true) }}. Молчание — не признак нечестности: причины бывают любые.</p>
          <template v-else>
            <p v-if="current.blitz.ai_analysis?.status === 'running' || current.blitz.ai_analysis?.status === 'pending'" class="muted">Разбор ответов выполняется…</p>
            <p v-else-if="current.blitz.ai_analysis?.status === 'failed'" class="toast-error">Разбор не выполнен: {{ current.blitz.ai_analysis.error }}</p>
            <MarkdownText v-else-if="current.blitz.ai_analysis?.summary" class="detection-summary" :text="current.blitz.ai_analysis.summary" />

            <article v-for="question in current.blitz.questions" :key="question.id" class="blitz-answer">
              <header><b><MarkdownText inline :text="question.text" /></b><span v-if="assessmentFor(question.id)" class="confidence" :class="assessmentFor(question.id).verdict === 'consistent' ? 'high' : assessmentFor(question.id).verdict === 'partial' ? 'medium' : 'low'">{{ ANSWER_VERDICTS[assessmentFor(question.id).verdict] }}</span></header>
              <blockquote>{{ answerText(question.id) || '— ответа нет —' }}</blockquote>
              <MarkdownText v-if="assessmentFor(question.id)" class="muted" :text="assessmentFor(question.id).note" />
              <div v-for="ground in (assessmentFor(question.id)?.grounds || [])" :key="ground" class="evidence"><span>“</span><code>{{ ground }}</code></div>
              <div v-if="statsFor(question.id)" class="telemetry-row">
                <span>{{ seconds(statsFor(question.id).active_ms) }} с за ответом</span>
                <span>набрано {{ statsFor(question.id).typed_chars }}</span>
                <span>вставлено {{ statsFor(question.id).pasted_chars }}</span>
                <span v-if="statsFor(question.id).away_count">уходов {{ statsFor(question.id).away_count }} · {{ seconds(statsFor(question.id).longest_away_ms) }} с</span>
                <b v-for="flag in statsFor(question.id).flags" :key="flag" class="telemetry-flag">{{ current.blitz.telemetry_titles[flag] }}</b>
              </div>
            </article>

            <div v-if="current.blitz.telemetry" class="telemetry-note">
              <template v-if="current.blitz.telemetry.collected">
                Данные о поведении собраны на устройстве студента и не являются доверенным источником: их можно подделать, отключив скрипт. Отсутствие пометок не доказывает честность, наличие — нечестность.
                <b v-for="flag in current.blitz.telemetry.flags" :key="flag" class="telemetry-flag">{{ current.blitz.telemetry_titles[flag] }}</b>
              </template>
              <template v-else>Данные о поведении не собраны — скрипт был отключён или недоступен. Это не наблюдение о студенте.</template>
            </div>
          </template>
        </section>

        <section v-if="current.detection" class="review-section fraud-panel">
          <div class="section-title"><h2>Решение по AI-фроду</h2><span>На балл не влияет</span></div>
          <article v-for="row in current.fraud_decisions" :key="row.decided_at" class="decision-done block">
            <b>{{ FRAUD_VERDICTS[row.verdict] }}</b><small>{{ formatDate(row.decided_at, true) }}</small><p>{{ row.rationale }}</p>
          </article>
          <p class="muted">Решение принимаете вы. Индекс и ответы на вопросы — материал для него, а не он сам. Балл складывается из решений по критериям и от этого вердикта не зависит.</p>
          <div class="fraud-actions">
            <label v-for="(title, key) in FRAUD_VERDICTS" :key="key" class="fraud-option"><input v-model="fraudVerdict" type="radio" :value="key" />{{ title }}</label>
          </div>
          <textarea v-model="fraudRationale" rows="3" placeholder="Обоснование: на что именно вы опирались (не менее 20 символов)" />
          <button class="secondary full" :disabled="!fraudVerdict || fraudRationale.trim().length < 20" @click="saveFraudDecision">Зафиксировать решение</button>
        </section>
        <section class="review-section feedback-editor"><div class="section-title"><h2>Обратная связь студенту</h2><span>Отправится только после подтверждения</span></div><textarea v-model="feedback" rows="7" /><div class="editor-actions"><button class="secondary" @click="rewrite">✦ Переформулировать</button><button class="primary" :disabled="current.submission.status === 'blitz_sent' || current.submission.status === 'completed'" @click="complete">Подтвердить и опубликовать</button></div></section>
      </aside>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-review'" class="empty-state"><span>⌁</span><h2>Выберите работу из очереди</h2><button class="primary" @click="emit('navigate', 'reviewer-queue')">Открыть очередь</button></section>
</template>
