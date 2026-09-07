#!/usr/bin/env python3
"""
企业关联风险智能洞察系统 —— 扩展数据源种子脚本（V2.0）。

在现有 C001-C010 十家模拟企业基础上，新增三类异构数据：
1. 舆情事件 (public_opinion_events)  — Pxxx
2. 财务报告 (financial_reports)      — Fxxx
3. 招聘事件 (recruitment_events)     — Hxxx

设计原则：
- 所有数据均为 SIMULATED，不伪装真实新闻
- 可重复运行（idempotent），使用固定数据
- 与现有 B/J/R 数据保持大致一致的企业背景
- 包含矛盾信号，测试 Agent 多源融合能力
- 舆情包含 positive/neutral/negative 三类
- 财务包含不同经营趋势（增长/下降/现金流恶化等）
- 招聘包含扩张/冻结/缩减等不同信号

运行方式：
    cd /path/to/risk && python scripts/seed_extended_risk_data.py

依赖：
    仅使用 Python 标准库（sqlite3）
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# ------------------------------------------------------------
# 路径
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "risk.db"


# ============================================================
# 1. 舆情事件数据（P001 - P035）
# ============================================================

PUBLIC_OPINION_EVENTS = [
    # ---- C001 华辰智能科技（软件和信息技术服务业）----
    # 背景：法人变更+地址变更，无司法风险，持有C002 75%
    {
        "event_id": "P001",
        "company_id": "C001",
        "publish_date": "2025-03-15",
        "topic": "业务扩张",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "华辰智能科技宣布拓展人工智能业务板块",
        "summary": "华辰智能科技有限公司宣布将在2025年加大人工智能领域投入，计划新增三条产品线，预计带动营收增长20%以上。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P002",
        "company_id": "C001",
        "publish_date": "2025-06-20",
        "topic": "高管变动",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "华辰智能科技完成管理层换届",
        "summary": "华辰智能科技有限公司近期完成管理层调整，新任总经理张明远表示将延续公司技术驱动战略。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P003",
        "company_id": "C001",
        "publish_date": "2025-09-10",
        "topic": "融资消息",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "华辰智能科技获得A轮融资5000万元",
        "summary": "华辰智能科技有限公司宣布完成A轮融资，由某知名创投基金领投，融资金额5000万元，将用于技术研发和市场拓展。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # ---- C002 远海供应链管理（商务服务业）----
    # 背景：经营异常+行政处罚+被执行人+失信被执行人，风险较高
    {
        "event_id": "P004",
        "company_id": "C002",
        "publish_date": "2025-04-10",
        "topic": "客户投诉",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "多家企业反映远海供应链服务延迟问题",
        "summary": "近期有多家企业反映远海供应链管理有限公司存在货物运输延迟、服务响应不及时等问题，涉及合同违约纠纷。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
    {
        "event_id": "P005",
        "company_id": "C002",
        "publish_date": "2025-07-22",
        "topic": "监管关注",
        "sentiment": "negative",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "远海供应链被列入经营异常名录引发市场关注",
        "summary": "远海供应链管理有限公司因通过登记住所无法取得联系被列入经营异常名录，市场对其经营状况产生担忧。",
        "verification_status": "verified",
        "response_status": "no_response",
        "data_type": "simulated",
    },
    {
        "event_id": "P006",
        "company_id": "C002",
        "publish_date": "2025-11-15",
        "topic": "合同纠纷",
        "sentiment": "negative",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "远海供应链涉嫌多起合同违约被诉",
        "summary": "据公开信息显示，远海供应链管理有限公司近期涉及多起合同纠纷案件，原告方包括多家物流合作企业。",
        "verification_status": "verified",
        "response_status": "no_response",
        "data_type": "simulated",
    },

    # ---- C003 恒达商贸（批发业）----
    # 背景：股东变更x2+经营异常+原告角色诉讼，整体中等风险
    {
        "event_id": "P007",
        "company_id": "C003",
        "publish_date": "2025-02-18",
        "topic": "市场传闻",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "恒达商贸股东结构调整引发市场猜测",
        "summary": "恒达商贸有限公司近期发生股东变更，市场传言公司可能进行业务转型，但公司未予正面回应。",
        "verification_status": "unverified",
        "response_status": "no_response",
        "data_type": "simulated",
    },
    {
        "event_id": "P008",
        "company_id": "C003",
        "publish_date": "2025-05-30",
        "topic": "产品质量",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "恒达商贸部分批次商品被抽检不合格",
        "summary": "市场监管部门对恒达商贸部分批次商品进行抽检，发现存在标签不规范等问题，公司已启动整改。",
        "verification_status": "verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
    {
        "event_id": "P009",
        "company_id": "C003",
        "publish_date": "2025-10-08",
        "topic": "项目中标",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "恒达商贸中标某大型采购项目",
        "summary": "恒达商贸有限公司成功中标某政府采购项目，合同金额约800万元，预计将对公司2025年度营收产生积极影响。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # ---- C004 新源新能源材料（新材料制造业）----
    # 背景：无B/J事件，持有C005 60%，与C008共同股东，相对稳定
    {
        "event_id": "P010",
        "company_id": "C004",
        "publish_date": "2025-01-20",
        "topic": "业务扩张",
        "sentiment": "positive",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "新源新能源材料产能扩张项目投产",
        "summary": "新源新能源材料有限公司新建生产线正式投产，年产能提升30%，主要面向新能源汽车电池材料市场。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P011",
        "company_id": "C004",
        "publish_date": "2025-08-05",
        "topic": "环境问题",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "新源新能源材料因排放问题被环保部门约谈",
        "summary": "新源新能源材料有限公司因废气排放指标偶发超标被当地环保部门约谈，公司表示已完成设备升级改造。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },

    # ---- C005 博远数字科技（软件和信息技术服务业）----
    # 背景：注册资本变更+被告角色诉讼+被C004持有60%，中等风险
    {
        "event_id": "P012",
        "company_id": "C005",
        "publish_date": "2025-03-25",
        "topic": "市场传闻",
        "sentiment": "negative",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "市场传闻博远数字科技存在资金压力",
        "summary": "有市场传闻称博远数字科技有限公司近期面临资金周转压力，部分供应商货款出现延迟支付情况。",
        "verification_status": "unverified",
        "response_status": "no_response",
        "data_type": "simulated",
    },
    {
        "event_id": "P013",
        "company_id": "C005",
        "publish_date": "2025-06-12",
        "topic": "重大合作",
        "sentiment": "positive",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "博远数字科技与某央企签署战略合作协议",
        "summary": "博远数字科技有限公司与某大型央企签署为期三年的数字化转型服务协议，合同总金额约2000万元。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P014",
        "company_id": "C005",
        "publish_date": "2025-11-28",
        "topic": "劳动争议",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "博远数字科技被曝存在裁员情况",
        "summary": "有媒体报道称博远数字科技有限公司近期进行了约15%的人员优化，公司回应称属于正常业务调整。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },

    # ---- C006 嘉盛产业投资（商务服务业）----
    # 背景：股东变更+投资C007 70%+投资C008 25%，相对稳定
    {
        "event_id": "P015",
        "company_id": "C006",
        "publish_date": "2025-04-08",
        "topic": "融资消息",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "嘉盛产业投资完成新一轮基金募集",
        "summary": "嘉盛产业投资有限公司宣布完成旗下产业基金新一轮募集，规模达3亿元，将重点布局先进制造业和新能源领域。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P016",
        "company_id": "C006",
        "publish_date": "2025-09-18",
        "topic": "监管关注",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "嘉盛产业投资旗下基金完成年检",
        "summary": "嘉盛产业投资有限公司旗下基金顺利通过年度合规检查，各项指标符合监管要求。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # ---- C007 鼎峰建设工程（建筑业）----
    # 背景：行政处罚+经营异常+被执行人x2+限制消费令+股权冻结，高风险
    {
        "event_id": "P017",
        "company_id": "C007",
        "publish_date": "2025-02-28",
        "topic": "工程质量",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "鼎峰建设工程某项目工程质量问题引发关注",
        "summary": "鼎峰建设工程有限公司承建的某住宅项目被业主投诉存在墙面开裂、渗水等质量问题，住建部门已介入调查。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
    {
        "event_id": "P018",
        "company_id": "C007",
        "publish_date": "2025-05-20",
        "topic": "劳动争议",
        "sentiment": "negative",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "鼎峰建设工程被曝拖欠工人工资",
        "summary": "有工人反映鼎峰建设工程有限公司存在拖欠工资情况，涉及金额约200万元，劳动监察部门已介入协调。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
    {
        "event_id": "P019",
        "company_id": "C007",
        "publish_date": "2025-08-15",
        "topic": "合同纠纷",
        "sentiment": "negative",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "鼎峰建设工程陷入多起材料款纠纷",
        "summary": "鼎峰建设工程有限公司近期涉及多起建筑材料采购合同纠纷，供应商方要求支付拖欠货款及违约金。",
        "verification_status": "verified",
        "response_status": "no_response",
        "data_type": "simulated",
    },
    {
        "event_id": "P020",
        "company_id": "C007",
        "publish_date": "2025-11-05",
        "topic": "项目中标",
        "sentiment": "positive",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "鼎峰建设工程中标某市政工程项目",
        "summary": "尽管面临诸多经营挑战，鼎峰建设工程有限公司仍成功中标某市政道路改造项目，合同金额约1500万元。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # ---- C008 瑞泽机械制造（通用设备制造业）----
    # 背景：地址变更+原告角色诉讼+与C004共同股东，中等偏低风险
    {
        "event_id": "P021",
        "company_id": "C008",
        "publish_date": "2025-03-10",
        "topic": "业务扩张",
        "sentiment": "positive",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "瑞泽机械制造新生产线开工仪式举行",
        "summary": "瑞泽机械制造有限公司新建成的智能生产线正式开工，预计将使公司产能翻倍，主要面向高端装备市场。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P022",
        "company_id": "C008",
        "publish_date": "2025-07-18",
        "topic": "产品质量",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "瑞泽机械制造通过ISO9001质量体系复审",
        "summary": "瑞泽机械制造有限公司顺利通过ISO9001质量管理体系年度复审，审核机构对其质量管控能力给予肯定。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # ---- C009 云启信息服务（互联网和相关服务）----
    # 背景：经营异常+移出+被C001投资20%，成立较晚(2023)，相对年轻
    {
        "event_id": "P023",
        "company_id": "C009",
        "publish_date": "2025-01-15",
        "topic": "业务扩张",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "云启信息服务获得天使轮融资",
        "summary": "成立仅两年的云启信息服务有限公司宣布获得天使轮融资1000万元，投资方包括华辰智能科技等。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P024",
        "company_id": "C009",
        "publish_date": "2025-05-22",
        "topic": "客户投诉",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "云启信息服务部分用户反映系统不稳定",
        "summary": "云启信息服务有限公司的部分企业客户反映其SaaS平台存在频繁宕机、数据同步延迟等问题。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
    {
        "event_id": "P025",
        "company_id": "C009",
        "publish_date": "2025-10-30",
        "topic": "重大合作",
        "sentiment": "positive",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "云启信息服务与某地方政府签署数字化服务协议",
        "summary": "云启信息服务有限公司成功与某地方政府签署智慧政务服务平台建设协议，合同金额约500万元。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # ---- C010 宏泰物流（道路运输业）----
    # 背景：行政处罚+被告角色诉讼+被C002担保，中等风险
    {
        "event_id": "P026",
        "company_id": "C010",
        "publish_date": "2025-02-05",
        "topic": "监管关注",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "宏泰物流因安全检查问题被通报",
        "summary": "宏泰物流有限公司因部分运输车辆未按规定进行安全检查被交通运输部门通报，引发行业关注。",
        "verification_status": "verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
    {
        "event_id": "P027",
        "company_id": "C010",
        "publish_date": "2025-06-28",
        "topic": "业务扩张",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "宏泰物流新增冷链运输业务线",
        "summary": "宏泰物流有限公司宣布正式开通冷链运输业务，首批投入50辆冷链运输车，覆盖华东地区主要城市。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },
    {
        "event_id": "P028",
        "company_id": "C010",
        "publish_date": "2025-09-20",
        "topic": "合同纠纷",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "宏泰物流与某货主企业就运输损耗达成和解",
        "summary": "宏泰物流有限公司与某大型货主企业就此前运输过程中的货物损耗问题达成和解协议，双方继续合作。",
        "verification_status": "verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },

    # ---- 额外补充：增加矛盾信号 ----

    # C002 虽然风险高，但有正面舆情（矛盾信号）
    {
        "event_id": "P029",
        "company_id": "C002",
        "publish_date": "2025-09-05",
        "topic": "项目中标",
        "sentiment": "positive",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "远海供应链中标某大型物流项目",
        "summary": "远海供应链管理有限公司在经历一系列经营困难后，成功中标某央企物流外包项目，合同金额约1200万元。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # C007 虽然高风险，但有中标（矛盾信号）
    {
        "event_id": "P030",
        "company_id": "C007",
        "publish_date": "2025-12-10",
        "topic": "市场传闻",
        "sentiment": "negative",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "鼎峰建设工程被传面临资金链紧张",
        "summary": "市场传闻鼎峰建设工程有限公司因多个项目回款不及时，面临一定资金压力，但公司方面未予证实。",
        "verification_status": "unverified",
        "response_status": "no_response",
        "data_type": "simulated",
    },

    # C004 环保问题后有正面回应（矛盾信号）
    {
        "event_id": "P031",
        "company_id": "C004",
        "publish_date": "2025-10-15",
        "topic": "重大合作",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "新源新能源材料与某车企签署长期供货协议",
        "summary": "新源新能源材料有限公司与某知名新能源车企签署为期五年的正极材料供货协议，年均合同金额约8000万元。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # C005 虽有资金传闻但有央企合作（矛盾信号）
    {
        "event_id": "P032",
        "company_id": "C005",
        "publish_date": "2025-08-20",
        "topic": "高管变动",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "博远数字科技任命新CTO",
        "summary": "博远数字科技有限公司任命某知名互联网公司前技术总监为新任首席技术官，负责AI产品研发。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # C008 虽有诉讼但业务扩张（矛盾信号）
    {
        "event_id": "P033",
        "company_id": "C008",
        "publish_date": "2025-11-22",
        "topic": "市场传闻",
        "sentiment": "neutral",
        "source_type": "行业媒体",
        "source_name": "模拟行业媒体02",
        "title": "瑞泽机械制造计划进军海外市场",
        "summary": "有行业消息称瑞泽机械制造有限公司正积极布局东南亚市场，已与多家海外代理商建立联系。",
        "verification_status": "unverified",
        "response_status": "no_response",
        "data_type": "simulated",
    },

    # C009 虽有投诉但增长迅速（矛盾信号）
    {
        "event_id": "P034",
        "company_id": "C009",
        "publish_date": "2025-07-08",
        "topic": "业务扩张",
        "sentiment": "positive",
        "source_type": "财经媒体",
        "source_name": "模拟财经媒体01",
        "title": "云启信息服务用户数突破10万",
        "summary": "云启信息服务有限公司宣布其SaaS平台注册企业用户数突破10万家，月活跃用户同比增长150%。",
        "verification_status": "verified",
        "response_status": "company_confirmed",
        "data_type": "simulated",
    },

    # C010 虽有行政处罚但新业务拓展（矛盾信号）
    {
        "event_id": "P035",
        "company_id": "C010",
        "publish_date": "2025-11-18",
        "topic": "劳动争议",
        "sentiment": "negative",
        "source_type": "地方媒体",
        "source_name": "模拟地方媒体03",
        "title": "宏泰物流被反映存在加班费纠纷",
        "summary": "有宏泰物流员工反映公司存在未足额支付加班费的情况，涉及约30名驾驶员，劳动仲裁部门已受理。",
        "verification_status": "partially_verified",
        "response_status": "company_responded",
        "data_type": "simulated",
    },
]


# ============================================================
# 2. 财务报告数据（F001 - F030）
#    每家公司 2023/2024/2025 三年
# ============================================================

FINANCIAL_REPORTS = [
    # ---- C001 华辰智能科技 ----
    # 类型A：收入稳定增长，利润稳定，现金流正常
    {
        "report_id": "F001",
        "company_id": "C001",
        "period": "2023FY",
        "report_date": "2024-04-20",
        "revenue": 85_000_000,
        "net_profit": 8_500_000,
        "total_assets": 120_000_000,
        "total_liabilities": 45_000_000,
        "current_assets": 65_000_000,
        "current_liabilities": 30_000_000,
        "operating_cash_flow": 12_000_000,
        "accounts_receivable": 18_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F002",
        "company_id": "C001",
        "period": "2024FY",
        "report_date": "2025-04-18",
        "revenue": 102_000_000,
        "net_profit": 11_200_000,
        "total_assets": 145_000_000,
        "total_liabilities": 52_000_000,
        "current_assets": 78_000_000,
        "current_liabilities": 33_000_000,
        "operating_cash_flow": 15_500_000,
        "accounts_receivable": 22_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F003",
        "company_id": "C001",
        "period": "2025FY",
        "report_date": "2026-04-15",
        "revenue": 125_000_000,
        "net_profit": 14_500_000,
        "total_assets": 170_000_000,
        "total_liabilities": 58_000_000,
        "current_assets": 92_000_000,
        "current_liabilities": 36_000_000,
        "operating_cash_flow": 19_000_000,
        "accounts_receivable": 25_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C002 远海供应链 ----
    # 类型C：收入下降，净利润转负，经营现金流恶化
    {
        "report_id": "F004",
        "company_id": "C002",
        "period": "2023FY",
        "report_date": "2024-04-22",
        "revenue": 62_000_000,
        "net_profit": 2_100_000,
        "total_assets": 55_000_000,
        "total_liabilities": 32_000_000,
        "current_assets": 28_000_000,
        "current_liabilities": 25_000_000,
        "operating_cash_flow": 3_500_000,
        "accounts_receivable": 15_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F005",
        "company_id": "C002",
        "period": "2024FY",
        "report_date": "2025-04-20",
        "revenue": 53_000_000,
        "net_profit": -1_800_000,
        "total_assets": 48_000_000,
        "total_liabilities": 35_000_000,
        "current_assets": 22_000_000,
        "current_liabilities": 28_000_000,
        "operating_cash_flow": -4_200_000,
        "accounts_receivable": 20_000_000,
        "audit_opinion": "qualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F006",
        "company_id": "C002",
        "period": "2025FY",
        "report_date": "2026-04-18",
        "revenue": 41_000_000,
        "net_profit": -5_600_000,
        "total_assets": 42_000_000,
        "total_liabilities": 38_000_000,
        "current_assets": 18_000_000,
        "current_liabilities": 30_000_000,
        "operating_cash_flow": -8_500_000,
        "accounts_receivable": 22_000_000,
        "audit_opinion": "qualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C003 恒达商贸 ----
    # 类型B：收入增长但利润下降，应收账款快速增加
    {
        "report_id": "F007",
        "company_id": "C003",
        "period": "2023FY",
        "report_date": "2024-04-25",
        "revenue": 35_000_000,
        "net_profit": 2_800_000,
        "total_assets": 28_000_000,
        "total_liabilities": 12_000_000,
        "current_assets": 18_000_000,
        "current_liabilities": 10_000_000,
        "operating_cash_flow": 3_200_000,
        "accounts_receivable": 6_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F008",
        "company_id": "C003",
        "period": "2024FY",
        "report_date": "2025-04-22",
        "revenue": 42_000_000,
        "net_profit": 1_500_000,
        "total_assets": 35_000_000,
        "total_liabilities": 18_000_000,
        "current_assets": 22_000_000,
        "current_liabilities": 15_000_000,
        "operating_cash_flow": 800_000,
        "accounts_receivable": 12_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F009",
        "company_id": "C003",
        "period": "2025FY",
        "report_date": "2026-04-20",
        "revenue": 48_000_000,
        "net_profit": 600_000,
        "total_assets": 40_000_000,
        "total_liabilities": 22_000_000,
        "current_assets": 25_000_000,
        "current_liabilities": 18_000_000,
        "operating_cash_flow": -1_200_000,
        "accounts_receivable": 18_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C004 新源新能源材料 ----
    # 类型A：收入稳定增长，利润增长，现金流正常（行业景气）
    {
        "report_id": "F010",
        "company_id": "C004",
        "period": "2023FY",
        "report_date": "2024-04-18",
        "revenue": 180_000_000,
        "net_profit": 22_000_000,
        "total_assets": 200_000_000,
        "total_liabilities": 75_000_000,
        "current_assets": 110_000_000,
        "current_liabilities": 55_000_000,
        "operating_cash_flow": 28_000_000,
        "accounts_receivable": 35_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F011",
        "company_id": "C004",
        "period": "2024FY",
        "report_date": "2025-04-15",
        "revenue": 220_000_000,
        "net_profit": 30_000_000,
        "total_assets": 250_000_000,
        "total_liabilities": 88_000_000,
        "current_assets": 135_000_000,
        "current_liabilities": 60_000_000,
        "operating_cash_flow": 35_000_000,
        "accounts_receivable": 42_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F012",
        "company_id": "C004",
        "period": "2025FY",
        "report_date": "2026-04-12",
        "revenue": 265_000_000,
        "net_profit": 38_000_000,
        "total_assets": 310_000_000,
        "total_liabilities": 105_000_000,
        "current_assets": 165_000_000,
        "current_liabilities": 68_000_000,
        "operating_cash_flow": 42_000_000,
        "accounts_receivable": 48_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C005 博远数字科技 ----
    # 类型D：利润为正但经营现金流持续为负（收入增长但回款差）
    {
        "report_id": "F013",
        "company_id": "C005",
        "period": "2023FY",
        "report_date": "2024-04-20",
        "revenue": 72_000_000,
        "net_profit": 5_500_000,
        "total_assets": 85_000_000,
        "total_liabilities": 38_000_000,
        "current_assets": 45_000_000,
        "current_liabilities": 28_000_000,
        "operating_cash_flow": 2_000_000,
        "accounts_receivable": 20_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F014",
        "company_id": "C005",
        "period": "2024FY",
        "report_date": "2025-04-18",
        "revenue": 88_000_000,
        "net_profit": 4_200_000,
        "total_assets": 105_000_000,
        "total_liabilities": 52_000_000,
        "current_assets": 52_000_000,
        "current_liabilities": 38_000_000,
        "operating_cash_flow": -3_500_000,
        "accounts_receivable": 32_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F015",
        "company_id": "C005",
        "period": "2025FY",
        "report_date": "2026-04-15",
        "revenue": 105_000_000,
        "net_profit": 3_000_000,
        "total_assets": 125_000_000,
        "total_liabilities": 65_000_000,
        "current_assets": 58_000_000,
        "current_liabilities": 45_000_000,
        "operating_cash_flow": -6_800_000,
        "accounts_receivable": 45_000_000,
        "audit_opinion": "qualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C006 嘉盛产业投资 ----
    # 类型A：收入稳定，利润稳定，现金流正常（投资公司）
    {
        "report_id": "F016",
        "company_id": "C006",
        "period": "2023FY",
        "report_date": "2024-04-22",
        "revenue": 45_000_000,
        "net_profit": 12_000_000,
        "total_assets": 350_000_000,
        "total_liabilities": 120_000_000,
        "current_assets": 180_000_000,
        "current_liabilities": 80_000_000,
        "operating_cash_flow": 15_000_000,
        "accounts_receivable": 8_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F017",
        "company_id": "C006",
        "period": "2024FY",
        "report_date": "2025-04-20",
        "revenue": 52_000_000,
        "net_profit": 14_500_000,
        "total_assets": 380_000_000,
        "total_liabilities": 130_000_000,
        "current_assets": 200_000_000,
        "current_liabilities": 85_000_000,
        "operating_cash_flow": 18_000_000,
        "accounts_receivable": 9_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F018",
        "company_id": "C006",
        "period": "2025FY",
        "report_date": "2026-04-18",
        "revenue": 58_000_000,
        "net_profit": 16_000_000,
        "total_assets": 420_000_000,
        "total_liabilities": 140_000_000,
        "current_assets": 220_000_000,
        "current_liabilities": 90_000_000,
        "operating_cash_flow": 20_000_000,
        "accounts_receivable": 10_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C007 鼎峰建设工程 ----
    # 类型E：收入下降，负债明显上升，现金流恶化（高风险企业）
    {
        "report_id": "F019",
        "company_id": "C007",
        "period": "2023FY",
        "report_date": "2024-04-25",
        "revenue": 95_000_000,
        "net_profit": 3_200_000,
        "total_assets": 110_000_000,
        "total_liabilities": 65_000_000,
        "current_assets": 45_000_000,
        "current_liabilities": 42_000_000,
        "operating_cash_flow": 5_000_000,
        "accounts_receivable": 28_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F020",
        "company_id": "C007",
        "period": "2024FY",
        "report_date": "2025-04-22",
        "revenue": 78_000_000,
        "net_profit": -2_500_000,
        "total_assets": 105_000_000,
        "total_liabilities": 78_000_000,
        "current_assets": 38_000_000,
        "current_liabilities": 50_000_000,
        "operating_cash_flow": -8_000_000,
        "accounts_receivable": 35_000_000,
        "audit_opinion": "qualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F021",
        "company_id": "C007",
        "period": "2025FY",
        "report_date": "2026-04-20",
        "revenue": 62_000_000,
        "net_profit": -8_200_000,
        "total_assets": 95_000_000,
        "total_liabilities": 82_000_000,
        "current_assets": 30_000_000,
        "current_liabilities": 55_000_000,
        "operating_cash_flow": -15_000_000,
        "accounts_receivable": 38_000_000,
        "audit_opinion": "qualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C008 瑞泽机械制造 ----
    # 类型F：利润为正但负债上升，应收账款增加
    {
        "report_id": "F022",
        "company_id": "C008",
        "period": "2023FY",
        "report_date": "2024-04-20",
        "revenue": 55_000_000,
        "net_profit": 4_800_000,
        "total_assets": 72_000_000,
        "total_liabilities": 28_000_000,
        "current_assets": 38_000_000,
        "current_liabilities": 22_000_000,
        "operating_cash_flow": 6_500_000,
        "accounts_receivable": 12_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F023",
        "company_id": "C008",
        "period": "2024FY",
        "report_date": "2025-04-18",
        "revenue": 68_000_000,
        "net_profit": 5_500_000,
        "total_assets": 95_000_000,
        "total_liabilities": 42_000_000,
        "current_assets": 48_000_000,
        "current_liabilities": 32_000_000,
        "operating_cash_flow": 4_000_000,
        "accounts_receivable": 20_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F024",
        "company_id": "C008",
        "period": "2025FY",
        "report_date": "2026-04-15",
        "revenue": 82_000_000,
        "net_profit": 6_200_000,
        "total_assets": 115_000_000,
        "total_liabilities": 55_000_000,
        "current_assets": 55_000_000,
        "current_liabilities": 40_000_000,
        "operating_cash_flow": 2_500_000,
        "accounts_receivable": 30_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C009 云启信息服务 ----
    # 类型A：收入快速增长，利润改善，但规模小（初创企业）
    {
        "report_id": "F025",
        "company_id": "C009",
        "period": "2023FY",
        "report_date": "2024-04-25",
        "revenue": 5_000_000,
        "net_profit": -2_800_000,
        "total_assets": 12_000_000,
        "total_liabilities": 3_500_000,
        "current_assets": 8_000_000,
        "current_liabilities": 3_000_000,
        "operating_cash_flow": -3_200_000,
        "accounts_receivable": 1_500_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F026",
        "company_id": "C009",
        "period": "2024FY",
        "report_date": "2025-04-22",
        "revenue": 12_000_000,
        "net_profit": -800_000,
        "total_assets": 18_000_000,
        "total_liabilities": 4_500_000,
        "current_assets": 12_000_000,
        "current_liabilities": 4_000_000,
        "operating_cash_flow": -1_500_000,
        "accounts_receivable": 3_500_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F027",
        "company_id": "C009",
        "period": "2025FY",
        "report_date": "2026-04-20",
        "revenue": 22_000_000,
        "net_profit": 1_200_000,
        "total_assets": 28_000_000,
        "total_liabilities": 6_000_000,
        "current_assets": 18_000_000,
        "current_liabilities": 5_500_000,
        "operating_cash_flow": 500_000,
        "accounts_receivable": 6_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },

    # ---- C010 宏泰物流 ----
    # 类型B：收入微增但利润下降，负债上升
    {
        "report_id": "F028",
        "company_id": "C010",
        "period": "2023FY",
        "report_date": "2024-04-22",
        "revenue": 48_000_000,
        "net_profit": 3_500_000,
        "total_assets": 55_000_000,
        "total_liabilities": 22_000_000,
        "current_assets": 28_000_000,
        "current_liabilities": 18_000_000,
        "operating_cash_flow": 5_000_000,
        "accounts_receivable": 10_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F029",
        "company_id": "C010",
        "period": "2024FY",
        "report_date": "2025-04-20",
        "revenue": 52_000_000,
        "net_profit": 1_800_000,
        "total_assets": 65_000_000,
        "total_liabilities": 30_000_000,
        "current_assets": 32_000_000,
        "current_liabilities": 24_000_000,
        "operating_cash_flow": 1_500_000,
        "accounts_receivable": 14_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
    {
        "report_id": "F030",
        "company_id": "C010",
        "period": "2025FY",
        "report_date": "2026-04-18",
        "revenue": 55_000_000,
        "net_profit": 800_000,
        "total_assets": 72_000_000,
        "total_liabilities": 38_000_000,
        "current_assets": 35_000_000,
        "current_liabilities": 28_000_000,
        "operating_cash_flow": -2_000_000,
        "accounts_receivable": 18_000_000,
        "audit_opinion": "unqualified",
        "currency": "CNY",
        "data_type": "simulated",
    },
]


# ============================================================
# 3. 招聘事件数据（H001 - H035）
# ============================================================

RECRUITMENT_EVENTS = [
    # ---- C001 华辰智能科技 ----
    # 稳定扩张型
    {
        "event_id": "H001",
        "company_id": "C001",
        "publish_date": "2025-01-15",
        "event_type": "hiring_expansion",
        "position_category": "技术研发",
        "position_name": "AI算法工程师",
        "planned_headcount": 8,
        "salary_min": 25000,
        "salary_max": 45000,
        "location": "上海",
        "status": "open",
        "description": "因业务扩张需求，计划招聘AI算法工程师8名，负责核心产品算法研发。",
        "data_type": "simulated",
    },
    {
        "event_id": "H002",
        "company_id": "C001",
        "publish_date": "2025-05-20",
        "event_type": "job_posting",
        "position_category": "产品运营",
        "position_name": "产品经理",
        "planned_headcount": 3,
        "salary_min": 18000,
        "salary_max": 30000,
        "location": "上海",
        "status": "open",
        "description": "招聘产品经理3名，负责SaaS产品规划与迭代。",
        "data_type": "simulated",
    },
    {
        "event_id": "H003",
        "company_id": "C001",
        "publish_date": "2025-09-10",
        "event_type": "mass_recruitment",
        "position_category": "技术研发",
        "position_name": "全栈开发工程师",
        "planned_headcount": 15,
        "salary_min": 20000,
        "salary_max": 35000,
        "location": "上海/北京",
        "status": "open",
        "description": "大规模招聘全栈开发工程师15名，支撑新业务线开发。",
        "data_type": "simulated",
    },

    # ---- C002 远海供应链 ----
    # 收缩型（与经营困难一致）
    {
        "event_id": "H004",
        "company_id": "C002",
        "publish_date": "2025-03-10",
        "event_type": "posting_withdrawal",
        "position_category": "物流运营",
        "position_name": "区域物流经理",
        "planned_headcount": 2,
        "salary_min": 15000,
        "salary_max": 25000,
        "location": "深圳",
        "status": "withdrawn",
        "description": "原计划招聘区域物流经理2名，因业务调整已撤回招聘。",
        "data_type": "simulated",
    },
    {
        "event_id": "H005",
        "company_id": "C002",
        "publish_date": "2025-06-15",
        "event_type": "hiring_freeze",
        "position_category": "职能管理",
        "position_name": "财务主管",
        "planned_headcount": 1,
        "salary_min": 12000,
        "salary_max": 20000,
        "location": "深圳",
        "status": "frozen",
        "description": "因公司经营调整，财务主管岗位暂停招聘。",
        "data_type": "simulated",
    },
    # 矛盾信号：虽有困难但仍在招关键岗位
    {
        "event_id": "H006",
        "company_id": "C002",
        "publish_date": "2025-10-08",
        "event_type": "key_role_opening",
        "position_category": "高层管理",
        "position_name": "运营副总裁",
        "planned_headcount": 1,
        "salary_min": 40000,
        "salary_max": 60000,
        "location": "深圳",
        "status": "open",
        "description": "招聘运营副总裁1名，负责公司业务重组和运营优化。",
        "data_type": "simulated",
    },

    # ---- C003 恒达商贸 ----
    # 正常招聘
    {
        "event_id": "H007",
        "company_id": "C003",
        "publish_date": "2025-02-20",
        "event_type": "job_posting",
        "position_category": "销售",
        "position_name": "区域销售经理",
        "planned_headcount": 4,
        "salary_min": 12000,
        "salary_max": 22000,
        "location": "广州",
        "status": "open",
        "description": "招聘区域销售经理4名，拓展华南市场。",
        "data_type": "simulated",
    },
    {
        "event_id": "H008",
        "company_id": "C003",
        "publish_date": "2025-07-12",
        "event_type": "recruitment_reduction",
        "position_category": "仓储物流",
        "position_name": "仓库管理员",
        "planned_headcount": 2,
        "salary_min": 6000,
        "salary_max": 9000,
        "location": "广州",
        "status": "open",
        "description": "原计划招聘仓库管理员5名，因仓储自动化改造缩减至2名。",
        "data_type": "simulated",
    },

    # ---- C004 新源新能源材料 ----
    # 扩张型（与业务增长一致）
    {
        "event_id": "H009",
        "company_id": "C004",
        "publish_date": "2025-01-08",
        "event_type": "mass_recruitment",
        "position_category": "生产制造",
        "position_name": "生产线技术员",
        "planned_headcount": 20,
        "salary_min": 8000,
        "salary_max": 12000,
        "location": "合肥",
        "status": "open",
        "description": "新生产线投产，大规模招聘生产线技术员20名。",
        "data_type": "simulated",
    },
    {
        "event_id": "H010",
        "company_id": "C004",
        "publish_date": "2025-06-18",
        "event_type": "hiring_expansion",
        "position_category": "技术研发",
        "position_name": "材料研发工程师",
        "planned_headcount": 6,
        "salary_min": 20000,
        "salary_max": 35000,
        "location": "合肥",
        "status": "open",
        "description": "招聘材料研发工程师6名，加强电池材料研发能力。",
        "data_type": "simulated",
    },

    # ---- C005 博远数字科技 ----
    # 矛盾信号：有裁员传闻但仍招技术岗
    {
        "event_id": "H011",
        "company_id": "C005",
        "publish_date": "2025-02-25",
        "event_type": "posting_withdrawal",
        "position_category": "市场销售",
        "position_name": "市场推广经理",
        "planned_headcount": 2,
        "salary_min": 15000,
        "salary_max": 25000,
        "location": "北京",
        "status": "withdrawn",
        "description": "因业务调整，市场推广经理岗位招聘已撤回。",
        "data_type": "simulated",
    },
    {
        "event_id": "H012",
        "company_id": "C005",
        "publish_date": "2025-07-15",
        "event_type": "hiring_expansion",
        "position_category": "技术研发",
        "position_name": "AI产品经理",
        "planned_headcount": 3,
        "salary_min": 22000,
        "salary_max": 38000,
        "location": "北京",
        "status": "open",
        "description": "招聘AI产品经理3名，负责新AI产品线规划。",
        "data_type": "simulated",
    },

    # ---- C006 嘉盛产业投资 ----
    # 稳定型
    {
        "event_id": "H013",
        "company_id": "C006",
        "publish_date": "2025-03-05",
        "event_type": "job_posting",
        "position_category": "投资管理",
        "position_name": "投资经理",
        "planned_headcount": 2,
        "salary_min": 25000,
        "salary_max": 40000,
        "location": "上海",
        "status": "open",
        "description": "招聘投资经理2名，负责先进制造业领域投资。",
        "data_type": "simulated",
    },
    {
        "event_id": "H014",
        "company_id": "C006",
        "publish_date": "2025-08-20",
        "event_type": "job_posting",
        "position_category": "风控合规",
        "position_name": "风控专员",
        "planned_headcount": 1,
        "salary_min": 18000,
        "salary_max": 28000,
        "location": "上海",
        "status": "open",
        "description": "招聘风控专员1名，加强投资后管理风控能力。",
        "data_type": "simulated",
    },

    # ---- C007 鼎峰建设工程 ----
    # 收缩型（与经营困难一致）
    {
        "event_id": "H015",
        "company_id": "C007",
        "publish_date": "2025-01-20",
        "event_type": "hiring_freeze",
        "position_category": "工程管理",
        "position_name": "项目经理",
        "planned_headcount": 3,
        "salary_min": 18000,
        "salary_max": 30000,
        "location": "成都",
        "status": "frozen",
        "description": "因项目回款延迟，项目经理岗位暂停招聘。",
        "data_type": "simulated",
    },
    {
        "event_id": "H016",
        "company_id": "C007",
        "publish_date": "2025-05-08",
        "event_type": "recruitment_reduction",
        "position_category": "工程技术",
        "position_name": "施工员",
        "planned_headcount": 5,
        "salary_min": 8000,
        "salary_max": 12000,
        "location": "成都/重庆",
        "status": "open",
        "description": "原计划招聘施工员10名，因在建项目减少缩减至5名。",
        "data_type": "simulated",
    },
    # 矛盾信号：虽有困难但仍招关键岗位（新中标项目）
    {
        "event_id": "H017",
        "company_id": "C007",
        "publish_date": "2025-11-20",
        "event_type": "key_role_opening",
        "position_category": "高层管理",
        "position_name": "安全总监",
        "planned_headcount": 1,
        "salary_min": 25000,
        "salary_max": 40000,
        "location": "成都",
        "status": "open",
        "description": "招聘安全总监1名，因新项目要求加强安全管理。",
        "data_type": "simulated",
    },

    # ---- C008 瑞泽机械制造 ----
    # 扩张型（与产能扩张一致）
    {
        "event_id": "H018",
        "company_id": "C008",
        "publish_date": "2025-02-10",
        "event_type": "mass_recruitment",
        "position_category": "生产制造",
        "position_name": "数控操作工",
        "planned_headcount": 12,
        "salary_min": 7000,
        "salary_max": 11000,
        "location": "苏州",
        "status": "open",
        "description": "新生产线投产，大规模招聘数控操作工12名。",
        "data_type": "simulated",
    },
    {
        "event_id": "H019",
        "company_id": "C008",
        "publish_date": "2025-08-15",
        "event_type": "hiring_expansion",
        "position_category": "技术研发",
        "position_name": "机械设计工程师",
        "planned_headcount": 4,
        "salary_min": 18000,
        "salary_max": 30000,
        "location": "苏州",
        "status": "open",
        "description": "招聘机械设计工程师4名，加强产品研发能力。",
        "data_type": "simulated",
    },

    # ---- C009 云启信息服务 ----
    # 快速扩张型（初创企业增长期）
    {
        "event_id": "H020",
        "company_id": "C009",
        "publish_date": "2025-01-25",
        "event_type": "mass_recruitment",
        "position_category": "技术研发",
        "position_name": "前端开发工程师",
        "planned_headcount": 5,
        "salary_min": 15000,
        "salary_max": 25000,
        "location": "杭州",
        "status": "open",
        "description": "因用户增长迅速，大规模招聘前端开发工程师5名。",
        "data_type": "simulated",
    },
    {
        "event_id": "H021",
        "company_id": "C009",
        "publish_date": "2025-05-15",
        "event_type": "hiring_expansion",
        "position_category": "客户服务",
        "position_name": "客户成功经理",
        "planned_headcount": 3,
        "salary_min": 12000,
        "salary_max": 20000,
        "location": "杭州",
        "status": "open",
        "description": "招聘客户成功经理3名，提升企业客户服务体验。",
        "data_type": "simulated",
    },
    {
        "event_id": "H022",
        "company_id": "C009",
        "publish_date": "2025-10-12",
        "event_type": "hiring_expansion",
        "position_category": "市场销售",
        "position_name": "大客户销售",
        "planned_headcount": 4,
        "salary_min": 15000,
        "salary_max": 28000,
        "location": "杭州/上海",
        "status": "open",
        "description": "招聘大客户销售4名，拓展政企客户市场。",
        "data_type": "simulated",
    },

    # ---- C010 宏泰物流 ----
    # 正常偏保守
    {
        "event_id": "H023",
        "company_id": "C010",
        "publish_date": "2025-02-18",
        "event_type": "job_posting",
        "position_category": "物流运营",
        "position_name": "运输调度员",
        "planned_headcount": 3,
        "salary_min": 8000,
        "salary_max": 12000,
        "location": "南京",
        "status": "open",
        "description": "招聘运输调度员3名，保障运输业务运转。",
        "data_type": "simulated",
    },
    {
        "event_id": "H024",
        "company_id": "C010",
        "publish_date": "2025-07-05",
        "event_type": "hiring_expansion",
        "position_category": "物流运营",
        "position_name": "冷链运输司机",
        "planned_headcount": 10,
        "salary_min": 10000,
        "salary_max": 15000,
        "location": "南京/上海",
        "status": "open",
        "description": "冷链业务拓展，招聘冷链运输司机10名。",
        "data_type": "simulated",
    },
    {
        "event_id": "H025",
        "company_id": "C010",
        "publish_date": "2025-11-10",
        "event_type": "recruitment_reduction",
        "position_category": "职能管理",
        "position_name": "行政专员",
        "planned_headcount": 1,
        "salary_min": 6000,
        "salary_max": 9000,
        "location": "南京",
        "status": "open",
        "description": "原计划招聘行政专员2名，因成本控制缩减至1名。",
        "data_type": "simulated",
    },

    # ---- 额外补充：增加矛盾信号 ----

    # C002 矛盾信号：虽有冻结但招关键角色
    {
        "event_id": "H026",
        "company_id": "C002",
        "publish_date": "2025-12-05",
        "event_type": "hiring_freeze",
        "position_category": "物流运营",
        "position_name": "仓库主管",
        "planned_headcount": 2,
        "salary_min": 10000,
        "salary_max": 15000,
        "location": "深圳",
        "status": "frozen",
        "description": "因业务收缩，仓库主管岗位暂停招聘。",
        "data_type": "simulated",
    },

    # C007 矛盾信号：虽有冻结但新项目需要人
    {
        "event_id": "H027",
        "company_id": "C007",
        "publish_date": "2025-03-15",
        "event_type": "recruitment_reduction",
        "position_category": "职能管理",
        "position_name": "人力资源专员",
        "planned_headcount": 1,
        "salary_min": 7000,
        "salary_max": 10000,
        "location": "成都",
        "status": "open",
        "description": "原计划招聘人力资源专员2名，缩减至1名。",
        "data_type": "simulated",
    },

    # C005 矛盾信号：虽有裁员但招AI岗
    {
        "event_id": "H028",
        "company_id": "C005",
        "publish_date": "2025-11-18",
        "event_type": "hiring_expansion",
        "position_category": "技术研发",
        "position_name": "大模型工程师",
        "planned_headcount": 2,
        "salary_min": 35000,
        "salary_max": 55000,
        "location": "北京",
        "status": "open",
        "description": "招聘大模型工程师2名，负责企业级AI应用开发。",
        "data_type": "simulated",
    },

    # C003 矛盾信号：虽有缩减但招销售
    {
        "event_id": "H029",
        "company_id": "C003",
        "publish_date": "2025-11-25",
        "event_type": "job_posting",
        "position_category": "销售",
        "position_name": "电商运营专员",
        "planned_headcount": 2,
        "salary_min": 8000,
        "salary_max": 14000,
        "location": "广州",
        "status": "open",
        "description": "招聘电商运营专员2名，拓展线上销售渠道。",
        "data_type": "simulated",
    },

    # C010 矛盾信号：虽有缩减但冷链扩张
    {
        "event_id": "H030",
        "company_id": "C010",
        "publish_date": "2025-09-15",
        "event_type": "hiring_expansion",
        "position_category": "物流运营",
        "position_name": "冷链仓储管理员",
        "planned_headcount": 3,
        "salary_min": 8000,
        "salary_max": 12000,
        "location": "南京",
        "status": "open",
        "description": "冷链业务拓展，招聘冷链仓储管理员3名。",
        "data_type": "simulated",
    },

    # C008 矛盾信号：扩张但也有冻结
    {
        "event_id": "H031",
        "company_id": "C008",
        "publish_date": "2025-11-08",
        "event_type": "hiring_freeze",
        "position_category": "职能管理",
        "position_name": "行政主管",
        "planned_headcount": 1,
        "salary_min": 10000,
        "salary_max": 15000,
        "location": "苏州",
        "status": "frozen",
        "description": "因成本控制，行政主管岗位暂停招聘。",
        "data_type": "simulated",
    },

    # C009 矛盾信号：快速扩张但有质量投诉
    {
        "event_id": "H032",
        "company_id": "C009",
        "publish_date": "2025-08-08",
        "event_type": "job_posting",
        "position_category": "技术研发",
        "position_name": "测试工程师",
        "planned_headcount": 2,
        "salary_min": 12000,
        "salary_max": 20000,
        "location": "杭州",
        "status": "open",
        "description": "招聘测试工程师2名，加强产品质量保障。",
        "data_type": "simulated",
    },

    # C004 矛盾信号：环保问题但仍在扩张
    {
        "event_id": "H033",
        "company_id": "C004",
        "publish_date": "2025-09-22",
        "event_type": "hiring_expansion",
        "position_category": "环保安全",
        "position_name": "环保工程师",
        "planned_headcount": 2,
        "salary_min": 15000,
        "salary_max": 25000,
        "location": "合肥",
        "status": "open",
        "description": "招聘环保工程师2名，加强环保合规管理。",
        "data_type": "simulated",
    },

    # C006 稳定型补充
    {
        "event_id": "H034",
        "company_id": "C006",
        "publish_date": "2025-11-15",
        "event_type": "job_posting",
        "position_category": "投资管理",
        "position_name": "投后管理专员",
        "planned_headcount": 1,
        "salary_min": 15000,
        "salary_max": 22000,
        "location": "上海",
        "status": "open",
        "description": "招聘投后管理专员1名，加强已投项目管理。",
        "data_type": "simulated",
    },

    # C001 稳定型补充
    {
        "event_id": "H035",
        "company_id": "C001",
        "publish_date": "2025-12-01",
        "event_type": "job_posting",
        "position_category": "职能管理",
        "position_name": "人力资源经理",
        "planned_headcount": 1,
        "salary_min": 18000,
        "salary_max": 28000,
        "location": "上海",
        "status": "open",
        "description": "招聘人力资源经理1名，支撑团队快速扩张。",
        "data_type": "simulated",
    },
]


# ============================================================
# 数据库操作
# ============================================================


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接。"""
    if not db_path.exists():
        raise FileNotFoundError(f"找不到数据库文件：{db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """创建三个新表（如不存在）。"""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS public_opinion_events (
            event_id           TEXT PRIMARY KEY,
            company_id         TEXT NOT NULL REFERENCES companies(company_id),
            publish_date       TEXT,
            topic              TEXT,
            sentiment          TEXT,
            source_type        TEXT,
            source_name        TEXT,
            title              TEXT,
            summary            TEXT,
            verification_status TEXT,
            response_status    TEXT,
            data_type          TEXT NOT NULL DEFAULT 'simulated'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS financial_reports (
            report_id            TEXT PRIMARY KEY,
            company_id           TEXT NOT NULL REFERENCES companies(company_id),
            period               TEXT,
            report_date          TEXT,
            revenue              REAL,
            net_profit           REAL,
            total_assets         REAL,
            total_liabilities    REAL,
            current_assets       REAL,
            current_liabilities  REAL,
            operating_cash_flow  REAL,
            accounts_receivable  REAL,
            audit_opinion        TEXT,
            currency             TEXT DEFAULT 'CNY',
            data_type            TEXT NOT NULL DEFAULT 'simulated'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS recruitment_events (
            event_id           TEXT PRIMARY KEY,
            company_id         TEXT NOT NULL REFERENCES companies(company_id),
            publish_date       TEXT,
            event_type         TEXT,
            position_category  TEXT,
            position_name      TEXT,
            planned_headcount  INTEGER,
            salary_min         REAL,
            salary_max         REAL,
            location           TEXT,
            status             TEXT,
            description        TEXT,
            data_type          TEXT NOT NULL DEFAULT 'simulated'
        )
    """)

    # 索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_po_company ON public_opinion_events(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_po_sentiment ON public_opinion_events(sentiment)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_company ON financial_reports(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_period ON financial_reports(period)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_re_company ON recruitment_events(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_re_type ON recruitment_events(event_type)")

    conn.commit()


def _insert_events(
    conn: sqlite3.Connection,
    table: str,
    events: list,
) -> int:
    """幂等插入事件列表（已存在则跳过）。返回实际插入数。"""
    count = 0
    for event in events:
        # 检查是否已存在（idempotent）
        pk_col = list(event.keys())[0]
        existing = conn.execute(
            f"SELECT 1 FROM {table} WHERE {pk_col} = ?",
            (event[pk_col],),
        ).fetchone()
        if existing is not None:
            continue

        cols = ", ".join(event.keys())
        placeholders = ", ".join(["?"] * len(event))
        conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(event.values()),
        )
        count += 1

    conn.commit()
    return count


def main() -> None:
    """主函数：建表 + 插入数据。"""
    print(f"数据库路径: {DB_PATH}")
    print(f"备份文件: {PROJECT_ROOT / 'risk_before_extended_sources.db'}")

    conn = _get_connection(DB_PATH)

    try:
        print("\n[1/4] 创建新表...")
        create_tables(conn)

        print("[2/4] 插入舆情事件...")
        n = _insert_events(conn, "public_opinion_events", PUBLIC_OPINION_EVENTS)
        print(f"  插入 {n} 条舆情事件（共 {len(PUBLIC_OPINION_EVENTS)} 条，已存在的跳过）")

        print("[3/4] 插入财务报告...")
        n = _insert_events(conn, "financial_reports", FINANCIAL_REPORTS)
        print(f"  插入 {n} 条财务报告（共 {len(FINANCIAL_REPORTS)} 条，已存在的跳过）")

        print("[4/4] 插入招聘事件...")
        n = _insert_events(conn, "recruitment_events", RECRUITMENT_EVENTS)
        print(f"  插入 {n} 条招聘事件（共 {len(RECRUITMENT_EVENTS)} 条，已存在的跳过）")

        # 验证
        print("\n--- 数据验证 ---")
        for table in ["public_opinion_events", "financial_reports", "recruitment_events"]:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            print(f"  {table}: {row[0]} 条记录")

        # 按企业统计
        print("\n--- 各企业数据覆盖 ---")
        for cid in [f"C{i:03d}" for i in range(1, 11)]:
            po = conn.execute(
                "SELECT COUNT(*) FROM public_opinion_events WHERE company_id = ?",
                (cid,),
            ).fetchone()[0]
            fr = conn.execute(
                "SELECT COUNT(*) FROM financial_reports WHERE company_id = ?",
                (cid,),
            ).fetchone()[0]
            re = conn.execute(
                "SELECT COUNT(*) FROM recruitment_events WHERE company_id = ?",
                (cid,),
            ).fetchone()[0]
            status = "OK" if (po >= 2 and fr == 3 and re >= 2) else "MISSING DATA"
            print(f"  {cid}: P={po} F={fr} H={re}  [{status}]")

        print("\n扩展数据初始化完成。")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
