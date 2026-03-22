"""Research IDEA generator."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from ..config import PaperPulseConfig
from ..storage.database import Database
from ..storage.models import Idea, Paper
from .scorer import IdeaScorer


# Prompt templates
IDEA_GENERATION_PROMPT = """Based on the following recent papers, generate innovative research ideas.

Papers:
{papers_text}

For each idea, provide:
1. A clear, specific title (one sentence)
2. A detailed description (2-3 paragraphs) explaining:
   - What the idea is
   - Why it's novel (how it differs from existing work)
   - How it could be implemented
3. List of related paper numbers (from the above list)

Generate {num_ideas} innovative research ideas that:
- Combine insights from multiple papers
- Address limitations or gaps in current research
- Are feasible to implement and validate

Respond with a JSON array of objects, each with:
- "title": the idea title
- "description": detailed description
- "related_paper_indices": list of paper indices (1-based)

Response (JSON only, no markdown):
"""


class IdeaGenerator:
    """Generate research ideas from papers."""

    def __init__(
        self,
        llm_client,
        db: Database,
        config: PaperPulseConfig,
    ):
        """Initialize idea generator.

        Args:
            llm_client: LLM client for generation
            db: Database instance
            config: PaperPulse configuration
        """
        self.llm = llm_client
        self.db = db
        self.config = config
        self.scorer = IdeaScorer(llm_client, config.ideas.scoring)

    def generate_ideas(
        self,
        papers: list[Paper],
        num_ideas: int = 5,
    ) -> list[Idea]:
        """Generate research ideas from papers.

        Args:
            papers: List of analyzed papers
            num_ideas: Number of ideas to generate

        Returns:
            List of generated ideas
        """
        if not papers:
            return []

        # Filter papers with analysis
        analyzed_papers = [
            p for p in papers
            if p.keywords or p.innovations
        ]

        if len(analyzed_papers) < 2:
            # Not enough analyzed papers
            return []

        # Build papers text
        papers_text = self._build_papers_text(analyzed_papers)

        # Generate ideas
        prompt = IDEA_GENERATION_PROMPT.format(
            papers_text=papers_text,
            num_ideas=num_ideas,
        )

        try:
            response = self.llm.analyze(prompt)
            ideas_data = self._parse_response(response)

            # Create Idea objects
            ideas = []
            for idea_dict in ideas_data:
                # Map paper indices to paper IDs
                related_indices = idea_dict.get("related_paper_indices", [])
                related_paper_ids = []
                for idx in related_indices:
                    if 1 <= idx <= len(analyzed_papers):
                        related_paper_ids.append(analyzed_papers[idx - 1].paper_id)

                # Create idea
                idea = Idea(
                    idea_id=self._generate_id(idea_dict["title"]),
                    title=idea_dict["title"],
                    description=idea_dict.get("description", ""),
                    related_paper_ids=related_paper_ids,
                )

                # Score the idea
                idea = self.scorer.score_idea(idea, analyzed_papers)

                # Save to database
                self.db.insert_idea(idea)

                ideas.append(idea)

            return ideas

        except Exception as e:
            print(f"Idea generation error: {e}")
            return []

    def generate_from_recent(self, days: int = 7, num_ideas: int = 5) -> list[Idea]:
        """Generate ideas from recent papers.

        Args:
            days: Number of days to look back
            num_ideas: Number of ideas to generate

        Returns:
            List of generated ideas
        """
        # Get recent analyzed papers
        papers = self.db.get_recent_papers(days=days, limit=50)
        analyzed = [p for p in papers if p.status.value == "analyzed"]

        return self.generate_ideas(analyzed, num_ideas)

    def generate_for_paper(self, paper: Paper, num_ideas: int = 3) -> list[Idea]:
        """Generate ideas building on a specific paper.

        Args:
            paper: The paper to build on
            num_ideas: Number of ideas to generate

        Returns:
            List of generated ideas
        """
        # Get related papers
        related = []
        if paper.keywords:
            for kw in paper.keywords[:3]:
                related.extend(self.db.search_papers(kw, limit=5))

        # Remove duplicates and the original paper
        related = [p for p in related if p.paper_id != paper.paper_id]
        seen = {paper.paper_id}
        unique_related = []
        for p in related:
            if p.paper_id not in seen:
                seen.add(p.paper_id)
                unique_related.append(p)

        # Generate with paper and related papers
        all_papers = [paper] + unique_related[:4]
        return self.generate_ideas(all_papers, num_ideas)

    def _build_papers_text(self, papers: list[Paper]) -> str:
        """Build papers text for prompt."""
        lines = []

        for i, paper in enumerate(papers[:10], 1):  # Max 10 papers
            innovations = "\n   - ".join(paper.innovations[:3]) if paper.innovations else "N/A"
            limitations = "\n   - ".join(paper.limitations[:2]) if paper.limitations else "N/A"

            lines.append(f"""
{i}. {paper.title}
   Authors: {', '.join(a.name for a in paper.authors[:3])}
   Year: {paper.year}
   Keywords: {', '.join(paper.keywords[:5])}
   Key Innovations:
   - {innovations}
   Limitations:
   - {limitations}
   Abstract: {paper.abstract[:300]}...
""")

        return "\n".join(lines)

    def _parse_response(self, response: str) -> list[dict]:
        """Parse LLM response."""
        response = response.strip()

        # Handle markdown code blocks
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(
                lines[1:-1] if lines[-1].startswith("```") else lines[1:]
            )

        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

    def _generate_id(self, title: str) -> str:
        """Generate unique ID for idea."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        title_hash = hashlib.md5(title.encode()).hexdigest()[:6]
        return f"idea-{timestamp}-{title_hash}"