import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { SearchItem } from '../api/types'
import { BusinessStatusTag } from '../components/Badges'
import { EmptyState, ErrorBlock, LoadingState } from '../components/States'
import { truncate } from '../lib/format'

type SearchState =
  | { status: 'idle' }
  | { status: 'loading'; keyword: string }
  | { status: 'done'; keyword: string; total: number; items: SearchItem[] }
  | { status: 'error'; keyword: string; error: ApiError }

/** 演示用热门企业快捷入口（仅展示 ID，数据均来自真实接口） */
const HOT_IDS = ['C001', 'C004', 'C005']

export default function HomePage() {
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [state, setState] = useState<SearchState>({ status: 'idle' })
  const seqRef = useRef(0)

  const doSearch = async (keyword: string) => {
    const kw = keyword.trim()
    if (!kw) return
    const seq = ++seqRef.current
    setState({ status: 'loading', keyword: kw })
    try {
      const res = await api.search(kw)
      if (seq !== seqRef.current) return // 丢弃过期响应
      setState({ status: 'done', keyword: res.keyword, total: res.total, items: res.items })
    } catch (e) {
      if (seq !== seqRef.current) return
      setState({ status: 'error', keyword: kw, error: e as ApiError })
    }
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    void doSearch(input)
  }

  return (
    <div>
      {/* 品牌 Hero + 搜索 */}
      <section className="hero">
        <div className="hero-inner">
          <h1>企业关联风险智能洞察系统</h1>
          <p className="hero-desc">
            企业工商信息 · 经营动态 · 司法风险 · 关联关系 · AI 风险洞察
            —— 数据均实时来自系统后端，AI 分析由 Risk Harness 真实执行
          </p>
          <form className="search-box" onSubmit={onSubmit}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" style={{ flex: 'none', alignSelf: 'center' }}>
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.2-3.2" strokeLinecap="round" />
            </svg>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入企业名称 / company_id / 统一社会信用代码，如：华辰 或 C001"
              autoFocus
            />
            <button type="submit" disabled={state.status === 'loading'}>
              {state.status === 'loading' ? (
                <>
                  <span className="spinner" style={{ borderColor: 'rgba(255,255,255,.4)', borderTopColor: '#fff' }} />
                  搜索中
                </>
              ) : (
                '搜索企业'
              )}
            </button>
          </form>
          <div className="hot-tips">
            <span>热门企业（演示快捷入口）：</span>
            {HOT_IDS.map((id) => (
              <a key={id} className="hot-chip" onClick={() => navigate(`/company/${id}`)}>
                {id}
              </a>
            ))}
          </div>
        </div>
      </section>

      <div className="page">
        {/* 搜索结果区 */}
        {state.status === 'idle' && (
          <div className="card">
            <div className="card-body" style={{ padding: '36px 24px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
                <div style={{ width: 48, height: 48, borderRadius: 12, background: 'var(--brand-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="1.8">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="M3 10h18M8 15h4" strokeLinecap="round" />
                  </svg>
                </div>
                <div style={{ fontWeight: 600, fontSize: 15 }}>输入关键词开始查询</div>
                <div className="desc" style={{ color: 'var(--text-3)', fontSize: 13, maxWidth: 480 }}>
                  支持企业名称（如「华辰」）、企业 ID（如 C001）、统一社会信用代码（如 SYN-C001）三种检索方式。
                  查询结果将展示企业的基本工商信息，点击可进入详情页查看经营动态、司法风险、关联关系与 AI 风险洞察。
                </div>
              </div>
            </div>
          </div>
        )}

        {state.status === 'loading' && (
          <div className="card">
            <LoadingState text={`正在搜索「${state.keyword}」…`} />
          </div>
        )}

        {state.status === 'error' && (
          <div className="card">
            <div className="card-body">
              <ErrorBlock
                title={`搜索「${state.keyword}」失败`}
                message={state.error.message}
                code={state.error.code}
                onRetry={() => void doSearch(state.keyword)}
              />
            </div>
          </div>
        )}

        {state.status === 'done' && (
          <div className="card">
            <div className="stat-bar">
              <span>
                关键词 <b>「{state.keyword}」</b>
              </span>
              <span>
                命中 <b>{state.total}</b> 家企业
              </span>
            </div>
            {state.items.length === 0 ? (
              <EmptyState
                title="未找到匹配的企业"
                desc={`未找到与「${state.keyword}」相关的企业。请尝试企业名称（如 华辰）、企业 ID（如 C001）或统一社会信用代码。`}
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>企业名称</th>
                      <th>企业 ID</th>
                      <th>统一社会信用代码</th>
                      <th>法定代表人</th>
                      <th>行业</th>
                      <th>经营状态</th>
                      <th>数据来源</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.items.map((it) => (
                      <tr
                        key={it.company_id}
                        style={{ cursor: 'pointer' }}
                        onClick={() => navigate(`/company/${it.company_id}`)}
                        title="点击查看企业详情"
                      >
                        <td>
                          <b>{it.company_name}</b>
                        </td>
                        <td className="mono">{it.company_id}</td>
                        <td className="mono muted">{it.credit_code ?? '-'}</td>
                        <td>{it.legal_rep ?? '-'}</td>
                        <td className="muted">{truncate(it.industry, 16)}</td>
                        <td>
                          <BusinessStatusTag raw={it.business_status} />
                        </td>
                        <td className="muted">{it.data_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}