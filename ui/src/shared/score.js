/**
 * Суммарный балл за работу — из решений по критериям.
 *
 * Складывать умеет только эта функция, и складывает она то же, что сложит
 * сервер при публикации (`sum(final_score)`), с одной оговоркой: пока решения
 * по критерию нет, в сумму идёт оценка AI. Иначе первое же открытие работы
 * показывало бы ноль из десяти — не «пока не решено», а «работа плохая».
 *
 * Отсюда и разделение в результате: `pending` — это ровно то, чем итог
 * отличается от предварительного балла, и экран обязан об этом сказать.
 */

/** Копейки в баллах не нужны, а 0.1 + 0.2 в двоичной дроби — нужны. */
function round(value) {
  return Math.round(value * 100) / 100
}

export function reviewTotals(items) {
  const rows = Array.isArray(items) ? items : []
  let score = 0
  let decided = 0
  let maximum = 0
  for (const item of rows) {
    const settled = Boolean(item.reviewer_action) && item.reviewer_action !== 'pending'
    if (settled) decided += 1
    score += Number(settled ? item.final_score : item.ai_score) || 0
    maximum += Number(item.max_score) || 0
  }
  return {
    score: round(score),
    // Знаменатель ревью приходит с сервера (рубрика), но если его нет —
    // сумма максимумов по критериям это та же величина, а не догадка.
    max_score: round(maximum),
    decided,
    pending: rows.length - decided,
    total: rows.length,
  }
}
