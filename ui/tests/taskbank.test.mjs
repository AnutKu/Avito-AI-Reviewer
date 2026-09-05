/**
 * Логика объединённого банка заданий.
 *
 * Здесь проверяется то, что решает поведение экрана, а не его вид: как задания
 * раскладываются по вкладкам, что считается незаполненным перед публикацией,
 * и почему статус публикации нельзя путать с состоянием AI-прогона.
 *
 * Запуск: npm test из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  cleanCriterion,
  debtEmptyState,
  debtFace,
  debtLink,
  criteriaTotal,
  defaultPassScore,
  filledCriteria,
  mergeCriterion,
  filterAssignments,
  isDirty,
  kindLabel,
  openRecommendations,
  publishBlockers,
  personaAbout,
  personaFace,
  personaName,
  runIntro,
  runTitle,
  runTypeFrom,
  samplingNote,
  scoreWarning,
  splitByPublication,
} from '../src/shared/taskbank.js'
import { parseHash } from '../src/shared/route.js'

const ROWS = [
  { id: '1', title: 'Кейс по оттоку', course: 'Аналитика', published: true, last_run: { status: 'completed', persona_type: 'reviewer', completed_at: '2026-09-02T10:00:00Z' } },
  { id: '2', title: 'Метрики подписки', course: 'Аналитика', published: false, last_run: null },
  { id: '3', title: 'Пул воркеров', course: 'Backend', published: false, last_run: { status: 'failed', persona_type: 'student', completed_at: '2026-09-01T10:00:00Z' } },
]

describe('список', () => {
  it('вкладки делят задания по факту публикации', () => {
    const { published, drafts } = splitByPublication(ROWS)
    assert.deepEqual(published.map(r => r.id), ['1'])
    assert.deepEqual(drafts.map(r => r.id), ['2', '3'])
  })

  it('пустой банк не ломает раскладку', () => {
    assert.deepEqual(splitByPublication(undefined), { published: [], drafts: [] })
  })

  it('поиск ищет и по названию, и по курсу', () => {
    assert.deepEqual(filterAssignments(ROWS, 'воркер').map(r => r.id), ['3'])
    assert.deepEqual(filterAssignments(ROWS, 'backend').map(r => r.id), ['3'])
  })

  it('пустой запрос ничего не отфильтровывает', () => {
    assert.equal(filterAssignments(ROWS, '   ').length, 3)
  })

  it('состояние прогона не подменяет статус публикации', () => {
    // Черновик может быть проверен, опубликованное — ни разу не проверено.
    // Поэтому это два разных поля и два разных индикатора.
    const draftChecked = { published: false, last_run: { status: 'completed', persona_type: 'student' } }
    assert.equal(draftChecked.published, false)
    assert.match(runTitle(draftChecked.last_run), /AI-студенты · проверено/)
    assert.equal(runTitle(null), 'Проверка не запускалась')
  })
})

describe('баллы', () => {
  it('максимум — сумма заполненных критериев', () => {
    assert.equal(criteriaTotal([{ title: 'A', max_score: 4 }, { title: 'B', max_score: 6 }]), 10)
  })

  it('пустая заготовка в сумму не идёт', () => {
    // Иначе добавленный, но ещё не заполненный критерий ломает арифметику
    // раньше, чем в него что-то написали.
    assert.equal(criteriaTotal([{ title: 'A', max_score: 4 }, { title: '', max_score: 5 }]), 4)
    assert.equal(filledCriteria([{ title: 'A' }, { title: '  ' }]).length, 1)
  })

  it('проходной балл по умолчанию — 60% суммы, целым числом', () => {
    assert.equal(defaultPassScore([{ title: 'A', max_score: 4 }, { title: 'B', max_score: 6 }]), 6)
    assert.equal(defaultPassScore([{ title: 'A', max_score: 7 }]), 4, 'дробный порог округляется')
    assert.equal(defaultPassScore([]), 0)
  })

  it('проходной балл выше максимума — предупреждение', () => {
    assert.match(scoreWarning([{ title: 'A', max_score: 4 }], 6), /больше максимума/)
  })

  it('нулевой балл критерия ловится отдельно', () => {
    assert.match(scoreWarning([{ title: 'A', max_score: 0 }], 0), /больше нуля/)
  })

  it('корректная рубрика молчит', () => {
    assert.equal(scoreWarning([{ title: 'A', max_score: 4 }, { title: 'B', max_score: 6 }], 6), '')
  })

  it('пустая заготовка не мешает публикации', () => {
    const draft = { title: 'Кейс', statement: 'Условие', pass_score: 3,
      criteria: [{ title: 'A', max_score: 5 }, { title: '', max_score: 5 }] }
    assert.deepEqual(publishBlockers(draft), [])
  })
})

describe('редактор', () => {
  it('несохранённые изменения видны', () => {
    const saved = { title: 'A', criteria: [] }
    assert.equal(isDirty({ ...saved }, saved), false)
    assert.equal(isDirty({ ...saved, title: 'B' }, saved), true)
  })

  it('перед публикацией называются все незаполненные блоки сразу', () => {
    const blockers = publishBlockers({ title: '', statement: '', criteria: [] })
    assert.deepEqual(blockers, ['название', 'условие', 'хотя бы один критерий'])
  })

  it('заполненный черновик публикуется без замечаний', () => {
    const ok = { title: 'Кейс', statement: 'Условие', criteria: [{ title: 'A', max_score: 5 }], pass_score: 3 }
    assert.deepEqual(publishBlockers(ok), [])
  })

  it('черновик из одних пустых заготовок публиковать нечего', () => {
    const blank = { title: 'Кейс', statement: 'Условие', criteria: [{ title: '', max_score: 5 }] }
    assert.ok(publishBlockers(blank).includes('хотя бы один критерий'))
  })
})

describe('прогон', () => {
  it('разбор объясняет, что именно проверяли', () => {
    assert.match(runIntro('student'), /видя только то, что видит студент/)
    assert.match(runIntro('reviewer'), /оценки расходятся/)
    assert.notEqual(runIntro('student'), runIntro('reviewer'))
  })

  it('решённые рекомендации уходят из списка открытых', () => {
    const run = { recommendations: [{ status: 'new' }, { status: 'applied' }, { status: 'rejected' }] }
    assert.equal(openRecommendations(run).length, 1)
  })

  it('незнакомый код находки всё равно называется по-человечески', () => {
    assert.equal(kindLabel('unmeasurable'), 'Субъективная формулировка')
    assert.equal(kindLabel('что-то новое'), 'Замечание к формулировке')
  })
})

describe('маршруты', () => {
  it('раздел берётся из первого сегмента, остальное отдаётся разделу', () => {
    assert.deepEqual(parseHash('#methodist-rubrics'), { page: 'methodist-rubrics', sub: [], redirectTo: null })
    assert.deepEqual(parseHash('#methodist-rubrics/new').sub, ['new'])
    assert.deepEqual(parseHash('#methodist-rubrics/run/abc-123').sub, ['run', 'abc-123'])
  })

  it('старая ссылка AI-конструктора ведёт в объединённый банк', () => {
    const route = parseHash('#methodist-taskcreater')
    assert.equal(route.page, 'methodist-rubrics')
    assert.equal(route.redirectTo, 'methodist-rubrics')
  })

  it('редирект сохраняет хвост адреса', () => {
    assert.equal(parseHash('#methodist-taskcreater/new').redirectTo, 'methodist-rubrics/new')
  })

  it('пустой и мусорный хеш не роняют разбор', () => {
    assert.deepEqual(parseHash(''), { page: '', sub: [], redirectTo: null })
    assert.deepEqual(parseHash('#///'), { page: '', sub: [], redirectTo: null })
    assert.deepEqual(parseHash(undefined), { page: '', sub: [], redirectTo: null })
  })

  it('живой раздел не редиректится', () => {
    assert.equal(parseHash('#methodist-performance').redirectTo, null)
  })
})

describe('персоны', () => {
  it('у каждой персоны своё лицо и человеческое имя', () => {
    const keys = ['diligent_strong', 'minimalist_weak', 'rule_lawyer', 'ambiguity_prober']
    const faces = keys.map(personaFace)
    assert.equal(new Set(faces).size, 4, 'смайлики не должны повторяться — иначе они не различают')
    assert.equal(personaName('rule_lawyer'), 'Юрист правил')
    assert.ok(personaAbout('minimalist_weak').length > 10)
  })

  it('незнакомая персона не ломает карточку', () => {
    assert.equal(personaFace('кто-то новый'), '🤖')
    assert.equal(personaName('кто-то новый'), 'кто-то новый')
  })
})

describe('проверка на персонах', () => {
  it('режим «оба» объясняет, что проверяются оба слоя', () => {
    const intro = runIntro('both')
    assert.match(intro, /AI-студенты/)
    assert.match(intro, /AI-ревьюеры/)
  })

  it('везде, где участвуют ревьюеры, сказано откуда берутся решения', () => {
    // Без этого непонятно, что оценивают ревьюеры, если студентов не запускали.
    for (const type of ['reviewer', 'both']) {
      assert.match(runIntro(type), /Решения для проверки пишут AI-студенты/)
    }
  })

  it('повторы объясняются только когда они были', () => {
    assert.equal(samplingNote(1), '')
    assert.equal(samplingNote(0), '')
    assert.match(samplingNote(3), /оценено 3 раз/)
    assert.match(samplingNote(3), /разброс самой модели/)
  })
})

describe('выбор проверки', () => {
  it('обе галочки — это один прогон по обоим слоям, а не третий вид', () => {
    assert.equal(runTypeFrom(true, true), 'both')
    assert.equal(runTypeFrom(true, false), 'student')
    assert.equal(runTypeFrom(false, true), 'reviewer')
  })

  it('без галочек запускать нечего', () => {
    assert.equal(runTypeFrom(false, false), null)
  })
})

describe('критерий перед отправкой', () => {
  it('уровни и признаки доезжают целиком', () => {
    const clean = cleanCriterion({
      title: 'Метрики', max_score: '6', description: 'признак',
      expected_signals: ['есть формула', 'есть вывод'],
      levels: [{ points: '0', label: 'Не выполнено', descriptor: 'нет' }],
    })
    assert.equal(clean.max_score, 6)
    assert.deepEqual(clean.expected_signals, ['есть формула', 'есть вывод'])
    assert.deepEqual(clean.levels, [{ points: 0, label: 'Не выполнено', descriptor: 'нет' }])
  })

  it('пустые строки признаков не уезжают в рубрику', () => {
    const clean = cleanCriterion({ title: 'x', max_score: 1, expected_signals: ['есть формула', '', '   '] })
    assert.deepEqual(clean.expected_signals, ['есть формула'])
  })

  it('недописанный уровень отбрасывается, а не портит шкалу', () => {
    const clean = cleanCriterion({
      title: 'x', max_score: 3,
      levels: [{ points: 3, label: 'Полно', descriptor: '' }, { points: 0, label: '', descriptor: '' }],
    })
    assert.equal(clean.levels.length, 1)
    assert.equal(clean.levels[0].label, 'Полно')
  })

  it('критерий без скрытой части не падает', () => {
    const clean = cleanCriterion({ title: 'Метрики', max_score: 4 })
    assert.deepEqual(clean.expected_signals, [])
    assert.deepEqual(clean.levels, [])
  })
})

describe('образовательный долг', () => {
  it('пустой экран и нехватка данных — разные сообщения', () => {
    // «Долга нет» и «мы не смогли посчитать» выглядят одинаково пусто, но
    // означают противоположное. Путать их — значит успокаивать без оснований.
    const thin = debtEmptyState({ coverage: { enough: false, graded: 2 }, items: [] })
    assert.match(thin.title, /Данных пока мало/)
    assert.match(thin.text, /2/)

    const clean = debtEmptyState({ coverage: { enough: true, graded: 40 }, items: [] })
    assert.match(clean.title, /Долга не видно/)
    assert.match(clean.text, /не гарантия/)
  })

  it('когда долг есть, заглушки нет', () => {
    assert.equal(debtEmptyState({ coverage: { enough: true, graded: 40 }, items: [{}] }), null)
  })

  it('без данных о долге блок вообще не рисуется', () => {
    assert.equal(debtEmptyState(null), null)
    assert.equal(debtEmptyState(undefined), null)
  })

  it('у каждого вида долга своё лицо', () => {
    const kinds = ['topic', 'repeated_error', 'criterion_corrections', 'questions', 'stale_task']
    assert.equal(new Set(kinds.map(debtFace)).size, 5)
    assert.equal(debtFace('что-то новое'), '•')
  })
})

describe('переход из долга в правку', () => {
  it('критерий ведёт прямо к критерию, а не просто к заданию', () => {
    const link = debtLink({ assignment_id: 'a1', criterion_key: 'metrics' })
    assert.equal(link.path, 'methodist-rubrics/a1/criterion/metrics')
    assert.match(link.label, /критерий/i)
  })

  it('задание ведёт в редактор задания', () => {
    assert.equal(debtLink({ assignment_id: 'a1' }).path, 'methodist-rubrics/a1')
  })

  it('тема ведёт в банк, отфильтрованный по теме', () => {
    const link = debtLink({ topic: 'Работа с данными' })
    assert.match(link.path, /^methodist-rubrics\/topic\//)
    assert.equal(decodeURIComponent(link.path.split('/topic/')[1]), 'Работа с данными')
  })

  it('ключ критерия со слэшем не ломает адрес', () => {
    const link = debtLink({ assignment_id: 'a1', criterion_key: 'a/b' })
    assert.equal(link.path.split('/').length, 4, 'слэш внутри ключа должен быть закодирован')
  })

  it('без цели кнопки нет', () => {
    assert.equal(debtLink({}), null)
    assert.equal(debtLink(null), null)
  })

  it('поиск в банке находит задания темы — иначе переход ведёт в пустоту', () => {
    const rows = [{ title: 'Кейс', course: 'ML', authoring: { topic: 'Работа с данными' } }]
    assert.equal(filterAssignments(rows, 'Работа с данными').length, 1)
  })
})

describe('вставка предложения в критерий', () => {
  const proposed = {
    title: 'Причины оттока', student_hint: 'что оценивается',
    description: 'Названы причины с опорой на данные',
    expected_signals: ['есть расчёт'], levels: [{ points: 0, label: 'Нет', descriptor: 'нет' }],
  }

  it('вес и ключ остаются за автором', () => {
    const current = { key: 'churn', max_score: 7, title: 'Мой критерий' }
    const merged = mergeCriterion(current, proposed)
    assert.equal(merged.max_score, undefined, 'вес не входит в правку — его не трогают')
    assert.equal(merged.key, undefined)
    assert.equal(merged.title, 'Мой критерий', 'своё название не перебивается')
  })

  it('пустому критерию название даёт агент', () => {
    assert.equal(mergeCriterion({ title: '' }, proposed).title, 'Причины оттока')
  })

  it('скрытая часть приезжает целиком', () => {
    const merged = mergeCriterion({}, proposed)
    assert.deepEqual(merged.expected_signals, ['есть расчёт'])
    assert.equal(merged.levels.length, 1)
  })

  it('ответ без признаков и уровней не оставляет undefined', () => {
    // Иначе шаблон падает на c.levels.length, и экран замирает до перезагрузки.
    const merged = mergeCriterion({}, { title: 'X', description: 'Y' })
    assert.deepEqual(merged.expected_signals, [])
    assert.deepEqual(merged.levels, [])
  })

  it('служебный ключ списка не уезжает в рубрику', () => {
    assert.equal(cleanCriterion({ _uid: 7, title: 'A', max_score: 3 })._uid, undefined)
  })
})
