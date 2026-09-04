import { describe, it, expect } from 'vitest'
import { mdToHtml } from './md'

describe('mdToHtml', () => {
  it('returns empty string for null/undefined', () => {
    expect(mdToHtml(null)).toBe('')
    expect(mdToHtml(undefined)).toBe('')
  })

  it('escapes HTML', () => {
    expect(mdToHtml('<script>')).toBe('&lt;script&gt;')
    expect(mdToHtml('&amp;')).toBe('&amp;amp;')
  })

  it('converts h1/h2/h3', () => {
    expect(mdToHtml('# Привет')).toBe('<h1>Привет</h1>')
    expect(mdToHtml('## Заголовок')).toBe('<h2>Заголовок</h2>')
    expect(mdToHtml('### Подзаголовок')).toBe('<h3>Подзаголовок</h3>')
  })

  it('converts bold', () => {
    expect(mdToHtml('Привет **мир**!')).toBe('Привет <b>мир</b>!')
    expect(mdToHtml('**полный bold**')).toBe('<b>полный bold</b>')
  })

  it('converts inline code', () => {
    expect(mdToHtml('试试 `console.log`')).toBe('试试 <code>console.log</code>')
  })

  it('converts unordered list', () => {
    expect(mdToHtml('- пункт')).toBe('<ul><li>пункт</li></ul>')
    expect(mdToHtml('* другой')).toBe('<ul><li>другой</li></ul>')
  })

  it('converts ordered list', () => {
    expect(mdToHtml('1. первый')).toBe('<ol><li>первый</li></ol>')
    expect(mdToHtml('2. второй')).toBe('<ol><li>второй</li></ol>')
  })

  it('converts code block', () => {
    const md = '```\nconst x = 1;\n```'
    const result = mdToHtml(md)
    expect(result).toContain('<pre><code>')
    expect(result).toContain('const x = 1;')
  })

  it('converts code block with language', () => {
    const md = '```js\nconsole.log("hi")\n```'
    const result = mdToHtml(md)
    expect(result).toContain('<pre><code>')
    expect(result).toContain('console.log')
  })

  it('converts blockquote', () => {
    const result = mdToHtml('> 引用的文字')
    expect(result).toContain('<blockquote>')
    expect(result).toContain('引用的文字')
  })

  it('converts multi-line', () => {
    const result = mdToHtml('Привет!\nКак дела?')
    expect(result).toContain('Привет!<br>')
    expect(result).toContain('Как дела?')
  })

  it('handles nested structures', () => {
    const md = '# Заголовок\n\n- элемент **жирный**\n\n```\ncode here\n```'
    const html = mdToHtml(md)
    expect(html).toContain('<h1>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<b>')
    expect(html).toContain('<pre><code>')
  })
})