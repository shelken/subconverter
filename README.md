# subconverter
## 简介
基于 [stilleshan/subconverter](https://github.com/stilleshan/subconverter) 配置修改

转移至 》[docker-images](https://github.com/shelken/docker-images/tree/main/apps/subconverter)

## TOML 外部配置说明

项目使用 subconverter 的**外部配置**（external config）定义策略组和规则集，将代理订阅转换为 Clash（mihomo）可用的 YAML。

主配置为 `config.toml`，`config.ini` 是历史 INI 格式配置，保留做对照，不再使用。

### 配置结构总览

外部配置分为三个部分：

```toml
version = 1
[custom]
enable_rule_generator = true
overwrite_original_rules = true

[[custom_groups]]
# ... 策略组定义

[[rulesets]]
# ... 规则集定义
```

### `[custom]` — 全局开关

| 字段 | 说明 |
|------|------|
| `enable_rule_generator` | 启用自定义分组和规则集。**必须为 true**，否则 `[[custom_groups]]` 不生效 |
| `overwrite_original_rules` | 用下方 `[[rulesets]]` 覆盖模板的默认规则 |

### `[[custom_groups]]` — 策略组

每定义一个 `[[custom_groups]]` 就是一个 Clash 策略组（proxy-group）。

```toml
[[custom_groups]]
name = "🔰 PROXY"
type = "select"
rule = ["[]🇭🇰 香港节点", "[]👻 SelfHost", ".*"]
```

**字段：**

| 字段 | 说明 |
|------|------|
| `name` | 策略组名称 |
| `type` | `select` — 手动选择 / `url-test` — 自动测速切换 |
| `rule` | 策略项列表，按顺序匹配（见下方） |
| `url` | url-test 类型专用：测速 URL |
| `interval` | url-test 类型专用：测速间隔（秒） |
| `tolerance` | url-test 类型专用：切换容忍值（ms） |

**`rule` 数组：**

数组每一项可以是以下两种之一：

1. **引用策略组**（以 `[]` 开头）— `[]🇭🇰 香港节点` 表示引用名为「🇭🇰 香港节点」的策略组
2. **节点名正则** — 直接写正则匹配节点 remark，如 `(vps|hy)` 匹配名称含 vps 或 hy 的节点；`.*` 是兜底，匹配所有节点

顺序即 Clash 客户端选择面板的显示顺序。

#### select 类型 — 手动选择

```toml
[[custom_groups]]
name = "🚫 AdBlock"
type = "select"
rule = ["[]REJECT", "[]🎯 DIRECT", "[]🔰 PROXY", ".*"]
```

Clash 中显示为下拉列表，用户手动选择。`[]REJECT` 是内置拦截策略。

#### url-test 类型 — 自动测速

```toml
[[custom_groups]]
name = "👻 SelfHost"
type = "url-test"
rule = ["(vps|hy)"]
url = "http://www.gstatic.com/generate_204"
interval = 120
tolerance = 50
```

匹配到的节点中按延迟自动选最快的。`tolerance` 字段是 TOML 的优势——INI 格式不支持（subconverter issue #553）。

#### 纯正则筛选组

```toml
[[custom_groups]]
name = "🇭🇰 香港节点"
type = "select"
rule = ["(香港|港|HK|Hong Kong)"]
```

从订阅中筛选出匹配节点，其他组可以通过 `[]🇭🇰 香港节点` 引用。

### `[[rulesets]]` — 规则集

决定哪些流量进入哪个策略组：

```toml
[[rulesets]]
group = "🚫 AdBlock"
ruleset = "https://raw.githubusercontent.com/shelken/subconverter/master/custom/MyReject.list"
```

| 字段 | 说明 |
|------|------|
| `group` | 流量流向的策略组名称（需与 `[[custom_groups]]` 对应） |
| `ruleset` | 规则集来源，可以是远程 URL、内建规则（`[]GEOIP,CN`、`[]FINAL`）或本地路径 |

优先级按 `[[rulesets]]` 声明顺序，自上而下。

### INI → TOML 对照

INI（旧）：
```ini
custom_proxy_group=🔰 PROXY`select`[]🇭🇰 香港节点`[]👻 SelfHost`.*
ruleset=🚫 AdBlock,https://example.com/list
```

TOML（新）：
```toml
[[custom_groups]]
name = "🔰 PROXY"
type = "select"
rule = ["[]🇭🇰 香港节点", "[]👻 SelfHost", ".*"]

[[rulesets]]
group = "🚫 AdBlock"
ruleset = "https://example.com/list"
```

核心变化：反引号分隔的各段变成 `rule` 数组的各个元素。

### 配置生效检查

修改后可以通过 API 验证：

```
GET /sub?target=clash&url=订阅URL&config=config.toml
```

或跑测试（需 Docker）：

```bash
bash tests/ini-to-toml/run-test.sh
```

测试用 `config.ini` 和 `config.toml` 分别生成 YAML 并比对，确认一致。详见 [tests/ini-to-toml/README.md](tests/ini-to-toml/README.md)。
