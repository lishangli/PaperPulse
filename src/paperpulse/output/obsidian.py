"""Obsidian vault integration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import PaperPulseConfig
from ..storage.database import Database
from ..storage.models import Idea, Paper


class ObsidianWriter:
    """Write notes to Obsidian vault."""

    def __init__(self, config: PaperPulseConfig, db: Database):
        """Initialize Obsidian writer.

        Args:
            config: PaperPulse configuration
            db: Database instance
        """
        self.config = config
        self.db = db

        # Get vault path
        if config.obsidian.vault_path:
            self.vault_path = Path(config.obsidian.vault_path)
        else:
            self.vault_path = Path("./obsidian")

        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Folder names
        self.papers_folder = config.obsidian.folders.papers
        self.ideas_folder = config.obsidian.folders.ideas
        self.daily_folder = config.obsidian.folders.daily
        self.latex_folder = config.obsidian.folders.latex

        # Create folders
        for folder in [self.papers_folder, self.ideas_folder, self.daily_folder, self.latex_folder]:
            (self.vault_path / folder).mkdir(parents=True, exist_ok=True)

    def sync_paper(self, paper: Paper) -> str:
        """Sync a paper to Obsidian.

        Args:
            paper: Paper to sync

        Returns:
            Path to created note
        """
        # Create dated subfolder
        date_str = datetime.now().strftime("%Y-%m-%d")
        paper_dir = self.vault_path / self.papers_folder / date_str
        paper_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize title for filename
        safe_title = self._sanitize_filename(paper.title[:50])
        if paper.arxiv_id:
            filename = f"📄 {paper.arxiv_id} - {safe_title}.md"
        else:
            filename = f"📄 {safe_title}.md"

        note_path = paper_dir / filename

        # Build note content
        lines = [
            f"# 📄 {paper.title}",
            "",
        ]

        # Metadata
        if paper.arxiv_id:
            lines.append(f"**arXiv**: [[{paper.arxiv_id}]]")
        if paper.doi:
            lines.append(f"**DOI**: {paper.doi}")
        lines.append(f"**日期**: {paper.published_date.strftime('%Y-%m-%d') if paper.published_date else 'N/A'}")
        lines.append(f"**作者**: {', '.join(a.name for a in paper.authors[:5])}")
        lines.append(f"**领域**: #{paper.venue.replace('.', '_') if paper.venue else 'Unknown'}")
        lines.append(f"**来源**: {paper.source.value}")
        lines.append("")

        # URL
        if paper.url:
            lines.append(f"**链接**: [{paper.url}]({paper.url})")
            lines.append("")

        # Tags
        if paper.keywords:
            tags = " ".join(f"#{kw.replace(' ', '_').replace('-', '_')}" for kw in paper.keywords[:10])
            lines.append(f"**标签**: {tags}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # Abstract
        lines.append("## 📝 摘要")
        lines.append("")
        lines.append(paper.abstract or "无摘要")
        lines.append("")

        # Innovations
        if paper.innovations:
            lines.append("## 💡 创新点")
            lines.append("")
            for innovation in paper.innovations:
                lines.append(f"- {innovation}")
            lines.append("")

        # Limitations
        if paper.limitations:
            lines.append("## ⚠️ 局限性")
            lines.append("")
            for limitation in paper.limitations:
                lines.append(f"- {limitation}")
            lines.append("")

        # BibTeX
        if paper.arxiv_id:
            lines.extend([
                "## 📊 引用信息",
                "",
                "```bibtex",
                f"@article{{{paper.arxiv_id.replace('.', '_')},",
                f"  title={{{paper.title}}},",
                f"  author={{{' and '.join(a.name for a in paper.authors[:3])}}},",
                f"  journal={{arXiv preprint arXiv:{paper.arxiv_id}}},",
                f"  year={{{paper.year}}}",
                "}",
                "```",
                "",
            ])

        # Files
        if paper.pdf_path or paper.latex_path:
            lines.append("## 📁 相关文件")
            lines.append("")
            if paper.pdf_path:
                lines.append(f"- **PDF**: `{paper.pdf_path}`")
            if paper.latex_path:
                lines.append(f"- **LaTeX**: `{paper.latex_path}`")
            if paper.markdown_path:
                lines.append(f"- **Markdown**: `{paper.markdown_path}`")
            lines.append("")

        # Write note
        note_path.write_text("\n".join(lines), encoding="utf-8")

        return str(note_path)

    def sync_papers(self, papers: list[Paper]) -> list[str]:
        """Sync multiple papers.

        Args:
            papers: List of papers

        Returns:
            List of created note paths
        """
        paths = []
        for paper in papers:
            try:
                path = self.sync_paper(paper)
                paths.append(path)
            except Exception as e:
                print(f"Error syncing paper {paper.paper_id}: {e}")

        return paths

    def sync_idea(self, idea: Idea, papers: Optional[list[Paper]] = None) -> str:
        """Sync an idea to Obsidian.

        Args:
            idea: Idea to sync
            papers: Related papers (fetched if None)

        Returns:
            Path to created note
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        idea_dir = self.vault_path / self.ideas_folder / date_str
        idea_dir.mkdir(parents=True, exist_ok=True)

        safe_title = self._sanitize_filename(idea.title[:50])
        filename = f"💡 {safe_title}.md"
        note_path = idea_dir / filename

        # Fetch related papers if not provided
        if papers is None:
            papers = []
            for paper_id in idea.related_paper_ids:
                paper = self.db.get_paper(paper_id)
                if paper:
                    papers.append(paper)

        # Build note content
        lines = [
            f"# 💡 {idea.title}",
            "",
            f"**ID**: `{idea.idea_id}`",
            f"**评分**: {idea.score:.2f}",
            f"**创建时间**: {idea.created_at.strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        # Scores
        lines.extend([
            "## 📊 评分详情",
            "",
            "| 维度 | 评分 |",
            "|------|------|",
            f"| 新颖性 | {idea.novelty_score:.2f} |",
            f"| 可行性 | {idea.feasibility_score:.2f} |",
            f"| 影响力 | {idea.impact_score:.2f} |",
            f"| 证据支撑 | {idea.evidence_score:.2f} |",
            f"| 时机 | {idea.timing_score:.2f} |",
            "",
        ])

        # Description
        lines.extend([
            "## 📝 描述",
            "",
            idea.description or "无详细描述",
            "",
        ])

        # Research directions
        if idea.research_directions:
            lines.extend([
                "## 🔬 研究方向",
                "",
            ])
            for direction in idea.research_directions:
                lines.append(f"- {direction}")
            lines.append("")

        # Related papers
        if papers:
            lines.extend([
                "## 📚 相关论文",
                "",
            ])
            for paper in papers[:5]:
                link = f"[[{paper.arxiv_id}]]" if paper.arxiv_id else paper.title
                lines.append(f"- {link}: {paper.title}")
            lines.append("")

        # Research command
        lines.extend([
            "## 🚀 开始研究",
            "",
            f"```bash",
            f"paperpulse research {idea.idea_id}",
            f"```",
            "",
        ])

        note_path.write_text("\n".join(lines), encoding="utf-8")

        return str(note_path)

    def sync_ideas(self, ideas: list[Idea]) -> list[str]:
        """Sync multiple ideas."""
        paths = []
        for idea in ideas:
            try:
                path = self.sync_idea(idea)
                paths.append(path)
            except Exception as e:
                print(f"Error syncing idea {idea.idea_id}: {e}")

        return paths

    def sync_latex(self, arxiv_id: str, latex_path: Path) -> str:
        """Create a reference note for LaTeX source.

        Args:
            arxiv_id: arXiv ID
            latex_path: Path to LaTeX source directory

        Returns:
            Path to created note
        """
        latex_dir = self.vault_path / self.latex_folder
        latex_dir.mkdir(parents=True, exist_ok=True)

        filename = f"📐 {arxiv_id}.md"
        note_path = latex_dir / filename

        lines = [
            f"# 📐 LaTeX Source: {arxiv_id}",
            "",
            f"**本地路径**: `{latex_path}`",
            "",
            "## 文件列表",
            "",
        ]

        # List files
        latex_path = Path(latex_path)
        for f in sorted(latex_path.rglob("*"))[:20]:
            if f.is_file():
                rel_path = f.relative_to(latex_path)
                lines.append(f"- `{rel_path}`")

        lines.append("")
        lines.append(f"*Source: arXiv:{arxiv_id}*")

        note_path.write_text("\n".join(lines), encoding="utf-8")

        return str(note_path)

    def write_daily_summary(self, papers: list[Paper], ideas: list[Idea]) -> str:
        """Write daily summary note.

        Args:
            papers: Today's papers
            ideas: Today's ideas

        Returns:
            Path to created note
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_dir = self.vault_path / self.daily_folder
        daily_dir.mkdir(parents=True, exist_ok=True)

        filename = f"📊 {date_str}.md"
        note_path = daily_dir / filename

        lines = [
            f"# 📊 每日总结 - {date_str}",
            "",
            f"**论文数**: {len(papers)}",
            f"**IDEA 数**: {len(ideas)}",
            "",
            "## 📄 新论文",
            "",
        ]

        for paper in papers[:10]:
            link = f"[[{paper.arxiv_id}]]" if paper.arxiv_id else paper.title
            lines.append(f"- {link}: {paper.title[:60]}...")

        lines.extend([
            "",
            "## 💡 新 IDEA",
            "",
        ])

        for idea in ideas[:5]:
            lines.append(f"- **{idea.title}** (评分: {idea.score:.2f})")

        lines.append("")

        note_path.write_text("\n".join(lines), encoding="utf-8")

        return str(note_path)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use as filename."""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        return name.strip()