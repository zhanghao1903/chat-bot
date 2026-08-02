# 乐枝 v0.3 候选资产确认单

- 状态：等待用户单独确认
- 候选清单 SHA-256：`1dd20aeca66a5f6cc0cc6ac5f952593abc418cd9b8fab60ce140239fb2224e5b`
- 48 条语义目录 SHA-256：`bd85f2a6ead7943d2504d3e5203ddb54e35aa3e91446b8f5743c9ba28372f3cd`
- 头像目录 SHA-256：`abd8aa18ab295cb261d7610daabf6650e82de8c5640855c51755de0d5c25f4ea`
- 当前生产状态：全部 `candidate`；未上传、未映射、未启用；自动头像轮换关闭

## 逐组预览

- [全部 48 枚联系表](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/previews/contact-all.png)
- [A 组浅色联系表](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/previews/contact-a.png)
- [B 组浅色联系表](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/previews/contact-b.png)
- [C 组浅色联系表](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/previews/contact-c.png)
- [规范目录 JSON](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/catalog.json)：含每枚 `use_when`、`avoid_when`、母版/WebP 摘要和来源格

每枚还有 `previews/light/<坐标>.png` 与 `previews/dark/<坐标>.png`，用于检查透明边缘、白帽、
白衣、文案和相邻格污染。确认时可以批准全部 48 枚，也可以明确给出语义 ID 子集。

## 48 条目录摘要

| 格 | 稳定语义 ID | 文案 | 独立内容摘要 | 意图 | 最低关系 | Emoji |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | `lezhi.hello_wave.a01` | 嗨～ | 挥手问候，以明快表达“嗨～” | greeting | public | 👋 |
| A02 | `lezhi.acknowledged.a02` | 收到 | 比出确认手势，以可靠表达“收到” | acknowledge | public | 👌 |
| A03 | `lezhi.listening.a03` | 我在听 | 侧耳倾听，以专注表达“我在听” | listen | public | 👂 |
| A04 | `lezhi.quietly_caring.a04` | 有点在意 | 轻声关心，以在意表达“有点在意” | care | familiar | 💙 |
| A05 | `lezhi.thinking.a05` | 让我想想 | 托腮思考，以思索表达“让我想想” | think | public | 🤔 |
| A06 | `lezhi.approving.a06` | 这个不错 | 竖起拇指，以认可表达“这个不错” | approve | public | 👍 |
| A07 | `lezhi.laughing.a07` | 笑死我了 | 捂嘴大笑，以欢乐表达“笑死我了” | amuse | familiar | 😂 |
| A08 | `lezhi.cheering.a08` | 冲呀 | 挥拳加油，以振奋表达“冲呀” | encourage | public | 💪 |
| A09 | `lezhi.apologetic.a09` | 抱歉呀 | 合掌道歉，以歉意表达“抱歉呀” | apologize | public | 🙏 |
| A10 | `lezhi.curious_huh.a10` | 嗯？ | 歪头疑问，以好奇表达“嗯？” | clarify | public | ❓ |
| A11 | `lezhi.calming.a11` | 先别急 | 抬手安抚，以沉着表达“先别急” | calm | public | 🫶 |
| A12 | `lezhi.checking.a12` | 查一下 | 拿出平板查询，以认真表达“查一下” | investigate | public | 🔎 |
| A13 | `lezhi.celebrate_open_arms.a13` | 好耶 | 张开双臂庆祝，以雀跃表达“好耶” | celebrate | public | 🎉 |
| A14 | `lezhi.appreciation.a14` | 辛苦啦 | 合掌致谢，以温暖表达“辛苦啦” | appreciate | public | 🌷 |
| A15 | `lezhi.good_night.a15` | 晚安 | 抱着海豚入睡，以安宁表达“晚安” | sleep | familiar | 🌙 |
| A16 | `lezhi.cuddle_dolphin.a16` | 贴贴 | 拥抱海豚贴近，以亲昵表达“贴贴” | affection | close | 💞 |
| B01 | `lezhi.smug_hmph.b01` | 哼哼 | 抱臂轻哼，以得意表达“哼哼” | tease | familiar | 😏 |
| B02 | `lezhi.playful_guess.b02` | 你猜 | 眨眼卖关子，以俏皮表达“你猜” | tease | familiar | 😉 |
| B03 | `lezhi.tongue_tease.b03` | 略略略 | 吐舌做鬼脸，以淘气表达“略略略” | tease | close | 😝 |
| B04 | `lezhi.feigned_cool.b04` | 装一下 | 闭眼摆姿态，以自得表达“装一下” | style | familiar | ✨ |
| B05 | `lezhi.confident_got_it.b05` | 拿捏了 | 自信指向前方，以笃定表达“拿捏了” | confidence | public | 😎 |
| B06 | `lezhi.grand_entrance.b06` | 本小姐登场 | 张开双臂登场，以张扬表达“本小姐登场” | greeting | familiar | 🌟 |
| B07 | `lezhi.elegant_tea.b07` | 优雅 | 端杯品茶，以从容表达“优雅” | style | public | ☕ |
| B08 | `lezhi.watching_drama.b08` | 看戏 | 躲在帘后围观，以好奇表达“看戏” | observe | familiar | 👀 |
| B09 | `lezhi.bashful_giggle.b09` | 嘻嘻 | 捂嘴偷笑，以甜美表达“嘻嘻” | amuse | familiar | 🤭 |
| B10 | `lezhi.carefree_play.b10` | 别管我啦 | 抱着海豚玩闹，以自在表达“别管我啦” | tease | familiar | 🐬 |
| B11 | `lezhi.knowing_point.b11` | 懂了吧 | 眨眼比出手势，以机灵表达“懂了吧” | acknowledge | familiar | 💡 |
| B12 | `lezhi.mock_profound.b12` | 高深 | 托腮故作深沉，以装深沉表达“高深” | tease | familiar | 🧐 |
| B13 | `lezhi.mock_annoyed.b13` | 不许笑 | 抱臂脸红，以羞恼表达“不许笑” | boundary | familiar | 😤 |
| B14 | `lezhi.flustered.b14` | 哎呦喂 | 慌张伸手，以惊慌表达“哎呦喂” | react | public | 😵 |
| B15 | `lezhi.just_kidding.b15` | 骗你的 | 眨眼做噤声手势，以顽皮表达“骗你的” | tease | familiar | 🤫 |
| B16 | `lezhi.mischievous_cuddle.b16` | 欠欠的 | 坏笑抱海豚，以欠揍式俏皮表达“欠欠的” | tease | close | 😼 |
| C01 | `lezhi.startled_question.c01` | 啊？！ | 捧脸惊叫，以惊讶表达“啊？！” | react | public | 😲 |
| C02 | `lezhi.wait_stop.c02` | 等等 | 伸手叫停，以急切表达“等等” | boundary | public | ✋ |
| C03 | `lezhi.shocked_blank.c03` | 震惊 | 瞪大眼睛僵住，以震撼表达“震惊” | react | public | 😳 |
| C04 | `lezhi.devastated_cry.c04` | 我裂开了 | 大哭崩溃，以崩溃表达“我裂开了” | distress | familiar | 😭 |
| C05 | `lezhi.frightened.c05` | 别吓我 | 后退摆手，以受惊表达“别吓我” | react | public | 😨 |
| C06 | `lezhi.absurd_point.c06` | 离谱 | 指向荒唐之事，以难以置信表达“离谱” | skepticism | familiar | 🙃 |
| C07 | `lezhi.pouting.c07` | 气鼓鼓 | 抱臂生闷气，以不满表达“气鼓鼓” | boundary | familiar | 😠 |
| C08 | `lezhi.crying.c08` | 呜呜 | 捂嘴落泪，以委屈表达“呜呜” | distress | familiar | 🥺 |
| C09 | `lezhi.skeptical.c09` | 真的假的 | 托腮质疑，以怀疑表达“真的假的” | skepticism | public | 🤨 |
| C10 | `lezhi.overloaded.c10` | 脑袋宕机 | 眼冒圈圈停机，以混乱表达“脑袋宕机” | confuse | public | 🌀 |
| C11 | `lezhi.calling_help.c11` | 救命 | 伸手求救，以慌乱表达“救命” | rescue | familiar | 🛟 |
| C12 | `lezhi.celebrate_fist.c12` | 好耶 | 握拳欢呼，以兴奋表达“好耶” | celebrate | public | 🙌 |
| C13 | `lezhi.intense_stare.c13` | 盯—— | 趴桌凝视，以专注表达“盯——” | observe | familiar | 👁️ |
| C14 | `lezhi.firm_boundary.c14` | 不许这样 | 交叉双臂拒绝，以严肃表达“不许这样” | boundary | public | 🙅 |
| C15 | `lezhi.dizzy.c15` | 我晕 | 眼冒圈圈发晕，以眩晕表达“我晕” | confuse | public | 😵‍💫 |
| C16 | `lezhi.warm_hug.c16` | 贴贴 | 开心拥抱海豚，以温柔亲近表达“贴贴” | affection | close | 🫂 |

## 头像候选

| 头像 ID | 来源 | 允许心情 | 圆形预览 | 生产状态 |
| --- | --- | --- | --- | --- |
| `lezhi-default` | Character Visual Bible 正面头像裁切 | default | [预览](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/avatars/lezhi-default-circle.png) | candidate |
| `lezhi-joyful` | A13 | joyful / celebratory | [预览](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/avatars/lezhi-joyful-circle.png) | candidate |
| `lezhi-playful` | B03 | playful / mischievous | [预览](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/avatars/lezhi-playful-circle.png) | candidate |
| `lezhi-pouty` | C07 | pouty / mildly_annoyed | [预览](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/avatars/lezhi-pouty-circle.png) | candidate |
| `lezhi-gentle` | A04 | gentle / caring | [预览](../../../../src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/avatars/lezhi-gentle-circle.png) | candidate |

需要分别确认：默认头像裁切；允许进入集合的心情头像；每个 mood 映射；是否启用自动轮换。
确认头像不等于确认表情生产子集，确认表情也不自动授权修改公开头像。
