# PaperPulse

> 📜 论文监控、分析与创新 IDEA 推荐系统

## 功能特性

| 功能 | 描述 |
|------|------|
| 🔍 **多源监控** | arXiv、Semantic Scholar、Papers with Code |
| 📥 **文档下载** | PDF 下载 + arXiv LaTeX 源码下载 |
| 📄 **PDF 转换** | MinerU 转换 PDF → Markdown |
| 🤖 **LLM 分析** | 自动提取关键词、创新点、局限性 |
| 📈 **趋势分析** | 检测热门关键词和新兴方向 |
| 💡 **IDEA 生成** | 基于多篇论文生成创新研究想法 |
| 📝 **每日报告** | Markdown 报告 + Obsidian 笔记 |
| ⏰ **定时任务** | 可配置的自动监控和报告 |
| 🔗 **研究集成** | 一键启动 AutoResearchClaw 研究 |

## 快速开始

```bash
# 1. 克隆项目
cd /home/lishangli/repos/paperpulse

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -e .

# 4. 配置
cp config.example.yaml config.yaml
# 编辑 config.yaml，设置 OPENAI_API_KEY

# 5. 检查环境
paperpulse doctor

# 6. 运行监控
paperpulse monitor
```

## CLI 命令

```bash
# 监控论文 (一键执行全部流程)
paperpulse monitor

# 只收集论文
paperpulse collect --days 1 --limit 50

# 下载文档 (PDF 和 LaTeX)
paperpulse download 2301.00001

# 转换 PDF → Markdown
paperpulse convert 2301.00001

# 分析论文
paperpulse analyze 2301.00001

# 生成 IDEA
paperpulse ideas --num 5

# 查看趋势
paperpulse trends

# 生成报告
paperpulse report --daily

# 同步到 Obsidian
paperpulse obsidian

# 启动 IDEA 研究
paperpulse research idea-20260322-abc123

# 查看数据库统计
paperpulse db

# 环境检查
paperpulse doctor
```

## 配置说明

### 数据源配置

```yaml
sources:
  arxiv:
    enabled: true
    categories: [cs.AI, cs.CL, cs.LG, cs.CV, cs.NE]
    max_papers_per_day: 100

  semantic_scholar:
    enabled: true
    fields: ["Artificial Intelligence", "Machine Learning"]

  papers_with_code:
    enabled: true
    areas: [natural-language-processing, computer-vision]
```

### arXiv 类别

| 类别 | 领域 |
|------|------|
| cs.AI | 人工智能 |
| cs.CL | 计算与语言 (NLP) |
| cs.LG | 机器学习 |
| cs.CV | 计算机视觉 |
| cs.NE | 神经计算 |
| cs.RO | 机器人 |
| stat.ML | 统计机器学习 |

### 定时任务配置

```yaml
scheduler:
  enabled: true
  daily_monitor: "0 8 * * *"     # 每天 8:00
  daily_report: "30 8 * * *"     # 每天 8:30
  weekly_summary: "0 9 * * 1"    # 每周一 9:00
```

### Obsidian 集成

```yaml
obsidian:
  enabled: true
  vault_path: "/path/to/your/vault"  # 或留空使用默认目录
  folders:
    papers: "Papers"
    ideas: "Ideas"
    daily: "Daily"
```

## 输出示例

### 每日报告

```markdown
# 📜 PaperPulse 每日报告 - 2026-03-22

> 🤖 发现 **47** 篇新论文 | 生成 **8** 个创新 IDEA

## 🔥 热门关键词

| 关键词 | 论文数 | 趋势 |
|--------|--------|------|
| Mixture of Experts | 12 | ↑ 156% |
| Long Context | 9 | ↑ 89% |

## 💡 今日推荐 IDEA

### #1 [高价值] MoE + Long Context 的动态专家选择机制

**评分**: 0.86 ⭐⭐⭐⭐

**描述**: 当前 MoE 的专家选择在长文本中面临效率问题...
```

## 与 AutoResearchClaw 联动

```bash
# 1. 查看 IDEA
paperpulse ideas

# 2. 启动研究
paperpulse research idea-20260322-abc123

# 自动调用 AutoResearchClaw 生成论文
```

## 依赖安装

### 基础依赖

```bash
pip install -e .
```

### MinerU (PDF 转 Markdown)

```bash
pip install mineru[all]
```

## 项目结构

```
paperpulse/
├── src/paperpulse/
│   ├── cli.py              # CLI 入口
│   ├── config.py           # 配置管理
│   ├── collectors/         # 论文采集
│   ├── downloader/         # 文档下载
│   ├── converter/          # PDF 转换
│   ├── storage/            # 数据存储
│   ├── analysis/           # LLM 分析
│   ├── ideas/              # IDEA 生成
│   ├── output/             # 报告输出
│   └── integration/        # 第三方集成
├── data/                   # 本地数据
│   ├── papers.db           # SQLite 数据库
│   ├── pdfs/               # PDF 文件
│   ├── latex/              # LaTeX 源码
│   └── markdown/           # Markdown 转换结果
├── reports/                # 报告输出
└── obsidian/               # Obsidian 笔记
```

## License

MIT