# 事实层：正式采集、来源和账本

静观维护先读maintenance.md；来源问题读source-contracts.md。下述地址/指标是定位线索，实际接口契约以已安装对应skill及正式项目源码为准，不复制旧鉴权逻辑。

## 正式项目入口

从包含stillpoint-data与stillpoint-pages的工作区，先只读预检：

```text
python3 <本skill>/scripts/preflight.py --workspace <工作区>
python3 <本skill>/scripts/invest_snapshot.py --workspace <工作区> --resolve-only
```

真正采集用既有snapshot workflow或该兼容入口（转给私有正式采集器）：

```text
python3 <本skill>/scripts/invest_snapshot.py --workspace <工作区> --days 2
```

支持正式脚本的days/topics/no-prices/no-watchlist/no-sectors/no-reports/compare/out参数；默认输出私有snapshots。compare为离线比较，输入使用明确路径。采集/额外源/归档/研究计算/公开page-data/发布是不同阶段，一次snapshot成功不等于全部更新。

不要使用旧`~/学习/auto/request.txt`或默认安装历史launchd脚本。项目源码中的auto脚本仅历史存档，不在新版下载包中、不表示本机已启用。当前任务、原始日期和发布状态分别查证。无正式私有项目时，预检清楚说明；通用研究仍可按可用skills/公共原件取数，不假装运行了项目维护。

## 来源导航

- ARGUS：沿用argus-research的免密只读接口与更正纪律。常用主题liquidity/ai-infrastructure/china/energy；日报、周报、作者观点分开。fullReport=false只说明摘要可得。宏观观测日期与报告发表日期独立，编辑百分数不等于预测胜率。精确ID从catalog/现行源码查，不凭旧文猜。
- 吸引子：由shifenxiyin-perspective及共享attractor_client读取。key只通过原已配置环境/私有文件使用，不打印、不入包、不另索要替代PAT。19项核心与扩展项覆盖不同；核本次quality、返回/缺失、未来与旧日期，各灯另判合格票。
- 行情：正式market_sources与public_market_feeds；交易所原始日线优先，东财/Yahoo/新浪标行情接口，日期与市场状态按每只标的返回值。ETF前收依日期对齐，不能误算两日涨跌。
- A股全市场成交量/成交额/涨跌家数需明确板块覆盖和单位，不用上证+深证代理声称完整全A；Arms/TRIN=(上涨家数/下跌家数)/(上涨成交量/下跌成交量)，成交量口径不能偷换成交额，零分母缺值。
- 公告与报道：原公告优先，媒体转引标转引，共同原件只算一次。新闻盘中估数不覆盖同日完整收盘。原件被拒绝访问时使用合法可读转引/镜像并标限制，有界重试。

## 指数读法

吸引子正负号按**该指标自身语义**解释：资金利率正为钱贵，货币政策倾向正为偏松，不能统一正=利好。state/stateChange保留原文；“预警”含义如无独立定义标推断并查硬数据。

绝对值只说明归一化指数位置/幅度。旧强/中/边沿标签可作界面幅度描述，不能解释成底层同向占比或预测置信度；−1也不代表100%预测收缩。日期可用不证明因果，stateChange不单独证明拐点已获证。

## 账本

| 项目/证券身份 | 数值和单位 | 观测/报价期 | 发表/读取时点及时区 | 同口径变化 | 来源与核验状态 |
|---|---|---|---|---|---|

缺值不是零、重读旧观测不变新。未来/过旧/invalid不得伪装当前票；unverified/report-only作背景。量价、存量流量、年化单期、估算实测分开。ARGUS change是自身单位差，非涨跌幅。只把3–5条决定性证据写进结论，其余为背景/反方/路标；来源阻断与投资信号分开显示。

网络失败先核错误类型、官方来源和既有授权通道，读取最近有效日期可降级；不擅自改网络权限/安装任务/导出凭据。公开回执与私有Wind边界按maintenance执行。
