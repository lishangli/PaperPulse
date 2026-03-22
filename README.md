# PaperPulse

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 📜 **Paper Monitoring, Analysis & Innovative IDEA Recommendation System**

PaperPulse is an automated paper monitoring system that collects papers from multiple sources, analyzes them using LLM, detects trends, generates innovative research ideas, and integrates with your note-taking workflow.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Multi-source Collection** | arXiv, Semantic Scholar, Papers with Code |
| 📥 **Document Download** | PDF + arXiv LaTeX source code |
| 📄 **PDF Conversion** | Convert PDFs to Markdown using MinerU |
| 🤖 **LLM Analysis** | Extract keywords, innovations, and limitations |
| 📈 **Trend Detection** | Identify trending keywords and emerging topics |
| 💡 **IDEA Generation** | Generate innovative research ideas from papers |
| 📝 **Daily Reports** | Markdown reports + Obsidian notes |
| ⏰ **Scheduling** | Configurable automated monitoring |
| 🔗 **Research Integration** | One-click launch AutoResearchClaw experiments |

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/paperpulse.git
cd paperpulse

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Copy and configure
cp config.example.yaml config.yaml
# Edit config.yaml and set your OPENAI_API_KEY

# Check environment
paperpulse doctor

# Run monitoring
paperpulse monitor
```

## 📋 CLI Commands

```bash
# Run full monitoring pipeline
paperpulse monitor

# Collect papers only
paperpulse collect --days 1 --limit 50

# Download documents (PDF and LaTeX)
paperpulse download 2301.00001

# Convert PDF to Markdown
paperpulse convert 2301.00001

# Analyze papers with LLM
paperpulse analyze 2301.00001

# Generate research ideas
paperpulse ideas --num 5

# View trending keywords
paperpulse trends

# Generate reports
paperpulse report --daily

# Sync to Obsidian vault
paperpulse obsidian

# Start research for an idea
paperpulse research idea-20260322-abc123

# Show database statistics
paperpulse db

# Environment check
paperpulse doctor

# Start daemon
paperpulse daemon
```

## ⚙️ Configuration

### Data Sources

```yaml
sources:
  arxiv:
    enabled: true
    categories: [cs.AI, cs.CL, cs.LG, cs.CV, cs.NE]
    keywords: []  # Optional filter keywords
    max_papers_per_day: 100

  semantic_scholar:
    enabled: true
    fields: ["Artificial Intelligence", "Machine Learning"]
    max_papers_per_day: 50

  papers_with_code:
    enabled: true
    areas: [natural-language-processing, computer-vision]
    max_papers_per_day: 30
```

### arXiv Categories

| Category | Field |
|----------|-------|
| cs.AI | Artificial Intelligence |
| cs.CL | Computation and Language (NLP) |
| cs.LG | Machine Learning |
| cs.CV | Computer Vision |
| cs.NE | Neural Computing |
| cs.RO | Robotics |
| stat.ML | Statistics - Machine Learning |

### Scheduler Configuration

```yaml
scheduler:
  enabled: true
  daily_monitor: "0 8 * * *"     # Daily at 8:00 AM
  daily_report: "30 8 * * *"     # Daily at 8:30 AM
  weekly_summary: "0 9 * * 1"    # Monday at 9:00 AM
```

### Obsidian Integration

```yaml
obsidian:
  enabled: true
  vault_path: "/path/to/your/vault"  # Leave empty for default
  folders:
    papers: "Papers"
    ideas: "Ideas"
    daily: "Daily"
    latex: "LaTeX"
```

### LLM Configuration

```yaml
llm:
  provider: openai
  api_key_env: OPENAI_API_KEY
  base_url: https://api.openai.com/v1
  primary_model: gpt-4o
  fallback_model: gpt-4o-mini
```

## 📊 Output Example

### Daily Report

```markdown
# 📜 PaperPulse Daily Report - 2026-03-22

> 🤖 Discovered **47** new papers | Generated **8** innovative ideas

## 🔥 Trending Keywords

| Keyword | Papers | Trend |
|---------|--------|-------|
| Mixture of Experts | 12 | ↑ 156% |
| Long Context | 9 | ↑ 89% |
| Chain of Thought | 7 | ↑ 45% |

## 💡 Top Ideas Today

### #1 [High Value] Dynamic Expert Selection for MoE in Long Context

**Score**: 0.86 ⭐⭐⭐⭐

**Description**: Current MoE expert selection faces efficiency challenges in long documents...
```

## 🔗 AutoResearchClaw Integration

PaperPulse integrates with [AutoResearchClaw](https://github.com/yourusername/AutoResearchClaw) to automatically run experiments for generated ideas:

```bash
# View generated ideas
paperpulse ideas

# Start research for an idea
paperpulse research idea-20260322-abc123

# AutoResearchClaw will be invoked to generate a research paper
```

## 📁 Project Structure

```
paperpulse/
├── src/paperpulse/
│   ├── cli.py              # CLI entry point
│   ├── config.py           # Configuration management
│   ├── collectors/         # Paper collection
│   │   ├── arxiv.py        # arXiv + LaTeX download
│   │   ├── semantic_scholar.py
│   │   └── papers_with_code.py
│   ├── downloader/         # Document download
│   │   └── pdf.py          # PDF + LaTeX downloader
│   ├── converter/          # PDF conversion
│   │   └── mineru.py       # MinerU integration
│   ├── storage/            # Data storage
│   │   ├── models.py       # Data models
│   │   └── database.py     # SQLite database
│   ├── analysis/           # LLM analysis
│   │   ├── llm_client.py   # OpenAI client
│   │   ├── paper_analyzer.py
│   │   └── trend_detector.py
│   ├── ideas/              # Idea generation
│   │   ├── generator.py
│   │   └── scorer.py
│   ├── output/             # Output generation
│   │   ├── markdown.py     # Report generator
│   │   └── obsidian.py     # Obsidian sync
│   └── integration/        # External integrations
│       ├── researchclaw.py # AutoResearchClaw
│       └── scheduler.py    # Task scheduler
├── data/                   # Local data storage
│   ├── papers.db           # SQLite database
│   ├── pdfs/               # PDF files
│   ├── latex/              # LaTeX sources
│   └── markdown/           # Converted markdown
├── reports/                # Generated reports
├── obsidian/               # Obsidian notes
├── config.example.yaml     # Example configuration
├── pyproject.toml          # Project metadata
└── README.md
```

## 📦 Dependencies

### Core Dependencies

```bash
pip install -e .
```

This installs:
- `arxiv` - arXiv API client
- `openai` - OpenAI API client
- `httpx` - HTTP client
- `pydantic` - Data validation
- `click` - CLI framework
- `rich` - Terminal output
- `pyyaml` - YAML parsing
- `feedparser` - RSS parsing
- `schedule` - Task scheduling

### Optional: MinerU (PDF → Markdown)

For high-quality PDF to Markdown conversion:

```bash
pip install mineru[all]
```

MinerU is optimized for academic papers and supports:
- Mathematical formulas
- Tables
- Figures
- Multi-column layouts
- Chinese text

## 🔧 Advanced Usage

### Custom Collection Query

```bash
# Collect from specific arXiv categories
paperpulse collect --categories cs.AI,cs.LG --limit 100

# Collect from specific date range
paperpulse collect --days 7
```

### Batch Processing

```python
from paperpulse.config import load_config
from paperpulse.storage.database import Database
from paperpulse.collectors.arxiv import ArxivCollector
from paperpulse.analysis.llm_client import create_llm_client
from paperpulse.analysis.paper_analyzer import PaperAnalyzer

config = load_config()
db = Database(config.storage.database)

# Collect
collector = ArxivCollector(categories=["cs.CL", "cs.AI"])
papers = collector.collect()
db.insert_papers(papers)

# Analyze
llm = create_llm_client(config.llm)
analyzer = PaperAnalyzer(llm, db)
for paper in papers:
    analyzer.analyze_paper(paper)
```

### Obsidian Templates

PaperPulse creates structured Obsidian notes with:

- Paper metadata (arXiv ID, DOI, authors, date)
- Abstract and key points
- Extracted innovations and limitations
- BibTeX citation
- Links to PDF/LaTeX sources
- Research command snippets

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [arXiv](https://arxiv.org/) for providing open access to papers
- [Semantic Scholar](https://www.semanticscholar.org/) for their API
- [Papers with Code](https://paperswithcode.com/) for linking papers to code
- [MinerU](https://github.com/opendatalab/MinerU) for PDF parsing
- [AutoResearchClaw](https://github.com/yourusername/AutoResearchClaw) for research automation

---

<p align="center">
  Made with ❤️ by the PaperPulse Team
</p>