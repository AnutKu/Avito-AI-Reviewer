/**
 * Формулы из ответа модели — в читаемый текст.
 *
 * Модель пишет формулы латехом: `$$\text{ROMI} = \frac{A - B}{B} \times 100\%$$`.
 * Полноценный движок (KaTeX с шрифтами — сотни килобайт) ради нескольких
 * формул в условии задания не нужен: здесь не учебник математики, формулы
 * простые — дробь, произведение, процент, изредка индекс. Поэтому разбирается
 * подмножество, а результат — обычный текст со знаками, который читается вслух:
 *
 *     ROMI = (Выручка − Бюджет) / Бюджет × 100%
 *
 * Вход уже экранирован (см. markdown.js): сюда попадает текст, отсюда выходит
 * текст плюс sup/sub. Новых тегов, кроме них, не появляется.
 *
 * Неизвестная команда теряет обратный слэш и остаётся словом — это хуже, чем
 * настоящий рендер, но лучше, чем `\qquad` посреди условия.
 */

const SYMBOLS = {
  times: '×', cdot: '·', div: '÷', pm: '±', mp: '∓',
  leq: '≤', le: '≤', geq: '≥', ge: '≥', neq: '≠', ne: '≠',
  approx: '≈', equiv: '≡', sim: '∼', propto: '∝',
  sum: 'Σ', prod: '∏', int: '∫', infty: '∞', partial: '∂',
  rightarrow: '→', to: '→', leftarrow: '←', Rightarrow: '⇒',
  in: '∈', notin: '∉', subset: '⊂', cup: '∪', cap: '∩',
  ldots: '…', dots: '…', cdots: '…',
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', varepsilon: 'ε',
  theta: 'θ', lambda: 'λ', mu: 'μ', pi: 'π', rho: 'ρ', sigma: 'σ', tau: 'τ',
  phi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω',
  Delta: 'Δ', Sigma: 'Σ', Omega: 'Ω', Phi: 'Φ', Lambda: 'Λ',
}

// Обёртки, которые в тексте ничего не значат: содержимое остаётся, команда уходит.
const TRANSPARENT = /\\(?:text|textrm|textbf|textit|mathrm|mathbf|mathit|mathsf|operatorname)\s*\{/

/** Находит закрывающую скобку для открывающей на позиции `open`. */
function matchBrace(text, open) {
  let depth = 0
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1
    else if (text[i] === '}') {
      depth -= 1
      if (!depth) return i
    }
  }
  return -1
}

/** Аргумент после команды: `{...}` целиком или один следующий символ. */
function takeArg(text, from) {
  if (text[from] === '{') {
    const close = matchBrace(text, from)
    if (close === -1) return null
    return { value: text.slice(from + 1, close), end: close + 1 }
  }
  if (from < text.length && !/\s/.test(text[from])) {
    return { value: text[from], end: from + 1 }
  }
  return null
}

// Скобки вокруг части дроби нужны только если внутри есть чем ошибиться:
// (a − b) / c читается однозначно, а вот a − b / c — уже нет. Пробел таким
// поводом не является: «Маркетинговый бюджет» в скобках — шум, а не точность.
const NEEDS_BRACKETS = /[+\-−×·/]/

function bracket(part) {
  const trimmed = part.trim()
  return NEEDS_BRACKETS.test(trimmed) ? `(${trimmed})` : trimmed
}

function unwrapTransparent(text) {
  let result = text
  for (let guard = 0; guard < 50; guard += 1) {
    const match = result.match(TRANSPARENT)
    if (!match) break
    const open = match.index + match[0].length - 1
    const close = matchBrace(result, open)
    if (close === -1) break
    result =
      result.slice(0, match.index) + result.slice(open + 1, close) + result.slice(close + 1)
  }
  return result
}

function expandFractions(text) {
  let result = text
  for (let guard = 0; guard < 50; guard += 1) {
    // Изнутри наружу: внешней дроби нужно видеть, что в числителе уже есть
    // деление, — иначе \\frac{\\frac{a}{b}}{c} схлопнется в «a / b / c».
    const at = result.lastIndexOf('\\frac')
    if (at === -1) break
    const numerator = takeArg(result, at + 5)
    if (!numerator) break
    const denominator = takeArg(result, numerator.end)
    if (!denominator) break
    const replaced = `${bracket(numerator.value)} / ${bracket(denominator.value)}`
    result = result.slice(0, at) + replaced + result.slice(denominator.end)
  }
  return result
}

function expandScripts(text) {
  let result = text
  for (const [mark, tag] of [['^', 'sup'], ['_', 'sub']]) {
    for (let guard = 0; guard < 50; guard += 1) {
      const at = result.indexOf(mark)
      if (at === -1) break
      const arg = takeArg(result, at + 1)
      if (!arg) break
      result = `${result.slice(0, at)}<${tag}>${arg.value}</${tag}>${result.slice(arg.end)}`
    }
  }
  return result
}

/** Одна формула (без ограничителей) → читаемый текст. */
export function renderLatex(source) {
  let text = String(source ?? '')

  text = text.replace(/\\(?:left|right|displaystyle|limits|!)/g, '')
  text = unwrapTransparent(text)
  text = expandFractions(text)
  text = text.replace(/\\sqrt\s*\{([^{}]*)\}/g, '√($1)')

  // Экранированные символы — до таблицы команд: \% это процент, а не команда.
  text = text.replace(/\\([%$&#_{}])/g, '$1')
  text = text.replace(/\\[,;:\s]/g, ' ')

  text = text.replace(/\\([A-Za-z]+)/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(SYMBOLS, name) ? SYMBOLS[name] : name,
  )

  text = expandScripts(text)
  // Скобки уцелевают только у неразобранного — там пробел честнее склейки:
  // «frac a b» видно, что не разобралось, а «fracab» выглядит словом.
  text = text.replace(/[{}]/g, ' ')
  // Минус в формуле — знак, а не дефис переноса.
  text = text.replace(/(\s)-(\s)/g, '$1−$2')

  return text.replace(/\s+/g, ' ').trim()
}

// $$...$$ и \[...\] — выключная формула, $...$ и \(...\) — строчная.
const BLOCK_MATH = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]/g
const INLINE_MATH = /\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g

// Одиночные доллары в тексте — чаще цены, чем формулы: «$100 в месяц» формулой
// не является. Признак настоящей формулы — команда или индекс внутри.
const LOOKS_LIKE_MATH = /\\[A-Za-z]|[_^]/
// Плюс одиночная латинская буква: «обозначим $x$» — это переменная, а не сумма
// в долларах (в цене после знака идёт число). Доллары вокруг неё — разметка,
// и на экране им делать нечего.
const SINGLE_VARIABLE = /^[A-Za-z]$/

const isMath = (body) => LOOKS_LIKE_MATH.test(body) || SINGLE_VARIABLE.test(body.trim())

/**
 * Строчные формулы. Обычным `replace` не обойтись: отвергнутая пара долларов
 * («$100, а метрика $») съедала бы доллар, которым открывается настоящая
 * формула следом. Поэтому после отказа поиск продолжается со ВТОРОГО доллара
 * пары, а не за ней.
 */
function replaceInlineMath(text, wrap) {
  const pattern = new RegExp(INLINE_MATH.source, 'g')
  let out = ''
  let tail = 0
  let match = pattern.exec(text)
  while (match) {
    const [whole, dollars, parens] = match
    if (dollars !== undefined && !isMath(dollars)) {
      const resume = match.index + whole.length - 1
      out += text.slice(tail, resume)
      tail = resume
      pattern.lastIndex = resume
    } else {
      out += text.slice(tail, match.index) + wrap(renderLatex(dollars ?? parens), false)
      tail = match.index + whole.length
      pattern.lastIndex = tail
    }
    match = pattern.exec(text)
  }
  return out + text.slice(tail)
}

/**
 * Заменяет формулы на результат `wrap(текст, выключная)`.
 * Разделено с рендером, чтобы markdown.js мог спрятать формулы за метки до
 * своих правил: `_` в индексе — не курсив, а `\frac{a}{b}` — не выделение.
 */
export function replaceMath(text, wrap) {
  const blocks = String(text ?? '').replace(BLOCK_MATH, (whole, dollars, brackets) =>
    wrap(renderLatex(dollars ?? brackets), true),
  )
  return replaceInlineMath(blocks, wrap)
}
