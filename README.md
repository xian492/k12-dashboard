# K12 官方信源看板

[在线查看](https://xian492.github.io/k12-dashboard/)

北京 K12 信息入口与动态看板，每 6 小时自动更新，GitHub Pages 托管。

当前覆盖：

- 北京市教委、教育部及北京 18 个区的官方信息
- 区教委与学校动态
- 149 个学校官网或官方入口
- 学校及区级微信公众号 ID

学校名称可点击进入对应官网；没有独立官网的学校，保留区政府或教委的官方目录入口。

学校动态只从已确认的学校官网和区级官方信源抓取。区政府目录仅用于导航，不作为具体学校的抓取地址；微信公众号 ID 仅供人工检索，不参与自动抓取或 RSS 生成。

## 本地构建

```bash
python3 tools/build.py
```

构建产物位于 `docs/`。

## 社区信源工作区

论坛、家长社区和地方生活论坛的采集与分析独立放在 [`community/`](community/)，不参与官网看板构建。

## 主要文件

```text
.github/workflows/build.yml  定时构建与 Pages 部署
tools/build.py               信源、学校目录与构建逻辑
tools/school_crawler.py      学校官网动态抓取与链接筛选
docs/index.html              看板页面
docs/data.json               数据快照
docs/school-crawler-health.json  学校官网抓取状态
```
