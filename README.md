# Multi-Source AI Models RSS 🚀

[![RSS Feed](https://img.shields.io/badge/RSS-2.0-orange?style=flat-square&logo=rss)](dist/rss.xml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/Automated-Cron%20Update-brightgreen?style=flat-square&logo=github-actions)](.github/workflows/rss.yml)

自动化抓取多个模型目录站点，聚合成**一个统一的 RSS 2.0 订阅源**。

每条条目标题格式为 `【源】真实标题`：

- `【NVIDIA】Llama-3.3-70B-Instruct`
- `【AMD】DeepSeek-V4-Flash-0731`

---

## 📡 当前数据源

| 源标签 | 站点 | 说明 |
| --- | --- | --- |
| `NVIDIA` | <https://build.nvidia.com/models> | AI 基础模型与 NIM 微服务，卡片自带更新时间 |
| `AMD` | <https://developer.amd.com.cn/radeon/tokenfactory> | TokenFactory **免费（Free / Limited Free）**模型，接口无日期字段 |
| `ModelScope` | <https://api-inference.modelscope.cn> | 魔搭 API-Inference 大模型，远端时间优先，无时间以首次发现时间为准 |

### 无日期条目如何定时间

对于无时间字段的模型：在**第一次被抓取到时**记录当前 UTC 时间，并持久化到状态文件（纳入版本控制，CI 每次运行后自动提交）。后续运行复用首次记录的日期，条目时间与位置不会在每次刷新时跳动。

---

## 📁 目录结构

```text
.
├── .github/workflows/rss.yml   # 定时抓取 -> 回写 state -> 发布 GitHub Pages
├── fetch_feeds.py              # 聚合入口：跑所有源 -> 去重 -> 单一 RSS
├── fetch_modelscope.py          # ModelScope 独立抓取与 Feed 生成引擎
├── sources/
│   ├── base.py                 # Source 基类、Item 结构、首次抓取日期存储
│   ├── nvidia.py               # NVIDIA Build 抓取器
│   ├── amd.py                  # AMD Radeon TokenFactory 抓取器
│   └── modelscope.py           # ModelScope API-Inference 抓取器
├── state/seen.json             # 无日期条目的首次抓取时间
├── data/modelscope_history.json # ModelScope 模型历史发现与时间记录
└── dist/                       # 产物（rss.xml / index.html / 各源 xml），不入库
```

---

## 🛠️ 本地运行

```bash
pip install -r requirements.txt
python fetch_feeds.py
python fetch_modelscope.py
```

产物（每个源一份，另加一份汇总）：

| 文件 | 内容 |
| --- | --- |
| `dist/modelscope.xml` / `dist/modelscope_rss.xml` | 魔搭 API-Inference 模型 |
| `dist/modelscope_atom.xml` | 魔搭 API-Inference Atom 1.0 |
| `dist/modelscope.html` | 魔搭 API 模型在线预览门户 |
| `dist/amd.xml` | 仅 AMD Radeon TokenFactory 免费模型 |
| `dist/nvidia.xml` | 仅 NVIDIA Build 模型 |
| `dist/rss.xml` | 全部源汇总，按 `pubDate` 倒序混排 |
| `dist/index.html` | 按源分组的综合预览门户 |

---

## 🚀 自动化与订阅

GitHub Actions 每 6 小时运行一次（`0 */6 * * *`），支持手动触发，并把 `dist/` 发布到 GitHub Pages。

订阅地址：

- **汇总全部源**：<https://mmschzs.github.io/nvidia-models-rss/rss.xml>
- **ModelScope 专源**：<https://mmschzs.github.io/nvidia-models-rss/modelscope.xml>
- **NVIDIA 专源**：<https://mmschzs.github.io/nvidia-models-rss/nvidia.xml>
- **AMD 专源**：<https://mmschzs.github.io/nvidia-models-rss/amd.xml>
- **综合展示主页**：<https://mmschzs.github.io/nvidia-models-rss/>
- **ModelScope 专用主页**：<https://mmschzs.github.io/nvidia-models-rss/modelscope.html>

---

## 📄 License

MIT。数据版权归各来源站点所有。
