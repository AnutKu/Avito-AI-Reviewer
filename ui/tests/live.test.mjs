import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, nextTick, ref } from 'vue'

import { MACHINE_TICK, useLiveRefresh } from '../src/shared/live.js'

/**
 * Время в тестах идёт по команде: настоящие таймеры сделали бы проверки либо
 * медленными, либо зависящими от того, успела ли машина. `document` в node нет
 * вовсе — подставляем ровно то, чем пользуется composable.
 *
 * Проверяется поведение, а не устройство: «прошло столько-то времени — сходил
 * ли за данными», а не «сколько таймеров зарегистрировано».
 */
function stubDocument() {
  const listeners = {}
  const real = globalThis.document
  globalThis.document = {
    hidden: false,
    visibilityState: 'visible',
    addEventListener: (name, fn) => { listeners[name] = fn },
    removeEventListener: (name) => { delete listeners[name] },
  }
  return { listeners, restore: () => { globalThis.document = real } }
}

/** Дать разрешённым промисам догореть: тик синхронный, обновление — нет. */
const settle = () => new Promise(resolve => setImmediate(resolve))

/** Composable живёт в области реактивности — как в setup компонента. */
function mount(pending, refresh, options) {
  const scope = effectScope()
  scope.run(() => useLiveRefresh(pending, refresh, options))
  return scope
}

test('опрос идёт, только пока чего-то ждём', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const doc = stubDocument()
  try {
    const pending = ref(false)
    let calls = 0
    const scope = mount(() => pending.value, async () => { calls += 1 })

    // Экран без фоновой работы не обращается к серверу вовсе. Это важнее
    // интервала: иначе кабинет опрашивал бы сервер круглосуточно ни за чем.
    t.mock.timers.tick(MACHINE_TICK * 3)
    assert.equal(calls, 0)

    pending.value = true
    await nextTick()
    t.mock.timers.tick(MACHINE_TICK)
    assert.equal(calls, 1)
    await settle()

    pending.value = false
    await nextTick()
    t.mock.timers.tick(MACHINE_TICK * 3)
    assert.equal(calls, 1)
    scope.stop()
  } finally { doc.restore() }
})

test('свёрнутая вкладка не опрашивается, а по возвращении догоняет', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const doc = stubDocument()
  try {
    let calls = 0
    const scope = mount(() => true, async () => { calls += 1 })

    globalThis.document.hidden = true
    t.mock.timers.tick(MACHINE_TICK * 3)
    assert.equal(calls, 0)

    // Браузер и сам тормозит таймеры фоновой вкладки, но запросы уходили бы
    // настоящие. Вернулись — обновляемся сразу, не дожидаясь следующего тика.
    globalThis.document.hidden = false
    await doc.listeners.visibilitychange()
    assert.equal(calls, 1)
    scope.stop()
  } finally { doc.restore() }
})

test('пока ответ не пришёл, второй запрос не уходит', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const doc = stubDocument()
  try {
    let calls = 0
    let release
    const scope = mount(() => true, () => {
      calls += 1
      return new Promise(resolve => { release = resolve })
    })

    t.mock.timers.tick(MACHINE_TICK)
    assert.equal(calls, 1)
    // Второй запрос поверх неотвеченного первого — гонка: какой из двух ответов
    // долетит последним, неизвестно, и экран мог бы откатиться на старые данные.
    t.mock.timers.tick(MACHINE_TICK)
    assert.equal(calls, 1)

    release()
    await settle()
    t.mock.timers.tick(MACHINE_TICK)
    assert.equal(calls, 2)
    scope.stop()
  } finally { doc.restore() }
})

test('неудачный тик не останавливает опрос', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const doc = stubDocument()
  try {
    let calls = 0
    const scope = mount(() => true, async () => {
      calls += 1
      throw new Error('сеть моргнула')
    })

    t.mock.timers.tick(MACHINE_TICK)
    await settle()
    t.mock.timers.tick(MACHINE_TICK)
    await settle()
    // Одна моргнувшая сеть не должна оставлять экран устаревшим до F5.
    assert.equal(calls, 2)
    scope.stop()
  } finally { doc.restore() }
})

test('уход с экрана снимает и таймер, и слушателя', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const doc = stubDocument()
  try {
    let calls = 0
    const scope = mount(() => true, async () => { calls += 1 })

    scope.stop()
    t.mock.timers.tick(MACHINE_TICK * 3)
    assert.equal(calls, 0)
    assert.equal(doc.listeners.visibilitychange, undefined)
  } finally { doc.restore() }
})
