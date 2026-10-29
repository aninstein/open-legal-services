# UI 验证记录

日期：2026-10-28。

- `node --check prototype/app.js`：通过。
- `python3 -m http.server 8765 --bind 127.0.0.1 -d prototype` 与 `curl -I http://127.0.0.1:8765/`：返回 HTTP 200。
- 静态 HTML 检查：54 个 ID 无重复；本地 CSS/JS 资源存在。JS 中 `contactRequest`、`contactLawyer` 两个 ID 是在详情弹层打开时动态生成的。
- `npx -p @google/design.md designmd lint DESIGN.md`：0 错误，8 条仅提示部分 token 未被 frontmatter 的组件映射直接引用；这些 token 已在 CSS 使用。
- `audit_project.py . --mode strict`：0 个未定所有权项；34 个 `affordance.actionless-button` 报告来自审计脚本只识别 HTML 内联 `onclick`，不识别本 demo 在 `prototype/app.js` 中通过 `addEventListener` 绑定的操作。按钮均有外部脚本绑定或为表单提交。原始报告为本地生成文件，未纳入仓库。
- 可视化浏览器验证未完成：本次浏览器环境将 8080 指向已有 nginx 页面，且本地文件 URL 被浏览器安全策略阻止。未对页面截图、窄屏或实际键盘行为作通过声明。

后续正式开发需补充真实浏览器的桌面/窄屏、键盘、表单错误、筛选空结果、弹层、IME、屏幕阅读器验证。当前静态原型不应作为生产验收。

## 运行页面 `web/`（第一阶段实现记录）

- `node --check web/app.js` 和 `python3 -m compileall -q src/legal_service`：通过。
- 产品 API 单元测试：8 个通过；继承底座的 10 个单元测试在此前版本通过。覆盖账号、CSRF、求取审核与消息隔离、文书读取/修改隔离、律师核验、法考链接检索、授权题导入、模拟练习答案隐藏、Office 模板下载和私有文件隔离。
- `docker compose --env-file .env -f compose.yaml -f compose.external.yaml config --quiet`：通过。项目现只保留在线模型启动模式；先前镜像构建验证通过，镜像以非 root 用户运行，显式设置 `LEGAL_WEB_DIR=/app/web`。
- 直接运行该镜像的冒烟检查：`/healthz` 200、首页 200、`/api/v1/exam/papers` 200 且返回 5 条官方目录；测试容器随后清理。
- 本地 `uvicorn legal_service.app:app --host 127.0.0.1 --port 8788`：首页、健康检查、资料及法考 API 可访问。
- 浏览器实测：注册后显示账户状态；求取提交后只在“我的发布”显示“待审核”；欠薪催告函可生成、在文本区修改并保存；法律资料目录正常显示；法考“2016”关键词筛出当年官方目录链接；Agent 在未配模型时显示“来源导航”及原站链接。
- 严格 UI 审计当时报告 22 条 `affordance.actionless-button`：审计器只识别 HTML 内联动作，运行页按钮由 `web/app.js` 的 `addEventListener` 绑定，已对关键按钮做浏览器交互验证。原始报告为本地生成文件，未纳入仓库。未完成完整的窄屏、屏幕阅读器和人工法律内容审校。

## 模拟法考补充验证

- 运行页 `#exam` 浏览器可见：AI 原创提示、科目与题量控件、开始按钮、个人练习记录，以及下方既有真题入口；桌面截图检查通过。
- 实际在线主模型 `deepseek-flash` 生成题目约 11 秒；接口冒烟测试在独立临时数据库内完成注册、AI 出题、提交判题。题目返回前不含标准答案；提交后返回答案与解析。
- 本机另有一个损坏的 Ollama 进程（缺推理二进制），验证时临时启动的容器已停止并删除。本项目 `.env` 和启动脚本已改用在线模型，不启动 Ollama。

## Office 文件补充验证

- 浏览器实测 `#documents`：四种文书模板、租房合同预填表单、Word/Excel/PPT 空白模板和 AI 文件生成区可见；桌面布局及表单字段标签已检查。
- API 测试覆盖三种空白文件的真实 OOXML 格式、租房合同已知信息预填、日期与金额校验、草稿 Word 下载与打印视图、AI 文件的账户隔离，以及 Excel 外部输入不执行公式。
- 实际在线模型分别生成 Word、Excel、PPT 结构化内容，生成的文件可由相应库读取，样例大小约 38 KB、7 KB、39 KB。
- 预填租房合同、证据清单、案件简报经 macOS Quick Look 生成缩略图并逐个检查，中文可读、内容未截断。打包的 LibreOffice 渲染器在本机错误地将中文映射到西文字体，故未将该渲染结果作为文件质量依据。

## 2026-10-28 · 对话式文书场景库

- 在运行页面 `http://127.0.0.1:8788/#documents` 核验 44 个场景、分类和搜索；搜索“押金”会命中房屋租赁合同、押金催告等相关场景。
- 使用临时本地账号实际点击“房屋租赁合同”：Agent 展示自然语言提问，页面无字段表单。输入虚构租赁事实后，界面显示 Word 下载、打印和编辑草稿入口；“我的文书对话”与“我的可编辑草稿”显示新记录。
- 临时验证账号和其草稿已从本地数据库清理。在线模型完整链路另用临时数据库验证了 DOCX 正文包含提供的姓名、地址和金额。截图：[场景库](document-library-ui.png)、[对话生成](document-chat-ui.png)。
- 退出账号后再次进入文书区，聊天内容、下载入口和本人列表均清空；下载接口仍按所有者校验。

## 2026-10-29 · 当前页面与模型链路

- README 展示的工作台、文书场景库、对话生成、法考专项和后台截图均为本地运行页面截图。
- 管理后台已通过浏览器验证：管理员登录后从头像菜单进入，侧边栏没有管理入口；页面显示求取、律师、站内消息、用户角色、文书模板和官方更新区域。
- `deepseek-flash` 在线模型经当前 `.env` 配置实际返回成功；缺少可选 DeerFlow 包时，法律工作台通过同一模型配置直连在线接口。匿名示例问题的 `/api/v1/agent/ask` 返回 200，`runtime=online_fallback`。
- 当前测试套件 13 项通过，`node --check web/app.js` 通过。本项目运行与验证没有启动 Ollama。
