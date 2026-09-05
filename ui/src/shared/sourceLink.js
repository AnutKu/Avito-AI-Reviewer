/**
 * Цитата из разбора → ссылка на строку в GitHub.
 *
 * У модели нет номеров строк: в `evidence` приходят цитата и якорь словами
 * («Ячейка 12», «student_solution»). Проверить такое основание можно только
 * глазами, а глазами его сначала надо найти. Номер строки здесь не приходит
 * с сервера, а восстанавливается по снапшоту — тому же тексту, который читала
 * модель, и который у экрана уже есть целиком.
 *
 * Снапшот собирает services/github.py: файлы идут секциями, каждая начинается
 * строкой «# Файл: путь», дальше пустая строка и содержимое файла как есть.
 * Поэтому строка внутри секции — это строка файла на GitHub, один в один.
 *
 * Исключение — ноутбуки: services/github.py разворачивает .ipynb в текст ячеек,
 * и строки этого текста не совпадают со строками JSON в репозитории. Для них
 * возвращается ссылка на файл без номера: соврать якорем хуже, чем не дать его.
 */

const FILE_HEADER = /^# Файл: (.+)$/
// Заголовок секции и пустая строка после него: содержимое файла начинается
// через две строки, и с этого сдвига считаются номера строк.
const BODY_OFFSET = 2

/** Владелец и репозиторий из ссылки студента. Правила те же, что на сервере. */
export function parseRepository(sourceUrl) {
  let parsed
  try {
    parsed = new URL(String(sourceUrl || ''))
  } catch {
    return null
  }
  if (parsed.protocol !== 'https:') return null
  if (parsed.hostname !== 'github.com' && parsed.hostname !== 'www.github.com') return null
  const parts = parsed.pathname.split('/').filter(Boolean)
  if (parts.length < 2) return null
  const owner = parts[0]
  const repository = parts[1].replace(/\.git$/, '')
  const allowed = /^[A-Za-z0-9_.-]+$/
  if (!allowed.test(owner) || !allowed.test(repository)) return null
  return { owner, repository }
}

/**
 * Границы файловых секций снапшота.
 *
 * Разбор идёт по заголовкам, а не по разделителю секций: `---` — это ещё и
 * обычная горизонтальная линейка markdown, и файл с ней разваливал бы разбор
 * на середине.
 */
export function snapshotSections(content) {
  const lines = String(content || '').replace(/\r\n?/g, '\n').split('\n')
  const sections = []
  lines.forEach((line, index) => {
    const header = line.match(FILE_HEADER)
    if (!header) return
    if (sections.length) sections[sections.length - 1].end = index
    sections.push({ path: header[1].trim(), start: index, end: lines.length })
  })
  return { lines, sections }
}

function isNotebook(path) {
  return path.toLowerCase().endsWith('.ipynb')
}

/**
 * Файл и строка, где цитата встречается в снапшоте.
 *
 * Цитата может прийти многострочной или с обрезанным хвостом, поэтому кроме
 * неё целиком пробуются её собственные строки — по очереди, сверху вниз.
 * Не нашли — `null`: выдумывать место, которого не видели, нельзя.
 */
export function locateQuote(content, quote) {
  const needle = String(quote || '').trim()
  if (!needle) return null
  const { lines, sections } = snapshotSections(content)
  if (!sections.length) return null
  const probes = needle.includes('\n')
    ? needle.split('\n').map(line => line.trim()).filter(Boolean)
    : [needle]
  for (const probe of probes) {
    for (const section of sections) {
      for (let index = section.start + BODY_OFFSET; index < section.end; index += 1) {
        if (!lines[index].includes(probe)) continue
        return {
          path: section.path,
          line: isNotebook(section.path) ? 0 : index - section.start - (BODY_OFFSET - 1),
        }
      }
    }
  }
  return null
}

/**
 * Ссылка под цитатой: куда она ведёт и как называется.
 *
 * Ветка — HEAD: снапшот снят с неё же (codeload …/zip/HEAD), и прибивать
 * ссылку к имени ветки, которого мы не знаем, нечем.
 *
 * `exact: false` — цитату в снапшоте не нашли, ссылка ведёт в репозиторий.
 * Подпись про это говорит прямо: точная ссылка, ведущая не туда, хуже честной
 * ссылки на корень.
 */
export function evidenceLink(sourceUrl, content, quote) {
  const repository = parseRepository(sourceUrl)
  if (!repository) return null
  const root = `https://github.com/${repository.owner}/${repository.repository}`
  const found = locateQuote(content, quote)
  if (!found) return { url: root, label: 'репозиторий', exact: false }
  const path = found.path.split('/').map(encodeURIComponent).join('/')
  const url = `${root}/blob/HEAD/${path}`
  if (!found.line) return { url, label: found.path, exact: true }
  return { url: `${url}#L${found.line}`, label: `${found.path}:${found.line}`, exact: true }
}
