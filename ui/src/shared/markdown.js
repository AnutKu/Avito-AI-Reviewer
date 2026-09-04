/**
 * Markdown от модели — в HTML, безопасно по построению.
 *
 * Текст сюда приходит из ответа LLM, а он построен по репозиторию студента:
 * что угодно из чужого ноутбука может оказаться пересказанным в summary или
 * recommendation. Поэтому здесь нет и не должно появиться прохода «сырой HTML
 * как есть» — даже с санитайзером. Порядок обратный: сначала экранируется
 * ВСЁ, и только потом из экранированного текста собирается разметка по белому
 * списку. Худшее, что может случиться при промахе разбора, — кусок покажется
 * обычным текстом; вставить тег или обработчик через этот путь нельзя.
 *
 * Поддерживается намеренно урезанный набор: заголовки, списки, цитаты, блоки
 * и вставки кода, жирный, курсив, ссылки на http(s). Таблиц нет — модель их
 * почти не пишет, а разбор таблиц больше всего остального вместе взятого.
 * Неподдержанное остаётся видимым текстом, а не пропадает.
 */

// С расширением: этот модуль гоняется не только сборщиком, но и node --test,
// а node разрешает только точные пути.
import { replaceMath } from './latex.js'

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

// Метки вынутых кусков. Нужны символы, которых во входном тексте не бывает:
// слово вроде «code» встречается в обычной прозе и меткой служить не может.
const CODE_MARK = '\u0000'
const MATH_MARK = '\u0001'

export function escapeHtml(text) {
  // Метка вычищается из входа до разбора — иначе её можно было бы подсунуть
  // и подменить содержимое чужой вставки кода.
  return String(text ?? '')
    .replace(/[\u0000\u0001]/g, '')
    .replace(/[&<>"']/g, (char) => ESCAPES[char])
}

// Ссылки: только http и https. javascript:, data: и прочие схемы — способ
// выполнить чужой код по клику ревьюера, а модель может процитировать любую
// строку из решения. Не прошедшее остаётся текстом, как было написано.
function safeHref(url) {
  const trimmed = url.trim()
  return /^https?:\/\/[^\s]+$/i.test(trimmed) ? trimmed : null
}

function inline(escaped) {
  // Код и формулы вынимаются до остальных правил и возвращаются после: внутри
  // `**` — это звёздочки, а не выделение, а `x_i` в формуле — индекс, а не
  // курсив. Код идёт первым: `$x$` в обратных кавычках остаётся как написан.
  const codes = []
  let text = escaped.replace(/`([^`]+)`/g, (_, code) => {
    codes.push(code)
    return CODE_MARK
  })

  const formulas = []
  text = replaceMath(text, (rendered, block) => {
    formulas.push(
      `<span class="md-math${block ? ' md-math--block' : ''}">${rendered}</span>`,
    )
    return MATH_MARK
  })

  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (whole, label, url) => {
    const href = safeHref(url)
    return href
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : whole
  })
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  text = text.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  text = text.replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>')

  text = text.replace(/\u0001/g, () => formulas.shift())
  return text.replace(/\u0000/g, () => `<code>${codes.shift()}</code>`)
}

const HEADING = /^(#{1,6})\s+(.*)$/
const BULLET = /^\s*[-*+]\s+(.*)$/
const ORDERED = /^\s*\d+[.)]\s+(.*)$/
const QUOTE = /^\s*>\s?(.*)$/
const RULE = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/
const FENCE = /^\s*```/

/** Одна строка markdown → HTML. Блоков не делает: для подписей и заголовков. */
export function renderInline(text) {
  return inline(escapeHtml(text))
}

/**
 * Полный текст → HTML-блоки.
 *
 * Заголовки намеренно не становятся h1–h6: в кабинете эти теги — каркас
 * страницы со своими размерами, и заголовок из ответа модели ломал бы
 * иерархию экрана. Уровень остаётся в data-атрибуте, вид задаёт CSS.
 */
export function renderMarkdown(text) {
  const source = String(text ?? '').replace(/\r\n?/g, '\n')
  if (!source.trim()) return ''

  const lines = source.split('\n')
  const out = []
  let paragraph = []
  let list = null // { tag, items }

  const flushParagraph = () => {
    if (!paragraph.length) return
    out.push(`<p>${inline(escapeHtml(paragraph.join(' ')))}</p>`)
    paragraph = []
  }
  const flushList = () => {
    if (!list) return
    const items = list.items.map((item) => `<li>${inline(escapeHtml(item))}</li>`).join('')
    out.push(`<${list.tag}>${items}</${list.tag}>`)
    list = null
  }
  const flushAll = () => {
    flushParagraph()
    flushList()
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]

    if (FENCE.test(line)) {
      flushAll()
      const code = []
      index += 1
      while (index < lines.length && !FENCE.test(lines[index])) {
        code.push(lines[index])
        index += 1
      }
      out.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`)
      continue
    }

    if (!line.trim()) {
      flushAll()
      continue
    }

    if (RULE.test(line)) {
      flushAll()
      out.push('<hr />')
      continue
    }

    const heading = line.match(HEADING)
    if (heading) {
      flushAll()
      out.push(
        `<p class="md-head" data-level="${heading[1].length}">` +
          `${inline(escapeHtml(heading[2]))}</p>`,
      )
      continue
    }

    const quote = line.match(QUOTE)
    if (quote) {
      flushAll()
      out.push(`<blockquote>${inline(escapeHtml(quote[1]))}</blockquote>`)
      continue
    }

    const bullet = line.match(BULLET)
    const ordered = line.match(ORDERED)
    if (bullet || ordered) {
      flushParagraph()
      const tag = bullet ? 'ul' : 'ol'
      if (list && list.tag !== tag) flushList()
      if (!list) list = { tag, items: [] }
      list.items.push((bullet || ordered)[1])
      continue
    }

    flushList()
    paragraph.push(line.trim())
  }

  flushAll()
  return out.join('')
}
