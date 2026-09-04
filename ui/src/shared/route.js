// Разбор адреса кабинета. Хеш — единственный источник правды об открытом
// экране: первый сегмент выбирает раздел, остальные принадлежат самому разделу.
// Отсюда же работают прямая ссылка, F5 и кнопки «назад/вперёд» браузера.

// Разделы, которые переехали. Ключ — старый идентификатор, значение — новый.
export const REDIRECTS = {
  // AI-конструктор перестал быть отдельным разделом: создание, правка и
  // проверка задания живут внутри банка. Старые ссылки ведут туда же.
  'methodist-taskcreater': 'methodist-rubrics',
}

/**
 * @returns {{ page: string, sub: string[], redirectTo: string|null }}
 * `redirectTo` заполнен, если адрес устарел, — по нему нужно заменить хеш,
 * не добавляя лишнюю запись в историю.
 */
export function parseHash(hash, redirects = REDIRECTS) {
  const [page = '', ...sub] = String(hash || '').replace(/^#/, '').split('/').filter(Boolean)
  const moved = redirects[page]
  return {
    page: moved || page,
    sub,
    redirectTo: moved ? [moved, ...sub].join('/') : null,
  }
}
