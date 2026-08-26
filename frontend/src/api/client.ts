/**
 * API 客户端：统一封装 fetch、错误归一化与超时控制。
 *
 * - 所有路径走相对地址，由 Vite dev server 代理到后端（见 vite.config.ts）
 * - 后端统一错误格式：{"detail": {"code": string, "message": string}}
 * - POST /api/analysis 为同步阻塞接口（实测 3-20 分钟），超时设为 30 分钟，
 *   不设短超时，避免长分析被中断
 */
import type {
  AnalysisResponse,
  ApiErrorBody,
  BusinessEventsResponse,
  JudicialEventsResponse,
  ProfileResponse,
  RelationNetworkResponse,
  RelationsResponse,
  SearchResponse,
  TaskResponse,
} from './types'

/** 前端错误分类：与后端错误码相互独立 */
export type ApiErrorKind =
  | 'HTTP' // 后端返回了非 2xx（含 400/404/503/504/500）
  | 'NETWORK' // 网络不可达 / 连接被拒绝
  | 'TIMEOUT' // 超时（仅非 analysis 接口）
  | 'PARSE' // 响应解析失败

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number
  readonly code: string | null

  constructor(kind: ApiErrorKind, message: string, status = 0, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}

export const HTTP_TIMEOUT_MS = 30_000
export const ANALYSIS_TIMEOUT_MS = 30 * 60 * 1000 // 30 分钟，覆盖后端 3-20 分钟阻塞耗时

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = HTTP_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new ApiError('TIMEOUT', `请求超时（${Math.round(timeoutMs / 1000)} 秒）`, 0, 'TIMEOUT')
    }
    throw new ApiError('NETWORK', '网络错误：无法连接后端服务，请确认后端已启动', 0, 'NETWORK_ERROR')
  } finally {
    clearTimeout(timer)
  }

  const text = await res.text().catch(() => '')
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }

  if (!res.ok) {
    const body = data as ApiErrorBody | null
    const detail = body?.detail
    if (detail && typeof detail.code === 'string') {
      throw new ApiError('HTTP', detail.message, res.status, detail.code)
    }
    throw new ApiError('HTTP', `请求失败（HTTP ${res.status}）`, res.status, 'HTTP_ERROR')
  }
  return data as T
}

export const api = {
  /** 企业搜索（名称 / company_id / 统一社会信用代码） */
  search(keyword: string): Promise<SearchResponse> {
    return request<SearchResponse>(`/api/companies/search?keyword=${encodeURIComponent(keyword)}`)
  },

  /** 企业完整工商信息 */
  profile(companyId: string): Promise<ProfileResponse> {
    return request<ProfileResponse>(`/api/companies/${encodeURIComponent(companyId)}`)
  },

  /** 工商（经营）动态事件 */
  businessEvents(companyId: string): Promise<BusinessEventsResponse> {
    return request<BusinessEventsResponse>(
      `/api/companies/${encodeURIComponent(companyId)}/business-events`,
    )
  },

  /** 司法事件 */
  judicialEvents(companyId: string): Promise<JudicialEventsResponse> {
    return request<JudicialEventsResponse>(
      `/api/companies/${encodeURIComponent(companyId)}/judicial-events`,
    )
  },

  /** 一跳关联关系 */
  relations(companyId: string): Promise<RelationsResponse> {
    return request<RelationsResponse>(`/api/companies/${encodeURIComponent(companyId)}/relations`)
  },

  /** V1.1: 企业完整关联关系网络（多跳 BFS） */
  relationNetwork(companyId: string): Promise<RelationNetworkResponse> {
    return request<RelationNetworkResponse>(
      `/api/companies/${encodeURIComponent(companyId)}/relation-network`,
    )
  },

  /**
   * AI 风险分析（同步阻塞 3-20 分钟，真实调用 Risk Harness）。
   * 超时 30 分钟，期间不卡死页面（fetch 为异步，不阻塞主线程）。
   */
  analyze(companyId: string): Promise<AnalysisResponse> {
    return request<AnalysisResponse>(
      '/api/analysis',
      {
        method: 'POST',
        body: JSON.stringify({ company_id: companyId }),
      },
      ANALYSIS_TIMEOUT_MS,
    )
  },

  /** 创建异步分析任务 */
  createAnalysisTask(companyId: string): Promise<TaskResponse> {
    return request<TaskResponse>(
      '/api/analysis/tasks',
      {
        method: 'POST',
        body: JSON.stringify({ company_id: companyId }),
      },
    )
  },

  /** 查询任务状态 */
  getAnalysisTask(taskId: string): Promise<TaskResponse> {
    return request<TaskResponse>(
      `/api/analysis/tasks/${encodeURIComponent(taskId)}`,
    )
  },

  /** 查询企业当前活跃任务（无活跃任务时返回 null，不抛异常） */
  async getCompanyActiveTask(companyId: string): Promise<TaskResponse | null> {
    try {
      return await request<TaskResponse>(
        `/api/analysis/tasks/company/${encodeURIComponent(companyId)}/active`,
      )
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && e.code === 'TASK_NOT_FOUND') {
        return null
      }
      throw e
    }
  },

  /**
   * 读取已有分析结果（不触发 Harness，仅读取 runs/web/<id>/analysis_result.json）。
   * 404 时返回 null（表示该企业尚未分析）。
   */
  async latestAnalysis(companyId: string): Promise<AnalysisResponse | null> {
    try {
      return await request<AnalysisResponse>(
        `/api/companies/${encodeURIComponent(companyId)}/analysis/latest`,
      )
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && e.code === 'ANALYSIS_NOT_FOUND') {
        return null
      }
      throw e
    }
  },

  /** V1.1: 导出 AI 风险报告 PDF */
  async exportPdf(companyId: string): Promise<void> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS)

    try {
      const res = await fetch(
        `/api/analysis/${encodeURIComponent(companyId)}/latest/pdf`,
        {
          signal: controller.signal,
          headers: {
            Accept: 'application/pdf',
          },
        },
      )

      if (!res.ok) {
        const text = await res.text().catch(() => '')
        let data: unknown = null
        try {
          data = text ? JSON.parse(text) : null
        } catch {
          data = null
        }

        const body = data as ApiErrorBody | null
        const detail = body?.detail
        if (detail && typeof detail.code === 'string') {
          throw new ApiError('HTTP', detail.message, res.status, detail.code)
        }
        throw new ApiError('HTTP', `请求失败（HTTP ${res.status}）`, res.status, 'HTTP_ERROR')
      }

      // 获取文件名
      const disposition = res.headers.get('Content-Disposition')
      let filename = 'report.pdf'
      if (disposition) {
        const match = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/)
        if (match) {
          filename = decodeURIComponent(match[1])
        }
      }

      // 下载文件
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } finally {
      clearTimeout(timer)
    }
  },
}
