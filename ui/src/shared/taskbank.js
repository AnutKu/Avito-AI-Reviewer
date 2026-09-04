// Чистая логика банка заданий: раскладка по вкладкам, поиск, арифметика баллов
// и человеческие названия для того, что приходит от агентов. Без Vue и без
// сети — чтобы это можно было проверить тестами, а не кликами.

export const PUBLICATION = { published: 'Опубликовано', draft: 'Черновик' }

// Состояние AI-операции. Отдельно от публикации намеренно: «опубликовано» и
// «идёт проверка» — независимые факты, одно поле на двоих их бы смешало.
export const RUN_STATE = {
  queued: ['в очереди', 'wait'],
  running: ['проверка идёт', 'wait'],
  completed: ['проверено', 'ok'],
  failed: ['ошибка прогона', 'bad'],
}

export const PERSONA_TYPE = {
  student: 'AI-студенты',
  reviewer: 'AI-ревьюеры',
  both: 'AI-студенты и ревьюеры',
}

// Смайлик персоны — чтобы в списке решений было видно, чьё оно, до чтения имени.
export const PERSONAS = {
  diligent_strong: ['🤓', 'Сильный добросовестный', 'Читает условие внимательно, делает всё и с запасом'],
  minimalist_weak: ['🥱', 'Слабый по минимуму', 'Берёт очевидное, остальное пропускает'],
  rule_lawyer: ['🧐', 'Юрист правил', 'Выполняет букву критерия, нарушая его смысл'],
  ambiguity_prober: ['🕵️', 'Ищет двусмысленности', 'Цепляется за всё, что можно прочитать двояко'],
  provided: ['📄', 'Присланное решение', 'Решение, переданное вручную'],
  demo: ['🧪', 'Демо', 'Демонстрационный прогон'],
}

export const personaFace = (key) => PERSONAS[key]?.[0] || '🤖'
export const personaName = (key) => PERSONAS[key]?.[1] || key
export const personaAbout = (key) => PERSONAS[key]?.[2] || ''

// Кто пишет решения, которые оценивают ревьюеры. Вопрос возникает у каждого, кто
// первый раз выбирает «проверить критерии»: оценивать-то нечего, студентов же не
// запускали. На самом деле решения пишутся в этом же прогоне, просто их не
// показывают как отдельный шаг — об этом и говорим прямо на экране.
export const SOLUTIONS_NOTE =
  'Решения для проверки пишут AI-студенты — это происходит внутри того же прогона, отдельно запускать их не нужно.'

export const SEVERITY = {
  critical: ['критично', 'high'],
  important: ['важно', 'medium'],
  improvement: ['улучшение', 'low'],
}

export const RECOMMENDATION_STATE = {
  new: '',
  applied: 'применена',
  edited: 'применена с правкой',
  rejected: 'отклонена',
}

// Находки агентов приходят кодом. Методисту нужен не код, а что это значит.
export const KIND_PLAIN = {
  ambiguous: ['Читается двояко', 'Разные студенты и ревьюеры поймут по-разному — баллы будут несправедливыми.'],
  underspecified: ['Не хватает деталей', 'Ревьюер не сможет поставить балл однозначно.'],
  gameable: ['Можно выполнить формально', 'Слабое решение наберёт максимум, обойдя смысл.'],
  overlapping: ['Критерии пересекаются', 'Один и тот же аспект оценивается дважды.'],
  unmeasurable: ['Субъективная формулировка', '«Хорошо / качественно» без порогов — каждый понимает по-своему.'],
  missing_criterion: ['Аспект задания не покрыт', 'Важную часть работы никто не оценит.'],
  inconsistent_scoring: ['Не различает уровни', 'Сильная и слабая работа получают одинаковый балл.'],
  weight_imbalance: ['Вес не по важности', 'Второстепенное весит больше ключевого.'],
  scope_creep: ['Требует того, чего нет в условии', 'Студент не мог знать об этом требовании.'],
  unfair_hidden: ['Скрытое ожидание', 'Рубрика требует того, чего студенту не сказали.'],
  leaky_public: ['Публичная часть раскрывает грейдинг', 'Можно подогнать ответ без реальной работы.'],
}

export const kindLabel = (kind) => KIND_PLAIN[kind]?.[0] || 'Замечание к формулировке'
export const kindWhy = (kind) => KIND_PLAIN[kind]?.[1] || ''

// --- список ----------------------------------------------------------------

export function splitByPublication(rows) {
  return {
    published: (rows || []).filter(r => r.published),
    drafts: (rows || []).filter(r => !r.published),
  }
}

export function filterAssignments(rows, query) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return rows || []
  return (rows || []).filter(r =>
    (r.title || '').toLowerCase().includes(q) || (r.course || '').toLowerCase().includes(q))
}

export function sortAssignments(rows, mode) {
  const list = [...(rows || [])]
  if (mode === 'title') return list.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'ru'))
  if (mode === 'checked') {
    // Сначала то, что давно не проверяли: непроверенное — самое срочное.
    const stamp = (r) => (r.last_run?.completed_at ? Date.parse(r.last_run.completed_at) : 0)
    return list.sort((a, b) => stamp(a) - stamp(b))
  }
  return list
}

// --- арифметика баллов -----------------------------------------------------

export const criteriaTotal = (criteria) =>
  (criteria || []).reduce((sum, c) => sum + (Number(c.max_score) || 0), 0)

export function scoreWarning(criteria, passScore) {
  const rows = criteria || []
  if (!rows.length) return 'Добавьте хотя бы один критерий.'
  if (rows.some(c => !(Number(c.max_score) > 0))) return 'У каждого критерия должен быть балл больше нуля.'
  const total = criteriaTotal(rows)
  if (Number(passScore) > total) return `Проходной балл ${passScore} больше максимума ${total}.`
  return ''
}

// --- редактор --------------------------------------------------------------

// Блоки, которые умеет заполнять AI. `field` совпадает с ключом на бэкенде,
// иначе «Применить» из рекомендации попадёт не в то поле.
export const AI_BLOCKS = [
  { field: 'statement', title: 'Условие задания' },
  { field: 'context', title: 'Контекст' },
  { field: 'expected_result', title: 'Ожидаемый результат' },
  { field: 'constraints', title: 'Ограничения' },
]

export const FIELD_TITLES = Object.fromEntries([
  ...AI_BLOCKS.map(b => [b.field, b.title]),
  ['student_hint', 'Подсказка студенту'],
  ['criteria', 'Критерии'],
])

export const fieldTitle = (field) => FIELD_TITLES[field] || field

export function isDirty(draft, saved) {
  return JSON.stringify(draft) !== JSON.stringify(saved)
}

export function publishBlockers(draft) {
  const blockers = []
  if (!(draft.title || '').trim()) blockers.push('название')
  if (!(draft.statement || '').trim()) blockers.push('условие')
  if (!(draft.criteria || []).length) blockers.push('хотя бы один критерий')
  const warning = scoreWarning(draft.criteria, draft.pass_score)
  if (warning && (draft.criteria || []).length) blockers.push('корректные баллы критериев')
  return blockers
}

// --- прогон ----------------------------------------------------------------

export function runTitle(run) {
  if (!run) return 'Проверка не запускалась'
  return `${PERSONA_TYPE[run.persona_type] || run.persona_type} · ${RUN_STATE[run.status]?.[0] || run.status}`
}

export function openRecommendations(run) {
  return (run?.recommendations || []).filter(r => r.status === 'new')
}

export function decidedRecommendations(run) {
  return (run?.recommendations || []).filter(r => r.status !== 'new')
}

// Один прогон отвечает на один вопрос — заголовок обязан это называть, иначе
// два разных разбора на экране выглядят одинаково.
export function runIntro(personaType) {
  if (personaType === 'student') {
    return 'AI-студенты разного уровня решали задание, видя только то, что видит студент. Показано, где постановка читается по-разному и каких данных не хватило.'
  }
  if (personaType === 'both') {
    return `AI-студенты разного уровня решили задание, а AI-ревьюеры оценили их решения по вашим критериям. Показано и где расходится понимание задания, и где расходятся оценки. ${SOLUTIONS_NOTE}`
  }
  return `AI-ревьюеры применяли критерии к решениям разного качества. Показано, где оценки расходятся и какие формулировки не позволяют поставить балл однозначно. ${SOLUTIONS_NOTE}`
}

// Что именно даёт повторная оценка одного и того же решения.
export function samplingNote(samples) {
  if (!samples || samples < 2) return ''
  return `Каждое решение оценено ${samples} раз(а) по одной и той же рубрике: так видно разброс самой модели — если баллы гуляют, дело не в работе студента, а в формулировке критерия.`
}
