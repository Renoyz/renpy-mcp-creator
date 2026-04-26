import type { ReactNode } from "react"

interface ChatMarkdownProps {
  content: string
  className?: string
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /\*\*([^*]+)\*\*/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    nodes.push(
      <strong key={`strong-${match.index}`} className="font-semibold">
        {match[1]}
      </strong>
    )
    lastIndex = pattern.lastIndex
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes.length > 0 ? nodes : [text]
}

export function ChatMarkdown({ content, className = "" }: ChatMarkdownProps) {
  const lines = content.split(/\r?\n/)
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = []
      while (index < lines.length) {
        const item = lines[index].trim()
        if (!/^[-*]\s+/.test(item)) break
        items.push(item.replace(/^[-*]\s+/, ""))
        index += 1
      }
      blocks.push(
        <ul key={`list-${index}`} className="list-disc space-y-1 pl-5">
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>
      )
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const paragraphLine = lines[index]
      const paragraphTrimmed = paragraphLine.trim()
      if (!paragraphTrimmed || /^[-*]\s+/.test(paragraphTrimmed)) break
      paragraphLines.push(paragraphLine)
      index += 1
    }
    blocks.push(
      <p key={`paragraph-${index}`} className="whitespace-pre-wrap">
        {renderInlineMarkdown(paragraphLines.join("\n"))}
      </p>
    )
  }

  return <div className={`space-y-2 ${className}`.trim()}>{blocks}</div>
}
