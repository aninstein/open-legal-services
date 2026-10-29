"""Conversation-first, versioned document blueprints for common life situations.

The source links are structural references. The Chinese draft text is original and
must be checked against current law and the user's actual facts before use.
"""
from __future__ import annotations

from fastapi import HTTPException
from . import custom_templates

SOURCES = {
    "居住租赁": "https://htsfwb.samr.gov.cn/View?id=2340996b-882d-47a4-b74d-c30784628737",
    "诉讼与调解": "https://www.court.gov.cn/fabu/xiangqing/468671.html",
}

# id, category, title, purpose, required, recommended, optional, body paragraphs.
# Field syntax: key:label. A semicolon separates fields. The body is a saved
# original draft, not a copy of an official form.
RAW = [
("rental-contract","居住租赁","房屋租赁合同","约定出租、使用和费用", "landlord:出租人;tenant:承租人;property:房屋地址;term:租赁期限;rent:租金金额及支付周期", "deposit:押金及返还时间;fees:水电物业等费用承担;handover:交付日期与设施", "repair:维修约定;termination:提前解除约定", "出租人 {landlord} 与承租人 {tenant} 就 {property} 的租赁达成如下草稿。租期为 {term}，租金及支付周期为 {rent}。|押金及返还：{deposit}。费用承担：{fees}。交付及设施状况：{handover}。双方应在交付时记录钥匙、表计读数和照片。|维修与使用：{repair}。提前解除及争议处理：{termination}。双方应在签署前核对权属、房屋安全和全部约定。"),
("rental-handover","居住租赁","房屋交接确认书","记录租房交付或返还", "landlord:出租方;tenant:承租方;property:房屋地址;handover_date:交接日期", "meters:水电燃气表读数;items:钥匙与家具电器清单;condition:房屋现状", "photos:照片或视频存放位置;fees:待结费用", "出租方 {landlord} 与承租方 {tenant} 于 {handover_date} 对 {property} 进行交接。|表计读数：{meters}。钥匙、家具和电器：{items}。房屋现状：{condition}。相关照片或视频：{photos}。|待结费用及处理：{fees}。双方确认以上记录反映交接时状况，异议应写明后再签字。"),
("deposit-demand","居住租赁","押金返还催告函","催告返还租房押金", "landlord:出租方;tenant:承租方;property:房屋地址;amount:押金金额", "end_date:退租或交接日期;deadline:希望返还日期;basis:合同中押金返还约定", "deductions:对扣除项目的异议;payment:收款方式", "致 {landlord}：本人 {tenant} 就 {property} 的押金 {amount} 请求核对并返还。退租或交接时间：{end_date}。|依照双方约定 {basis}，请在 {deadline} 前完成返还。如有扣除，请列明项目、金额和依据。本人对扣除项目的意见：{deductions}。|收款方式：{payment}。请保存本函及送达、交接和支付记录。"),
("rent-repair","居住租赁","房屋维修通知","向出租方说明维修需求", "landlord:出租方;tenant:承租方;property:房屋地址;issue:故障或损坏情况", "discovered:发现时间;impact:对使用的影响;deadline:希望处理时间", "photos:照片或报修记录;contact:联系方式", "致 {landlord}：本人 {tenant} 承租的 {property} 出现以下问题：{issue}。发现时间：{discovered}。|对居住或使用的影响：{impact}。请在 {deadline} 前与本人联系并安排检查或维修。相关照片、报修记录：{photos}。|联系方式：{contact}。请双方记录维修方案、时间和费用承担的协商结果。"),
("rental-termination","居住租赁","租赁提前解除协议","记录双方协商退租", "landlord:出租方;tenant:承租方;property:房屋地址;end_date:协商解除日期", "deposit:押金处理;rent_balance:租金与费用结清;handover:交房安排", "compensation:补偿或违约金;other:其他安排", "出租方 {landlord} 与承租方 {tenant} 同意于 {end_date} 解除关于 {property} 的租赁关系。|交房安排：{handover}。押金处理：{deposit}。租金及其他费用结清：{rent_balance}。|补偿或违约金：{compensation}。其他安排：{other}。双方在交接时另行确认房屋及物品状况。"),
("roommate-agreement","居住租赁","合租事项约定","记录合租人之间的生活与费用约定", "parties:合租人姓名;property:房屋地址;term:合租期限;cost:租金分担", "deposit:押金分担;utilities:水电网等费用;rooms:房间使用安排", "guests:访客约定;exit:提前退出安排", "合租人 {parties} 就 {property} 的共同居住约定如下。期限：{term}，租金分担：{cost}。|押金分担：{deposit}。水电网等费用：{utilities}。房间及公共区域使用：{rooms}。|访客与生活安排：{guests}。提前退出及费用结清：{exit}。本约定不替代与出租人的租赁合同。"),
("wage-demand","劳动与工作","欠薪催告函","书面催告已到期工资", "employer:用人单位;employee:劳动者;period:欠薪期间;amount:欠薪金额", "deadline:希望支付日期;work_basis:劳动关系及工作证据;payments:已支付金额", "contact:联系方式;account:收款方式", "致 {employer}：本人 {employee} 就 {period} 期间的工资进行核对，目前认为尚欠 {amount}。|劳动关系及工作证据：{work_basis}。已支付金额：{payments}。请于 {deadline} 前核对并支付；如有异议请书面说明。|联系方式：{contact}。收款方式：{account}。请保存工资记录和本函送达凭证。"),
("employment-certificate","劳动与工作","在职证明草稿","向单位申请出具在职证明", "employer:单位名称;employee:员工姓名;position:岗位;start_date:入职时间", "purpose:证明用途;end_date:需要出具日期", "department:部门;salary:是否需要写明收入", "兹证明 {employee} 自 {start_date} 起在 {employer} 任职，岗位为 {position}。|本证明拟用于 {purpose}，希望于 {end_date} 前出具。部门：{department}。收入信息要求：{salary}。|本草稿需由单位核对后决定是否加盖公章，不应冒用单位名义。"),
("resignation-notice","劳动与工作","离职通知","记录劳动者提出离职", "employer:用人单位;employee:劳动者;notice_date:通知日期;last_day:拟最后工作日", "handover:工作交接安排;reason:离职原因", "contact:后续联系方式;materials:希望领取的证明材料", "致 {employer}：本人 {employee} 于 {notice_date} 提出离职，拟最后工作日为 {last_day}。|离职原因或说明：{reason}。工作交接安排：{handover}。请协助核对工资、社保及离职证明等事项。|后续联系方式：{contact}。希望领取的材料：{materials}。请核对适用的通知期限与合同约定。"),
("termination-objection","劳动与工作","解除劳动关系异议函","记录对解除决定的异议", "employer:用人单位;employee:劳动者;decision:解除决定及日期;objection:异议理由", "evidence:有关证据;request:希望单位采取的措施;deadline:希望回复时间", "contact:联系方式", "致 {employer}：本人 {employee} 收到或获知 {decision}，现提出异议。|异议理由及事实：{objection}。已有证据：{evidence}。请核对并于 {deadline} 前回复，拟请求：{request}。|联系方式：{contact}。本函仅记录异议事实，具体权利义务应结合劳动合同和现行规定判断。"),
("overtime-record","劳动与工作","加班事实记录","整理加班日期和报酬线索", "employee:劳动者;employer:用人单位;period:加班期间;details:加班日期和时长", "instruction:安排加班的证据;payment:已支付加班费或调休", "witness:知情人;files:电子记录位置", "劳动者 {employee} 就在 {employer} 的加班情况作如下记录。期间：{period}。|具体日期、时长与工作事项：{details}。安排加班的依据：{instruction}。已支付报酬或调休：{payment}。|知情人与电子记录：{witness}；{files}。该记录应与考勤、聊天和工资材料逐项核对。"),
("work-injury-statement","劳动与工作","工伤事故经过说明","记录工作事故基本事实", "worker:受伤人员;employer:单位;time:事故时间;place:事故地点;event:事故经过", "injury:受伤情况;witness:现场证人;medical:就医资料", "report:报告情况;files:影像或其他证据", "受伤人员 {worker} 所在单位为 {employer}。事故发生于 {time}，地点 {place}。|事故经过：{event}。受伤情况：{injury}。现场证人：{witness}。就医资料：{medical}。|报告情况：{report}。其他证据：{files}。请按真实记忆描述，不确定的事实应标明待核实。"),
("iou","借贷与支付","借条草稿","记录借款与还款安排", "lender:出借人;borrower:借款人;amount:借款金额;transfer_date:实际交付款日期;due_date:还款日期", "purpose:借款用途;payment:交付及还款方式;interest:是否约定利息", "guarantee:担保安排;contacts:联系地址", "借款人 {borrower} 确认向出借人 {lender} 借款 {amount}，实际交付日期为 {transfer_date}。|借款用途：{purpose}。交付及还款方式：{payment}。还款日期：{due_date}。利息约定：{interest}。|担保安排：{guarantee}。联系地址：{contacts}。双方应保存资金交付凭证，利息及担保条款需另行核对合法性。"),
("repayment-agreement","借贷与支付","分期还款协议","约定既有债务的分期偿还", "creditor:债权人;debtor:债务人;balance:确认的未还金额;schedule:分期金额与日期", "origin:债务形成经过;payment:付款方式;default:逾期处理", "guarantor:担保人;prior:既往付款", "债权人 {creditor} 与债务人 {debtor} 核对未还金额为 {balance}。债务形成经过：{origin}。|双方拟按以下安排分期还款：{schedule}。付款方式：{payment}。既往付款：{prior}。|逾期处理：{default}。担保安排：{guarantor}。每次付款后应保留凭证，并核对原合同是否仍有效。"),
("loan-demand","借贷与支付","借款还款催告函","催告清偿到期借款", "lender:出借人;borrower:借款人;amount:尚欠金额;loan_date:借款日期", "due_date:约定还款日期;deadline:希望清偿日期;proof:交付凭证", "partial:已还金额;contact:联系方式", "致 {borrower}：本人 {lender} 就 {loan_date} 的借款核对，认为目前尚欠 {amount}。|约定还款日期：{due_date}。资金交付凭证：{proof}。已还金额：{partial}。请于 {deadline} 前核对并清偿，如有异议请书面说明。|联系方式：{contact}。请保留本函及送达记录。"),
("payment-reminder","借贷与支付","服务或货款催款函","催告合同款项", "payer:付款方;payee:收款方;contract:合同或交易事项;amount:待付金额", "due_date:约定付款日期;invoice:发票或交付情况;deadline:希望付款日期", "account:收款账户;proof:履约证据", "致 {payer}：{payee} 就 {contract} 项下待付金额 {amount} 向贵方核对。|约定付款日期：{due_date}。发票或交付情况：{invoice}。请于 {deadline} 前付款或书面提出异议。|收款账户：{account}。履约凭证：{proof}。请核对实际合同及结算单。"),
("receipt","借贷与支付","收款收据","记录一笔实际收款", "payer:付款人;payee:收款人;amount:实收金额;date:收款日期;reason:款项用途", "method:付款方式;transaction:交易流水或凭证", "balance:尚余金额;note:其他说明", "收款人 {payee} 确认于 {date} 收到付款人 {payer} 支付的 {amount}，款项用途为 {reason}。|付款方式：{method}。交易流水或凭证：{transaction}。尚余金额：{balance}。|其他说明：{note}。本收据仅确认实际收到的款项，不应预先确认未到账款项。"),
("refund-request","消费交易","退款申请函","向商家提出退款请求", "merchant:商家;consumer:消费者;purchase:商品或服务;amount:支付金额;reason:退款原因", "date:购买或支付日期;order:订单号;request:希望的处理方式", "proof:支付与沟通证据;deadline:希望回复日期", "致 {merchant}：消费者 {consumer} 就 {purchase} 提出退款申请，支付金额为 {amount}，购买或支付日期为 {date}。|退款原因：{reason}。订单号：{order}。希望的处理方式：{request}，请于 {deadline} 前回复。|支付与沟通凭证：{proof}。请按实际交易和适用规则核对退款条件。"),
("quality-claim","消费交易","商品质量问题说明与处理请求","记录商品问题并提出处理", "merchant:商家;buyer:购买人;product:商品及订单;problem:质量问题", "purchase_date:购买日期;discovery:发现时间;request:希望的处理方式", "photos:照片视频;repair:维修或检测记录", "致 {merchant}：购买人 {buyer} 就 {product} 的质量问题进行说明。|问题表现：{problem}。购买日期：{purchase_date}。发现时间：{discovery}。拟请求的处理方式：{request}。|照片视频：{photos}。维修或检测记录：{repair}。请书面回复并保留售后沟通记录。"),
("service-cancel","消费交易","预付服务解约与退款请求","取消课程、健身等预付服务", "provider:服务商;customer:消费者;service:服务项目;paid:已支付金额;reason:取消原因", "unused:未使用次数或期限;contract:合同退款约定;request:希望退款金额", "proof:付款及沟通证据;deadline:回复期限", "致 {provider}：消费者 {customer} 就 {service} 申请终止后续服务。已支付 {paid}。|取消原因：{reason}。未使用部分：{unused}。合同退款约定：{contract}。拟请求退款：{request}。|付款和沟通证据：{proof}。请于 {deadline} 前说明核算方法并回复。"),
("secondhand-sale","消费交易","二手物品买卖协议","记录个人之间二手物品交易", "seller:卖方;buyer:买方;item:物品及型号;price:成交价;delivery:交付日期地点", "condition:已知瑕疵与现状;payment:付款方式;accessories:配件与凭证", "warranty:售后约定;transport:运输安排", "卖方 {seller} 将 {item} 出售给买方 {buyer}，价款为 {price}，交付安排：{delivery}。|物品现状及已知瑕疵：{condition}。配件和凭证：{accessories}。付款方式：{payment}。|运输安排：{transport}。售后约定：{warranty}。交易前应核对所有权、实物和支付记录。"),
("renovation-agreement","消费交易","家庭装修施工约定","记录小型家庭装修项目", "owner:业主;contractor:施工方;property:施工地址;scope:施工范围;price:总价及付款节点", "schedule:开工与完工时间;materials:材料品牌规格;acceptance:验收标准", "warranty:保修安排;changes:变更计价", "业主 {owner} 与施工方 {contractor} 就 {property} 的装修施工约定如下。施工范围：{scope}。价款及付款节点：{price}。|施工时间：{schedule}。材料品牌规格：{materials}。验收标准与记录：{acceptance}。|变更计价：{changes}。保修安排：{warranty}。开工前应核对施工资质、物业要求和安全责任。"),
("moving-service","消费交易","搬家服务约定","记录搬家服务范围与费用", "customer:委托人;provider:服务方;from:起点;to:终点;date:搬运日期;price:费用", "items:主要物品;stairs:楼层电梯情况;damage:损坏处理", "extras:额外收费;contact:现场联系人", "委托人 {customer} 委托 {provider} 于 {date} 从 {from} 搬运至 {to}，费用为 {price}。|主要物品：{items}。楼层及电梯：{stairs}。额外收费约定：{extras}。|物品损坏处理：{damage}。现场联系人：{contact}。搬运前后建议拍照核对。"),
("child-support","家庭与继承","子女抚养费用约定草稿","记录父母对子女费用的协商", "parent_a:一方姓名;parent_b:另一方姓名;child:子女姓名或称呼;arrangement:主要照护安排;support:抚养费金额与频率", "education:教育医疗分担;visits:探望安排;start:开始日期", "changes:变更机制;contact:沟通方式", "{parent_a} 与 {parent_b} 就子女 {child} 的照护与费用作如下协商记录。主要照护安排：{arrangement}。|抚养费金额与支付频率：{support}。教育、医疗等费用分担：{education}。探望安排：{visits}。开始日期：{start}。|变更机制：{changes}。沟通方式：{contact}。应以子女利益为先，正式协议需核对当地实际要求。"),
("family-loan","家庭与继承","家庭成员借款确认书","记录亲属间借款", "lender:出借人;borrower:借款人;amount:借款金额;date:交付日期;due:还款日期", "purpose:用途;method:交付方式;interest:利息约定", "witness:见证人;security:担保", "出借人 {lender} 与借款人 {borrower} 确认于 {date} 交付借款 {amount}。用途：{purpose}。|交付方式：{method}。约定还款日期：{due}。利息约定：{interest}。|担保：{security}。见证人：{witness}。请保留真实资金往来记录。"),
("inheritance-inventory","家庭与继承","遗产资料清单","整理继承相关资产与材料", "decedent:被继承人;date:去世日期;assets:已知财产;heirs:已知继承人", "debts:已知债务;wills:遗嘱或协议情况;documents:权属材料", "disputes:待核实争议;keeper:保管人", "被继承人：{decedent}；去世日期：{date}。已知继承人：{heirs}。|已知财产及线索：{assets}。已知债务：{debts}。遗嘱或协议情况：{wills}。权属材料：{documents}。|待核实争议：{disputes}。资料保管人：{keeper}。本清单仅整理线索，不认定财产归属或继承份额。"),
("caregiving-agreement","家庭与继承","老人照护分工约定","记录家庭成员照护与费用安排", "elder:被照护人;family:参与家庭成员;care:日常照护分工;cost:费用分担", "medical:就医与紧急联络;term:约定期限;review:定期核对安排", "assets:财物保管;other:其他安排", "参与家庭成员 {family} 就 {elder} 的照护达成以下记录。日常照护分工：{care}。费用分担：{cost}。|就医、紧急联络与决定沟通：{medical}。约定期限：{term}。定期核对安排：{review}。|财物保管：{assets}。其他安排：{other}。应尊重被照护人的真实意愿和依法享有的权利。"),
("civil-complaint","诉讼与调解","民事起诉状草稿","梳理诉讼请求和事实", "plaintiff:原告;defendant:被告;claim:具体诉讼请求;facts:关键事实经过", "amount:请求金额及计算方式;court:拟提交法院;proof:主要证据", "contact:送达联系方式;law:拟引用依据", "原告：{plaintiff}。被告：{defendant}。拟提交法院：{court}。|诉讼请求：{claim}。请求金额及计算方式：{amount}。事实与理由：{facts}。|主要证据：{proof}。送达联系方式：{contact}。拟引用依据：{law}。正式提交前应核对管辖、主体、请求和证据，并使用受理法院要求的文本。"),
("civil-defense","诉讼与调解","民事答辩状草稿","梳理对起诉请求的答复", "respondent:答辩人;opponent:对方当事人;case:案由或案件信息;response:逐项答辩意见", "facts:事实依据;evidence:证据;court:受理法院", "contact:送达方式;request:反诉或其他请求", "答辩人：{respondent}。对方当事人：{opponent}。案件信息：{case}。|对诉讼请求的逐项答复：{response}。事实依据：{facts}。现有证据：{evidence}。|受理法院：{court}。送达方式：{contact}。其他请求：{request}。正式提交前核对答辩期限和法院要求。"),
("evidence-index","诉讼与调解","证据目录说明","按编号整理证据和证明目的", "party:提交人;case:案件或事项;items:证据名称与编号;purpose:各证据拟证明的事实", "source:证据来源;copies:原件与复印件情况;date:整理日期", "objections:真实性或来源待核实事项", "提交人：{party}。事项：{case}。整理日期：{date}。|证据名称与编号：{items}。各证据拟证明的事实：{purpose}。|来源：{source}。原件及复印件：{copies}。待核实事项：{objections}。应按提交机关或法院要求另行制作正式证据清单。"),
("mediation-application","诉讼与调解","调解申请书草稿","向调解组织申请沟通", "applicant:申请人;respondent:对方;dispute:争议事项;request:希望调解的结果", "timeline:事情经过;organization:拟申请组织;evidence:现有材料", "contact:联系方式;previous:此前沟通情况", "申请人 {applicant} 拟就与 {respondent} 之间的 {dispute} 申请调解。|事情经过：{timeline}。希望达成的结果：{request}。拟申请组织：{organization}。|现有材料：{evidence}。此前沟通：{previous}。联系方式：{contact}。提交前请核对该组织的受理范围。"),
("settlement-agreement","诉讼与调解","和解协议草稿","记录争议双方的解决方案", "party_a:甲方;party_b:乙方;dispute:争议事项;resolution:具体解决方案;deadline:履行期限", "payment:款项和支付方式;withdrawal:案件撤回或终结安排;default:不履行处理", "confidential:保密约定;other:其他事项", "甲方 {party_a} 与乙方 {party_b} 就 {dispute} 协商解决。|具体履行安排：{resolution}。期限：{deadline}。款项及支付方式：{payment}。相关程序的处理：{withdrawal}。|不履行处理：{default}。保密约定：{confidential}。其他事项：{other}。请核对协议与正在进行的司法或行政程序是否衔接。"),
("incident-timeline","诉讼与调解","事件时间线说明","按时间梳理事实和证据", "author:记录人;matter:事项;events:按时间顺序的事件", "people:涉及人员;proof:对应证据;unknown:尚不确定事实", "result:目前进展", "记录人 {author} 就 {matter} 整理以下事实时间线。|按时间顺序的事件：{events}。涉及人员：{people}。对应证据：{proof}。|尚不确定的事实：{unknown}。目前进展：{result}。请区分亲历事实、他人转述和个人判断。"),
("gov-info-request","公共事务","政府信息公开申请说明稿","梳理拟申请公开的信息", "agency:受理机关;applicant:申请人;information:希望公开的信息;purpose:希望获取的用途", "time_range:信息时间范围;format:获取形式;contact:接收方式", "clue:文件名称或编号;previous:此前查询", "致 {agency}：申请人 {applicant} 拟申请获取以下政府信息：{information}。|信息时间范围：{time_range}。希望获取形式：{format}。用途说明：{purpose}。文件名称或编号线索：{clue}。|此前查询：{previous}。接收方式：{contact}。正式提交应使用受理机关渠道并核对所需身份材料。"),
("admin-complaint","公共事务","行政事项投诉说明","向主管机关反映具体问题", "agency:拟提交机关;applicant:反映人;issue:具体问题;location:发生地点;time:发生时间", "request:希望处理事项;proof:证据材料;previous:已联系部门", "contact:联系方式", "致 {agency}：反映人 {applicant} 就 {location} 于 {time} 发生的事项反映如下。|具体问题：{issue}。希望处理事项：{request}。证据材料：{proof}。|此前联系部门及答复：{previous}。联系方式：{contact}。请按受理机关要求补充材料并核对职责范围。"),
("legal-aid-note","公共事务","法律援助申请情况说明草稿","梳理申请法律援助的事实", "applicant:申请人;matter:法律问题;region:所在地;need:希望获得的帮助", "status:案件或纠纷阶段;income:经济困难情况;materials:已有材料", "contact:联系方式;special:特殊情况", "申请人 {applicant} 位于 {region}，拟就 {matter} 咨询或申请法律援助。|目前阶段：{status}。希望获得的帮助：{need}。经济困难情况：{income}。已有材料：{materials}。|特殊情况：{special}。联系方式：{contact}。正式申请应以当地法律援助机构现行要求为准。"),
("personal-data-request","公共事务","个人信息查询或更正请求","向信息处理方提出查询更正", "controller:信息处理方;person:本人称呼;data:涉及的个人信息;request:查询或更正请求", "account:关联账号;problem:错误或疑问;proof:支持材料", "contact:回复方式;date:发现日期", "致 {controller}：本人 {person} 就贵方处理的 {data} 提出请求。|关联账号：{account}。存在的问题：{problem}。具体查询或更正请求：{request}。支持材料：{proof}。|发现日期：{date}。回复方式：{contact}。提交时仅提供核验身份所必需的信息。"),
("simple-service","工作与经营","个人服务协议","约定个人服务的内容与报酬", "client:委托方;provider:服务方;scope:服务内容与交付;price:报酬;term:服务期限", "acceptance:验收方式;payment:付款节点;changes:变更约定", "confidential:保密安排;termination:解除条件", "委托方 {client} 与服务方 {provider} 就以下服务协商：{scope}。期限：{term}。报酬：{price}。|交付与验收方式：{acceptance}。付款节点：{payment}。变更约定：{changes}。|保密安排：{confidential}。解除条件：{termination}。请核对实际关系是否可能构成劳动关系。"),
("nda","工作与经营","保密约定草稿","约定具体资料的使用与保护", "discloser:信息披露方;receiver:接收方;information:保密信息范围;purpose:允许使用目的;term:保密期限", "exceptions:公开信息等例外;return:资料返还或删除;breach:违反约定的处理", "contact:通知方式", "信息披露方 {discloser} 与接收方 {receiver} 就 {information} 的保护作如下约定。|允许使用目的：{purpose}。保密期限：{term}。不属于保密信息的例外：{exceptions}。|资料返还或删除：{return}。违反约定的处理：{breach}。通知方式：{contact}。不得将依法公开的信息笼统列为保密信息。"),
("invoice-request","工作与经营","开票申请说明","向交易相对方申请发票", "seller:开票方;buyer:购买方;transaction:交易内容;amount:开票金额", "date:支付或交付日期;invoice_type:发票类型;tax:开票抬头与税号", "delivery:接收邮箱或地址;proof:付款凭证", "致 {seller}：{buyer} 就 {transaction} 申请开具金额为 {amount} 的发票。|支付或交付日期：{date}。发票类型：{invoice_type}。开票抬头与税号：{tax}。|接收方式：{delivery}。付款凭证：{proof}。请按真实交易信息核对。"),
("meeting-minutes","工作与经营","合作沟通纪要","记录协商结论与待办", "parties:参与方;date:沟通日期;topic:讨论事项;conclusions:已达成结论", "actions:待办事项与负责人;deadline:完成期限;open:未解决问题", "attachments:附件;next:下次沟通", "参与方 {parties} 于 {date} 就 {topic} 进行沟通。|已达成结论：{conclusions}。待办事项及负责人：{actions}。完成期限：{deadline}。|尚未解决的问题：{open}。附件：{attachments}。下次沟通安排：{next}。本纪要需各方确认后再作为共同意思表示使用。"),
]


def _fields(raw: str, level: str) -> list[dict[str, str]]:
    return [{"key": pair.split(":", 1)[0], "label": pair.split(":", 1)[1], "level": level}
            for pair in raw.split(";") if pair]


def _scenario(row: tuple[str, ...]) -> dict:
    scenario_id, category, title, purpose, required, recommended, optional, body = row
    fields = _fields(required, "required") + _fields(recommended, "recommended") + _fields(optional, "optional")
    labels = lambda level: "、".join(field["label"] for field in fields if field["level"] == level)
    prompt = (f"你正在协助起草《{title}》，用途：{purpose}。请像对话一样询问，不要让用户填写表单。"
              f"必填信息：{labels('required')}；缺少其中任何一项时先追问，不得生成完成版。"
              f"非常建议提供：{labels('recommended')}；尽量在首次提问中一并询问，但用户不提供时可以留【待确认】。"
              f"选填信息：{labels('optional')}；只有与实际情况相关时询问。"
              "只摘取用户明确提供的事实，不得猜测姓名、金额、日期或法律结论；保护隐私，不主动索取身份证号、银行卡号等无关敏感信息。"
              "有足够必填信息后，把已知事实填入已保存草稿，未知项标【待确认】，输出可编辑 Word 文件并提醒用户核对。")
    return {"id": scenario_id, "category": category, "title": title, "purpose": purpose,
            "fields": fields, "intake_prompt": prompt, "paragraphs": body.split("|"),
            "source_url": ("https://www.moj.gov.cn/pub/sfbgw/zwfw/zwfwbszn/bsznflyz/202604/t20260417_533992.html"
                           if scenario_id == "legal-aid-note" else SOURCES.get(category)), "kind": "word"}

CATALOG = {row[0]: _scenario(row) for row in RAW}
for row, kind in [
    (("evidence-ledger-chat", "诉讼与调解", "案件证据清单 Excel", "把证据名称、来源和证明事项整理成表格",
      "matter:案件或事项;items:已有证据名称", "proof:各证据要证明什么;source:证据来源", "files:文件存放位置;notes:待核实问题",
      "事项：{matter}。已有证据：{items}。|证明事项：{proof}。来源：{source}。|文件位置：{files}。待核实：{notes}。"), "excel"),
    (("expense-ledger-chat", "借贷与支付", "费用分担台账 Excel", "记录合租、家庭或小组费用",
      "parties:参与人;period:费用期间;items:费用项目和金额", "split:分担规则;paid:已付款情况", "notes:待结事项",
      "参与人：{parties}。期间：{period}。|费用项目：{items}。分担规则：{split}。|已付款情况：{paid}。待结事项：{notes}。"), "excel"),
    (("case-brief-chat", "诉讼与调解", "案件沟通简报 PPT", "向律师或家人讲清事实和问题",
      "matter:案件或事项;parties:相关人员;facts:主要事实", "timeline:关键时间线;evidence:已有证据;questions:想咨询的问题", "goal:希望达成的结果",
      "事项：{matter}。相关人员：{parties}。|主要事实：{facts}。时间线：{timeline}。|证据：{evidence}。待咨询：{questions}。目标：{goal}。"), "ppt"),
]:
    item = _scenario(row)
    item["kind"] = kind
    item["intake_prompt"] = item["intake_prompt"].replace("Word 文件", "可编辑 Office 文件")
    CATALOG[item["id"]] = item


def office_payload(item: dict, facts: dict[str, str]) -> dict:
    if missing_required(item, facts):
        raise HTTPException(422, "缺少必填信息")
    value = lambda key: facts.get(key, "").strip() or "【待确认】"
    if item["id"] == "evidence-ledger-chat":
        names = [part.strip() for part in value("items").replace("，", "；").split("；") if part.strip()][:30]
        return {"title": item["title"], "columns": ["序号", "证据名称", "来源", "待证明事实", "文件位置", "备注"],
                "rows": [[i, name, value("source"), value("proof"), value("files"), value("notes")] for i, name in enumerate(names, 1)]}
    if item["id"] == "expense-ledger-chat":
        names = [part.strip() for part in value("items").replace("，", "；").split("；") if part.strip()][:30]
        return {"title": item["title"] + " · " + value("period"),
                "columns": ["序号", "费用项目及金额", "参与人", "分担规则", "已付款", "待结事项"],
                "rows": [[i, name, value("parties"), value("split"), value("paid"), value("notes")] for i, name in enumerate(names, 1)]}
    if item["id"] == "case-brief-chat":
        chunks = lambda text: [text[i:i + 65] for i in range(0, len(text), 65)][:6]
        return {"title": item["title"] + " · " + value("matter"), "slides": [
            {"title": "事项概览", "bullets": ["事项：" + value("matter"), "相关人员：" + value("parties"), "希望达成：" + value("goal")]},
            {"title": "主要事实", "bullets": chunks(value("facts"))},
            {"title": "关键时间线", "bullets": chunks(value("timeline"))},
            {"title": "现有证据", "bullets": chunks(value("evidence"))},
            {"title": "待咨询问题", "bullets": chunks(value("questions"))},
        ]}
    raise HTTPException(422, "文件场景不支持此格式")


def list_scenarios(q: str = "", category: str = "") -> list[dict]:
    needle = q.strip().lower()
    built_in = [{key: value for key, value in item.items() if key != "paragraphs"}
            for item in CATALOG.values()
            if (not category or item["category"] == category)
            and (not needle or needle in (item["title"] + item["purpose"] + item["category"] + " ".join(field["label"] for field in item["fields"])).lower())]
    return built_in + [{key: value for key, value in item.items() if key != "paragraphs"}
                       for item in custom_templates.list_items(q, category)]


def get_scenario(scenario_id: str) -> dict:
    item = CATALOG.get(scenario_id)
    if not item:
        return custom_templates.get(scenario_id)
    return item


def missing_required(item: dict, facts: dict[str, str]) -> list[dict]:
    return [field for field in item["fields"] if field["level"] == "required" and not facts.get(field["key"])]


def intake_question(item: dict, facts: dict[str, str] | None = None) -> str:
    facts = facts or {}
    missing = missing_required(item, facts)
    recommended = [field for field in item["fields"] if field["level"] == "recommended" and not facts.get(field["key"])]
    if facts and missing:
        return "还差几项起草必需的信息：" + "、".join(field["label"] for field in missing) + "。你可以像聊天一样一次告诉我。"
    if not missing:
        return "必需信息已经齐了。如果还有补充请直接说；否则我会生成可编辑 Word 草稿。"
    return (f"我来帮你起草《{item['title']}》。请直接说说：" + "、".join(field["label"] for field in missing)
            + "。如果方便，也建议补充" + "、".join(field["label"] for field in recommended)
            + "。不用整理成固定格式，也不用提供身份证号等无关敏感信息。")


def render_scenario(scenario_id: str, facts: dict[str, str]) -> tuple[str, str]:
    item = get_scenario(scenario_id)
    missing = missing_required(item, facts)
    if missing:
        raise HTTPException(422, "缺少必填信息：" + "、".join(field["label"] for field in missing))
    values = {field["key"]: facts.get(field["key"], "").strip() or "【待确认】" for field in item["fields"]}
    paragraphs = []
    for paragraph in item["paragraphs"]:
        for key, value in values.items():
            paragraph = paragraph.replace("{" + key + "}", value)
        paragraphs.append(paragraph)
    content = f"# {item['title']}\n\n" + "\n\n".join(paragraphs) + "\n\n"
    content += "签署或提交前请核对事实、证据、适用规则及受理机构要求。\n"
    if item["source_url"]:
        content += "结构参考（请核对原站现行文本）：" + item["source_url"] + "\n"
    return item["title"], content
