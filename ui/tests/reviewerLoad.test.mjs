/**
 * Подписи загрузки ревьюера.
 *
 * Числа здесь два — работы и трудоёмкость, — и весь смысл этого модуля в том,
 * чтобы их больше не путали местами. Проверяется склонение (иначе «3 работа»),
 * дробная сумма весов и то, что полоска не вылезает за свои сто процентов.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { effort, fill, summary, works } from '../src/shared/reviewerLoad.js'

describe('склонение после числительного', () => {
  it('единица', () => assert.equal(works(1), '1 работа'))
  it('двойка-четвёрка', () => {
    assert.equal(works(2), '2 работы')
    assert.equal(works(4), '4 работы')
  })
  it('пять и больше', () => {
    assert.equal(works(5), '5 работ')
    assert.equal(works(20), '20 работ')
  })
  it('подростковые числа — исключение', () => {
    assert.equal(works(11), '11 работ')
    assert.equal(works(12), '12 работ')
    assert.equal(works(14), '14 работ')
    assert.equal(works(114), '114 работ')
  })
  it('двадцать один — снова единственное', () => assert.equal(works(21), '21 работа'))
  it('ноль работ — это тоже ответ', () => assert.equal(works(0), '0 работ'))
  it('пустое значение не превращается в NaN', () => {
    assert.equal(works(undefined), '0 работ')
    assert.equal(works(null), '0 работ')
  })
})

describe('трудоёмкость против лимита', () => {
  it('дробная сумма весов — законное значение', () => {
    assert.equal(effort({ load: 3.7, capacity: 20 }), '3.7 из 20')
  })
  it('двоичный хвост суммы не доезжает до экрана', () => {
    assert.equal(effort({ load: 0.1 + 0.2 + 0.4, capacity: 12 }), '0.7 из 12')
  })
  it('без лимита показывается одна загрузка', () => {
    assert.equal(effort({ load: 2 }), '2')
  })
})

describe('строка целиком', () => {
  it('называет обе величины и не даёт их перепутать', () => {
    const line = summary({ active_count: 3, load: 3.7, capacity: 20 })
    assert.equal(line, '3 работы · 3.7 из 20 по трудоёмкости')
  })
})

describe('полоска заполнения', () => {
  it('считает долю лимита', () => assert.equal(fill({ load: 5, capacity: 20 }), 25))
  it('перегрузка не рисуется длиннее полоски', () => {
    assert.equal(fill({ load: 40, capacity: 20 }), 100)
  })
  it('нулевой лимит не делит на ноль', () => assert.equal(fill({ load: 3, capacity: 0 }), 0))
})
