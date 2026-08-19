# 企业关联风险智能洞察系统 —— Web 前端

专业金融风控风格的企业风险分析平台前端。所有数据均来自后端 FastAPI 真实接口，无任何 mock。

## 技术栈

| 类别 | 选型 |
|---|---|
| 构建 | Vite 6 + TypeScript 5.9 |
| 框架 | React 19 + react-router-dom 7 |
| 图表 | ECharts 5.6（原生封装，未用 echarts-for-react） |
| Markdown | react-markdown 10 + remark-gfm 4 |
| 样式 | 自定义 CSS 设计系统（CSS 变量，无 UI 框架） |

## 启动方式

### 1. 启动后端（端口 8000，可被 PORT 环境变量覆盖）

```bash
cd /Users/dujiangli/Desktop/risk/backend
.venv/bin/python -m app.main
```

### 2. 启动前端（端口 5173）

```bash
cd /Users/dujiangli/Desktop/risk/frontend
npm install        # 首次
npm run dev
```

访问 http://127.0.0.1:5173

Vite dev server 已配置代理：`/api` 与 `/health` → `http://127.0.0.1:8000`（无 CORS 问题；后端同时允许所有来源）。

### 构建

```bash
npm run build      # tsc --noEmit && vite build（产物在 dist/）
npm run preview    # 预览构建产物
```

## 页面与后端接口映射

| 页面 / 功能 | 路由 | 后端接口 |
|---|---|---|
| 首页（企业搜索） | `/` | `GET /api/companies/search?keyword=` |
| 企业详情 - 概览卡片 + 企业概况 Tab | `/company/:companyId?tab=overview` | `GET /api/companies/{company_id}` |
| 工商动态 Tab | `?tab=business` | `GET /api/companies/{company_id}/business-events` |
| 司法风险 Tab | `?tab=judicial` | `GET /api/companies/{company_id}/judicial-events` |
| 关联关系 Tab（表格 + 关系网络图） | `?tab=relations` | `GET /api/companies/{company_id}/relations` |
| AI 风险洞察 Tab | `?tab=analysis` | `POST /api/analysis`（body: `{"company_id": ...}`） |

## 目录结构

```
frontend/
├── index.html
├── package.json / tsconfig.json / tsconfig.node.json / vite.config.ts
└── src/
    ├── main.tsx                     # 入口（createRoot + StrictMode + BrowserRouter）
    ├── App.tsx                      # 路由表（/ 、/company/:companyId、兜底重定向）
    ├── api/
    │   ├── types.ts                 # 与后端契约一致的 TS 类型（models.py 为准）
    │   └── client.ts                # fetch 封装：错误归一化（400/404/503）、超时控制
    ├── lib/
    │   ├── format.ts                # 金额/百分比/日期/耗时格式化
    │   └── presentation.ts          # 展示层色阶映射（低/中/高/严重、角色、证据前缀）—— 不做任何风险推导
    ├── components/
    │   ├── Layout.tsx               # 深色顶部导航 + 后端健康状态
    │   ├── Badges.tsx               # 风险等级/Verification/证据/角色/事件类型标签
    │   ├── States.tsx               # loading / 错误 / 空状态 / 骨架屏
    │   ├── MarkdownReport.tsx       # react-markdown + remark-gfm
    │   └── RelationGraph.tsx        # ECharts graph 关系网络图（一跳）
    ├── pages/
    │   ├── HomePage.tsx             # 搜索页（热门企业 C001/C004/C005 快捷入口）
    │   ├── CompanyPage.tsx          # 详情页：概览卡片 + 5 Tab + AI 分析状态机（页面级持有）
    │   └── tabs/
    │       ├── OverviewTab.tsx
    │       ├── BusinessEventsTab.tsx
    │       ├── JudicialEventsTab.tsx
    │       ├── RelationsTab.tsx
    │       └── AnalysisTab.tsx      # idle → loading → done/error
    └── styles/global.css            # 设计系统（深色导航 + 浅色内容、风险色阶、紧凑表格）
```

## 关键设计说明

### AI 分析状态机（AnalysisTab）

```
idle ──点击「启动 AI 风险分析」──▶ loading ──▶ done（完整结果）
                                   │
                                   └──▶ error（404/503/网络，可重试）
```

- 状态提升到 CompanyPage 持有，**切换 Tab 不中断分析请求**（fetch 异步，不阻塞 UI）
- loading 期间：真实等待计时（客户端计时器）+ 三阶段静态流程示意（企业调查→覆盖审核→风险核验，标注"分析中"），**不伪造实时进度百分比**
- fetch 超时 30 分钟（后端同步阻塞 3-20 分钟）
- done 后展示：风险等级（后端原值）、summary、related_companies chips、evidence_ids 徽标（B=工商蓝/J=司法红/R=关系紫）、Verification 状态（PASS=绿/UNRESOLVED=橙/其他警示色，**如实展示后端返回值**）、完整 Markdown 报告、重新分析按钮

### 展示约束

- 前端**不计算**风险等级：只按后端返回的 risk_level 字符串做色阶映射（低=绿/中=橙/高=红/严重=深红，未知值回退中性灰），null 显示"未解析"
- 搜索结果表格不含"注册资本"列：后端搜索接口契约不返回该字段（契约以 backend/app/models.py 为准）
- 司法风险页注明"企业角色为原告的案件不代表企业自身风险"

### 已知问题

1. **echarts 5.6 graph 系列 bug**：graph 系列 data 携带 `category` 字段 + 配置 `legend` 组件（即使 `show:false`）时，数据会被处理为空导致图表空白。前端已规避：不配置 legend、data 不带 category（节点样式用 symbolSize/itemStyle 区分）。若升级 echarts 可重新验证。
2. 后端解析出的 `risk_level` 可能含 Markdown 符号残留（实测 C001 返回 `**低`），前端按约束如实展示原值。
3. 分析期间离开详情页（路由跳走）会丢失结果（fetch 仍会在后台完成但页面不再接收）。重新进入页面后需重新发起分析。
4. echarts 全量包约 1MB（gzip 343KB），已通过 manualChunks 独立分包，后续可按需引入 graph 模块瘦身。