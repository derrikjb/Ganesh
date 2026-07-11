/**
 * Strip markdown formatting from text for TTS consumption.
 *
 * Removes: headers, bold/italic markers, code blocks, inline code,
 * links (keeps text), images (removes), list markers, blockquotes,
 * strikethrough, horizontal rules, table pipes, HTML tags.
 * Collapses extra whitespace.
 */
export function stripMarkdown(text: string): string {
  if (!text) return ''

  let out = text

  // Fenced code blocks: ```lang\n...``` → keep code text
  out = out.replace(/```[\w-]*\n?([\s\S]*?)```/g, '$1')
  out = out.replace(/~~~[\w-]*\n?([\s\S]*?)~~~/g, '$1')

  // Images: ![alt](url) → remove entirely
  out = out.replace(/!\[([^\]]*)\]\([^)]*\)/g, '')

  // Links: [text](url) → keep text
  out = out.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')

  // Reference-style links: [text][ref] and [ref]: url lines
  out = out.replace(/\[([^\]]+)\]\[[^\]]*\]/g, '$1')
  out = out.replace(/^\s*\[[^\]]+\]:\s*.*$/gm, '')

  // Inline code: `code` → keep code text
  out = out.replace(/`([^`]+)`/g, '$1')

  // Headers: # ## ### at line start → remove prefix
  out = out.replace(/^\s{0,3}#{1,6}\s+/gm, '')

  // Horizontal rules: --- *** ___ on own line → remove
  out = out.replace(/^\s*([-*_])\1{2,}\s*$/gm, '')

  // Blockquotes: > at line start → remove marker (handles nested > > >)
  out = out.replace(/^(?:\s{0,3}>\s?)+/gm, '')

  // Strikethrough: ~~text~~ → keep text
  out = out.replace(/~~([^~]+)~~/g, '$1')

  // Bold: **text** or __text__ → keep text
  out = out.replace(/\*\*([^*]+)\*\*/g, '$1')
  out = out.replace(/__([^_]+)__/g, '$1')

  // Italic: *text* or _text_ → keep text (avoid matching ** / __ already handled)
  out = out.replace(/(?<!\*)\*(?!\*)([^*\n]+)\*(?!\*)/g, '$1')
  out = out.replace(/(?<!_)_(?!_)([^_\n]+)_(?!_)/g, '$1')

  // List markers: - * + 1. 2. at line start → remove marker
  out = out.replace(/^\s*[-*+]\s+/gm, '')
  out = out.replace(/^\s*\d+\.\s+/gm, '')

  // Table separator rows: |:---|---:| → remove entire line (use [ \t] not \s to avoid crossing lines)
  out = out.replace(/^\s*\|?[ \t:|-]*-+[ \t:|-]*.*$/gm, '')

  // Table pipes: | → space
  out = out.replace(/\|/g, ' ')

  // HTML tags → remove
  out = out.replace(/<\/?[a-zA-Z][^>]*>/g, '')

  // Collapse multiple spaces (preserve newlines)
  out = out.replace(/[ \t]+/g, ' ')

  // Strip trailing whitespace per line
  out = out.replace(/[ \t]+$/gm, '')

  // Collapse 3+ newlines into 2
  out = out.replace(/\n{3,}/g, '\n\n')

  return out.trim()
}
