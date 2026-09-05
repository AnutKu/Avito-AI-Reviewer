import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { errorText } from '../src/shared/api.js'

describe('текст ошибки из ответа сервера', () => {
  test('строковый detail уходит к пользователю как есть', () => {
    assert.equal(errorText({ detail: 'Работа по этому заданию уже принята' }, 409),
      'Работа по этому заданию уже принята')
  })

  test('список ошибок валидации разбирается в текст, а не в [object Object]', () => {
    // Ровно тот ответ, которым FastAPI встречал публикацию ревью. Раньше
    // new Error(список) давал «[object Object],[object Object]», и за этим
    // сообщением спрятался незарегистрированный роут.
    const detail = [
      { loc: ['query', 'submission'], msg: 'Field required' },
      { loc: ['query', 'review'], msg: 'Field required' },
    ]

    const text = errorText({ detail }, 422)

    assert.equal(text, 'submission: Field required; review: Field required')
    assert.ok(!text.includes('[object Object]'))
  })

  test('поле называется без служебного префикса body', () => {
    const detail = [{ loc: ['body', 'feedback'], msg: 'String should have at least 10 characters' }]

    assert.equal(errorText({ detail }, 422),
      'feedback: String should have at least 10 characters')
  })

  test('ошибка без места остаётся сообщением', () => {
    assert.equal(errorText({ detail: [{ msg: 'Ошибка разбора тела' }] }, 422), 'Ошибка разбора тела')
  })

  test('когда сервер не объяснил ничего, остаётся код', () => {
    // Пустой список — не «всё хорошо»: отказ был, объяснения нет.
    assert.equal(errorText({}, 500), 'Ошибка 500')
    assert.equal(errorText({ detail: [] }, 502), 'Ошибка 502')
    assert.equal(errorText({ detail: '' }, 503), 'Ошибка 503')
    assert.equal(errorText(null, 504), 'Ошибка 504')
  })
})
