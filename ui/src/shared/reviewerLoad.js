// Как читается загрузка ревьюера.
//
// Чисел здесь два, и путать их нельзя. `active_count` — сколько работ у
// человека сейчас на руках; это то, что методист и имеет в виду, когда
// спрашивает «сколько на нём висит». `load` — сумма трудоёмкости этих работ, и
// именно её сравнивает с лимитом балансировщик: задание на полторы недели и
// задание на вечер занимают ревьюера по-разному.
//
// Раньше в колонке «Сейчас в работе» стояло второе число. Выглядело это как
// «3.7 работы» — величина, которой не бывает, — и рождало разумный вопрос, как
// количество работ может быть дробным.

const FORMS = ['работа', 'работы', 'работ']

/** Русское склонение после числительного: 1 работа, 2 работы, 5 работ. */
export function works(count) {
  const n = Math.abs(Math.trunc(Number(count) || 0))
  const tail = n % 100
  if (tail >= 11 && tail <= 14) return `${n} ${FORMS[2]}`
  const last = n % 10
  if (last === 1) return `${n} ${FORMS[0]}`
  if (last >= 2 && last <= 4) return `${n} ${FORMS[1]}`
  return `${n} ${FORMS[2]}`
}

/** Трудоёмкость против лимита: «3.7 из 20». Дробное здесь законно. */
export function effort(person) {
  const load = round(person?.load)
  const capacity = round(person?.capacity)
  if (capacity === null) return load === null ? '' : String(load)
  return `${load ?? 0} из ${capacity}`
}

/** Полная подпись для мест, где помещается одна строка. */
export function summary(person) {
  const line = effort(person)
  return line ? `${works(person?.active_count)} · ${line} по трудоёмкости` : works(person?.active_count)
}

/** Доля лимита — для полоски. Всегда в пределах 0…100. */
export function fill(person) {
  const capacity = Number(person?.capacity)
  if (!capacity) return 0
  return Math.max(0, Math.min(100, (Number(person?.load) || 0) / capacity * 100))
}

// Хвост в 0.7000000000000002 — обычное дело для суммы весов, и на экране он не нужен.
function round(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? Math.round(number * 10) / 10 : null
}
