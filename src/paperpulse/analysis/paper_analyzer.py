"""Paper analyzer using LLM."""

from __future__ import annotations

import json
from typing import Optional

from ..storage.database import Database
from ..storage.models import Paper, PaperStatus
from .llm_client import LLMClient


# Prompts for paper analysis
ANALYSIS_PROMPT = """Analyze the following academic paper and extract key information.

Title: {title}

Abstract:
{abstract}

{content_section}

Please provide a JSON response with the following fields:
1. "keywords": A list of 5-10 relevant keywords/tags
2. "innovations": A list of 2-5 key innovations or contributions (brief, 1-2 sentences each)
3. "limitations": A list of 2-3 limitations or future work directions mentioned
4. "significance": A brief assessment of the paper's significance (1-2 sentences)

Response (JSON only, no markdown):
"""

CONTENT_SECTION = """
Full Text Excerpt:
{content}
"""


class PaperAnalyzer:
    """Analyze papers using LLM."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: Database,
        use_full_text: bool = True,
    ):
        """Initialize paper analyzer.

        Args:
            llm_client: LLM client for analysis
            db: Database instance
            use_full_text: Whether to use full text when available
        """
        self.llm = llm_client
        self.db = db
        self.use_full_text = use_full_text

    def analyze_paper(self, paper: Paper) -> bool:
        """Analyze a single paper.

        Args:
            paper: Paper to analyze

        Returns:
            Success status
        """
        # Prepare content
        content = ""
        if self.use_full_text and paper.markdown_path:
            try:
                md_content = open(paper.markdown_path).read()
                # Truncate to avoid token limits
                if len(md_content) > 10000:
                    content = md_content[:10000] + "\n... (truncated)"
                else:
                    content = md_content
            except Exception:
                pass

        # Build prompt
        content_section = ""
        if content:
            content_section = CONTENT_SECTION.format(content=content)

        prompt = ANALYSIS_PROMPT.format(
            title=paper.title,
            abstract=paper.abstract or "Not available",
            content_section=content_section,
        )

        # Call LLM
        try:
            response = self.llm.analyze(prompt)

            # Parse JSON response
            # Handle potential markdown code blocks
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

            result = json.loads(response)

            # Update paper
            paper.keywords = result.get("keywords", [])
            paper.innovations = result.get("innovations", [])
            paper.limitations = result.get("limitations", [])
            paper.status = PaperStatus.ANALYZED

            # Save to database
            self.db.update_paper(paper)

            return True

        except json.JSONDecodeError as e:
            print(f"JSON parse error for {paper.paper_id}: {e}")
            return False
        except Exception as e:
            print(f"Analysis error for {paper.paper_id}: {e}")
            return False

    def analyze_papers(
        self,
        papers: list[Paper],
        delay: float = 1.0,
    ) -> dict[str, bool]:
        """Analyze multiple papers.

        Args:
            papers: List of papers to analyze
            delay: Delay between API calls

        Returns:
            Dict mapping paper_id to success status
        """
        import time

        results = {}

        for i, paper in enumerate(papers):
            if i > 0:
                time.sleep(delay)

            results[paper.paper_id] = self.analyze_paper(paper)

        return results

    def get_papers_for_analysis(self, limit: int = 50) -> list[Paper]:
        """Get papers that need analysis.

        Args:
            limit: Maximum papers to return

        Returns:
            List of papers needing analysis
        """
        # Get papers that are downloaded but not analyzed
        downloaded = self.db.get_papers(status=PaperStatus.DOWNLOADED, limit=limit)

        # Also include papers with PDF but marked as NEW
        new_with_pdf = [
            p for p in self.db.get_papers(status=PaperStatus.NEW, limit=limit)
            if p.pdf_path or p.markdown_path
        ]

        return downloaded + new_with_pdf

    def extract_keywords_batch(self, papers: list[Paper]) -> dict[str, list[str]]:
        """Extract keywords from multiple papers in one API call.

        Args:
            papers: List of papers

        Returns:
            Dict mapping paper_id to keywords
        """
        # Build batch prompt
        paper_list = "\n".join([
            f"{i+1}. {p.title}"
            for i, p in enumerate(papers[:20])  # Limit to 20
        ])

        prompt = f"""For each paper below, provide 3-5 relevant keywords as a JSON object mapping paper number to keywords list.

Papers:
{paper_list}

Response (JSON only):
"""

        try:
            response = self.llm.analyze(prompt)
            result = json.loads(response.strip())

            # Map back to paper IDs
            keywords_map = {}
            for i, paper in enumerate(papers[:20]):
                key = str(i + 1)
                if key in result:
                    keywords_map[paper.paper_id] = result[key]
                    paper.keywords = result[key]
                    self.db.update_paper(paper)

            return keywords_map

        except Exception as e:
            print(f"Batch keyword extraction error: {e}")
            return {}