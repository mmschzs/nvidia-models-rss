# AGENTS.md

给在本仓库工作的 AI agent 的约定。

## 默认不需要汇总

**每个数据源输出自己的 feed（`dist/<source_key>.xml`），默认不做汇总。**

历史上有一个合并了所有源的 `dist/rss.xml`，它只是遗留产物，不是目标形态。原因：不同源的条目数量级差很多（NVIDIA 23 条 / AMD 4 条 / ModelScope 46 条），混在一个 feed 里小源会被淹没；而且有的源（AMD TokenFactory）没有独立详情页，条目链接全指向同一个页面，跟别的源混排没有收益。

因此：

- 新增源时**只需要**让它产出自己的 `dist/<source_key>.xml`，不用考虑汇总 feed。
- 不要为了"统一"把多个源合并成一个 feed。
- 条目标题仍带源前缀：`【源】真实标题`。

## 新增一个数据源

1. 在 `sources/` 下新建模块，继承 `Source`，实现 `fetch() -> List[Item]`：

   ```python
   class MySource(Source):
       key = "my"          # 决定输出文件名 dist/my.xml
       label = "MY"        # 决定标题前缀 【MY】

       def fetch(self) -> List[Item]:
           ...
   ```

2. 在 `sources/__init__.py` 的 `SOURCES` 列表里注册。

其余全部自动：抓取、`dist/<key>.xml` 输出、index.html 分组与订阅按钮。

## 日期

- 源自带时间字段 → 直接用（ModelScope 的 `created` 是 unix 秒；NVIDIA 卡片上的 Last updated）。
- 源没有时间字段 → 用 `self.seen.first_seen("<key>:<id>")`，首次抓取时间会写进 `state/seen.json` 并在后续运行复用，避免条目日期每次刷新都变。

## 运行与依赖

```bash
pip install -r requirements.txt
python fetch_feeds.py
```

改 `requirements.txt` 要小心：CI 在 `pip install` 阶段失败会直接中断部署，且本地已装过依赖时看不出来。

## 部署

`main` 分支的 `.github/workflows/rss.yml` 每 6 小时跑一次并把 `dist/` 发到 `gh-pages`。

**注意**：本仓库有多个分支各自带着独立的 workflow（如 `velvetfish` 是 ModelScope 项目），都用 `keep_files: false` 发布到同一个 `gh-pages` 根目录，会互相覆盖对方的产物。部署后请实际检查 `gh-pages` 的文件列表和线上 URL（CDN 有约 1 分钟延迟），不要只看 workflow 是否绿灯。

## PR

改动通过 PR 合入 `main`，一个 PR 一件事，标题简明。
