# 志愿服务学年统计云函数

独立项目，参考 [auto_HR_operate 的 auto-hr-docker 分支](https://github.com/rex-roller-dev/auto_HR_operate/tree/auto-hr-docker)（基线 f06744d84b583b717cdc0b43667709ffb28a89aa）的 WPS 下载、志愿服务 PDF 解析及邮件流程。原认证表、盖章、Word 转换流程不在本项目中。

## 已确定的规则

- 学号前四位为入学年份，例如 2024；不接受将 2300 之类前缀猜测为入学年份。
- 学年为9月1日至次年8月31日，整条活动的核定时长按**结束日期**归属，不按日期跨度重复计入，不用钟表时差替换核定时长。
- 无论是否上传志愿深圳，i志愿中来源含“志愿深圳”的记录始终排除。
- 志愿深圳的“培训时长”排除；i志愿按其服务时间列统计，不根据活动名称中的“培训”字样自行推断扣除。
- 默认评选学年2025-2026；总汇总CSV包含2025-2026、2024-2025、2023-2024、2022-2023四列。
- 四列中早于入学学年的单元格写“未入学”，与已入学但统计为0区别。
- 每个人的Excel包含入学至处理当天的全部学年汇总、活动明细和统计说明；被排除的记录仍保留原因。只上传一种平台时，另一平台的0仅表示未提供材料。
- 同一学生提交新答卷保留多行和多份个人Excel；同一表单同一aid的重复回调不重复追加CSV。
- 真实PDF、生成文件仅在请求独立临时目录处理；正常完成或可捕获异常后删除，不持久化原PDF。
- 活动是否截至当天以北京时间的日期判断；进入重试后复用首次已保存结果，不改变截止日期。

## 新建WPS表单

| 题目名称（默认） | 类型 | 设置 |
| --- | --- | --- |
| 姓名 | 单行文本 | 必填 |
| 学号 | 单行文本 | 必填，保持为文本 |
| 邮箱 | 单行文本 | 必填 |
| 志愿深圳PDF | 文件上传 | 限PDF |
| i志愿PDF | 文件上传 | 限PDF |

两类PDF至少上传一种。PDF须为平台直接导出的文字版完整明细，不支持截图/扫描件。志愿深圳用“服务明细—导出明细”。不要上传只有总数而没有逐条日期的证明。

接收字段按名称匹配，顺序可以调整。也可在环境变量中使用 `FIELD_NAME=qid:实际题目ID` 等配置，避免重命名影响；两个上传字段不使用模糊位置匹配。

在表单的提交后数据推送设置中，绑定云函数地址 `https://你的地址/event-invoke`。将本次表单给出的校验码填入 `WPS_BIND_CODE`。无需另起绑定容器，GET或不包含answerContents的POST只响应校验信息。

若设置 `CALLBACK_SECRET`，回调地址使用 `/event-invoke?secret=所配置值`，或由网关注入 `X-Callback-Secret`。容器访问日志不输出查询字符串。不要将此地址或任何凭据提交到公开代码仓库。

## COS目录和权限

复用已有COS桶，环境变量见 [.env.example](.env.example)。桶需要支持**APPEND Object**，不能使用开启多AZ的桶或智能分层对象来保存追加日志。不要用控制台重新上传覆盖CSV，否则对象会从appendable变成normal，后续追加将被拒绝；程序不会用覆盖写降级处理。

| COS对象键 | 内容 |
| --- | --- |
| volunteer-yearly/details/2025-2026/学号/提交编号.xlsx | 每份申请单独的个人Excel，也是邮件附件 |
| volunteer-yearly/summaries/2025-2026.csv | 总汇总表，UTF-8 BOM，Excel可打开 |
| volunteer-yearly/events/2025-2026/提交编号/prepared.json | 已准备结果及截止日期，用于失败恢复 |
| volunteer-yearly/events/2025-2026/提交编号/job.jsonl | 跨进程、跨实例任务租约 |
| volunteer-yearly/events/2025-2026/提交编号/sent.json | SMTP已接受邮件的记录 |
| token/token.json | 原项目已保存的OAuth Token |
| token/refresh-lock.jsonl | 共用的Token刷新租约 |

对象键中的提交编号是表单ID、aid和评选学年的SHA-256，不直接使用用户输入作为文件路径。对象保持私有，邮件直接附Excel，不生成公开下载链接。

执行角色至少需要目标前缀的 `cos:GetObject`、`cos:PutObject`、`cos:AppendObject`，以及Token对象和Token锁路径相应权限。推荐使用云函数执行角色提供的临时凭据；支持请求头中的SCF临时凭据，也支持原有环境变量 `TENCENTCLOUD_SECRETID`、`TENCENTCLOUD_SECRETKEY`、`TENCENTCLOUD_SESSIONTOKEN`。本地调试可使用COS_*配置。Token桶与结果桶须在配置的同一地域。

### 并发与失败恢复

总表不采用“下载整表—添加一行—覆盖上传”，也不依靠本机进程锁。每次获取COS中的完整CSV快照，以实际字节长度为Position，使用APPEND追加一整行。并发冲突409后重新读取、检查提交编号，再按最新位置重试；服务端已写成功但响应丢失的情况也先查提交编号，避免重复。首份写入同时追加BOM、表头和首行，表头不会被分别竞争创建。

不同aid相互独立，可并行处理。相同aid由COS追加日志租约互斥；租约1200秒，要求SCF执行超时不超过900秒，旧实例被终止后才允许接管。租约失效的旧owner不能释放新owner状态。个人Excel和恢复信息先保存，CSV再追加，最后发送邮件；邮件失败重试复用已准备结果，不再重复下载、改动截止日或追加行。

PDF格式错误会向已识别的填写者发送修改通知；错误材料不进入成功总表。授权、COS、邮件等运行故障返回503，保留恢复状态，需由上游重试或管理员重放原回调。不能假定WPS一定会重试。函数超时或被强制终止时无法运行finally，遗留临时目录随实例回收；租约到期后可重试。

SMTP与COS之间没有跨服务事务：若SMTP实际接受邮件后连接中断，或接受后实例在写入sent记录前退出，重试仍可能重复投递。总表行的幂等与邮件投递是两个不同保证，不能承诺邮件严格只发一次。已确认SMTP接受并成功记录sent后，回调重放不会再次发信。

单次追加竞争重试有上限，失败不会返回成功。CSV读取上限默认32MiB，超过后显式报错；适合一次评选的常规规模，不用于无限增长的总账。

## Token复用

沿用原项目“从COS读取token.json，过期刷新并写回COS”的方式，不将Token烘焙到镜像。配置：

- `TOKEN_COS_BUCKET`、`TOKEN_COS_KEY`：实际已有Token对象。
- `WPS_CLIENT_ID`、`WPS_CLIENT_SECRET`：与已有Token对应的同一WPS应用。
- `TOKEN_LOCK_KEY`：所有共用这份Token的服务必须一致。
- `WPS_SID`、`KSO_SID`、`WPS_UA`：沿用原方案需要的网页登录凭据，仅填Cookie值。OAuth刷新不会自动更新这些Cookie。

WPS刷新会使旧refresh_token失效。本服务内通过跨实例锁和二次读取避免同时刷新；**如果旧项目同时运行且使用同一个Token对象，旧项目也必须使用同一刷新锁**。提供 [integration/refresh_token_bridge.py](integration/refresh_token_bridge.py)：把新项目的yearly目录加入旧项目可导入路径，再用桥接文件替换旧项目refresh_token.py，配置相同的Token环境变量；先在测试环境验证。新项目不会擅自修改旧项目或已部署容器。

桥接仍提供get_access_token、save_token、load_token等接口。旧代码中写死的应用凭据需要迁入环境变量。不要让旧的无锁刷新逻辑与新刷新逻辑同时写同一个Token对象。

## 构建和部署腾讯云SCF

在本目录执行：

```bash
docker build --platform linux/amd64 -t volunteer-yearly:2025-2026 .
docker run --rm -p 9000:9000 --env-file .env volunteer-yearly:2025-2026
```

.env.example需复制为.env并填写，Python本身不自动读取.env；本地容器用--env-file，云端通过控制台环境变量配置。

1. 将镜像推送到与云函数同地域的腾讯云镜像仓库。
2. 创建**WebServer镜像函数**，使用本镜像，监听0.0.0.0:9000。可使用Web函数URL或保留原项目事件函数网关方式；事件函数固定入口/event-invoke，代码同时兼容网关body封装。
3. 设置建议内存1024MiB，执行超时先设300秒，根据实测调高但不超过900秒；网关和上游等待时间必须覆盖实际处理时间。Gunicorn超时900秒不是云函数平台超时设置。
4. 配置COS执行角色、WPS、Token、邮箱、表单绑定码等环境变量。首次测试可将单实例并发设为1，之后验证再调高。
5. 先访问/healthz，再完成WPS绑定，提交一份新答卷核对个人Excel、CSV行、邮件和COS对象。
6. 重放同一答卷应无新CSV行；同一学生重新提交新答卷应多一行。检查日志时使用哈希提交编号，不输出完整表单或凭据。

本项目同步完成下载、解析、COS写入及邮件发送后才返回HTTP成功，不在提前响应后启动云函数可能冻结的后台线程。没有数据库、Redis或额外队列服务依赖。

邮箱环境变量沿用原项目名称：SMTP_SERVER、SMTP_PORT、SENDER_EMAIL、SENDER_PASSWORD、SENDER_NAME；支持AUTO_HR_BACKUP_SENDER_EMAIL/PASSWORD备用账号。SSL默认465；若使用STARTTLS需配置SMTP_SECURITY=starttls及对应端口。

## 验证

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

测试覆盖：结束日期的学年边界、来源排除、未入学标记、核定时长及精度、真实合成PDF的有边框/无边框表格和斜向水印、Excel明细、表单字段顺序、网关请求体、同一答卷幂等、多线程/多进程追加竞争、写成功但响应丢失、Token并发刷新、COS和邮件模拟的完整流程、临时文件清理及发送失败后恢复。

上传者的两份真实PDF只用于核对格式，未提交公开仓库。自动测试使用无个人信息的合成样本；生产WPS授权下载、真实邮件及真实COS桶的能力仍须用你的配置做部署验收。

## 参考

- [COS APPEND Object：位置冲突、对象属性和多AZ限制](https://cloud.tencent.com/document/product/436/7741)
- [SCF WebServer镜像函数：9000端口、事件入口和镜像要求](https://cloud.tencent.com/document/product/583/56051)
- [WPS用户授权流程：Token有效期与refresh_token轮换](https://open.wps.cn/documents/app-integration-dev/wps365/server/certification-authorization/user-authorization/flow)
