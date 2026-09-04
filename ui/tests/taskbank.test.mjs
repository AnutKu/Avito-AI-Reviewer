/**
 * Логика объединённого банка заданий.
 *
 * Здесь проверяется то, что решает поведение экрана, а не его вид: как задания
 * раскладываются по вкладкам, что считается незаполненным перед публикацией,
 * и почему статус публикации нельзя путать с состоянием AI-прогона.
 *
 * Запуск: npm test из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  criteriaTotal,
  filterAssignments,
  isDirty,
  kindLabel,
  openRecommendations,
  publishBlockers,
  runIntro,
  runTitle,
  scoreWarning,
  sortAssignments,
  splitByPublication,
} from '../src/shared/taskbank.js'
import { parseHash } from '../src/shared/route.js'

const ROWS = [
  { id: '1', title: 'Кейс по оттоку', course: 'Аналитика', published: true, last_run: { status: 'completed', persona_type: 'reviewer', completed_at: '2026-09-02T10:00:00Z' } },
  { id: '2', title: 'Метрики подписки', course: 'Аналитика', published: false, last_run: null },
  { id: '3', title: 'Пул воркеров', course: 'Backend', published: false, last_run: { status: 'failed', persona_type: 'student', completed_at: '2026-09-01T10:00:00Z' } },
]

describe('список', () => {
  it('вкладки делят задания по факту публикации', () => {
    const { published, drafts } = splitByPublication(ROWS)
    assert.deepEqual(published.map(r => r.id), ['1'])
    assert.deepEqual(drafts.map(r => r.id), ['2', '3'])
  })

  it('пустой банк не ломает раскладку', () => {
    assert.deepEqual(splitByPublication(undefined), { published: [], drafts: [] })
  })

  it('поиск ищет и по названию, и по курсу', () => {
    assert.deepEqual(filterAssignments(ROWS, 'воркер').map(r => r.id), ['3'])
    assert.deepEqual(filterAssignments(ROWS, 'backend').map(r => r.id), ['3'])
  })

  it('пустой запрос ничего не отфильтровывает', () => {
    assert.equal(filterAssignments(ROWS, '   ').length, 3)
  })

  it('сортировка «давно не проверяли» поднимает непроверенное наверх', () => {
    assert.deepEqual(sortAssignments(ROWS, 'checked').map(r => r.id), ['2', '3', '1'])
  })

  it('состояние прогона не подменяет статус публикации', () => {
    // Черновик может быть проверен, опубликованное — ни разу не проверено.
    // Поэтому это два разных поля и два разных индикатора.
    const draftChecked = { published: false, last_run: { status: 'completed', persona_type: 'student' } }
    assert.equal(draftChecked.published, false)
    assert.match(runTitle(draftChecked.last_run), /AI-студенты · проверено/)
    assert.equal(runTitle(null), 'Проверка не запускалась')
  })
})

describe('баллы', () => {
  it('максимум — сумма критериев', () => {
    assert.equal(criteriaTotal([{ max_score: 4 }, { max_score: 6 }]), 10)
  })

  it('проходной балл выше максимума — предупреждение', () => {
    assert.match(scoreWarning([{ max_score: 4 }], 6), /больше максимума/)
  })

  it('нулевой балл критерия ловится отдельно', () => {
    assert.match(scoreWarning([{ max_score: 0 }], 0), /больше нуля/)
  })

  it('корректная рубрика молчит', () => {
    assert.equal(scoreWarning([{ max_score: 4 }, { max_score: 6 }], 6), '')
  })
})

describe('редактор', () => {
  it('несохранённые изменения видны', () => {
    const saved = { title: 'A', criteria: [] }
    assert.equal(isDirty({ ...saved }, saved), false)
    assert.equal(isDirty({ ...saved, title: 'B' }, saved), true)
  })

  it('перед публикацией называются все незаполненные блоки сразу', () => {
    const blockers = publishBlockers({ title: '', statement: '', criteria: [] })
    assert.deepEqual(blockers, ['название', 'условие', 'хотя бы один критерий'])
  })

  it('заполненный черновик публикуется без замечаний', () => {
    const ok = { title: 'Кейс', statement: 'Условие', criteria: [{ max_score: 5 }], pass_score: 3 }
    assert.deepEqual(publishBlockers(ok), [])
  })
})

describe('прогон', () => {
  it('разбор объясняет, что именно проверяли', () => {
    assert.match(runIntro('student'), /видя только то, что видит студент/)
    assert.match(runIntro('reviewer'), /оценки расходятся/)
    assert.notEqual(runIntro('student'), runIntro('reviewer'))
  })

  it('решённые рекомендации уходят из списка открытых', () => {
    const run = { recommendations: [{ status: 'new' }, { status: 'applied' }, { status: 'rejected' }] }
    assert.equal(openRecommendations(run).length, 1)
  })

  it('незнакомый код находки всё равно называется по-человечески', () => {
    assert.equal(kindLabel('unmeasurable'), 'Субъективная формулировка')
    assert.equal(kindLabel('что-то новое'), 'Замечание к формулировке')
  })
})

describe('маршруты', () => {
  it('раздел берётся из первого сегмента, остальное отдаётся разделу', () => {
    assert.deepEqual(parseHash('#methodist-rubrics'), { page: 'methodist-rubrics', sub: [], redirectTo: null })
    assert.deepEqual(parseHash('#methodist-rubrics/new').sub, ['new'])
    assert.deepEqual(parseHash('#methodist-rubrics/run/abc-123').sub, ['run', 'abc-123'])
  })

  it('старая ссылка AI-конструктора ведёт в объединённый банк', () => {
    const route = parseHash('#methodist-taskcreater')
    assert.equal(route.page, 'methodist-rubrics')
    assert.equal(route.redirectTo, 'methodist-rubrics')
  })

  it('редирект сохраняет хвост адреса', () => {
    assert.equal(parseHash('#methodist-taskcreater/new').redirectTo, 'methodist-rubrics/new')
  })

  it('пустой и мусорный хеш не роняют разбор', () => {
    assert.deepEqual(parseHash(''), { page: '', sub: [], redirectTo: null })
    assert.deepEqual(parseHash('#///'), { page: '', sub: [], redirectTo: null })
    assert.deepEqual(parseHash(undefined), { page: '', sub: [], redirectTo: null })
  })

  it('живой раздел не редиректится', () => {
    assert.equal(parseHash('#methodist-performance').redirectTo, null)
  })
})
