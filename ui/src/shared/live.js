/**
 * Экран, который сам догоняет фоновую работу.
 *
 * Очередей и веб-сокетов в прототипе нет: разбор Z.AI, детекция и прогон
 * конструктора живут в BackgroundTasks того же процесса, и узнать об их
 * окончании можно только спросив. Раньше спрашивал каждый экран по-своему —
 * где циклом с фиксированным числом попыток, где никак, — и «Проверка
 * выполняется…» висела до F5, хотя проверка давно закончилась.
 *
 * Опрос идёт, пока предикат говорит, что чего-то ждём, и прекращается сам,
 * когда ждать перестало быть чего. Это важнее интервала: экран без фоновой
 * работы не должен обращаться к серверу вообще.
 */

// onScopeDispose, а не onUnmounted: привязка к области реактивности, а не к
// компоненту. В компоненте это то же самое (setup — своя область), но
// composable остаётся пригодным и вне его, и проверяемым тестом.
import { onScopeDispose, watch } from 'vue'

// Машинное ожидание: разбор Z.AI, детекция, прогон конструктора. Считается
// секундами и десятками секунд, и минутный интервал тут — это «готово, но
// узнаете потом».
export const MACHINE_TICK = 2500

// Человеческое: ревьюер публикует результат, отправляет вопросы студенту.
// Здесь спешить некуда, а частый опрос — трафик и нагрузка ради ничего.
export const HUMAN_TICK = 30_000

/**
 * @param {() => boolean} pending  ждём ли чего-то прямо сейчас
 * @param {() => Promise} refresh  тихое обновление: без скелетонов и без
 *                                 затирания несохранённого ввода
 */
export function useLiveRefresh(pending, refresh, { interval = MACHINE_TICK } = {}) {
  let timer = null
  let busy = false

  async function tick() {
    // Предыдущий ответ ещё не пришёл — второй запрос поверх него только
    // добавит гонку: какой из двух долетит последним, неизвестно.
    if (busy) return
    // Свёрнутую вкладку не опрашиваем вовсе. Браузер всё равно тормозит её
    // таймеры, а запросы уходили бы настоящие; вернувшись, догоняем сразу.
    if (document.hidden) return
    busy = true
    try { await refresh() }
    catch { /* сеть моргнула — следующий тик попробует снова */ }
    finally { busy = false }
  }

  function stop() { clearInterval(timer); timer = null }

  // Интервал, а не цепочка таймаутов: цепочка держится на том, что каждый шаг
  // успешно поставит следующий, и один сбой останавливает обновление до
  // перезагрузки страницы. Интервал снимается ровно в одном месте.
  function sync(active) {
    if (active && !timer) timer = setInterval(tick, interval)
    else if (!active) stop()
  }

  function onVisibility() {
    if (document.visibilityState === 'visible' && timer) tick()
  }

  watch(pending, sync, { immediate: true })
  document.addEventListener('visibilitychange', onVisibility)
  onScopeDispose(() => { stop(); document.removeEventListener('visibilitychange', onVisibility) })

  return { stop, refreshNow: tick }
}
