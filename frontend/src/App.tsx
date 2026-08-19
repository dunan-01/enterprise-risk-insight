import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import CompanyPage from './pages/CompanyPage'
import HomePage from './pages/HomePage'

/**
 * 路由表：
 * - "/"                     首页（企业搜索）
 * - "/company/:company_id"  企业详情页（5 个 Tab：概况/工商/司法/关系/AI 洞察）
 * - 其他                     兜底重定向到首页
 */
export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/company/:companyId" element={<CompanyPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}