<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { aiStatusNames, api, formatDate } from '../../shared/api'
import { useLiveRefresh } from '../../shared/live'
import { reviewTotals } from '../../shared/score'
import { evidenceLink } from '../../shared/sourceLink'
import MarkdownText from '../../shared/ui/MarkdownText.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'

const props = defineProps({ active: String, sub: { type: Array, default: () => [] } })
const emit = defineEmits(['navigate'])
// Открытая работа живёт в адресе: «назад» из разбора обязан вести в очередь,
// а F5 на разборе — открывать ту же работу, а не пустой экран.
const REVIEW = 'reviewer-review'
const openedId = computed(() => (props.active === REVIEW ? props.sub[0] || '' : ''))
const queue = ref([])
const history = ref([])
const current = ref(null)
const error = ref('')
const notice = ref('')
const feedback = ref('')
const loading = ref(true)
const loadingReview = ref(false)
const showAllQueue = ref(false)

// По умолчанию в очереди — работы, которые ждут действия ревьюера.
// «blitz_sent» = ждём ответа студента, взять в работу нельзя.
const ACTIONABLE = ['assigned', 'in_review', 'blitz_answered']
const actionable = computed(() => queue.value.filter(i => ACTIONABLE.includes(i.status)))

const sortBy = ref('deadline')
const assignmentFilter = ref('')
const studentFilter = ref('')

// Дедлайн может быть не задан. Такие работы уходят вниз в обоих направлениях:
// «без срока» — не «очень рано» и не «очень поздно», сравнивать его не с чем.
function byDeadline(a, b, direction) {
  if (!a.deadline_at || !b.deadline_at) return (a.deadline_at ? 0 : 1) - (b.deadline_at ? 0 : 1)
  return direction * (new Date(a.deadline_at) - new Date(b.deadline_at))
}

const QUEUE_SORTS = {
  deadline: { label: 'Дедлайн проверки: ближайший первым', compare: (a, b) => byDeadline(a, b, 1) },
  deadline_desc: { label: 'Дедлайн проверки: поздний первым', compare: (a, b) => byDeadline(a, b, -1) },
  assignment: { label: 'Задание: А–Я', compare: (a, b) => a.assignment.localeCompare(b.assignment, 'ru') },
  student: { label: 'Студент: А–Я', compare: (a, b) => a.student.localeCompare(b.student, 'ru') },
}

function options(field) {
  return [...new Set(queue.value.map(i => i[field]))].sort((a, b) => a.localeCompare(b, 'ru'))
}
const assignmentOptions = computed(() => options('assignment'))
const studentOptions = computed(() => options('student'))
const hasFilters = computed(() => Boolean(assignmentFilter.value || studentFilter.value))

// Очередь у ревьюера короткая и приходит целиком, поэтому фильтры и сортировка
// живут на клиенте. Порядок по умолчанию тот же, что отдаёт сервер.
const visibleQueue = computed(() =>
  (showAllQueue.value ? queue.value : actionable.value)
    .filter(i => !assignmentFilter.value || i.assignment === assignmentFilter.value)
    .filter(i => !studentFilter.value || i.student === studentFilter.value)
    .sort(QUEUE_SORTS[sortBy.value].compare),
)

// `silent` — обновление по таймеру, а не по действию человека. Скелетон на нём
// не показывается: список уже на экране, и мигать он не должен.
async function loadQueue({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    queue.value = await api('/reviewer/queue')
    // Работу могли завершить или передать другому — фильтр по ней остался бы
    // выбранным и показывал бы пустой список без видимой причины.
    if (!assignmentOptions.value.includes(assignmentFilter.value)) assignmentFilter.value = ''
    if (!studentOptions.value.includes(studentFilter.value)) studentFilter.value = ''
  }
  // Молчаливый тик и молчит: одна неудачная фоновая попытка не повод писать
  // ревьюеру ошибку поверх работающего экрана — следующий тик попробует снова.
  catch (e) { if (!silent) error.value = e.message }
  finally { loading.value = false }
}

async function loadHistory() {
  try { history.value = await api('/reviewer/history') }
  catch (e) { error.value = e.message }
}

const openReview = (id) => emit('navigate', `${REVIEW}/${id}`)

async function loadReview(id) {
  current.value = null
  // Снапшот другой — найденные по нему места больше ничего не значат.
  proofCache = new Map()
  // Пока работа грузится, экран не должен говорить «выберите работу из
  // очереди»: она выбрана, её открывают.
  loadingReview.value = true
  try {
    current.value = await api(`/reviewer/submissions/${id}/review`)
    // Опубликованный текст, а если работа ещё не закрыта — черновик AI. Тут
    // стоял только черновик: открыв завершённую работу, ревьюер видел в
    // редакторе предложение модели и считал его тем, что ушло студенту, — а
    // ушла его собственная правка, которой на экране не было.
    feedback.value = current.value.review.final_feedback || current.value.review.draft_feedback
    current.value.review.items.forEach(item => { item.editScore = item.final_score ?? item.ai_score; item.editComment = item.reviewer_comment })
    // Черновик мог остаться с прошлого захода: без этого он бы показался с
    // пустыми галочками, и «Отправить» ругалось бы на пустой выбор.
    picked.value = Object.fromEntries((current.value.blitz_draft?.questions || []).map(q => [q.id, true]))
    fraudVerdict.value = ''
  } catch (e) { error.value = e.message }
  finally { loadingReview.value = false }
}

// Совпал ли балл в поле с оценкой AI. От этого зависит, какая из двух кнопок
// активна: «Подтвердить» — когда подтверждать нечего кроме оценки AI,
// «Изменить» — когда ревьюер вписал своё число. Раньше активны были обе, и
// «Принять» отправляло ai_score поверх вписанного: правка пропадала молча, а
// итог за работу не двигался — считать ему было нечего, final_score приходил
// равным той же оценке AI.
function isAiScore(item) {
  return Number(item.editScore) === Number(item.ai_score)
}

async function decideItem(item, action) {
  // «Подтвердить» сохраняет оценку AI, «Изменить» — то, что в поле. Число
  // берётся здесь один раз: пусть кнопка и балл расходятся невозможным
  // образом, а не тихо.
  const score = action === 'accepted' ? Number(item.ai_score) : Number(item.editScore)
  if (!Number.isFinite(score)) { error.value = 'Укажите балл по критерию'; return }
  try {
    await api(`/reviewer/review-items/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ action, final_score: action === 'changed' ? score : null, comment: item.editComment || '' }),
    })
    item.reviewer_action = action
    item.final_score = score
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

// Стадии, которые считает машина: пока разбор или детекция в этих статусах,
// экран обязан догонять их сам.
const AI_IN_FLIGHT = ['pending', 'running']
const isPending = (status) => AI_IN_FLIGHT.includes(status)

// Разбор Z.AI и детекция приходят фоновыми задачами. Раньше их ждал цикл в
// rerun() на 60 попыток — и только он: работа, открытая, пока разбор ещё шёл,
// показывала «Проверка выполняется…» до перезагрузки, а перезапуск детекции не
// обновлял экран вовсе. Условие ожидания одно на обе стадии и живёт здесь.
const machineWorking = computed(() =>
  Boolean(current.value)
  && (isPending(current.value.review?.ai_status) || isPending(current.value.detection?.status)),
)

async function syncReview() {
  if (!current.value) return
  const fresh = await api(`/reviewer/submissions/${current.value.submission.id}/review`)
  // Детекция и блиц идут отдельными полями — их можно заменить целиком, не
  // трогая ничего из того, что ревьюер успел набрать.
  current.value.detection = fresh.detection
  current.value.blitz = fresh.blitz
  current.value.review.signals = fresh.review.signals
  if (!isPending(current.value.review.ai_status)) return
  current.value.review.ai_status = fresh.review.ai_status
  current.value.review.ai_error = fresh.review.ai_error
  if (isPending(fresh.review.ai_status)) return
  // Разбор доехал. Ответ берётся целиком: критериев на экране до этого не было,
  // решений по ним ревьюер принять не мог, и терять тут нечего.
  current.value.review = fresh.review
  feedback.value = fresh.review.final_feedback || fresh.review.draft_feedback
  fresh.review.items.forEach(item => { item.editScore = item.final_score ?? item.ai_score; item.editComment = item.reviewer_comment })
  notice.value = fresh.review.ai_status === 'ready' ? 'Проверка Z.AI готова' : ''
  if (fresh.review.ai_status === 'failed') error.value = fresh.review.ai_error || 'Проверка Z.AI завершилась ошибкой'
}

useLiveRefresh(() => machineWorking.value, syncReview)

// Очередь показывает статус разбора по каждой работе: пока хоть один идёт,
// список обновляется сам, иначе не опрашивается вовсе.
useLiveRefresh(
  () => props.active === 'reviewer-queue' && queue.value.some(row => isPending(row.ai_status)),
  () => loadQueue({ silent: true }),
)

async function rerun() {
  try {
    await api(`/reviewer/reviews/${current.value.review.id}/rerun`, { method: 'POST' })
    // Дальше экран ведёт useLiveRefresh: статус running включает опрос, готовый
    // разбор его выключает. Ждать здесь больше нечем и незачем.
    current.value.review.ai_status = 'running'
    notice.value = 'Z.AI начал повторную проверку'
  } catch (e) { error.value = e.message }
}

const CATEGORY_TITLES = {
  no_signs: 'Признаков не наблюдается',
  tool_assisted: 'Похоже на использование AI как инструмента',
  likely_generated: 'Похоже на сгенерированное решение',
}

// Вердикт голосования прогонов. Те же три категории, что и выше, но названные
// так, как о них думают: подпись «2 из 3» рядом объясняет, откуда категория
// взялась, — иначе она выглядит как вывод из индекса, а индекс её не считает.
const VERDICT_TITLES = {
  human: 'Human',
  human_ai_assisted: 'Human + AI assistant',
  ai: 'AI',
}

const CONFIDENCE_TITLES = {
  high: 'Высокая — было что наблюдать',
  medium: 'Средняя — часть признаков недоступна',
  low: 'Низкая — наблюдать почти нечего',
}

// Уверенность модели в оценке критерия — не важность замечания и не серьёзность
// нарушения. Словом её больше не пишем: «ВЫСОКАЯ» рядом с «0 / 2» читалось как
// оценка тяжести, а зелёный цвет рядом с нулём — как противоречие. Осталcя
// светофор с подписью, которая называет величину целиком.
const SCORE_CONFIDENCE_HINTS = {
  high: 'Высокая: оценка опирается на прямо наблюдаемое в решении',
  medium: 'Средняя: часть основания в решении не видна',
  low: 'Низкая: наблюдать почти нечего, проверьте критерий сами',
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
      body: JSON.stringify({ verdict: fraudVerdict.value, blitz_id: current.value.blitz?.id || null }),
    })
    notice.value = 'Решение зафиксировано. На балл оно не влияет.'
    fraudVerdict.value = ''
    current.value = await api(`/reviewer/submissions/${current.value.submission.id}/review`)
  } catch (e) { error.value = e.message }
}

async function complete() {
  try {
    const result = await api(`/reviewer/reviews/${current.value.review.id}/complete`, { method: 'POST', body: JSON.stringify({ feedback: feedback.value }) })
    notice.value = `Ревью опубликовано · ${result.score}${result.max_score != null ? ` из ${result.max_score}` : ''}`
    current.value.submission.status = 'completed'
    // Что опубликовали, то и лежит в ревью. Без этой строки местное состояние
    // расходилось с сервером сразу после публикации: на экране черновик, у
    // студента — отправленный текст.
    current.value.review.final_feedback = feedback.value
    current.value.review.final_score = result.score
  } catch (e) { error.value = e.message }
}

// Суммарный балл за работу — до разбора по критериям. Пока решения приняты не
// по всем критериям, это оценка AI, и говорить о ней надо словом, а не мелким
// шрифтом: ревьюер публикует именно это число.
const totals = computed(() => reviewTotals(current.value?.review?.items))
const totalMax = computed(() => current.value?.review?.max_score ?? totals.value.max_score ?? null)

const snapshotFiles = computed(() => current.value?.snapshot?.parsed_facts?.files || [])

// Цитата — это основание оценки, и проверять её ревьюер должен в исходнике, а
// не глазами по снапшоту. Место ищется по тому же тексту, который читала
// модель, поэтому ссылка ведёт ровно туда, откуда цитата взята.
//
// Кэш не для скорости поиска, а для числа поисков: шаблон спрашивает ссылку на
// каждой перерисовке, а снапшот на открытой работе не меняется.
let proofCache = new Map()

function proofLink(quote) {
  if (!proofCache.has(quote)) {
    proofCache.set(
      quote,
      evidenceLink(current.value?.submission?.source_url, current.value?.snapshot?.content, quote),
    )
  }
  return proofCache.get(quote)
}

/** Цитата, подпись и ссылка одной строкой — так они и стоят на экране. */
function evidenceRows(evidence) {
  return (evidence || []).map(proof => {
    const link = proofLink(proof.quote)
    return {
      quote: proof.quote,
      // Якорь модели — слова («Ячейка 12»). Он остаётся подписью, когда точное
      // место в файле не нашлось: указание, где смотреть, всё равно есть.
      label: link?.exact ? link.label : proof.anchor,
      url: link?.url || '',
    }
  })
}

// Повод для доп. вопросов и решения по фроду — это сигнал, а не сам факт
// проверки. Без сигнала спрашивать не о чем и решать нечего, поэтому оба блока
// не показываются: пустая форма вердикта провоцирует его вынести.
const hasAiSignal = computed(() => {
  const detection = current.value?.detection
  const overThreshold = Boolean(
    detection?.reportable && detection.score >= detection.blitz_threshold,
  )
  return overThreshold || Boolean(current.value?.review?.signals?.length)
})

// Черновик ревьюер правит текстом, а студент читает разметкой. Пока их видно
// рядом, «стена текста» замечается до публикации, а не после неё.
const showFeedbackPreview = ref(true)

// Условие и критерии — справочная панель поверх экрана проверки: свериться с
// заданием нужно, не теряя разбор и несохранённые решения по критериям.
// Критерии здесь берутся из рубрики, а не из разбора AI, поэтому список полный
// и доступен ещё до того, как разбор готов.
const CHANNEL_NAMES = { github: 'Ссылка на GitHub-репозиторий', stepik: 'Stepik', gdocs: 'Google Docs' }
const panel = ref('')
const assignment = computed(() => current.value?.assignment || {})
const rubric = computed(() => assignment.value.rubric || [])

function onKeydown(event) { if (event.key === 'Escape') panel.value = '' }

watch(() => props.active, value => {
  error.value = ''
  panel.value = ''
  if (value === 'reviewer-queue') loadQueue()
  if (value === 'reviewer-history') loadHistory()
})
// Переход между работами разделом не считается: из очереди в разбор и обратно
// раздел меняется, а с одной работы на другую — только адрес.
watch(openedId, id => { if (id) loadReview(id); else current.value = null })

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  if (openedId.value) return loadReview(openedId.value)
  props.active === 'reviewer-history' ? loadHistory() : loadQueue()
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <section v-if="active === 'reviewer-queue'">
    <div class="page-heading"><div><h1>Моя очередь</h1></div><div class="queue-summary"><b>{{ actionable.length }}</b><small>ждут действия</small></div></div>
    <div class="registry-tools queue-tools">
      <select v-model="sortBy"><option v-for="(sort, key) in QUEUE_SORTS" :key="key" :value="key">{{ sort.label }}</option></select>
      <select v-model="assignmentFilter"><option value="">Все задания</option><option v-for="title in assignmentOptions" :key="title" :value="title">{{ title }}</option></select>
      <select v-model="studentFilter"><option value="">Все студенты</option><option v-for="name in studentOptions" :key="name" :value="name">{{ name }}</option></select>
    </div>
    <div class="filter-row">
      <label class="chk"><input type="checkbox" v-model="showAllQueue" /> Показывать все актуальные работы</label>
      <span />
      <small v-if="!showAllQueue && queue.length > actionable.length">скрыто «ждёт ответа студента»: {{ queue.length - actionable.length }}</small>
    </div>
    <div class="table-card queue-table">
      <div class="table-row table-head"><span>Студент и работа</span><span>Статус</span><span>Дедлайн проверки</span></div>
      <button v-for="item in visibleQueue" :key="item.id" class="table-row" :disabled="item.status === 'blitz_sent'" @click="item.status !== 'blitz_sent' && openReview(item.id)">
        <span class="student-cell"><i>{{ item.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ item.student }}</b><small>{{ item.assignment }}<template v-if="item.is_overdue"> · сдано после срока</template></small></span></span>
        <StatusBadge :status="item.status" />
        <span :class="{ danger: item.deadline_state === 'overdue', warn: item.deadline_state === 'risk' }"><b>{{ formatDate(item.deadline_at, true) }}</b><small v-if="item.deadline_state === 'overdue'">Срок вышел</small><small v-else-if="item.deadline_state === 'risk'">Меньше суток</small></span>
      </button>
      <div v-if="!loading && !visibleQueue.length" class="empty-mini padded">{{ !queue.length ? 'Очередь пуста' : hasFilters ? 'Под выбранные фильтры работ нет' : 'Все работы в очереди ждут ответа студента — включите «показывать все актуальные»' }}</div>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-history'">
    <div class="page-heading"><div><h1>История</h1></div><div class="queue-summary"><b>{{ history.length }}</b><small>всего работ</small></div></div>
    <div class="table-card history-table">
      <div class="table-row table-head"><span>Студент и работа</span><span>Статус</span><span>Балл</span><span>Сдано</span></div>
      <button v-for="item in history" :key="item.id" class="table-row" :disabled="!item.is_current || item.status === 'completed'" @click="item.is_current && item.status !== 'completed' && openReview(item.id)">
        <span class="student-cell"><i>{{ item.student.split(' ').map(x => x[0]).join('').slice(0,2) }}</i><span><b>{{ item.student }}</b><small>{{ item.assignment }}</small></span></span>
        <StatusBadge :status="item.status" />
        <span><b>{{ item.final_score ?? '—' }}</b><small v-if="item.final_score != null && item.max_score != null">из {{ item.max_score }}</small></span>
        <span><b>{{ formatDate(item.submitted_at, true) }}</b><small v-if="item.completed_at">проверено {{ formatDate(item.completed_at, true) }}</small></span>
      </button>
      <div v-if="!history.length" class="empty-mini padded">Здесь появятся все проверенные вами работы</div>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-review' && current" class="review-page">
    <button class="back" @click="emit('navigate', 'reviewer-queue')">← Вернуться в очередь</button>
    <div class="review-title">
      <div>
        <h1>{{ current.submission.student }}</h1><p>{{ current.submission.assignment }} · сдано {{ formatDate(current.submission.submitted_at, true) }}</p>
        <div class="review-title-actions">
          <button class="secondary" @click="panel = 'statement'">Условие</button>
          <button class="secondary" @click="panel = 'criteria'">Критерии</button>
        </div>
      </div>
      <StatusBadge :status="current.submission.status" />
    </div>
    <div v-if="notice" class="toast-success">✓ {{ notice }}<button @click="notice = ''">×</button></div>
    <div v-if="error" class="toast-error">{{ error }}<button @click="error = ''">×</button></div>
    <section class="score-total" :class="{ settled: totals.total && !totals.pending }">
      <div class="score-total-value"><b>{{ totals.total ? totals.score : '—' }}</b><small v-if="totalMax != null">из {{ totalMax }}</small></div>
      <div class="score-total-meta">
        <b>{{ totals.total && !totals.pending ? 'Итоговый балл за работу' : 'Предварительный балл за работу' }}</b>
        <small v-if="!totals.total">Ревью по критериям ещё нет — {{ aiStatusNames[current.review.ai_status] || current.review.ai_status }}.</small>
        <small v-else-if="totals.pending">Утверждено {{ totals.decided }} из {{ totals.total }} критериев. По остальным пока стоит оценка AI — она станет вашей, когда вы примете решение ниже.</small>
        <small v-else>Утверждены все {{ totals.total }} критериев. Публикация выставит студенту это число.</small>
        <div v-if="totals.total" class="score-total-bar"><i :style="{ width: `${Math.round((totals.decided / totals.total) * 100)}%` }" /></div>
      </div>
    </section>
    <div class="review-workspace">
      <article class="notebook-panel"><header><div class="file-tab" :title="snapshotFiles.join('\n')"><span>◇</span>{{ snapshotFiles[0] || 'Снапшот решения' }}<i v-if="snapshotFiles.length > 1">+{{ snapshotFiles.length - 1 }}</i></div><a :href="current.submission.source_url" target="_blank">GitHub ↗</a></header><pre>{{ current.snapshot.content }}</pre><footer><span>Снапшот сохранён {{ formatDate(current.snapshot.fetched_at, true) }}</span><span>Повторных запросов к GitHub нет</span></footer></article>
      <aside class="review-panel">
        <div class="ai-summary"><span class="spark">✦</span><div><span class="eyebrow">AI-РЕВЬЮ</span><b><MarkdownText v-if="current.review.summary" inline :text="current.review.summary" /><template v-else>{{ current.review.ai_status === 'running' ? 'Проверка выполняется…' : 'Результат пока не сформирован' }}</template></b><small>Модель {{ current.review.model }}</small></div><button class="ai-rerun" :disabled="current.review.is_demo || current.review.ai_status === 'running' || current.submission.status === 'completed'" @click="rerun">↻ Перезапустить</button></div>
        <div v-if="current.review.ai_status === 'failed'" class="toast-error">Z.AI: {{ current.review.ai_error }}</div>

        <!-- Критерии идут первыми: ревьюер пришёл выставить балл, а признаки
             использования AI на балл не влияют и стоят после решения по нему. -->
        <section class="review-section"><div class="section-title"><h2>Оценки по критериям</h2><span>{{ current.review.items.filter(i => i.reviewer_action !== 'pending').length }} / {{ current.review.items.length }} утверждено</span></div>
          <article v-for="item in current.review.items" :key="item.id" class="review-item" :class="`decision-${item.reviewer_action}`">
            <header>
              <div>
                <h3><MarkdownText inline :text="item.criterion_title" /></h3>
                <!-- Светофор без слова: словом эту величину путали с важностью
                     замечания, а «ВЫСОКАЯ» рядом с «0 / 2» читалось как
                     противоречие. Уровень остаётся цветом, смысл — подписью. -->
                <span class="ai-confidence" :class="item.confidence" :title="SCORE_CONFIDENCE_HINTS[item.confidence]"><i />уверенность AI в оценке критерия</span>
              </div>
              <!-- Действующий балл по критерию, а не оценка AI: после решения
                   ревьюера в шапке карточки стояло старое число, и оно
                   расходилось с итогом за работу, который считается по нему же. -->
              <strong>{{ item.final_score ?? item.ai_score }} <small>/ {{ item.max_score }}</small></strong>
            </header>
            <MarkdownText :text="item.recommendation" />
            <template v-for="proof in evidenceRows(item.evidence)" :key="proof.quote">
              <a v-if="proof.url" class="evidence linked" :href="proof.url" target="_blank" rel="noopener noreferrer"><span>“</span><code>{{ proof.quote }}</code><small>{{ proof.label }} ↗</small></a>
              <div v-else class="evidence"><span>“</span><code>{{ proof.quote }}</code><small>{{ proof.label }}</small></div>
            </template>
            <div v-if="item.levels?.length" class="levels">
              <small>Что означает балл по этому критерию</small>
              <div v-for="level in item.levels" :key="level.points" class="level-row" :class="{ picked: Number(level.points) === Number(item.final_score ?? item.ai_score) }">
                <b>{{ level.points }}</b><span><i>{{ level.label }}</i><MarkdownText inline :text="level.descriptor" /></span>
              </div>
            </div>
            <div v-if="item.reviewer_action === 'pending'" class="decision-box"><div class="edit-inline"><label>Ваш балл<input v-model="item.editScore" type="number" min="0" :max="item.max_score" step="0.5" /></label><label>Комментарий<input v-model="item.editComment" placeholder="Необязательно" /></label></div><div class="decision-actions"><button class="accept" :disabled="!isAiScore(item)" title="Согласиться с оценкой AI" @click="decideItem(item, 'accepted')">✓ Подтвердить</button><button :disabled="isAiScore(item)" title="Сохранить балл из поля «Ваш балл»" @click="decideItem(item, 'changed')">Изменить</button></div></div>
            <div v-else class="decision-done">✓ Решение: {{ { accepted: 'принято', changed: 'изменено', rejected: 'отклонено' }[item.reviewer_action] }} <button @click="item.reviewer_action = 'pending'">Изменить</button></div>
          </article>
        </section>

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
                <span v-if="current.detection.verdict" class="detection-vote">
                  Голосование прогонов: <b>{{ VERDICT_TITLES[current.detection.verdict] }}</b>
                  <i :class="{ split: current.detection.vote_agreement < current.detection.votes.length }">{{ current.detection.vote_agreement }} из {{ current.detection.votes.length }}</i>
                  <em v-for="(vote, index) in current.detection.votes" :key="index" :class="vote">{{ VERDICT_TITLES[vote] }}</em>
                </span>
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
                <em v-for="proof in evidenceRows(item.evidence)" :key="proof.quote">«{{ proof.quote }}»
                  <a v-if="proof.url" :href="proof.url" target="_blank" rel="noopener noreferrer">{{ proof.label }} ↗</a>
                  <i v-else>{{ proof.label }}</i>
                </em>
              </span>
            </div>
            <div v-if="current.detection.reportable && current.detection.score >= current.detection.blitz_threshold" class="attention-panel">
              <h3><span>?</span> Стоит задать вопросы по работе</h3>
              <p>Индекс выше порога {{ current.detection.blitz_threshold }}. Это повод проверить понимание, а не снизить балл: решение о баллах принимаете вы и только по критериям.</p>
            </div>
            <details v-if="current.detection.limitations"><summary>Ограничения метода</summary><MarkdownText :text="current.detection.limitations" /></details>
          </template>
        </section>
        <!-- Пустого заголовка тут больше нет: раз доп. вопросы появляются по
             сигналу, секция без сигналов выглядела как сломанное условие. -->
        <section v-if="current.review.signals?.length" class="review-section"><div class="section-title"><h2>AI-сигнал</h2><span>Не влияет на балл</span></div><article v-for="signal in current.review.signals" :key="signal.id" class="signal-card"><header><span class="signal-icon">⌁</span><div><small>{{ signal.kind === 'ai_use' ? 'ВОЗМОЖНОЕ ИСПОЛЬЗОВАНИЕ AI' : 'РИСК ПОНИМАНИЯ' }}</small><h3><MarkdownText inline :text="signal.summary" /></h3></div><span class="confidence" :class="signal.level">{{ signal.level }}</span></header><ul><li v-for="ground in signal.grounds" :key="ground"><MarkdownText inline :text="ground" /></li></ul><details><summary>Ограничения метода</summary><MarkdownText :text="signal.limitations" /></details><div v-if="signal.reviewer_decision === 'pending'" class="decision-actions"><button class="accept" @click="decideSignal(signal, 'confirmed')">Подтвердить сигнал</button><button @click="decideSignal(signal, 'dismissed')">Отклонить</button></div><div v-else class="decision-done">Решение сохранено: {{ signal.reviewer_decision }}</div></article></section>
        <!-- Только когда есть сигнал: без него спрашивать не о чем, а форма,
             стоящая на каждой работе, сама делает опрос рутиной. Начатый
             черновик остаётся на экране, даже если сигнал успели снять. -->
        <section v-if="current.submission.status === 'in_review' && (hasAiSignal || current.blitz_draft)" class="review-section">
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
                <em class="expected">Понимающий ответ покажет: <MarkdownText inline :text="question.expected_points.join('; ')" /></em>
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

        <!-- Тоже только по сигналу. Уже вынесенные решения показываются всегда:
             история пересмотров не должна исчезать вместе с поводом. -->
        <section v-if="current.detection && (hasAiSignal || current.fraud_decisions?.length)" class="review-section fraud-panel">
          <div class="section-title"><h2>Решение по AI-фроду</h2><span>На балл не влияет</span></div>
          <article v-for="row in current.fraud_decisions" :key="row.decided_at" class="decision-done block">
            <b>{{ FRAUD_VERDICTS[row.verdict] }}</b><small>{{ formatDate(row.decided_at, true) }}</small><p v-if="row.rationale">{{ row.rationale }}</p>
          </article>
          <p class="muted">Решение принимаете вы. Индекс и ответы на вопросы — материал для него, а не он сам. Балл складывается из решений по критериям и от этого вердикта не зависит.</p>
          <div class="fraud-actions">
            <label v-for="(title, key) in FRAUD_VERDICTS" :key="key" class="fraud-option"><input v-model="fraudVerdict" type="radio" :value="key" />{{ title }}</label>
          </div>
          <button class="secondary full" :disabled="!fraudVerdict" @click="saveFraudDecision">Зафиксировать решение</button>
        </section>
        <section class="review-section feedback-editor">
          <div class="section-title"><h2>Обратная связь студенту</h2><span>Отправится только после подтверждения</span></div>
          <textarea v-model="feedback" rows="14" spellcheck="true" placeholder="Что получилось, что доработать и почему. Абзацы разделяйте пустой строкой, перечисления — строками через «- »." />
          <!-- Студент читает не поле ввода, а разметку. Показывать её рядом
               дешевле, чем узнавать про слипшийся абзац после публикации. -->
          <div class="feedback-preview-head">
            <button class="linklike" @click="showFeedbackPreview = !showFeedbackPreview">{{ showFeedbackPreview ? 'Скрыть' : 'Показать' }} вид у студента</button>
            <small>{{ feedback.trim() ? `${feedback.trim().length} символов` : 'черновик пуст' }}</small>
          </div>
          <MarkdownText v-if="showFeedbackPreview && feedback.trim()" class="feedback-preview" :text="feedback" />
          <div class="editor-actions"><button class="secondary" @click="rewrite">✦ Переформулировать</button><button class="primary" :disabled="current.submission.status === 'blitz_sent' || current.submission.status === 'completed'" @click="complete">Подтвердить и опубликовать</button></div>
        </section>
      </aside>
    </div>

    <div v-if="panel" class="drawer-backdrop" @click.self="panel = ''">
      <aside class="drawer">
        <header>
          <div><span class="eyebrow">{{ assignment.title }}</span><h2>{{ panel === 'statement' ? 'Условие задания' : 'Критерии и разбалловка' }}</h2></div>
          <button class="drawer-close" aria-label="Закрыть" @click="panel = ''">×</button>
        </header>

        <div v-if="panel === 'statement'" class="drawer-body">
          <dl class="drawer-facts">
            <div><dt>Формат сдачи</dt><dd>{{ CHANNEL_NAMES[assignment.submission_channel] || assignment.submission_channel || '—' }}</dd></div>
            <div><dt>Дедлайн проверки</dt><dd>{{ assignment.deadline_at ? formatDate(assignment.deadline_at, true) : 'не задан' }}</dd></div>
            <div><dt>Максимум за работу</dt><dd>{{ assignment.max_score ?? '—' }}</dd></div>
            <div><dt>Порог зачёта</dt><dd>{{ assignment.pass_score ?? '—' }}</dd></div>
          </dl>
          <MarkdownText v-if="assignment.statement" :text="assignment.statement" />
          <p v-else class="muted">Условие к заданию не заполнено.</p>
          <p class="muted small">Требования к результату, ограничения и формат сдачи методист описывает в тексте условия — здесь оно показано целиком, без сокращений.</p>
        </div>

        <div v-else class="drawer-body">
          <p class="muted">Полная рубрика с градацией по баллам. Она не зависит от AI-ревью: список доступен и до того, как ревью готово, и после утверждения оценок.</p>
          <article v-for="criterion in rubric" :key="criterion.key" class="drawer-criterion">
            <header><b><MarkdownText inline :text="criterion.title" /></b><strong>{{ criterion.max_score }}</strong></header>
            <p v-if="criterion.student_hint" class="muted"><MarkdownText inline :text="criterion.student_hint" /></p>
            <div v-for="level in criterion.levels || []" :key="level.points" class="level-row"><b>{{ level.points }}</b><span><i>{{ level.label }}</i><MarkdownText inline :text="level.descriptor" /></span></div>
            <p v-if="!criterion.levels?.length" class="muted small">Градация по баллам в рубрике не задана.</p>
          </article>
          <p v-if="!rubric.length" class="muted">Критерии к заданию не заведены.</p>
          <p v-else class="drawer-total">Итого по рубрике: <b>{{ assignment.max_score ?? '—' }}</b><template v-if="assignment.pass_score != null"> · зачёт от {{ assignment.pass_score }}</template></p>
        </div>
      </aside>
    </div>
  </section>

  <section v-else-if="active === 'reviewer-review' && loadingReview" class="empty-state"><span>⌁</span><h2>Открываем работу…</h2></section>

  <!-- Открытой работы нет. Пункта «Ревью» в меню больше нет, но по прямой
       ссылке или после перезагрузки страницы сюда ещё можно попасть. -->
  <section v-else-if="active === 'reviewer-review'" class="empty-state"><span>⌁</span><h2>{{ error ? 'Работа не открылась' : 'Выберите работу из очереди' }}</h2><button class="primary" @click="emit('navigate', 'reviewer-queue')">Открыть очередь</button></section>
</template>
