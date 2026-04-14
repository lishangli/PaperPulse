"""Synthesis report generator - LLM driven research analysis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import PaperPulseConfig
from ..storage.database import Database
from ..storage.models import Paper


# LLM Prompt for synthesis report
SYNTHESIS_PROMPT = """分析以下论文并生成研究综述报告。

论文内容:
---
{paper_content}
---

生成一份结构清晰、内容完整的研究综述报告，直接以报告正文开始，不要包含任何开场白、思考过程或自我陈述。

报告结构建议:
1. 论文基本信息（标题、作者、来源等）
2. 核心贡献与定位
3. 领域发展脉络（从相关工作分析）
4. 方法对比分析
5. 局限性与改进机会
6. 跨论文/跨理论结合机会
7. 研究方向建议

输出要求:
- 直接输出 Markdown 格式的报告正文
- 不要写"让我分析"、"现在我来"等自我陈述
- 不要写"从文件中可以看到"等思考过程
- 报告第一行直接是标题或正文内容
- 内容要有洞察力，帮助读者快速理解论文价值"""


class SynthesisReport:
    """Generate synthesis reports using LLM."""

    def __init__(
        self,
        db: Database,
        config: PaperPulseConfig,
        llm_backend,
    ):
        """Initialize synthesis report generator.

        Args:
            db: Database instance
            config: PaperPulse configuration
            llm_backend: LLM backend for analysis
        """
        self.db = db
        self.config = config
        self.llm = llm_backend
        self.output_dir = Path(config.output.reports_dir) / "synthesis"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        paper: Paper,
        content: Optional[str] = None,
    ) -> str:
        """Generate synthesis report for a paper.

        Args:
            paper: Paper to analyze
            content: Paper content (read from markdown_path if None)

        Returns:
            Path to generated report
        """
        # Read paper content
        if content is None:
            if not paper.markdown_path:
                raise ValueError(f"Paper {paper.paper_id} has no markdown content")
            
            content_path = Path(paper.markdown_path)
            if not content_path.exists():
                raise ValueError(f"Markdown file not found: {content_path}")
            
            content = content_path.read_text(encoding="utf-8")

        # Truncate if too long (LLM token limit)
        max_chars = 50000  # ~12k tokens
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... (content truncated due to length)"

        # Build prompt
        prompt = SYNTHESIS_PROMPT.format(paper_content=content)

        # Call LLM
        report_content = self.llm.analyze(prompt)

        # Save report
        date = datetime.now().strftime("%Y%m%d")
        report_filename = f"{paper.arxiv_id or paper.paper_id}_synthesis_{date}.md"
        report_path = self.output_dir / report_filename
        report_path.write_text(report_content, encoding="utf-8")

        return str(report_path)

    def generate_for_recent(
        self,
        days: int = 1,
        limit: int = 5,
    ) -> list[str]:
        """Generate synthesis reports for recent papers.

        Args:
            days: Days to look back
            limit: Maximum papers to process

        Returns:
            List of generated report paths
        """
        papers = self.db.get_recent_papers(days=days, limit=limit)
        
        # Filter papers with markdown content
        papers_with_content = [p for p in papers if p.markdown_path]
        
        if not papers_with_content:
            return []

        report_paths = []
        for paper in papers_with_content:
            try:
                path = self.generate_report(paper)
                report_paths.append(path)
            except Exception as e:
                print(f"Error generating report for {paper.paper_id}: {e}")

        return report_paths