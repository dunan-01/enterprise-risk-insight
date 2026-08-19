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