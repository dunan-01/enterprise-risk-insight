import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * AI 风险报告渲染（react-markdown + remark-gfm）。
 * 支持表格、标题、列表、代码块等 GFM 语法。
 */
export default function MarkdownReport({ content }: { content: string }) {
  return (
    <div className="report-body">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </div>
  )
}