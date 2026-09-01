import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { EvidenceResponse } from '../api/types'

/**
 * Evidence Detail Panel（V2.0）。
 *
 * 右侧面板组件，展示指定企业的全部 Evidence 列表。
 * 支持点击节点时打开，显示该企业的所有证据。
 */

// ------------------------------------------------------------
// Evidence 类型标签
// ------------------------------------------------------------

function EvidenceTypeTag({ type }: { type: string }) {
  const config: Record<string, { label: string; color: string; bg: string }> = {
    business: { label: '工商', color: '#2563eb', bg: '#dbeafe' },
    judicial: { label: '司法', color: '#7c3aed', bg: '#ede9fe' },
    relation: { label: '关系', color: '#0891b2', bg: '#cffafe' },
  }
  const c = config[type] || { label: type, color: '#64748b', bg: '#f1f5f9' }
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        color: c.color,
        backgroundColor: c.bg,
      }}
    >
      {c.label}
    </span>
  )
}

// ------------------------------------------------------------
// Evidence 卡片
// ------------------------------------------------------------

function EvidenceCard({
  evidence,
  onClick,
}: {
  evidence: EvidenceResponse
  onClick: () => void
}) {
  const data = evidence.data as Record<string, any> || {}
  
  // 提取关键信息
  const getTitle = () => {
    if (evidence.evidence_type === 'business') {
      return data.event_type || '工商事件'
    }
    if (evidence.evidence_type === 'judicial') {
      return data.case_type || '司法案件'
    }
    if (evidence.evidence_type === 'relation') {
      return data.relation_type || '企业关系'
    }
    return evidence.evidence_id
  }

  const getDescription = () => {
    if (evidence.evidence_type === 'business') {
      return data.detail || data.new_value || '-'
    }
    if (evidence.evidence_type === 'judicial') {
      return data.cause || data.case_number || '-'
    }
    if (evidence.evidence_type === 'relation') {
      const targetName = data.to_company_name || data.to_company_id || ''
      return `${data.relation_type || ''} ${targetName}`
    }
    return '-'
  }

  const getRiskMeaning = () => {
    if (evidence.evidence_type === 'judicial') {
      const caseType = data.case_type || ''
      if (caseType.includes('执行')) return '被执行人 - 存在未履行债务'
      if (caseType.includes('失信')) return '失信被执行人 - 信用严重受损'
      if (caseType.includes('限制')) return '限制消费令 - 高消费受限'
      if (caseType.includes('冻结')) return '股权冻结 - 股权处置受限'
      if (caseType.includes('诉讼')) return '诉讼案件 - 存在法律纠纷'
    }
    if (evidence.evidence_type === 'business') {
      const eventType = data.event_type || ''
      if (eventType.includes('异常')) return '经营异常 - 需关注经营状况'
      if (eventType.includes('处罚')) return '行政处罚 - 存在违规行为'
      if (eventType.includes('变更')) return '工商变更 - 需关注变动原因'
    }
    return null
  }

  const riskMeaning = getRiskMeaning()

  return (
    <div
      onClick={onClick}
      style={{
        padding: '12px 16px',
        borderBottom: '1px solid #e2e8f0',
        cursor: 'pointer',
        transition: 'background-color 0.15s',
        backgroundColor: 'transparent',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = '#f8fafc'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent'
      }}
    >
      {/* 头部：ID + 类型标签 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span
          style={{
            fontFamily: 'monospace',
            fontSize: 12,
            fontWeight: 600,
            color: '#1e293b',
          }}
        >
          {evidence.evidence_id}
        </span>
        <EvidenceTypeTag type={evidence.evidence_type} />
      </div>

      {/* 标题 */}
      <div
        style={{
          fontSize: 13,
          fontWeight: 500,
          color: '#1e293b',
          marginBottom: 4,
          lineHeight: 1.4,
        }}
      >
        {getTitle()}
      </div>

      {/* 描述 */}
      <div
        style={{
          fontSize: 12,
          color: '#64748b',
          lineHeight: 1.4,
          marginBottom: riskMeaning ? 6 : 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {getDescription()}
      </div>

      {/* 风险含义 */}
      {riskMeaning && (
        <div
          style={{
            fontSize: 11,
            color: '#dc2626',
            backgroundColor: '#fef2f2',
            padding: '4px 8px',
            borderRadius: 4,
            border: '1px solid #fecaca',
          }}
        >
          ⚠️ {riskMeaning}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------
// 主组件
// ------------------------------------------------------------

export default function EvidenceDetailPanel({
  companyId,
  companyName,
  evidenceIds,
  onClose,
}: {
  companyId: string
  companyName: string
  evidenceIds: string[]
  onClose: () => void
}) {
  const [evidences, setEvidences] = useState<EvidenceResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceResponse | null>(null)

  const fetchEvidences = useCallback(async (ids: string[]) => {
    if (ids.length === 0) {
      setEvidences([])
      return
    }

    setLoading(true)
    setError(null)
    setEvidences([])

    try {
      const results = await Promise.all(
        ids.map(async (id) => {
          try {
            return await api.getEvidence(id)
          } catch (e) {
            // 单个证据加载失败，返回 null
            return null
          }
        })
      )
      setEvidences(results.filter((r): r is EvidenceResponse => r !== null))
    } catch (e) {
      setError('加载证据列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (evidenceIds.length > 0) {
      void fetchEvidences(evidenceIds)
    } else {
      setEvidences([])
    }
  }, [evidenceIds, fetchEvidences])

  // ESC 关闭
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  return (
    <>
      {/* 遮罩层 */}
      <div
        className="ev-overlay"
        onClick={onClose}
        style={{ opacity: 1, pointerEvents: 'auto' }}
      />

      {/* Panel */}
      <div
        className="ev-drawer ev-drawer-open"
        style={{
          width: 420,
          maxWidth: '90vw',
        }}
      >
        {/* Header */}
        <div className="ev-header">
          <div className="ev-header-top">
            <h3>企业证据详情</h3>
            <button className="ev-close" onClick={onClose} title="关闭">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          {/* 企业信息 */}
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#1e293b' }}>
              {companyName}
            </div>
            <div style={{ fontSize: 13, color: '#64748b', fontFamily: 'monospace' }}>
              {companyId}
            </div>
          </div>
          {/* 统计 */}
          <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
            共 {evidenceIds.length} 条证据
            {evidences.length > 0 && ` · 已加载 ${evidences.length} 条`}
          </div>
        </div>

        {/* Content */}
        <div className="ev-body" style={{ padding: 0 }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '32px 0' }}>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
                <span className="spinner" />
                <span style={{ fontSize: 14, color: '#64748b' }}>加载证据中…</span>
              </div>
            </div>
          )}

          {error && (
            <div style={{ padding: 16, color: '#dc2626', fontSize: 13 }}>
              {error}
            </div>
          )}

          {!loading && !error && evidences.length === 0 && (
            <div style={{ textAlign: 'center', padding: '32px 0', color: '#64748b' }}>
              <div style={{ fontSize: 14, marginBottom: 8 }}>暂无证据</div>
              <div style={{ fontSize: 12 }}>该企业暂无关联证据记录</div>
            </div>
          )}

          {!loading && !error && evidences.length > 0 && (
            <div>
              {evidences.map((ev) => (
                <EvidenceCard
                  key={ev.evidence_id}
                  evidence={ev}
                  onClick={() => setSelectedEvidence(ev)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 证据详情弹窗 */}
      {selectedEvidence && (
        <EvidenceDetailModal
          evidence={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
        />
      )}
    </>
  )
}

// ------------------------------------------------------------
// 证据详情弹窗
// ------------------------------------------------------------

function EvidenceDetailModal({
  evidence,
  onClose,
}: {
  evidence: EvidenceResponse
  onClose: () => void
}) {
  const data = evidence.data as Record<string, any> || {}

  return (
    <>
      {/* 遮罩层 */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          zIndex: 10000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onClick={onClose}
      />

      {/* 弹窗 */}
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          backgroundColor: '#fff',
          borderRadius: 12,
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          zIndex: 10001,
          width: 480,
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflow: 'auto',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#1e293b' }}>
              证据详情
            </div>
            <div style={{ fontSize: 13, color: '#64748b', fontFamily: 'monospace', marginTop: 4 }}>
              {evidence.evidence_id}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              borderRadius: 4,
              color: '#64748b',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '16px 20px' }}>
          {/* 数据字段 */}
          <div>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>数据详情</div>
            <div
              style={{
                backgroundColor: '#f8fafc',
                borderRadius: 8,
                padding: 12,
                fontFamily: 'monospace',
                fontSize: 12,
                color: '#475569',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {JSON.stringify(data, null, 2)}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
