---
version: alpha
colors:
  background: "#F5F8FC"
  surface: "#FFFFFF"
  ink: "#142B43"
  muted: "#61748B"
  line: "#DDE7F0"
  brand: "#2679D8"
  primary: "#176EC6"
  brandDeep: "#145CB3"
  brandSoft: "#E6F1FC"
  aqua: "#DAF3F4"
  success: "#26785B"
  warning: "#9B6A16"
typography:
  display:
    fontFamily: "'Noto Serif SC', 'Songti SC', 'STSong', serif"
  body:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif"
  data:
    fontFamily: "'SFMono-Regular', 'Cascadia Code', monospace"
rounded:
  panel: "22px"
  control: "12px"
  pill: "999px"
spacing:
  unit: "4px"
  panel: "24px"
components:
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
  primaryAction:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
---

## Overview

法寻面向第一次处理法律问题的公众，同时容纳律师和信息提供者。主界面是安静的法律服务工作台，首页让用户把问题交给 Agent，再沿“依据—步骤—文书—人工服务”继续。视觉签名是浅蓝流线，表达从问题到可核验路径的引导；不使用法槌、天平等刻板图形做主要标识。

## Colors

背景为带蓝灰的白 `#F5F8FC`，卡片纯白。蓝色表示可行动与可点击，绿色表示已核验状态，金色表示报酬或待处理提醒。认证标签同时写出文字和核验主体，不能只靠颜色。

## Typography

大标题用克制的宋体来承载公共服务的正式感，操作与正文用清晰的无衬线字体。数据、编号可用等宽字体。中文优先，不依赖远端字体加载。

## Layout

桌面为 232px 左侧导航和主内容双栏；首页 Agent 入口占首屏视觉中心。信息求取页采用列表和右侧说明。移动端导航收敛为顶部可横向滚动入口，卡片单列。卡片间距 16–20px，内容上限 1420px。

## Elevation & Depth

只用细边框和很轻的蓝灰阴影区分层级。信息密集页面优先留白和边界，避免浮层过多。

## Shapes

面板 22px，控件 12px，标签胶囊形。流线只用于背景，不能降低文字对比度。

## Components

按钮、输入、标签、来源卡、列表卡、侧栏在 `web/styles.css` 与 `web/extra.css` 以 `:root` token 落地。法考目录使用淡紫色图标区分学习场景，仍沿用统一卡片和搜索控件。表单错误保留输入值并紧贴字段提示；空结果提供清除筛选。蓝色实心按钮只给当前区域主操作。

## Do's and Don'ts

- 展示来源机构、更新日期、效力状态和“示例数据”标记。
- 让免费入口先于付费入口，收费信息明示报酬与付款状态。
- 不用“官方认证”称呼平台自身核验。
- 不用 AI 生成的虚构法条、案例编号或承诺性的胜诉表述。
