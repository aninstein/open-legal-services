"""Deterministic document drafts. These are editable starting points, not legal advice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

TEMPLATES = {
    "wage-demand": {
        "title": "欠薪催告函",
        "category": "劳动",
        "description": "向用人单位书面催告支付已到期工资。",
        "fields": [
            {"key": "employer", "label": "用人单位名称"},
            {"key": "employee", "label": "劳动者姓名"},
            {"key": "period", "label": "欠薪期间"},
            {"key": "amount", "label": "欠薪金额（元）"},
            {"key": "deadline", "label": "希望支付日期"},
        ],
    },
    "deposit-demand": {
        "title": "租赁押金返还催告函",
        "category": "租赁",
        "description": "向出租方提出押金返还请求并保留沟通记录。",
        "fields": [
            {"key": "landlord", "label": "出租方称呼"},
            {"key": "tenant", "label": "承租方称呼"},
            {"key": "property", "label": "房屋地址或合同标识"},
            {"key": "amount", "label": "押金金额（元）"},
            {"key": "deadline", "label": "希望返还日期"},
        ],
    },
    "loan-demand": {
        "title": "借款还款催告函",
        "category": "民事",
        "description": "向借款人确认借款事实并催告还款。",
        "fields": [
            {"key": "borrower", "label": "借款人称呼"},
            {"key": "lender", "label": "出借人称呼"},
            {"key": "loan_date", "label": "借款日期"},
            {"key": "amount", "label": "借款金额（元）"},
            {"key": "deadline", "label": "希望还款日期"},
        ],
    },
    "rental-contract": {
        "title": "房屋租赁合同（草稿）",
        "category": "租赁",
        "description": "填写已知信息，未填写处保留待确认标记；可下载 Word 并打印签署。",
        "source_url": "https://htsfwb.samr.gov.cn/View?id=2340996b-882d-47a4-b74d-c30784628737",
        "fields": [
            {"key": "landlord", "label": "出租人姓名或名称", "required": False},
            {"key": "tenant", "label": "承租人姓名或名称", "required": False},
            {"key": "property", "label": "房屋详细地址", "required": False},
            {"key": "start_date", "label": "租期开始日期", "type": "date", "required": False},
            {"key": "end_date", "label": "租期结束日期", "type": "date", "required": False},
            {"key": "rent", "label": "月租金（元）", "type": "number", "required": False},
            {"key": "deposit", "label": "押金（元）", "type": "number", "required": False},
            {"key": "payment", "label": "租金支付周期与方式", "required": False},
            {"key": "handover", "label": "交付日期及设施清单约定", "required": False},
        ],
    },
}


def list_templates() -> list[dict]:
    return [{"id": key, **value} for key, value in TEMPLATES.items()]


def render(template_id: str, fields: dict[str, str]) -> tuple[str, str]:
    template = TEMPLATES.get(template_id)
    if not template:
        raise HTTPException(404, "文书模板不存在")
    cleaned: dict[str, str] = {}
    for field in template["fields"]:
        key = field["key"]
        value = str(fields.get(key, "")).strip()
        if (not value and field.get("required", True)) or len(value) > 200 or any(char in value for char in "\r\n"):
            raise HTTPException(422, f"请正确填写：{field['label']}")
        cleaned[key] = value or f"【{field['label']}待确认】"
    if template_id == "rental-contract":
        start, end = fields.get("start_date", ""), fields.get("end_date", "")
        try:
            start_date = date.fromisoformat(start) if start else None
            end_date = date.fromisoformat(end) if end else None
        except ValueError as exc:
            raise HTTPException(422, "请使用有效的租期日期") from exc
        if start_date and end_date and start_date > end_date:
            raise HTTPException(422, "租期结束日期不能早于开始日期")
        for key in ("rent", "deposit"):
            if fields.get(key):
                try:
                    amount = Decimal(fields[key])
                except InvalidOperation as exc:
                    raise HTTPException(422, "租金和押金须为非负金额") from exc
                if not amount.is_finite() or amount < 0 or amount > 100000000:
                    raise HTTPException(422, "租金和押金须为有效的非负金额")
    if template_id == "wage-demand":
        body = (f"致：{cleaned['employer']}\n\n本人 {cleaned['employee']} 就 {cleaned['period']} 期间尚未支付的工资"
                f"人民币 {cleaned['amount']} 元，现请贵单位核对并于 {cleaned['deadline']} 前支付。"
                "如金额或支付情况有异议，请书面说明并提供相关记录。\n\n此函用于记录沟通及催告事实。")
    elif template_id == "deposit-demand":
        body = (f"致：{cleaned['landlord']}\n\n本人 {cleaned['tenant']} 就 {cleaned['property']} 的租赁押金"
                f"人民币 {cleaned['amount']} 元，请于 {cleaned['deadline']} 前核对并返还；"
                "如有扣除项目，请提供合同依据与明细。\n\n此函用于记录沟通及催告事实。")
    elif template_id == "loan-demand":
        body = (f"致：{cleaned['borrower']}\n\n本人 {cleaned['lender']} 就 {cleaned['loan_date']} 的借款"
                f"人民币 {cleaned['amount']} 元，请于 {cleaned['deadline']} 前核对并偿还。"
                "如对金额或履行情况有异议，请书面说明并提供相关记录。\n\n此函用于记录沟通及催告事实。")
    else:
        body = (
            f"出租人（甲方）：{cleaned['landlord']}\n承租人（乙方）：{cleaned['tenant']}\n\n"
            "一、房屋与用途\n"
            f"甲方将位于 {cleaned['property']} 的房屋出租给乙方居住使用。双方应在签署前核对出租资格、房屋权属、实际状况及允许的使用范围。\n\n"
            "二、租赁期限与交付\n"
            f"租期自 {cleaned['start_date']} 起至 {cleaned['end_date']} 止。交付安排：{cleaned['handover']}。"
            "双方应另附房屋交割单，记录钥匙、家具电器、表计读数及照片。\n\n"
            "三、租金、押金与费用\n"
            f"月租金为人民币 {cleaned['rent']} 元；押金为人民币 {cleaned['deposit']} 元。"
            f"租金支付周期与方式：{cleaned['payment']}。水、电、燃气、网络、物业等费用的承担及结算方式由双方在交割单或补充条款中明确。"
            "押金扣除项目应有合同依据和明细，返还时间及方式须在签署前补充约定。\n\n"
            "四、使用、维修与转租\n"
            "乙方应按约定用途使用房屋，妥善保管设施；房屋及设施的维修责任、报修方式和合理响应期限由双方补充明确。"
            "未经双方书面约定，不应擅自改变房屋结构或转租。\n\n"
            "五、变更、解除与违约处理\n"
            "提前退租、逾期交付、逾期支付租金、房屋不符合约定等情形的通知期限、整改期限、违约金及损失承担，"
            "由双方结合实际情况在补充条款中明确。争议发生后先协商；协商不成，依法选择有管辖权的争议解决渠道。\n\n"
            "六、补充约定与附件\n"
            "补充约定：________________________________。附件：房屋交割单、设施清单及双方确认的其他材料。\n\n"
            "甲方签字/盖章：________________    日期：____________\n"
            "乙方签字/盖章：________________    日期：____________\n\n"
            "签署前核对：双方身份与出租资格、权属、房屋安全、租期、支付方式、押金返还、费用分担、维修与提前解除条款。"
        )
    if template_id == "rental-contract":
        content = (f"# {template['title']}\n\n{body}\n\n---\n"
                   "草稿提示：请按房屋所在地现行规定和双方真实约定核对后再签署。"
                   f"国家市场监督管理总局示范文本：{template['source_url']}")
    else:
        content = (f"# {template['title']}\n\n{body}\n\n发函人：____________\n日期：____________\n\n"
                   "---\n草稿提示：请核对事实、合同、证据、送达方式与期限；复杂事项请咨询执业律师。"
                   "本模板未自动判断具体法律关系或诉讼时效。")
    return template["title"], content
