// Чистая логика кабинета студента: порядок списка заданий и ближайший срок.
// Без Vue и без сети — чтобы это проверялось тестами, а не кликами.

/**
 * Что студенту делать с заданием. Три состояния, а не семь статусов работы:
 * студенту важно не то, назначен ли ревьюер, а его собственный следующий шаг.
 */
export const STAGES = ['not_submitted', 'in_review', 'completed']

export function assignmentStage(item) {
  if (!item || !item.submission) return 'not_submitted'
  return item.submission.status === 'completed' ? 'completed' : 'in_review'
}

/**
 * Порядок списка: несданные → непроверенные → проверенные.
 *
 * Наверху то, что ещё требует действия студента, внизу — то, что уже закрыто.
 * Внутри группы порядок сохраняется тот, что пришёл с сервера (по дедлайну):
 * сортировка в JS стабильна, поэтому второй ключ не нужен.
 */
export function orderAssignments(items) {
  return [...(items || [])].sort(
    (a, b) => STAGES.indexOf(assignmentStage(a)) - STAGES.indexOf(assignmentStage(b)),
  )
}

const DAY = 24 * 60 * 60 * 1000

/** «1 день», «2 дня», «5 дней» — иначе счётчик читается как машинный вывод. */
export function plural(count, [one, few, many]) {
  const tens = Math.abs(count) % 100
  const units = tens % 10
  if (tens > 10 && tens < 20) return many
  if (units > 1 && units < 5) return few
  return units === 1 ? one : many
}

function stamp(item) {
  const value = new Date(item.deadline_at).getTime()
  return Number.isNaN(value) ? null : value
}

/**
 * Ближайший срок среди несданных заданий — то, что стоит подсветить наверху.
 *
 * Сданное сюда не попадает: напоминать о сроке работы, которая уже отправлена,
 * незачем. Просроченное берётся только если впереди вообще ничего нет — иначе
 * пропущенный месяц назад дедлайн перекрывал бы живой срок через три дня.
 *
 * @returns {{ assignment: object, state: string, days: number, text: string }|null}
 * `state`: `overdue` — срок прошёл, `today` — меньше суток, `soon` — до трёх
 * суток, `calm` — время ещё есть.
 */
export function nearestDeadline(items, now = Date.now()) {
  const pending = (items || []).filter(
    item => assignmentStage(item) === 'not_submitted' && item.deadline_at && stamp(item) !== null,
  )
  if (!pending.length) return null

  const ahead = pending.filter(item => stamp(item) > now)
  // Впереди — самый ранний срок; позади — самый поздний, то есть последний
  // пропущенный, а не первый за всю историю курса.
  const pick = (rows, sign) => rows.reduce((best, item) => (sign * (stamp(item) - stamp(best)) < 0 ? item : best))
  const assignment = ahead.length ? pick(ahead, 1) : pick(pending, -1)

  const left = stamp(assignment) - now
  if (left <= 0) {
    const days = Math.floor(-left / DAY)
    return {
      assignment,
      state: 'overdue',
      days,
      text: days
        ? `Дедлайн прошёл ${days} ${plural(days, ['день', 'дня', 'дней'])} назад`
        : 'Дедлайн прошёл сегодня',
    }
  }

  const days = Math.floor(left / DAY)
  return {
    assignment,
    state: days < 1 ? 'today' : days <= 3 ? 'soon' : 'calm',
    days,
    text: days
      ? `До ближайшего дедлайна осталось ${days} ${plural(days, ['день', 'дня', 'дней'])}`
      : 'До ближайшего дедлайна осталось меньше суток',
  }
}
