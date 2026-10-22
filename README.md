# K12 官方信源看板

**在线地址**：https://xian492.github.io/k12-dashboard/

监控北京 K12 官方信源的自动看板，GitHub Actions 每 6 小时拉取一次，GitHub Pages 托管。

## 信源（20 路）

- 市级（2）：北京市教委通知公告、教育部公告公示
- 区级（18）：北京义务教育入学服务平台（yjrx）全区招生政策

构建逻辑：`tools/build.py` 直接拉各信源原始接口（yjrx JSON / 官网列表页解析），零第三方依赖，生成 `docs/index.html`。

## 本地开发

```bash
python3 tools/build.py   # 生成看板，浏览器打开 docs/index.html
```

## 结构

```
.github/workflows/build.yml   # 定时构建 + 部署 Pages
tools/build.py                # 构建脚本（纯标准库）
docs/index.html               # 看板产物
docs/data.json                # 数据快照（留痕/回溯）
```
