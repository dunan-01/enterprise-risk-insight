import { tool } from "@opencode-ai/plugin"
import path from "path"


async function callPython(
    action: string,
    value: string,
    context: any
) {
    const root = context.directory

    const script = path.join(
        root,
        ".opencode",
        "tools",
        "risk_bridge.py"
    )

    const proc = Bun.spawn(
        [
            "python",
            script,
            action,
            value
        ],
        {
            cwd: root,
            stdout: "pipe",
            stderr: "pipe"
        }
    )

    const stdout = await new Response(proc.stdout).text()
    const stderr = await new Response(proc.stderr).text()

    const exitCode = await proc.exited

    if (exitCode !== 0) {
        return JSON.stringify(
            {
                error: "Python tool execution failed",
                exit_code: exitCode,
                action,
                value,
                directory: context.directory,
                worktree: context.worktree,
                script,
                stdout,
                stderr
            },
            null,
            2
        )
    }

    return stdout.trim()
}


// ============================================================
// 搜索企业
// ============================================================

export const search_company = tool({
    description:
        "根据企业ID、企业名称或统一社会信用代码搜索企业。调查企业前，如果用户提供的是企业名称而不是company_id，应先使用该工具。",

    args: {
        keyword: tool.schema
            .string()
            .describe("企业ID、企业名称或统一社会信用代码"),
    },

    async execute(args, context) {
        return callPython(
            "search_company",
            args.keyword,
            context
        )
    },
})


// ============================================================
// 企业基本信息
// ============================================================

export const get_company_profile = tool({
    description:
        "查询指定企业的完整基本工商信息，包括法定代表人、注册资本、成立日期、行业、经营状态、地址和经营范围等。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_company_profile",
            args.company_id,
            context
        )
    },
})


// ============================================================
// 经营事件
// ============================================================

export const get_business_events = tool({
    description:
        "查询指定企业的经营及工商动态事件，包括法人变更、股东变更、经营异常、行政处罚、地址变更、注册资本变更等。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_business_events",
            args.company_id,
            context
        )
    },
})


// ============================================================
// 司法事件
// ============================================================

export const get_judicial_events = tool({
    description:
        "查询指定企业的司法事件，包括诉讼、被执行、失信被执行、限制消费、股权冻结等。返回结果包含企业在案件中的role，分析时应注意区分原告、被告、被执行人等不同角色。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_judicial_events",
            args.company_id,
            context
        )
    },
})


// ============================================================
// 企业关系
// ============================================================

export const get_company_relations = tool({
    description:
        "查询指定企业的一跳直接关联企业及关系，包括股权、对外投资、共同法人、共同股东、担保等。该工具只返回一跳关系，如需调查关联企业，应继续查询对应企业。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_company_relations",
            args.company_id,
            context
        )
    },
})


// ============================================================
// 舆情事件
// ============================================================
export const get_public_opinion_events = tool({
    description:
        "查询指定企业的舆情事件，包括产品质量、合同纠纷、环境问题、劳动争议、融资消息、项目中标、市场传闻等。返回舆情标题、情感倾向、核实状态等，注意区分已核实和未经核实的信息。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_public_opinion_events",
            args.company_id,
            context
        )
    },
})

// ============================================================
// 财务报告
// ============================================================
export const get_financial_reports = tool({
    description:
        "查询指定企业的财务报告，包括营业收入、净利润、总资产、总负债、经营现金流、应收账款等。返回连续年度数据，附带资产负债率、流动比率、净利率、同比增长率等计算指标。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_financial_reports",
            args.company_id,
            context
        )
    },
})

// ============================================================
// 招聘事件
// ============================================================
export const get_recruitment_events = tool({
    description:
        "查询指定企业的招聘信息，包括岗位类型、岗位名称、计划招聘人数、薪资范围、招聘状态等。招聘信息属于弱经营信号，需结合财务、司法、舆情等多源数据综合判断。",

    args: {
        company_id: tool.schema
            .string()
            .describe("企业唯一ID，例如 C001"),
    },

    async execute(args, context) {
        return callPython(
            "get_recruitment_events",
            args.company_id,
            context
        )
    },
})