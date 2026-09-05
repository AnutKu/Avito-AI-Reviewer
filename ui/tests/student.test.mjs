/**
 * Кабинет студента: порядок списка и ближайший срок.
 *
 * Главное здесь — что наверху списка оказывается то, что студент ещё не сдал,
 * а подсвеченный срок относится к живому дедлайну, а не к пропущенному месяц
 * назад.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { nearestDeadline, orderAssignments, plural } from '../src/shared/student.js'

const DAY = 24 * 60 * 60 * 1000
const NOW = Date.parse('2026-09-05T12:00:00Z')
const at = (days) => new Date(NOW + days * DAY).toISOString()

const task = (title, { days = 10, status = null } = {}) => ({
  id: title,
  title,
  deadline_at: at(days),
  submission: status ? { id: `s-${title}`, status } : null,
})

describe('порядок заданий', () => {
  it('несданные идут перед непроверенными, непроверенные — перед проверенными', () => {
    const rows = [
      task('проверенная', { status: 'completed' }),
      task('на проверке', { status: 'in_review' }),
      task('несданная'),
    ]

    assert.deepEqual(orderAssignments(rows).map(r => r.title), ['несданная', 'на проверке', 'проверенная'])
  })

  it('внутри группы сохраняется порядок сервера — по дедлайну', () => {
    const rows = [task('раньше', { days: 1 }), task('позже', { days: 5 }), task('сдана', { status: 'submitted' })]

    assert.deepEqual(orderAssignments(rows).map(r => r.title), ['раньше', 'позже', 'сдана'])
  })

  it('любой статус, кроме completed, — это «на проверке», а не «сдавать»', () => {
    const rows = ['submitted', 'proposed', 'assigned', 'in_review', 'blitz_sent', 'blitz_answered']
      .map(status => task(status, { status }))

    assert.deepEqual(orderAssignments([...rows, task('несданная')])[0].title, 'несданная')
  })

  it('исходный массив не меняется', () => {
    const rows = [task('сдана', { status: 'completed' }), task('несданная')]
    orderAssignments(rows)

    assert.equal(rows[0].title, 'сдана')
  })
})

describe('ближайший дедлайн', () => {
  it('считает дни до самого раннего несданного задания', () => {
    const highlight = nearestDeadline([task('через 5 дней', { days: 5 }), task('через 2 дня', { days: 2 })], NOW)

    assert.equal(highlight.assignment.title, 'через 2 дня')
    assert.equal(highlight.days, 2)
    assert.equal(highlight.text, 'До ближайшего дедлайна осталось 2 дня')
  })

  it('меньше суток — не «0 дней»', () => {
    const highlight = nearestDeadline([task('сегодня', { days: 0.5 })], NOW)

    assert.equal(highlight.state, 'today')
    assert.equal(highlight.text, 'До ближайшего дедлайна осталось меньше суток')
  })

  it('сданные задания срок не подсвечивают', () => {
    const rows = [task('сдана завтра', { days: 1, status: 'submitted' }), task('несданная', { days: 6 })]

    assert.equal(nearestDeadline(rows, NOW).assignment.title, 'несданная')
  })

  it('живой срок важнее пропущенного', () => {
    const rows = [task('пропущенная', { days: -30 }), task('через 3 дня', { days: 3 })]

    assert.equal(nearestDeadline(rows, NOW).assignment.title, 'через 3 дня')
    assert.equal(nearestDeadline(rows, NOW).state, 'soon')
  })

  it('если впереди ничего нет — показывает последний пропущенный', () => {
    const rows = [task('давняя', { days: -30 }), task('свежая', { days: -2 })]
    const highlight = nearestDeadline(rows, NOW)

    assert.equal(highlight.assignment.title, 'свежая')
    assert.equal(highlight.state, 'overdue')
    assert.equal(highlight.text, 'Дедлайн прошёл 2 дня назад')
  })

  it('нечего подсвечивать, когда всё сдано или сроков нет', () => {
    assert.equal(nearestDeadline([task('сдана', { status: 'completed' })], NOW), null)
    assert.equal(nearestDeadline([{ id: 'x', title: 'без срока', deadline_at: null, submission: null }], NOW), null)
    assert.equal(nearestDeadline([], NOW), null)
  })
})

describe('склонение', () => {
  it('день, дня, дней', () => {
    const forms = ['день', 'дня', 'дней']
    assert.deepEqual([1, 2, 5, 11, 21, 22, 25].map(n => plural(n, forms)),
      ['день', 'дня', 'дней', 'дней', 'день', 'дня', 'дней'])
  })
})
