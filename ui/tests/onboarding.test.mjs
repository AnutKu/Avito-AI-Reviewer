/**
 * Знакомство с кабинетом.
 *
 * Проверяется главным образом «один раз»: показать проводку повторно при каждом
 * входе — назойливо, а уронить кабинет из-за недоступного localStorage (частное
 * окно, запрет на данные сайта) — недопустимо. Плюс содержание: у каждой роли
 * своё, у чужой роли — пусто, без выдуманных шагов.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { beforeEach, describe, it } from 'node:test'

import { ONBOARDING, markSeen, shouldShow, stepsFor, titleFor, wasSeen } from '../src/shared/onboarding.js'

// Хранилища в node нет — подменяем его тем, что ведёт себя как браузерное.
function useStorage(impl) { globalThis.localStorage = impl }
function memoryStorage() {
  const map = new Map()
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
  }
}
const throwingStorage = {
  getItem() { throw new DOMException('denied') },
  setItem() { throw new DOMException('denied') },
}

describe('содержание проводки', () => {
  it('покрывает все три роли кабинета', () => {
    assert.deepEqual(Object.keys(ONBOARDING).sort(), ['methodist', 'reviewer', 'student'])
  })

  it('в каждом шаге есть значок, заголовок и объяснение', () => {
    for (const [role, block] of Object.entries(ONBOARDING)) {
      assert.ok(block.steps.length >= 3, `${role}: слишком короткая проводка`)
      for (const [icon, title, text] of block.steps) {
        assert.ok(icon && title, `${role}: шаг без значка или заголовка`)
        // Шаг должен объяснять, а не называть раздел ещё раз.
        assert.ok(text.length > 40, `${role}: пустое объяснение «${title}»`)
      }
    }
  })

  it('о незнакомой роли ничего не выдумывает', () => {
    useStorage(memoryStorage())
    assert.deepEqual(stepsFor('admin'), [])
    assert.equal(shouldShow('admin'), false)
    assert.equal(shouldShow(undefined), false)
    assert.ok(titleFor('admin'))
  })
})

describe('показ при первом входе', () => {
  beforeEach(() => useStorage(memoryStorage()))

  it('показывается один раз на роль', () => {
    assert.equal(shouldShow('student'), true)
    markSeen('student')
    assert.equal(shouldShow('student'), false)
  })

  it('роли не мешают друг другу: демо-вход бывает под любой', () => {
    markSeen('student')
    assert.equal(shouldShow('reviewer'), true)
    markSeen('reviewer')
    assert.deepEqual(['student', 'reviewer', 'methodist'].map(wasSeen), [true, true, false])
  })

  it('повторная отметка не плодит записей', () => {
    markSeen('methodist'); markSeen('methodist')
    assert.equal(localStorage.getItem('avito-onboarding-seen'), 'methodist')
  })
})

describe('недоступное хранилище', () => {
  it('не роняет кабинет, а показывает проводку заново', () => {
    useStorage(throwingStorage)
    assert.equal(wasSeen('student'), false)
    assert.doesNotThrow(() => markSeen('student'))
    assert.equal(shouldShow('student'), true)
  })
})
