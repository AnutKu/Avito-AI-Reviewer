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
 * и вставки кода, таблицы, жирный, курсив, ссылки на http(s).
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
const ESCAPED_MARK = '\u0002'

export function escapeHtml(text) {
  // Метка вычищается из входа до разбора — иначе её можно было бы подсунуть
  // и подменить содержимое чужой вставки кода.
  return String(text ?? '')
    .replace(/[\u0000-\u0002]/g, '')
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

  // Экранированные символы: `snake\_case`, `100\$`, `\*звёздочка\*`. Модель
  // закрывает ими то, что иначе стало бы разметкой, и обратный слэш не должен
  // доехать до экрана. Вынимаются после кода и формул: там слэш принадлежит
  // коду и латеху, а не markdown.
  const escapes = []
  text = text.replace(/\\([\\`*_{}[\]()#+\-.!$])/g, (_, char) => {
    escapes.push(char)
    return ESCAPED_MARK
  })

  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (whole, label, url) => {
    const href = safeHref(url)
    return href
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : whole
  })
  text = text.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/__([\s\S]+?)__/g, '<strong>$1</strong>')
  text = text.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  text = text.replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>')

  text = text.replace(/\u0002/g, () => escapes.shift())
  text = text.replace(/\u0001/g, () => formulas.shift())
  return text.replace(/\u0000/g, () => `<code>${codes.shift()}</code>`)
}

const HEADING = /^(#{1,6})\s+(.*)$/
const BULLET = /^\s*[-*+]\s+(.*)$/
const ORDERED = /^\s*\d+[.)]\s+(.*)$/
const QUOTE = /^\s*>\s?(.*)$/
const RULE = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/
const FENCE = /^\s*```/
// Строка таблицы и разделитель под шапкой: `| a | b |` + `| --- | --- |`.
// Разделитель обязателен — без него строка с вертикальными чертами остаётся
// текстом, как её написали.
const TABLE_ROW = /^\s*\|(.*)\|\s*$/
const TABLE_SPLIT = /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/

const splitRow = (line) =>
  line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((cell) => cell.trim())

function renderTable(head, body) {
  const cells = (row, tag) =>
    row.map((cell) => `<${tag}>${inline(escapeHtml(cell))}</${tag}>`).join('')
  const rows = body.map((row) => `<tr>${cells(row, 'td')}</tr>`).join('')
  // Обёртка нужна ради прокрутки: таблица от модели шире панели ревьюера
  // бывает чаще, чем уже.
  return (
    '<div class="md-table"><table>' +
    `<thead><tr>${cells(head, 'th')}</tr></thead><tbody>${rows}</tbody>` +
    '</table></div>'
  )
}

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

    if (TABLE_ROW.test(line) && TABLE_SPLIT.test(lines[index + 1] || '')) {
      flushAll()
      const head = splitRow(line)
      const body = []
      index += 2
      while (index < lines.length && TABLE_ROW.test(lines[index])) {
        body.push(splitRow(lines[index]))
        index += 1
      }
      index -= 1
      out.push(renderTable(head, body))
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

    // Продолжение пункта: длинный пункт модель переносит на следующую строку
    // с отступом. Без этого он отрывался от списка и печатался абзацем следом.
    if (list && /^\s{2,}\S/.test(line)) {
      list.items[list.items.length - 1] += ` ${line.trim()}`
      continue
    }

    flushList()
    paragraph.push(line.trim())
  }

  flushAll()
  return out.join('')
}
