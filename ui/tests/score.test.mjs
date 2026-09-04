/**
 * Суммарный балл за работу.
 *
 * Главное здесь — что показанное число совпадает с тем, что выставит сервер
 * при публикации: ревьюер принимает решение о баллах, глядя ровно на него.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { reviewTotals } from '../src/shared/score.js'

const decided = (final, max) => ({ reviewer_action: 'accepted', ai_score: final, final_score: final, max_score: max })
const pending = (ai, max) => ({ reviewer_action: 'pending', ai_score: ai, final_score: null, max_score: max })

describe('сумма по критериям', () => {
  it('решённые критерии дают ту же сумму, что выставит публикация', () => {
    const totals = reviewTotals([decided(3, 3), decided(1.5, 2), decided(0, 2)])

    assert.equal(totals.score, 4.5)
    assert.equal(totals.pending, 0)
    assert.equal(totals.decided, 3)
  })

  it('по нерешённому критерию в сумму идёт оценка AI', () => {
    // Иначе только что открытая работа показывала бы 0 — это читается как
    // «решение плохое», а не «решения ревьюера пока нет».
    const totals = reviewTotals([decided(3, 3), pending(2, 3)])

    assert.equal(totals.score, 5)
    assert.equal(totals.pending, 1)
  })

  it('отклонённый критерий приносит ноль, а не оценку AI', () => {
    const totals = reviewTotals([
      { reviewer_action: 'rejected', ai_score: 3, final_score: 0, max_score: 3 },
    ])

    assert.equal(totals.score, 0)
    assert.equal(totals.pending, 0)
  })

  it('дробные баллы не расползаются в двоичной дроби', () => {
    const totals = reviewTotals([decided(0.1, 1), decided(0.2, 1)])

    assert.equal(totals.score, 0.3)
  })

  it('максимум считается по критериям — на случай ревью без рубрики', () => {
    const totals = reviewTotals([pending(1, 3), pending(2, 7)])

    assert.equal(totals.max_score, 10)
  })

  it('пустой разбор не притворяется нулевым баллом', () => {
    const totals = reviewTotals([])

    assert.equal(totals.total, 0)
    assert.equal(totals.score, 0)
    assert.deepEqual(reviewTotals(null), reviewTotals([]))
  })
})
