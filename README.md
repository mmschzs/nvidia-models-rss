# NVIDIA Models RSS Feed 🚀

[![RSS Feed](https://img.shields.io/badge/RSS-2.0-orange?style=flat-square&logo=rss)](dist/rss.xml)
[![Atom Feed](https://img.shields.io/badge/Atom-1.0-blue?style=flat-square&logo=atom)](dist/atom.xml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/Automated-Cron%20Update-brightgreen?style=flat-square&logo=github-actions)](.github/workflows/rss.yml)

自动化跟踪与解析 [NVIDIA Build Models](https://build.nvidia.com/models) 平台上最新发布和更新的 AI 基础模型及 NIM 微服务，自动生成标准 **RSS 2.0** 与 **Atom 1.0** 订阅源，并通过 **GitHub Actions** 定时更新与发布到 **GitHub Pages**。

---

## 🌟 特性

- **全量模型元数据提取**：
  - **模型名称**与官方直达链接（如 `/nvidia/nemotron-3.5-lightning-30b-a3b`）
  - **发布者/组织**（NVIDIA, Meta, Google, Qwen, Mistral AI, Stepfun-ai, Poolside, etc.）
  - **核心功能徽章**（Downloadable, Free Endpoint, Self-Hosted 等）
  - **完整分类与标签**（MoE, Agent, Reasoning, Multimodal, Text-to-Text, Quantum Computing 等）
  - **模型简介与描述**
  - **更新时间**（解析为标准 UTC `pubDate` / `updated` 时间戳）
  - **调用量与统计信息**
- **三层容错解析架构**：
  1. **Next.js Pages Router 协议**：优先尝试提取 `<script id="__NEXT_DATA__">`。
  2. **Next.js App Router RSC 流式协议**：解析 `self.__next_f.push` 中的 React Query dehydrated 状态。
  3. **健壮 DOM 渲染解析器**：通过 BeautifulSoup 提取 `data-testid="nv-card-root"` 及相关标准语义节点，保证网页结构微调时永不失效。
- **现代化 Feed 体验**：
  - 每条 Feed 均注入精心排版的 HTML 卡片（包含组织彩色徽章、标签胶囊、直达按钮），兼容各类暗色/亮色 RSS 阅读器（Feedly, NetNewsWire, Inoreader, Fluent Reader, Readwise 等）。
  - 自动生成静态网页索引 `dist/index.html`，可直接作为展示门户。
- **自动化运维**：
  - GitHub Actions 每 6 小时自动触发抓取 (`0 */6 * * *`)。
  - 支持手动立即触发 (`workflow_dispatch`)。
  - 自动通过 `peaceiris/actions-gh-pages` 将产物发布至 `gh-pages` 分支。

---

## 📁 目录结构

```text
nvidia-models-rss/
├── .github/
│   └── workflows/
│       └── rss.yml          # GitHub Actions 自动化工作流
├── dist/                    # 生成的目标订阅产物（部署到 GitHub Pages）
│   ├── rss.xml              # RSS 2.0 订阅源
│   ├── atom.xml             # Atom 1.0 订阅源
│   └── index.html           # 静态展示页面
├── fetch_models.py          # 核心抓取与 Feed 生成引擎
├── requirements.txt         # Python 依赖清单
├── .gitignore               # Git 忽略配置
└── README.md                # 项目说明文档
```

---

## 🛠️ 本地运行与开发

### 1. 安装依赖

确保已安装 Python 3.10+，然后在项目根目录下运行：

```bash
pip install -r requirements.txt
```

### 2. 运行抓取脚本

```bash
python fetch_models.py
```

执行成功后，终端将输出抓取日志，并在 `dist/` 目录下生成：
- `dist/rss.xml`
- `dist/atom.xml`
- `dist/index.html`

---

## 🚀 GitHub Actions 部署指南

### 1. 推送至 GitHub

在本地初始化并推送到你的 GitHub 仓库：

```bash
git init
git add .
git commit -m "feat: initial commit for nvidia models rss generator"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

### 2. 启用 GitHub Pages

1. 进入 GitHub 仓库页面 -> **Settings** -> **Pages**。
2. 在 **Build and deployment** > **Source** 中选择 **Deploy from a branch**。
3. Branch 选择 **`gh-pages`** 分支，目录选择 **`/ (root)`**，点击 **Save**。

### 3. 获取订阅链接

部署完成后，你的 RSS / Atom 订阅链接为：

- **RSS 2.0**：`https://<your-username>.github.io/<your-repo-name>/rss.xml`
- **Atom 1.0**：`https://<your-username>.github.io/<your-repo-name>/atom.xml`
- **在线预览页面**：`https://<your-username>.github.io/<your-repo-name>/`

---

## 📄 License

本项目采用 [MIT License](LICENSE) 开源。数据来源归属于 [NVIDIA](https://build.nvidia.com)。
