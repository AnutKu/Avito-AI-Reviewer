/**
 * Формулы из ответа модели.
 *
 * Опорный пример — настоящий, из поля context_md реального задания
 * конструктора: именно он показывался в кабинете сырым латехом.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { renderLatex, replaceMath } from '../src/shared/latex.js'
import { renderMarkdown } from '../src/shared/markdown.js'

const ROMI =
  '$$\\text{ROMI} = \\frac{\\text{Выручка от маркетинга} - \\text{Маркетинговый бюджет}}' +
  '{\\text{Маркетинговый бюджет}} \\times 100\\%$$'

describe('разбор формулы', () => {
  it('формула ROMI из настоящего задания читается словами', () => {
    assert.equal(
      renderMarkdown(ROMI),
      '<p><span class="md-math md-math--block">ROMI = ' +
        '(Выручка от маркетинга − Маркетинговый бюджет) / Маркетинговый бюджет' +
        ' × 100%</span></p>',
    )
  })

  it('дробь без операторов внутри обходится без скобок', () => {
    assert.equal(renderLatex('\\frac{a}{b}'), 'a / b')
  })

  it('дробь с операторами получает скобки, иначе смысл меняется', () => {
    assert.equal(renderLatex('\\frac{a - b}{c}'), '(a − b) / c')
  })

  it('вложенная дробь разбирается целиком', () => {
    assert.equal(renderLatex('\\frac{\\frac{a}{b}}{c}'), '(a / b) / c')
  })

  it('индексы и степени становятся sub и sup', () => {
    assert.equal(renderLatex('x_i^2'), 'x<sub>i</sub><sup>2</sup>')
  })

  it('знаки заменяются, экранированный процент остаётся процентом', () => {
    assert.equal(renderLatex('a \\times b \\le 100\\%'), 'a × b ≤ 100%')
  })

  it('неизвестная команда теряет слэш, а не съедает строку', () => {
    assert.equal(renderLatex('\\qquad x'), 'qquad x')
  })

  it('незакрытая скобка не роняет разбор', () => {
    assert.equal(renderLatex('\\frac{a}{b'), 'frac a b')
  })
})

describe('где формула начинается', () => {
  it('строчная формула в скобках \\( \\) тоже разбирается', () => {
    assert.equal(
      renderMarkdown('Формула \\(x^2\\) внутри строки.'),
      '<p>Формула <span class="md-math">x<sup>2</sup></span> внутри строки.</p>',
    )
  })

  it('цена в долларах формулой не считается', () => {
    // Одиночные доллары вокруг обычного текста — почти всегда деньги.
    assert.equal(
      renderMarkdown('Бюджет $100 в месяц и ещё $200 сверху.'),
      '<p>Бюджет $100 в месяц и ещё $200 сверху.</p>',
    )
  })

  it('формула в обратных кавычках остаётся кодом, как её написали', () => {
    assert.equal(
      renderMarkdown('`$x^2$`'),
      '<p><code>$x^2$</code></p>',
    )
  })

  it('подчёркивание в индексе не превращается в курсив', () => {
    const html = renderMarkdown('$x_1 + x_2$')

    assert.ok(!html.includes('<em>'), html)
    assert.ok(html.includes('<sub>1</sub>'), html)
  })
})

describe('безопасность', () => {
  it('тег внутри формулы остаётся текстом', () => {
    const html = renderMarkdown('$$<script>alert(1)</script>$$')

    assert.ok(!html.includes('<script'), html)
    assert.ok(html.includes('&lt;script&gt;'), html)
  })

  it('формулы не открывают путь новым тегам, кроме sup, sub и span', () => {
    const html = renderMarkdown('$$\\text{<img src=x onerror="alert(1)">}$$')

    assert.ok(!html.includes('<img'), html)
    assert.ok(!/onerror="/.test(html), html)
  })

  it('замена происходит только на месте разделителей', () => {
    const seen = []
    replaceMath('a $$x$$ b', (rendered, block) => {
      seen.push([rendered, block])
      return 'M'
    })

    assert.deepEqual(seen, [['x', true]])
  })
})
