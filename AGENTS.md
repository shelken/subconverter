# AGENTS.md

## 配置语法查阅

- **subconverter 外部配置（TOML/INI）**：https://github.com/tindy2013/subconverter/blob/master/base/config/example_external_config.toml
- **mihomo 策略组**：https://wiki.metacubex.one/config/proxy-groups/
- **mihomo load-balance**：https://wiki.metacubex.one/config/proxy-groups/load-balance/

## 规则集来源

- **blackmatrix7**（Clash 规则）：https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash
- **NobyDa**（广告拦截）：https://github.com/NobyDa/Script/tree/master/Surge
- **自定义规则**：`custom/*.list`

## 注意事项

- `config.ini` 仅历史对照，不使用
- TOML 无锚点，复用正则用 `[]组名` 引用
- `load-balance` 的 `strategy` 仅 TOML 支持（INI 不支持，issue #553）
