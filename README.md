# K12 官方信源看板

[在线查看](https://xian492.github.io/k12-dashboard/)

北京 K12 信息入口与动态看板，每 6 小时自动更新，GitHub Pages 托管。

当前覆盖：

- 北京市教委、教育部及北京 18 个区的官方信息
- 区教委与学校动态
- 149 个学校官网或官方入口
- 学校及区级微信公众号 ID

学校官网和公众号仅作导航，不参与自动抓取或 RSS 生成。

## 本地构建

```bash
python3 tools/build.py
```

构建产物位于 `docs/`。

## 主要文件

```text
.github/workflows/build.yml  定时构建与 Pages 部署
tools/build.py               信源、学校目录与构建逻辑
docs/index.html              看板页面
docs/data.json               数据快照
```
