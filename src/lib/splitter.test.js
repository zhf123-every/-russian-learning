import { describe, it, expect } from 'vitest'
import { splitText } from './splitter'

describe('splitText', () => {
  it('splits on sentence punctuation', () => {
    expect(splitText('Привет! Как дела? Хорошо.')).toEqual(['Привет!', 'Как дела?', 'Хорошо.'])
  })
  it('merges tiny fragments into neighbors', () => {
    expect(splitText('Да! Ну, хорошо.')).toEqual(['Да! Ну, хорошо.'])
  })
  it('drops empty and whitespace-only lines', () => {
    expect(splitText('Привет!\n\n  \nКак дела?')).toEqual(['Привет!', 'Как дела?'])
  })
})
