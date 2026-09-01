import { useMemo, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import EvidenceDetailDrawer from './EvidenceDetailDrawer'

/**
 * AI 风险报告渲染（react-markdown + remark-gfm）。
 * 支持表格、标题、列表、代码块等 GFM 语法。
 *
 * V2.0：修复 Evidence ID 点击不一致问题。
 * 支持所有格式的 Evidence ID（Bxxx/Jxxx/Rxxx）。
 */

// ------------------------------------------------------------
// Evidence ID 正则：匹配所有格式
// 格式1: B009
// 格式2: (B009)
// 格式3: （B009）
// 格式4: **B009**
// 格式5: [B009]
// 格式6: J008/J009/J010/J011（斜杠分隔的多个 ID）
// ------------------------------------------------------------

// 匹配单个 Evidence ID（带可选括号或加粗标记）
const EVIDENCE_ID_PATTERN = /[\(（]?\*{0,2}([BJR]\d{3})\*{0,2}[\)）]?/g

// 检测证据类型颜色
function getBadgeClass(id: string): string {
  const prefix = id.charAt(0)
  if (prefix === 'B') return 'ev-badge ev-badge-business'
  if (prefix === 'J') return 'ev-badge ev-badge-judicial'
  return 'ev-badge ev-badge-relation'
}

// 检测证据类型标签
function getTypeLabel(id: string): string {
  const prefix = id.charAt(0)
  if (prefix === 'B') return '工商'
  if (prefix === 'J') return '司法'
  return '关系'
}

/**
 * 创建可点击的 Evidence Badge 组件。
 */
function createEvidenceBadge(
  evidenceId: string,
  onEvidenceClick: (id: string) => void,
  key: string,
) {
  return (
    <span
      key={key}
      className={getBadgeClass(evidenceId)}
      onClick={(e) => {
        e.stopPropagation()
        onEvidenceClick(evidenceId)
      }}
      title={`${getTypeLabel(evidenceId)}事件详情 — 点击查看原始事实`}
    >
      {evidenceId}
    </span>
  )
}

/**
 * 检测文本中的 Evidence ID，替换为可点击的 Badge。
 * 支持所有格式：
 * - B009
 * - (B009)
 * - （B009）
 * - **B009**
 * - [B009]
 * - J008/J009/J010/J011
 */
function renderWithEvidenceIds(
  text: string,
  onEvidenceClick: (id: string) => void,
) {
  const parts: React.ReactNode[] = []
  let lastIndex = 0

  // 收集所有匹配位置
  const allMatches: Array<{
    index: number
    length: number
    id: string
  }> = []

  // 重置正则
  EVIDENCE_ID_PATTERN.lastIndex = 0

  // 查找所有单个 ID
  let match: RegExpExecArray | null
  while ((match = EVIDENCE_ID_PATTERN.exec(text)) !== null) {
    allMatches.push({
      index: match.index,
      length: match[0].length,
      id: match[1],
    })
  }

  // 按索引排序
  allMatches.sort((a, b) => a.index - b.index)

  // 合并相邻的 ID（用斜杠分隔的）
  const mergedMatches: Array<{
    index: number
    length: number
    ids: string[]
  }> = []

  let i = 0
  while (i < allMatches.length) {
    const current = allMatches[i]
    const groupIds = [current.id]
    let groupEnd = current.index + current.length

    // 检查后续的 ID 是否与当前 ID 相邻（用斜杠分隔）
    while (i + 1 < allMatches.length) {
      const next = allMatches[i + 1]
      // 检查两个 ID 之间是否只有斜杠和空白
      const between = text.slice(groupEnd, next.index)
      if (/^\s*\/\s*$/.test(between)) {
        groupIds.push(next.id)
        groupEnd = next.index + next.length
        i++
      } else {
        break
      }
    }

    mergedMatches.push({
      index: current.index,
      length: groupEnd - current.index,
      ids: groupIds,
    })

    i++
  }

  // 生成渲染结果
  for (const match of mergedMatches) {
    // 匹配前的文本
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }

    // 为每个 ID 创建 Badge
    for (const id of match.ids) {
      parts.push(createEvidenceBadge(id, onEvidenceClick, `ev-${id}-${match.index}`))
    }

    lastIndex = match.index + match.length
  }

  // 剩余文本
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts
}

/**
 * 检查文本是否包含 Evidence ID。
 */
function containsEvidenceId(text: string): boolean {
  EVIDENCE_ID_PATTERN.lastIndex = 0
  return EVIDENCE_ID_PATTERN.test(text)
}

/**
 * 递归处理子节点，提取文本并检测 Evidence ID。
 */
function processChildren(
  children: React.ReactNode,
  onEvidenceClick: (id: string) => void,
): React.ReactNode {
  if (typeof children === 'string') {
    if (containsEvidenceId(children)) {
      return renderWithEvidenceIds(children, onEvidenceClick)
    }
    return children
  }

  if (Array.isArray(children)) {
    return children.map((child) => processChildren(child, onEvidenceClick))
  }

  return children
}

/**
 * 高阶组件：为 Markdown 元素注入 Evidence ID 检测。
 */
function withEvidenceDetection<T extends { children?: React.ReactNode }>(
  Component: React.ComponentType<T>,
) {
  return function EvidenceAwareComponent({
    children,
    ...props
  }: T & { onEvidenceClick?: (id: string) => void }) {
    const onEvidenceClick = (props as any).onEvidenceClick
    const processedChildren = processChildren(children, onEvidenceClick)
    return <Component {...(props as T)}>{processedChildren}</Component>
  }
}

export default function MarkdownReport({ content }: { content: string }) {
  const [drawerEvidenceId, setDrawerEvidenceId] = useState<string | null>(null)

  const handleEvidenceClick = useMemo(() => {
    return (id: string) => setDrawerEvidenceId(id)
  }, [])

  // 创建带有 onEvidenceClick 的组件
  const PComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <p>{children}</p>
    ))
    return Component
  }, [])

  const LiComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <li>{children}</li>
    ))
    return Component
  }, [])

  const TdComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <td>{children}</td>
    ))
    return Component
  }, [])

  const ThComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <th>{children}</th>
    ))
    return Component
  }, [])

  const StrongComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <strong>{children}</strong>
    ))
    return Component
  }, [])

  const EmComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <em>{children}</em>
    ))
    return Component
  }, [])

  const SpanComponent = useMemo(() => {
    const Component = withEvidenceDetection(({ children }: { children?: React.ReactNode }) => (
      <span>{children}</span>
    ))
    return Component
  }, [])

  const components = useMemo(
    () => ({
      p: (props: any) => <PComponent {...props} onEvidenceClick={handleEvidenceClick} />,
      li: (props: any) => <LiComponent {...props} onEvidenceClick={handleEvidenceClick} />,
      td: (props: any) => <TdComponent {...props} onEvidenceClick={handleEvidenceClick} />,
      th: (props: any) => <ThComponent {...props} onEvidenceClick={handleEvidenceClick} />,
      strong: (props: any) => <StrongComponent {...props} onEvidenceClick={handleEvidenceClick} />,
      em: (props: any) => <EmComponent {...props} onEvidenceClick={handleEvidenceClick} />,
      span: (props: any) => <SpanComponent {...props} onEvidenceClick={handleEvidenceClick} />,
    }),
    [handleEvidenceClick, PComponent, LiComponent, TdComponent, ThComponent, StrongComponent, EmComponent, SpanComponent],
  )

  return (
    <>
      <div className="report-body">
        <Markdown remarkPlugins={[remarkGfm]} components={components}>
          {content}
        </Markdown>
      </div>
      <EvidenceDetailDrawer
        evidenceId={drawerEvidenceId}
        onClose={() => setDrawerEvidenceId(null)}
      />
    </>
  )
}
