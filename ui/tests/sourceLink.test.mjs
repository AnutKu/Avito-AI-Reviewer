/**
 * Ссылка на строку в GitHub по цитате из разбора.
 *
 * Главное здесь — что номер строки совпадает со строкой файла в репозитории:
 * ссылка на соседнюю строку выглядит так же убедительно, как правильная, и
 * ревьюер поймёт ошибку только когда перепроверит цитату сам.
 *
 * Запуск: node --test tests/ из каталога ui.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { evidenceLink, locateQuote, parseRepository } from '../src/shared/sourceLink.js'

const SEPARATOR = '\n\n---\n\n'
const REPOSITORY = 'https://github.com/demo-student/homework'

// Форма снапшота из services/github.py: «# Файл: путь», пустая строка, файл.
const file = (path, body) => `# Файл: ${path}\n\n${body}`

const SNAPSHOT = [
  file('train.py', 'import mlflow\n\nwith mlflow.start_run():\n    mlflow.log_params(params)'),
  file('README.md', '# Решение\n\nЛучший результат показал Random Forest.'),
].join(SEPARATOR)

describe('ссылка на репозиторий', () => {
  it('владелец и репозиторий берутся из ссылки студента', () => {
    assert.deepEqual(parseRepository(REPOSITORY), {
      owner: 'demo-student',
      repository: 'homework',
    })
    assert.deepEqual(parseRepository(`${REPOSITORY}.git`).repository, 'homework')
  })

  it('не-GitHub и не-HTTPS ссылки отбрасываются', () => {
    // Тот же список, что и на сервере: снапшот снимается только с github.com.
    assert.equal(parseRepository('https://gitlab.com/user/repo'), null)
    assert.equal(parseRepository('http://github.com/user/repo'), null)
    assert.equal(parseRepository('https://github.com/user'), null)
    assert.equal(parseRepository(''), null)
  })
})

describe('поиск цитаты в снапшоте', () => {
  it('строка внутри секции — это строка файла на GitHub', () => {
    // train.py: 1 import, 2 пустая, 3 with, 4 log_params.
    assert.deepEqual(locateQuote(SNAPSHOT, 'import mlflow'), { path: 'train.py', line: 1 })
    assert.deepEqual(locateQuote(SNAPSHOT, 'with mlflow.start_run():'), {
      path: 'train.py',
      line: 3,
    })
  })

  it('нумерация второй секции идёт от её собственного заголовка', () => {
    // Иначе к номеру строки приклеивалась бы длина всех файлов перед ней.
    assert.deepEqual(locateQuote(SNAPSHOT, 'Лучший результат показал Random Forest.'), {
      path: 'README.md',
      line: 3,
    })
  })

  it('многострочная цитата ищется по своим строкам', () => {
    assert.deepEqual(locateQuote(SNAPSHOT, 'with mlflow.start_run():\n    mlflow.log_params'), {
      path: 'train.py',
      line: 3,
    })
  })

  it('у ноутбука строка не выдумывается', () => {
    // github.py разворачивает .ipynb в текст ячеек: строки этого текста не
    // совпадают со строками JSON в репозитории.
    const notebook = file('solution.ipynb', '## Ячейка 1 · code\nimport pandas as pd')

    assert.deepEqual(locateQuote(notebook, 'import pandas as pd'), {
      path: 'solution.ipynb',
      line: 0,
    })
  })

  it('ненайденная цитата остаётся ненайденной', () => {
    assert.equal(locateQuote(SNAPSHOT, 'mlflow.register_model(uri, name)'), null)
    assert.equal(locateQuote(SNAPSHOT, '   '), null)
    assert.equal(locateQuote('', 'import mlflow'), null)
  })
})

describe('ссылка под цитатой', () => {
  it('ведёт на строку файла в ветке по умолчанию', () => {
    const link = evidenceLink(REPOSITORY, SNAPSHOT, 'with mlflow.start_run():')

    assert.equal(link.url, `${REPOSITORY}/blob/HEAD/train.py#L3`)
    assert.equal(link.label, 'train.py:3')
    assert.equal(link.exact, true)
  })

  it('без номера строки ведёт на файл целиком', () => {
    const notebook = file('solution.ipynb', '## Ячейка 1 · code\nimport pandas as pd')
    const link = evidenceLink(REPOSITORY, notebook, 'import pandas as pd')

    assert.equal(link.url, `${REPOSITORY}/blob/HEAD/solution.ipynb`)
    assert.equal(link.label, 'solution.ipynb')
  })

  it('ненайденная цитата ведёт в репозиторий и говорит об этом', () => {
    // Точная ссылка, ведущая не туда, хуже честной ссылки на корень.
    const link = evidenceLink(REPOSITORY, SNAPSHOT, 'ничего подобного в решении нет')

    assert.equal(link.url, REPOSITORY)
    assert.equal(link.exact, false)
  })

  it('без разбираемой ссылки на репозиторий ссылки нет', () => {
    assert.equal(evidenceLink('https://gitlab.com/user/repo', SNAPSHOT, 'import mlflow'), null)
  })
})
