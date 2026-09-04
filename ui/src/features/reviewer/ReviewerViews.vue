<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, formatDate } from '../../shared/api'
import StatusBadge from '../../shared/ui/StatusBadge.vue'

const props = defineProps({ active: String })
const emit = defineEmits(['navigate'])
const queue = ref([])
const current = ref(null)
const error = ref('')
const notice = ref('')
const feedback = ref('')
const loading = ref(true)

async function loadQueue() {
  loading.value = true
  try { queue.value = await api('/reviewer/queue') }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function openReview(id) {
  try {
    current.value = await api(`/reviewer/submissions/${id}/review`)
    feedback.value = current.value.review.draft_feedback
    current.value.review.items.forEach(item => { item.editScore = item.final_score ?? item.ai_score; item.editComment = item.reviewer_comment })
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

async function sendBlitz() {
  try {
    const questions = current.value.suggested_questions
    await api(`/reviewer/reviews/${current.value.review.id}/blitz`, { method: 'POST', body: JSON.stringify({ questions }) })
    notice.value = 'Вопросы отправлены студенту на 48 часов'
    current.value.submission.status = 'blitz_sent'
  } catch (e) { error.value = e.message }
}

async function complete() {
  try {
    const result = await api(`/reviewer/reviews/${current.value.review.id}/complete`, { method: 'POST', body: JSON.stringify({ feedback: feedback.value }) })
    notice.value = `Ревью опубликовано · ${result.score} из 10`
    current.value.submission.status = 'completed'
  } catch (e) { error.value = e.message }
}

watch(() => props.active, value => { error.value = ''; if (value === 'reviewer-queue') loadQueue() })
onMounted(loadQueue)
</script>

<template>
  <section v-if="active === 'reviewer-queue'">
    <div class="page-heading"><div><span class="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</span><h1>Моя очередь</h1><p>Работы, назначенные после подтверждения методистом</p></div><div class="queue-summary"><b>{{ queue.length }}</b><small>активных работ</small></div></div>
    <div class="filter-row"><button class="chip active">Все · {{ queue.length }}</button><button class="chip">Новые</button><button class="chip">В работе</button><button class="chip">С риском срока</button><span /><label>Сначала срочные⌄</label></div>
    <div class="table-card">
      <div class="table-row table-head"><span>Студент и работа</span><span>Статус</span><span>AI-разбор</span><span>Срок</span><span /></div>
      <button v-for="item in queue" :key="item.id" class="table-row" @click="openReview(item.id)">
        <span class="student-cell"><i>{{ item.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ item.student }}</b><small>{{ item.assignment }}</small></span></span>
        <StatusBadge :status="item.status" />
        <span class="ai-ready" :class="[item.ai_status, { demo: item.is_demo }]"><i>✦</i>{{ item.is_demo ? 'Демо-фикстура' : item.ai_status === 'ready' ? 'Готов' : item.ai_status }}</span>
        <span :class="{ danger: item.deadline_risk }"><b>{{ formatDate(item.deadline_at, true) }}</b><small v-if="item.deadline_risk">Риск просрочки</small></span>
        <strong class="row-arrow">→</strong>
      </button>
      <div v-if="!loading && !queue.length" class="empty-mini padded">Очередь пуста</div>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-review' && current" class="review-page">
    <button class="back" @click="emit('navigate', 'reviewer-queue')">← Вернуться в очередь</button>
    <div class="review-title"><div><span class="eyebrow">РЕВЬЮ РАБОТЫ</span><h1>{{ current.submission.student }}</h1><p>{{ current.submission.assignment }} · сдано {{ formatDate(current.submission.submitted_at, true) }}</p></div><StatusBadge :status="current.submission.status" /></div>
    <div v-if="notice" class="toast-success">✓ {{ notice }}<button @click="notice = ''">×</button></div>
    <div v-if="error" class="toast-error">{{ error }}<button @click="error = ''">×</button></div>
    <div class="review-workspace">
      <article class="notebook-panel"><header><div class="file-tab"><span>◇</span>solution.ipynb</div><a :href="current.submission.source_url" target="_blank">GitHub ↗</a></header><pre>{{ current.snapshot.content }}</pre><footer><span>Снапшот сохранён {{ formatDate(current.snapshot.fetched_at, true) }}</span><span>Повторных запросов к GitHub нет</span></footer></article>
      <aside class="review-panel">
        <div class="ai-summary"><span class="spark">✦</span><div><span class="eyebrow">AI-РАЗБОР · {{ current.review.is_demo ? 'ДЕМО-ФИКСТУРА' : 'Z.AI' }}</span><b>{{ current.review.summary || (current.review.ai_status === 'running' ? 'Проверка выполняется…' : 'Результат пока не сформирован') }}</b><small>Модель {{ current.review.model }}</small></div><button class="ai-rerun" :disabled="current.review.is_demo || current.review.ai_status === 'running' || current.submission.status === 'completed'" @click="rerun">↻ Перезапустить</button></div>
        <div v-if="current.review.is_demo" class="fixture-note">Эта карточка — неизменяемый демонстрационный пример. Новые сдачи проверяются реальной моделью Z.AI.</div>
        <div v-if="current.review.ai_status === 'failed'" class="toast-error">Z.AI: {{ current.review.ai_error }}</div>
        <section class="attention-panel"><h3><span>!</span> Панель внимания</h3><p>Проверьте критерии с низкой уверенностью и отдельный AI-сигнал.</p></section>
        <section class="review-section"><div class="section-title"><h2>Критерии</h2><span>{{ current.review.items.filter(i => i.reviewer_action !== 'pending').length }} / {{ current.review.items.length }} решено</span></div>
          <article v-for="item in current.review.items" :key="item.id" class="review-item" :class="`decision-${item.reviewer_action}`">
            <header><div><span class="confidence" :class="item.confidence">{{ item.confidence === 'high' ? 'Высокая' : item.confidence === 'medium' ? 'Средняя' : 'Низкая' }}</span><h3>{{ item.criterion_title }}</h3></div><strong>{{ item.ai_score }} <small>/ {{ item.max_score }}</small></strong></header>
            <p>{{ item.recommendation }}</p><div class="evidence" v-for="proof in item.evidence" :key="proof.quote"><span>“</span><code>{{ proof.quote }}</code><small>{{ proof.anchor }}</small></div>
            <div v-if="item.reviewer_action === 'pending'" class="decision-box"><div class="edit-inline"><label>Ваш балл<input v-model="item.editScore" type="number" min="0" :max="item.max_score" step="0.5" /></label><label>Комментарий<input v-model="item.editComment" placeholder="Необязательно" /></label></div><div class="decision-actions"><button class="accept" @click="decideItem(item, 'accepted')">✓ Принять</button><button @click="decideItem(item, 'changed')">Изменить</button><button class="reject" @click="decideItem(item, 'rejected')">Отклонить</button></div></div>
            <div v-else class="decision-done">✓ Решение: {{ { accepted: 'принято', changed: 'изменено', rejected: 'отклонено' }[item.reviewer_action] }} <button @click="item.reviewer_action = 'pending'">Изменить</button></div>
          </article>
        </section>
        <section class="review-section"><div class="section-title"><h2>AI-сигнал</h2><span>Не влияет на балл</span></div><article v-for="signal in current.review.signals" :key="signal.id" class="signal-card"><header><span class="signal-icon">⌁</span><div><small>{{ signal.kind === 'ai_use' ? 'ВОЗМОЖНОЕ ИСПОЛЬЗОВАНИЕ AI' : 'РИСК ПОНИМАНИЯ' }}</small><h3>{{ signal.summary }}</h3></div><span class="confidence" :class="signal.level">{{ signal.level }}</span></header><ul><li v-for="ground in signal.grounds" :key="ground">{{ ground }}</li></ul><details><summary>Ограничения метода</summary><p>{{ signal.limitations }}</p></details><div v-if="signal.reviewer_decision === 'pending'" class="decision-actions"><button class="accept" @click="decideSignal(signal, 'confirmed')">Подтвердить сигнал</button><button @click="decideSignal(signal, 'dismissed')">Отклонить</button></div><div v-else class="decision-done">Решение сохранено: {{ signal.reviewer_decision }}</div></article></section>
        <section v-if="current.suggested_questions.length && current.submission.status === 'in_review'" class="review-section"><div class="section-title"><h2>Дополнительные вопросы</h2><span>До 48 часов</span></div><p class="muted">Выберите вопросы — студент не увидит упоминаний AI-сигнала.</p><label v-for="question in current.suggested_questions" :key="question.id" class="question-check"><input v-model="question.selected" type="checkbox" /><span><b>{{ question.text }}</b><small>{{ question.type }}</small></span></label><button class="secondary full" @click="sendBlitz">Отправить выбранные вопросы</button></section>
        <section class="review-section feedback-editor"><div class="section-title"><h2>Обратная связь студенту</h2><span>Отправится только после подтверждения</span></div><textarea v-model="feedback" rows="7" /><div class="editor-actions"><button class="secondary" @click="rewrite">✦ Переформулировать</button><button class="primary" :disabled="current.submission.status === 'blitz_sent' || current.submission.status === 'completed'" @click="complete">Подтвердить и опубликовать</button></div></section>
      </aside>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-review'" class="empty-state"><span>⌁</span><h2>Выберите работу из очереди</h2><button class="primary" @click="emit('navigate', 'reviewer-queue')">Открыть очередь</button></section>
</template>
