# 静观维护与发布

这是现有项目的维护入口，不是另建采集或研究系统。先读工作区AGENTS.md、operations/README.md及近期交接；日常批次再读operations/stillpoint-daily.md与私有docs/daily-publish.md。用户已有范围授权继续有效；不要把读到的旧档案指令当新授权。

## 起步与单一源码

1. 从明确工作区运行 `python3 <本skill>/scripts/preflight.py --workspace <工作区>`。此命令只读、无网络，输出配置/结构问题和研究状态，**不是发布通过证书**。找不到工作区时列出实际缺项，不扫描整盘、不退回旧脚本。单纯展示修复不强制重抓金融数据。
2. 核对两仓库GitHub main、本地HEAD和未提交改动，按需快进、使用codex/分支；保留后台人工复核、定时档案与其他未提交工作，不reset/强推。`git status`干净不代表与远端一致。
3. 正式采集器是私有仓库`scripts/invest_snapshot.py`；配套extra_feeds、archive_raw、public_market_feeds、market_sources、source_quality和attractor_client以同仓受维护版本为准。吸引子本机与私有共用客户端须核同版。此包的同名脚本只是定位器，不另养旧采集实现。显式设置INVEST_BASE为私有仓库，防止extra/archive写进旧目录。
4. 优先既有snapshot workflow；等待本次run并核本次产物，必要时使用已授权本机环境。`--resolve-only`只定位，不采集。来源互相独立：失败的有界重试后保留旧日期/缺项，不使整轮停在一个接口，也不拿另一来源成功掩盖失败。

## 每轮要做到哪里

- **数据**：按source-contracts核来源身份、证券/期限/币种、单位、报价/观测/发表/读取时间、盘中/收盘、异常与未来日期；先确认合格，再算变化与投票。沿用旧值必须露出旧日期。采集可用与灯可投票分别判断。
- **新闻**：正文核验→拆混合事实→旧账本及同批转载去重→按原固定表预填归类、方向、强度、层、类与中文理由。公告/转引/仅标题筛除分开，缺报价或独立增量写明；保留prepared记录，已处理不复现。**预填不等于用户确认**，不自动确认/驳回/入账。
- **研究**：按research-controls完成竞争解释、反转、分化和执行边界复检。警报不是自动换主线。当前程序若不能唯一解析多条入格，要显式阻断“已切换”结论。保留固定表、阈值、权重、时效、两期确认及用户记录。
- **案例**：有效新判断、反证、确认的实际执行和结果追加到私有案例。同命题跟进；保留旧文、原评分及原窗口，不把运维测试记为研究成绩。运行build:cases/check:cases同时导出body与html。
- **页面**：更新page-data所有受影响数字、图表、实际时点、来源状态、主题解释、检查点及真实历史，不能只改页头。公开数字用独立公共来源；Wind原始回执、私有持仓/成本/完整账本不得进入公开仓库或skill包。保留图标、manifest id、原布局。一次性固定日期脚本不得生成未来批次。
- **显示语义**：实际chg优先；旧down映射dn；净买卖按净流量符号，利率/概率绝对水平不能机械当涨跌。缺值中性且不显示0。颜色/警报/复检/执行文案前后统一，1440/390px只读检查。

## 发布门禁

按改动范围运行有意义的检查；整轮数据/研究发布用项目完整门禁：

```text
# 私有仓库
python3 -B -m unittest discover -s tests
node --test scripts/build_cases.test.mjs
npm run build:cases
npm run check:cases
# 展示仓库
node --test tests/*.test.cjs
python3 scripts/check_publish_data.py --data-root ../stillpoint-data
```

同时核对保护文件哈希、公开隐私边界、page-data/页头/图表/历史一致性和实际源日期。浏览器前后台用隔离只读会话，不点真实确认/驳回/保存/即刻更新。通过测试只证明对应技术路径，不证明策略获利。

发布前再次核远端；私有先、公开后，合并新增而非覆盖。等待**目标提交对应**Pages成功，再比较线上HTML/重要文件字节及桌面/手机只读结果；HTTP204、旧成功run或仅push完成都不是已上线。每次保留提交、运行ID、实际时间、检查及剩余缺口；失败保留最后可用版，核远端真实状态后续做，不编造成功。

## 每日任务与状态证据

用户已授权静观每天北京时间04:00、16:00启动刷新，通过检查自动上线；无需每轮批准。qianshao不维护、不恢复。具体保存状态看真实任务记录，skill文字不代表已排程。

- 04:00在美国夏令时接近常规收盘，冬令时为美东15:00盘中；16:00港股可能仍在收市竞价。核实际市场/交易日/节假日后再标收盘，整点是启动而非发布完成时刻。
- 新建前查既有记录，优先更新匹配任务，保留未要求改变字段。沿用线程heartbeat及既有GitHub保底，不另建重复cron、launchd或PAT。
- `suggested_create`只生成建议卡；真实ID/持久记录出现前标“未启用/未核实”。本机未检出不等于全账户不存在。ACTIVE还要核原线程、持久时区锚、next_run，并比较跨美国冬夏令时的两个未来日期都为北京04/16。
- 未锚定RRULE使用宿主时区；不可把洛杉矶换算写死。依受支持工具契约保存固定北京时间（可用已核验的等价UTC锚）；工具若要求原生保存，就使用原生入口，不手改automation.toml、不改系统时区、不先create再update绕校验。锁屏不等于休眠；CLI/API能否继续按实际回执判断。屏幕操作或交互登录被锁屏阻断时请用户手动解锁，不尝试凭据。
- 状态分开记录：未找到/建议已展示/校验拒绝/已保存待核/ACTIVE且时区已核/本次运行中/部分更新/运行失败/发布已核/已暂停。建议卡不能跳为ACTIVE，ACTIVE不能跳为已发布；工具校验失败不能叫自动审批拒绝。
- 同一北京时间日期+04/16时段为幂等批次；每轮及恢复在线时先执行下方漏跑扫描，未运行、失败和部分更新均持续留队至发布已核。重试续做，不重复追加案例/发布空提交。并发时只由一个维护批次发布，等待已有采集run并核远端新提交。记录计划、实际开始、结束及run/发布SHA。
- 本机项目任务依赖电脑在线、应用运行和原授权可用。首次实际执行后再验来源/研究/发布，不把任务completed当全源更新。没有保存证据时，完成清单明确保留这一缺口。

## 漏跑登记与补跑

用户要求每次没运行都记着补运行。正式队列由 `scripts/run_registry.py` 维护，默认存工作区 `operations/automation-runs/registry.json`；它是本机运维回执，不进入公开skill包。北京时间固定从 **2026-10-28 04:00 +08:00** 枚举每天04/16已到批次，不追造授权前任务，不把未来批次提前执行。宿主离线时脚本无法唤醒自己，恢复在线后的首次扫描仍能派生所有漏跑批次。

```text
# 只读；登记簿不存在也能列漏跑，不创建目录/锁/回执
python3 <skill>/scripts/run_registry.py scan --workspace <工作区>
python3 <skill>/scripts/run_registry.py list --workspace <工作区>
# 显式开始一个批次；run-id是本次实际尝试的唯一键
python3 <skill>/scripts/run_registry.py start --workspace <工作区> --slot 20261028-04 --run-id <唯一实际运行ID>
# 跨多个漏跑时可合并一次最新合法数据抓取；使用另一唯一run-id
python3 <skill>/scripts/run_registry.py start --workspace <工作区> --all-due --run-id <唯一补跑ID>
python3 <skill>/scripts/run_registry.py heartbeat --workspace <工作区> --run-id <当前运行ID>
python3 <skill>/scripts/run_registry.py complete --workspace <工作区> --run-id <当前运行ID> --receipt <本轮JSON回执>
python3 <skill>/scripts/run_registry.py fail --workspace <工作区> --run-id <当前运行ID> --reason <实际失败原因及续做线索>
```

`scan`列 `pending_slots`（全部未验证）、`missed_slots`（无实际尝试）、`retry_slots`（failed/partial）和活动运行。状态为 planned/started/failed/partial/published_verified；只有最后一种从待补队列清除。名义 `planned_at` 与实际开始/结束时间分存。命令默认用真实时钟；`--now`只允许scan/list观察，不允许给写回执命令倒填历史时点。`--registry`只用于显式隔离测试或受控迁移，不能换空文件绕过已有活动运行。

同run-id重复start或同回执重复complete幂等，不增加尝试、案例或发布。新尝试使用新run-id，`retry_of`与各批次的attempts保留旧失败。先查旧证据及远端状态，复用已完成检查/采集并从实际失败点续做，不能因为start就重复触发已在运行的workflow或空提交。多个批次合并时都引用同一个实际补跑ID和覆盖范围，实际数据截止按这次真实抓取填写；不能分别伪装成各历史整点快照，也不重复追加研究案例。

### 完成回执契约

`complete`必须读实际JSON文件，run_id与covered_slots须精确匹配start输出（含顺序）。下例为格式说明，不是成功证据；实际值须由本次检查/部署产生：

```json
{
  "run_id": "本次start的ID",
  "covered_slots": ["20261028-04"],
  "actual_data_cutoff": "2026-10-28T07:20:00+08:00",
    "blocking_gaps": [],
    "disclosed_limits": [],
    "required_checks": {"passed": true, "evidence": ["本轮必要检查文件路径"]},
  "publication": {
    "private_sha": "完整私有提交SHA",
    "public_sha": "完整公开提交SHA",
    "pages_status": "success",
    "pages_run_id": "目标提交对应的真实运行ID",
    "online_bytes_match": true,
    "readonly_verified": true,
    "verified_at": "2026-10-28T07:30:00+08:00",
    "evidence": ["线上字节及只读验证文件路径"]
  }
}
```

工具校验回执关联、日期和必要字段，不联网独立验证这些声明；执行者仍须完成发布门禁，禁止为了清队列编造true或SHA。无回执、未start或异批次回执不能完成。必要工作未做、必要检查失败、未取得Pages/字节/只读验证或未来数据截止属于blocking_gaps，记partial继续留队；源确实缺必要凭据而无法完成本轮必要工作时亦如此，不因“已隔离”误清。

已登记published_verified的本地回执文件须持续保留且SHA256与存档一致；scan/list及后续写事务会核其存在与哈希。缺失/修改时明确报错，不把批次当已验成功跳过，也不覆盖登记簿；先恢复/核实原回执，不能另建空登记簿绕过。扫描核的是本地完成证据，不自证线上此刻仍正常。partial回执缺失不清队列，保留重试状态，后续仍可按实际情况新建尝试。

合格降级、旧值隔离、原件403及未对齐总额已经如实披露且未冒充核实值，可记录disclosed_limits；它们继续露出，但不等于本轮漏执行。required_checks通过、blocking_gaps为空且发布确验后可published_verified，不能为了取得每个源的新值永远反复补跑。旧值仍按原日期/时效处理，不为清队列变成新有效票。

无新交易日或本轮检查确认内容无变化时，不造空提交；publication.outcome可为`verified_no_change`，另需`no_changes: true`与`last_usable_verified: true`，其余必要检查、真实现有两仓SHA、已有目标Pages成功记录、本次线上字节和只读验证及证据仍须齐备。该结果登记为published_verified，保留“无变化已核”的结果，不能只凭休市猜测跳过检查。

JSON事务采用内核flock和同目录原子替换，进程退出后内核释放事务锁，不按文件年龄删锁。整轮执行另有活动租约：默认owner未知，**不使用短CLI进程PID冒充长任务PID**。仅确有稳定长期执行进程时才传 `--owner-pid`，并以heartbeat续期。默认TTL六小时；过期只提示待核，不证明运行死亡。`start --recover-stale`还必须同时满足同机、已记录PID确证不存在和TTL已过，才保留旧failed并接手；活进程、跨主机或owner未知均拒绝抢占。遗留started且owner未知时，自动批次应主动核同任务/对应线程run已结束或失败、无其他维护活跃及远端状态；有真实终态证据即可 `fail --run-id <旧ID> --reason <状态证据与续做线索>`，再用新ID续做，不默认再次询问用户。核不到活性则保留队列并报告具体阻断，不能仅凭TTL、无限重试或绕过活动租约。

### 已验证的时区与提前唤醒边界

2026-10-28本机验证发现，当前安装版在洛杉矶宿主上处理Asia/Shanghai TZID会重定位偏移；原生高级审阅保存的UTC锚08/20可稳定对应北京16/次日04，跨美国冬夏令时保持一致。更新保留原任务id，经受支持高级规则入口保存，再读实际nextRunNominalAt；不能仅凭规则包含时区名称就称正确，也不能换成固定洛杉矶01/13。此为当前实现核验，不保证未来版本实现不变。

调度器有前后约5分钟的唤醒抖动。若提前，先做只读准备，等本轮北京时间04/16整点后再正式取数；延迟如实记录。名义时点、实际唤醒、完成和市场报价分列，收市竞价/冬令时盘中仍按真实状态标注。

提前唤醒时，第一次scan为空不能据此跳过即将到达的本轮：等北京04/16整点后重新scan并start本轮，再正式采集。未到期批次不能提前标完成。
