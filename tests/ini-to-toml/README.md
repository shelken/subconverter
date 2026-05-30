# ini-to-toml 转换验证测试

验证 subconverter 的 `.ini` 和 `.toml` 两种外部配置格式能输出完全一致的 Clash YAML。

## 目录结构

```
项目根/
├── config.ini          # 当前使用的 INI 格式配置（基线）
├── config.toml         # 1:1 转换后的 TOML 格式配置
└── tests/ini-to-toml/
    ├── README.md       # 本文件
    ├── run-test.sh     # 自动化测试脚本
    └── test_sub.txt    # 测试节点订阅（base64 编码的标准 SS 格式）
```

## 设计思路

INI 和 TOML 配置都挂载到同一个 subconverter 容器，请求相同的测试订阅，比对两次 Clash YAML 输出。

```
config.ini ──┐                    ┌── output.ini.yml
             ├─► subconverter ─→ Clash YAML
config.toml ─┘                    └── output.toml.yml
                   │
                   ▼
          diff output.ini.yml output.toml.yml
          ✅ MD5 一致 = 转换正确
```

## TOML 转换注意事项

- **`version = 1` 必须写在文件首行**，否则 subconverter 自带的 TOML 解析器报 `Duplicate section`
- `[[custom_groups]]` 数组表对应 INI 的 `custom_proxy_group=` 每行，字段对照：
  - `rule` 数组：INI 中反引号分隔的所有段（含 `[]` 前缀策略引用和正则），直接作为数组元素
- `[[rulesets]]` 对应 `ruleset=` 每行，`group` 为分组名，`ruleset` 为 URL 或 `[]GEOIP,CN`、`[]FINAL`
- `[custom]` 下放 `enable_rule_generator = true` 和 `overwrite_original_rules = true`

## INI → TOML 字段映射示例

INI:
```
custom_proxy_group=🔰 PROXY`select`[]🇭🇰 香港节点`[]👻 SelfHost`.*
```

TOML:
```toml
[[custom_groups]]
name = "🔰 PROXY"
type = "select"
rule = ["[]🇭🇰 香港节点", "[]👻 SelfHost", ".*"]
```

url-test 类型：
```
custom_proxy_group=👻 SelfHost`url-test`(vps|hy)`http://www.gstatic.com/generate_204`120,,50
```
→
```toml
[[custom_groups]]
name = "👻 SelfHost"
type = "url-test"
rule = ["(vps|hy)"]
url = "http://www.gstatic.com/generate_204"
interval = 120
tolerance = 50
```

## 运行

```bash
# 默认端口 25500
bash tests/ini-to-toml/run-test.sh

# 指定端口（避免冲突）
PORT=25501 bash tests/ini-to-toml/run-test.sh
```

## 前置条件

- Docker
- 镜像：`asdlokj1qpi23/subconverter:0.9.9`（首次运行自动拉取）
- 网络：需从 `raw.githubusercontent.com` 下载远程规则集（约 20+ 个 .list 文件）
