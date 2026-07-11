import { describe, it, expect } from 'vitest'
import { stripMarkdown } from '../utils/markdown'

describe('stripMarkdown', () => {
  it('returns empty string for empty input', () => {
    expect(stripMarkdown('')).toBe('')
  })

  it('strips headers', () => {
    expect(stripMarkdown('# Title')).toBe('Title')
    expect(stripMarkdown('## Subtitle')).toBe('Subtitle')
    expect(stripMarkdown('### Deep')).toBe('Deep')
    expect(stripMarkdown('###### Max')).toBe('Max')
  })

  it('strips bold markers', () => {
    expect(stripMarkdown('**bold text**')).toBe('bold text')
    expect(stripMarkdown('__bold text__')).toBe('bold text')
  })

  it('strips italic markers', () => {
    expect(stripMarkdown('*italic text*')).toBe('italic text')
    expect(stripMarkdown('_italic text_')).toBe('italic text')
  })

  it('handles bold + italic combination', () => {
    expect(stripMarkdown('**bold** and *italic*')).toBe('bold and italic')
  })

  it('strips inline code but keeps content', () => {
    expect(stripMarkdown('Use `const x = 1` here')).toBe('Use const x = 1 here')
  })

  it('strips fenced code blocks but keeps content', () => {
    const input = '```js\nconsole.log("hi")\n```'
    expect(stripMarkdown(input)).toBe('console.log("hi")')
  })

  it('strips fenced code blocks with language hint', () => {
    const input = '```python\nprint("hello")\n```'
    expect(stripMarkdown(input)).toBe('print("hello")')
  })

  it('keeps link text but removes url', () => {
    expect(stripMarkdown('[Click here](https://example.com)')).toBe('Click here')
  })

  it('removes images entirely', () => {
    expect(stripMarkdown('![alt text](image.png)')).toBe('')
    expect(stripMarkdown('Before ![alt](img.png) after')).toBe('Before after')
  })

  it('strips list markers', () => {
    expect(stripMarkdown('- item one')).toBe('item one')
    expect(stripMarkdown('* item one')).toBe('item one')
    expect(stripMarkdown('+ item one')).toBe('item one')
    expect(stripMarkdown('1. first')).toBe('first')
    expect(stripMarkdown('2. second')).toBe('second')
  })

  it('strips blockquote markers', () => {
    expect(stripMarkdown('> quoted text')).toBe('quoted text')
    expect(stripMarkdown('> > nested quote')).toBe('nested quote')
  })

  it('strips strikethrough but keeps text', () => {
    expect(stripMarkdown('~~deleted~~')).toBe('deleted')
  })

  it('removes horizontal rules', () => {
    expect(stripMarkdown('---')).toBe('')
    expect(stripMarkdown('***')).toBe('')
    expect(stripMarkdown('___')).toBe('')
  })

  it('strips table pipes', () => {
    const input = '| Name | Age |\n| --- | --- |\n| Bob | 30 |'
    const result = stripMarkdown(input)
    expect(result).not.toContain('|')
    expect(result).toContain('Name')
    expect(result).toContain('Bob')
  })

  it('removes HTML tags', () => {
    expect(stripMarkdown('<b>bold</b>')).toBe('bold')
    expect(stripMarkdown('<br>')).toBe('')
    expect(stripMarkdown('<div class="x">content</div>')).toBe('content')
  })

  it('collapses multiple blank lines', () => {
    const input = 'Para one\n\n\n\n\nPara two'
    expect(stripMarkdown(input)).toBe('Para one\n\nPara two')
  })

  it('strips trailing whitespace per line', () => {
    const input = 'line one   \nline two   '
    const result = stripMarkdown(input)
    expect(result).toBe('line one\nline two')
  })

  it('handles reference-style links', () => {
    expect(stripMarkdown('[text][ref]')).toBe('text')
  })

  it('removes reference link definitions', () => {
    const input = '[ref]: https://example.com\nSome text'
    expect(stripMarkdown(input)).toBe('Some text')
  })

  it('handles complex mixed markdown', () => {
    const input = `# Heading

This is **bold** and *italic* text with a [link](https://x.com).

- List item one
- List item two

\`inline code\` here.

> A quote

![image](pic.png)

---

Final paragraph.`
    const result = stripMarkdown(input)
    expect(result).not.toContain('#')
    expect(result).not.toContain('**')
    expect(result).not.toContain('[link]')
    expect(result).not.toContain('![')
    expect(result).not.toContain('---')
    expect(result).not.toContain('> ')
    expect(result).toContain('Heading')
    expect(result).toContain('bold')
    expect(result).toContain('link')
    expect(result).toContain('List item one')
    expect(result).toContain('inline code')
    expect(result).toContain('A quote')
    expect(result).toContain('Final paragraph')
  })

  it('preserves plain text unchanged', () => {
    expect(stripMarkdown('Just plain text.')).toBe('Just plain text.')
  })
})
