# 开源法律支持与权威数据源调研

调研日期：2026-10-28。目标法域：中国大陆。以下区分**代码可复用**与**数据可合法、稳定接入**；开源代码不等于其所附法条、案例数据有再分发许可。接入前需逐项核对许可证、服务条款、访问方式和更新责任。

## 可借鉴的开源项目

| 项目 | 能力与适用位置 | 初步结论 |
| --- | --- | --- |
| [docassemble](https://github.com/jhpyle/docassemble) | 访谈式问答、条件逻辑、文书组装；MIT | 文书生成可借鉴流程和模板结构；中文模板及中国法域审校需自建。 |
| [china-law-mcp](https://github.com/THUboran/china-law-mcp) | 本地法条检索、引用核验 | 可做原型/离线检索的候选适配器；覆盖范围和更新机制须与官方原文复核。 |
| [legal_rag](https://github.com/Teeeeen/legal_rag) | 中文法条与案例 RAG、分块和重排 | 参考检索管线及评估；其外部数据集许可和时效性不能直接继承。 |
| [LeCaRDv2](https://github.com/THUIR/LeCaRDv2) | 中文类案检索评测集 | 用于离线评测检索质量，不作为线上“完整案例库”。 |
| [LAiW](https://github.com/Dai-shen/LAiW) | 中文法律任务评测 | 可建立法条推荐、类案匹配、问答的回归基线。 |
| [DISC-LawLLM](https://github.com/FudanDISC/DISC-LawLLM) | 中文法律模型与部分公开问答数据 | 模型能力对照候选；不直接用模型参数代替权威检索。 |
| [CourtListener](https://github.com/freelawproject/courtlistener) | 美国判例检索、引用和公开 API；AGPL | 借鉴检索/引用/更新产品设计。中国大陆数据和许可路径不能照搬。 |

优先顺序：先以 `agent-foundation` 构建受控工具和引用证据链，再试验 docassemble 式文书访谈与法条检索适配器；不要把外部项目整仓嵌入作为底座。

## 法考真题专项

- [司法部 2016 年考试课堂目录](https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfkskskt/index_1.html)和[2013 年法考聚焦目录](https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfksfzkjj/index_8.html)列有当年试卷及部分参考答案；[2017 年发布目录](https://www.moj.gov.cn/fzgz/fzgzggflfwx/fzgzflzyzgks/index_12.html)列有试题与答案公布消息。2026-10-28 实测这些目录可打开，但其中多条旧试卷内链返回 404，因此产品只索引可访问的目录页，不将失效直达页标作可用题目。
- [司法部 2018 年法考公告](https://www.moj.gov.cn/pub/sfbgw/zlk/201806/t20180608_173795.html)明确不公布试题及参考答案；[2026 年公告](https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfkszxdt/202606/t20260609_536221.html)延续该规则。因此 2018 年后的商业回忆题不能标作官方真题。
- [JEC-QA](https://github.com/thunlp/jec-qa)等研究题库可作为格式和评估线索，但没有确认再分发许可时不导入其题干。逐题索引只接受有明确授权、许可或公有领域依据的运营导入，并保存来源 URL、权利依据、卷别、科目与题号。

## 权威数据入口与产品策略

| 需求 | 首选入口 | 接入原则 |
| --- | --- | --- |
| 法律、法规、效力状态 | [国家法律法规数据库](https://flk.npc.gov.cn/search)、[国家行政法规库](https://xzfg.moj.gov.cn/) | 记录版本、生效/失效时间、条款号、原文链接、抓取/核验时间。无授权接口时先深链与人工核验，不承诺自动全量同步。 |
| 参考案例 | [人民法院案例库说明](https://www.court.gov.cn/zixun/xiangqing/426222.html)及官方入口 | 区分指导性案例、参考案例与普通裁判文书；只表述“参考”，不推断裁判结果。 |
| 公共法律服务/律师 | [12348 中国法网说明](https://www.moj.gov.cn/pub/sfbgwapp/zwgk/tzggApp/202105/t20210517_395495.html)、[全国律师诚信信息公示平台说明](https://www.moj.gov.cn/pub/sfbgwapp/zwgk/jdhyApp/202204/t20220420_453358.html) | 律师认证核对姓名、执业证号、执业机构、状态及复核日期；案例展示须获权利人授权并脱敏。 |
| 政务办事 | [国家政务服务平台](https://gjzwfw.www.gov.cn/col/col1599/index.html)及地方主管部门 | 按地区、层级、事项维护材料清单和办理入口；无法确认时只给官方链接，不生成确定性步骤。 |
| 企业及股东公示 | [国家企业信用信息公示系统](https://www.gsxt.gov.cn/)；[市场监管总局说明](https://dj.samr.gov.cn/djfww/zczl/index.html) | 展示公示范围内的信息、来源和查询时间；变化与地域差异要显式提示，不能承诺完整股权穿透。 |

## 关键风险与验证项

1. 官网“可浏览”不代表“可批量抓取、缓存、再分发”。每个适配器需记录授权方式、频率、缓存期限和访问失败回退。
2. “官方认证”会暗示政府背书。平台自身审核应命名为“平台核验”；只有政府/司法机关真正出具的认证才可显示来源明确的“官方认证”。
3. 信息求取不能成为交易私人身份、联系方式、行踪、未公开案件材料等信息的入口。必须经过用途说明、范围限制、审核、举报和交付争议机制。
4. [个人信息保护法](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm)要求目的明确、最小必要；公开信息处理也受合理范围约束。密聊附件、委托材料、律师档案分别设留存与删除策略。
5. 不能将 AI 回答包装为律师执业意见；高风险问题需提示核验法条时点并转律师或公共法律援助渠道。
