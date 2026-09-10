# AGENTS.md

给在本仓库工作的 AI agent 的约定。

## ⚠️ 本仓库是公开的（public）

任何人都能读到源码、Issue、PR、Actions 日志和 `dist/` 发布物。**写任何东西之前默认它会被公开。**由此产生的要求：

- **禁止把密钥、token、API key、Cookie 写进任何文件**（源码、JSON、Markdown、提交信息都不行）。一律走环境变量 + 仓库 Secrets，代码里只从 `os.environ` 读，缺失就跳过该源而不是硬编码一个默认值。
- **提交前自查**：`git diff` 里出现 `sk-`、40 位十六进制串、Bearer token 等一律停下来。
- **`state/seen.json` 和 `dist/` 会被公开发布**，只能放模型 id 和日期，不要放账号信息、内部 URL、个人信息。
- **日志里不要打印密钥**。请求失败时也别把 header 打出来。
- 密钥一旦进过公开仓库就视为已泄漏：立刻去服务商轮换，删历史也没用（Git 历史、fork、缓存都还在）。

### 已知的安全注意事项

- **第三方 Actions 已 pin 到 commit SHA**（`actions/checkout`、`actions/setup-python`、`peaceiris/actions-gh-pages`）。注释里保留了对应的 tag 方便对照。**升级时重新解析 tag 拿新 SHA，不要手改 SHA 字符串：** `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`。别退回 `@v4` 这种可变 tag——上游被劫持就会在这个同时持有 `DMX_API_KEY` 和 write 权限 `GITHUB_TOKEN` 的 job 里执行任意代码。
- **不要用 `pull_request_target` 触发器**，也不要给 fork PR 暴露 Secrets。当前只有 `push`(main/master)、`schedule`、`workflow_dispatch`，fork PR 拿不到密钥，保持这样。
- **Python 依赖未锁定**（`requirements.txt` 里是 `>=`），没有 hash 校验。要加固就锁定版本 + `--require-hashes`。
- CI 里的 `git push`（回写 `state/seen.json`）依赖 `persist-credentials` 默认开启，job 内任何依赖理论上都能读到 `GITHUB_TOKEN`。代价和便利自己权衡。
- 已发布站点 `https://mmschzs.github.io/nvidia-models-rss/` 是**全网可读**的，即使仓库将来转私有，站点依然公开（除非 Enterprise Cloud 的私有 Pages）。

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
- 源的时间字段不可用 → 用 `self.seen.first_seen("<key>:<id>")`，首次抓取时间会写进 `state/seen.json` 并在后续运行复用，避免条目日期每次刷新都变。AMD 接口没有时间字段，DMXAPI 的 `created` 对所有模型都返回同一个占位值（2021-07-20），两者都走这条路。
- 从别的项目迁移源时，把旧的历史发现时间一并写进 `state/seen.json`，否则日期会重置成迁移当天。

## 运行与依赖

```bash
pip install -r requirements.txt
python fetch_feeds.py
```

改 `requirements.txt` 要小心：CI 在 `pip install` 阶段失败会直接中断部署，且本地已装过依赖时看不出来。

需要密钥的源（目前 `DMXAPI` 需要 `DMX_API_KEY`）从环境变量读取，没有就跳过并记录 warning —— 不要让单个源拖垮整次运行。新密钥要加到仓库 Secrets 并在 workflow 的对应 step 里透传。

## 部署

`main` 分支的 `.github/workflows/rss.yml` 每 6 小时跑一次并把 `dist/` 发到 `gh-pages`。

**注意**：本仓库有多个分支各自带着独立的 workflow（如 `velvetfish` 是 ModelScope 项目），都用 `keep_files: false` 发布到同一个 `gh-pages` 根目录，会互相覆盖对方的产物。部署后请实际检查 `gh-pages` 的文件列表和线上 URL（CDN 有约 1 分钟延迟），不要只看 workflow 是否绿灯。

## PR

改动通过 PR 合入 `main`，一个 PR 一件事，标题简明。
