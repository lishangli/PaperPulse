"""IDEA quality scorer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..storage.models import Idea, Paper


@dataclass
class ScoringWeights:
    """Weights for idea scoring."""
    novelty: float = 0.30
    feasibility: float = 0.25
    impact: float = 0.20
    evidence: float = 0.15
    timing: float = 0.10


SCORING_PROMPT = """Evaluate the following research idea on multiple dimensions.

Title: {title}

Description:
{description}

Related Papers: {num_papers} papers support this idea

Rate each dimension from 0.0 to 1.0:

1. Novelty: How original and innovative is this idea? Does it significantly differ from existing work?
2. Feasibility: How practical is this to implement? Consider technical complexity, resources needed, and time.
3. Impact: If successful, how significant would the contribution be to the field?
4. Evidence: How well is the idea supported by the related papers? Are there solid foundations?
5. Timing: Is this a timely idea? Is the field ready for this? Is there current interest?

Respond with JSON only:
{{
    "novelty": 0.0-1.0,
    "feasibility": 0.0-1.0,
    "impact": 0.0-1.0,
    "evidence": 0.0-1.0,
    "timing": 0.0-1.0,
    "reasoning": "Brief explanation of scores"
}}
"""


class IdeaScorer:
    """Score research ideas on multiple dimensions."""

    def __init__(self, llm_client, weights: ScoringWeights):
        """Initialize scorer.

        Args:
            llm_client: LLM client for scoring
            weights: Weights for combining scores
        """
        self.llm = llm_client
        self.weights = weights

    def score_idea(self, idea: Idea, related_papers: list[Paper]) -> Idea:
        """Score an idea.

        Args:
            idea: Idea to score
            related_papers: Related papers for context

        Returns:
            Idea with scores filled in
        """
        try:
            # Get LLM scores
            prompt = SCORING_PROMPT.format(
                title=idea.title,
                description=idea.description,
                num_papers=len(related_papers),
            )

            response = self.llm.analyze(prompt)
            scores = self._parse_scores(response)

            # Assign scores
            idea.novelty_score = scores.get("novelty", 0.5)
            idea.feasibility_score = scores.get("feasibility", 0.5)
            idea.impact_score = scores.get("impact", 0.5)
            idea.evidence_score = scores.get("evidence", 0.5)
            idea.timing_score = scores.get("timing", 0.5)

            # Calculate weighted total
            idea.score = self._calculate_total_score(idea)

        except Exception as e:
            print(f"Scoring error: {e}")
            # Use heuristic scores
            idea = self._heuristic_score(idea, related_papers)

        return idea

    def _parse_scores(self, response: str) -> dict[str, float]:
        """Parse LLM scoring response."""
        response = response.strip()

        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(
                lines[1:-1] if lines[-1].startswith("```") else lines[1:]
            )

        try:
            data = json.loads(response)
            return {
                k: max(0.0, min(1.0, float(v)))
                for k, v in data.items()
                if k in ["novelty", "feasibility", "impact", "evidence", "timing"]
            }
        except (json.JSONDecodeError, ValueError):
            return {}

    def _calculate_total_score(self, idea: Idea) -> float:
        """Calculate weighted total score."""
        return (
            self.weights.novelty * idea.novelty_score +
            self.weights.feasibility * idea.feasibility_score +
            self.weights.impact * idea.impact_score +
            self.weights.evidence * idea.evidence_score +
            self.weights.timing * idea.timing_score
        )

    def _heuristic_score(self, idea: Idea, papers: list[Paper]) -> Idea:
        """Calculate heuristic scores without LLM."""
        # Novelty: based on title/description length and uniqueness
        title_words = set(idea.title.lower().split())
        novel_keywords = {"novel", "new", "innovative", "first", "unique"}
        idea.novelty_score = min(1.0, 0.5 + 0.1 * len(title_words & novel_keywords))

        # Feasibility: assume medium
        idea.feasibility_score = 0.6

        # Impact: based on number of supporting papers
        idea.impact_score = min(1.0, 0.3 + 0.1 * len(papers))

        # Evidence: based on number of related papers
        idea.evidence_score = min(1.0, 0.2 + 0.15 * len(idea.related_paper_ids))

        # Timing: assume good timing
        idea.timing_score = 0.7

        # Total
        idea.score = self._calculate_total_score(idea)

        return idea

    def rank_ideas(self, ideas: list[Idea]) -> list[Idea]:
        """Rank ideas by score.

        Args:
            ideas: List of ideas to rank

        Returns:
            Sorted list (highest score first)
        """
        return sorted(ideas, key=lambda i: i.score, reverse=True)

    def filter_ideas(
        self,
        ideas: list[Idea],
        min_score: float = 0.6,
        min_novelty: float = 0.0,
    ) -> list[Idea]:
        """Filter ideas by minimum scores.

        Args:
            ideas: List of ideas
            min_score: Minimum total score
            min_novelty: Minimum novelty score

        Returns:
            Filtered list
        """
        return [
            i for i in ideas
            if i.score >= min_score and i.novelty_score >= min_novelty
        ]