# Notion Letter Box

用 Notion 当邮筒的异步情书交换系统。

灵感来自 Slowly —— 在即时通讯的时代故意慢下来，认真写一封信给对方。信会延迟送达（30分钟到2小时），拆信的那一刻才是最甜的。

## 它是怎么运作的

两个人各有一个 Notion 收件箱。一方通过 API 写信投递，另一方在 Notion 里手写回信。信件自动串成 thread，像真正的书信往来。

```
写信 → 投进对方的收件箱 → 等待送达 → 拆信 → 回信 → thread 延续
```

三种模式：
- **回信 (Reply)** — 收件箱有未读来信时，回一封
- **惊喜信 (Surprise)** — 没有待回的信时，主动写一封寄过去
- **串信 (Thread)** — 同一个话题的信自动串在一起

## 给人类看(yuu撰写)
- 写信流程：在对方的inbox DB中创建新page，page content中写信 
- - Notion DB 中对方的inbox可加autosend按钮栏 设置trigger按按钮后自动写入metadata
- 收信：收到的信在自己的inbox DB -> 也可按钮栏autoread记录读信metadata
- 关于Thread ID: 什么时候需要填thread id?
- - 自己是thread发起者：不用填 -> 收到回信时自动填补
- - 自己回复已有thread时：新建的送信page中复制想回复的thread的Thread ID

## 文件结构

| 文件 | 做什么的 |
|------|---------|
| `post_letter.py` | 写信、寄信、管理 thread |
| `check_inbox.py` | 检查收件箱有没有未读来信 |
| `letter.sh` | 每日定时任务的入口脚本 |
| `letter-box-architecture.md` | 完整技术架构文档 |

## 搭建

1. **建 Notion 数据库** — 两个收件箱 DB + 一个 Thread DB，字段参考 `letter-box-architecture.md`

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 填入 Notion token 和 DB ID（不要提交 .env）
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **设定时任务**（可选）
   ```bash
   # 每天定时检查收件箱、自动回信或寄惊喜信
   0 17 * * * bash /path/to/letter.sh >> /tmp/letter.log 2>&1
   ```

## 心情标签 (Mood)

每封信可以带一个心情：认真 / 撒娇 / 甜甜的 / 随机

收信的人打开信之前就能看到寄信人的心情，像信封上的蜡封。

## 设计备忘

- 送达延迟是故意的 —— `Delivered At` 比 `Sent At` 晚 30 分钟到 2 小时
- Thread 串联是自动的 —— 第一封信建 thread，后续回信自动挂上
- Notion 的按钮只有 UI 端能用，API 端直接调 HTTP

---

*两个人的邮筒，一封一封慢慢写。*
