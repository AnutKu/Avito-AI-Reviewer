/**
 * Правила вёрстки, которые могут поймать чужой текст.
 *
 * Строчный markdown вставляется в кабинет как <span class="md"> внутрь чужой
 * разметки — в заголовок, в ячейку, в подпись. Правило вида «.карточка span»
 * написано ради своего значка, но потомком ловит и этот span. Так название
 * критерия в кабинете студента превратилось в зелёный кружок 23×23 и
 * посыпалось по одному символу в строку: ни тесты, ни сборка этого не видели.
 *
 * Здесь проверяется само правило: если селектор заканчивается голым `span`
 * через потомка и задаёт геометрию — он поймает разметку. Нужен прямой
 * потомок.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// Комментарии убираются до разбора: иначе они приклеиваются к следующему
// селектору и правило перестаёт находиться по имени.
const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8')
  .replace(/\/\*[\s\S]*?\*\//g, '')

const RULES = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
  selectors: selector.split(',').map(one => one.trim()).filter(Boolean),
  body: body.trim(),
}))

// Свойства, которые превращают текст в коробку.
const BOXY = /(^|;)\s*(width|height|display\s*:\s*(grid|flex)|border-radius)\s*:/

/** Селектор заканчивается на `span`, доставшийся по потомку, а не прямому ребёнку. */
const catchesNestedSpan = (selector) =>
  /\sspan$/.test(selector) && !/>\s*span$/.test(selector)

describe('правила не должны ловить строчную разметку', () => {
  it('в файле вообще разобрались правила', () => {
    assert.ok(RULES.length > 100, 'не удалось разобрать style.css')
  })

  it('ни одно правило не задаёт геометрию вложенному span', () => {
    const guilty = []
    for (const rule of RULES) {
      if (!BOXY.test(rule.body)) continue
      for (const selector of rule.selectors) {
        if (catchesNestedSpan(selector)) guilty.push(`${selector} { ${rule.body.slice(0, 60)}… }`)
      }
    }
    assert.deepEqual(
      guilty,
      [],
      'эти правила поймают <span class="md"> и сломают текст; нужен прямой потомок:\n  ' +
        guilty.join('\n  '),
    )
  })

  it('строчной разметке возвращён обычный вид', () => {
    const reset = RULES.find(rule => rule.selectors.includes('span.md'))
    assert.ok(reset, 'нет правила span.md, которое снимает чужую геометрию')
    for (const property of ['display', 'width', 'height', 'background', 'color']) {
      assert.match(reset.body, new RegExp(`${property}\\s*:`), `span.md не сбрасывает ${property}`)
    }
  })
})

describe('сам сторож', () => {
  it('отличает потомка от прямого ребёнка', () => {
    assert.equal(catchesNestedSpan('.card span'), true)
    assert.equal(catchesNestedSpan('.card > span'), false)
    assert.equal(catchesNestedSpan('.card >span'), false)
    assert.equal(catchesNestedSpan('.card span.md'), false)
    assert.equal(catchesNestedSpan('span'), false)
  })
})
