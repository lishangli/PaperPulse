"""Trend detection for paper keywords."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Optional

from ..storage.database import Database
from ..storage.models import Paper, TrendKeyword


class TrendDetector:
    """Detect trending keywords and topics."""

    def __init__(
        self,
        db: Database,
        min_count: int = 3,
    ):
        """Initialize trend detector.

        Args:
            db: Database instance
            min_count: Minimum keyword count to consider
        """
        self.db = db
        self.min_count = min_count

    def detect_trends(self, days: int = 7) -> list[TrendKeyword]:
        """Detect trending keywords over a period.

        Args:
            days: Number of days to analyze

        Returns:
            List of trending keywords
        """
        # Try database-stored keywords first
        db_trends = self.db.get_keyword_trends(days)
        if db_trends:
            return db_trends

        # Fall back to analyzing paper keywords
        papers = self.db.get_recent_papers(days=days, limit=500)

        return self._analyze_paper_keywords(papers, days)

    def _analyze_paper_keywords(
        self,
        papers: list[Paper],
        days: int,
    ) -> list[TrendKeyword]:
        """Analyze keywords from papers."""
        if not papers:
            return []

        # Split papers into current and previous period
        cutoff = datetime.now() - timedelta(days=days // 2)

        current_papers = [p for p in papers if p.created_at >= cutoff]
        previous_papers = [p for p in papers if p.created_at < cutoff]

        # Count keywords
        current_counts = Counter()
        previous_counts = Counter()

        for paper in current_papers:
            for kw in paper.keywords:
                current_counts[kw.lower()] += 1

        for paper in previous_papers:
            for kw in paper.keywords:
                previous_counts[kw.lower()] += 1

        # Calculate trends
        trends = []
        for keyword, count in current_counts.most_common(50):
            if count < self.min_count:
                continue

            prev_count = previous_counts.get(keyword, 0)

            if prev_count > 0:
                trend_percent = ((count - prev_count) / prev_count) * 100
            else:
                trend_percent = 100.0 if count > 0 else 0.0

            trends.append(TrendKeyword(
                keyword=keyword,
                count=count,
                trend_percent=round(trend_percent, 1),
            ))

        # Sort by trend percentage (descending)
        trends.sort(key=lambda x: x.trend_percent, reverse=True)

        return trends[:20]

    def get_hot_topics(self, days: int = 7, top_n: int = 10) -> list[dict[str, Any]]:
        """Get hot topics with details.

        Args:
            days: Analysis period
            top_n: Number of topics to return

        Returns:
            List of topic dicts with keyword, count, trend, papers
        """
        trends = self.detect_trends(days)
        papers = self.db.get_recent_papers(days=days, limit=200)

        topics = []
        for trend in trends[:top_n]:
            # Find related papers
            related_papers = [
                p for p in papers
                if trend.keyword in [k.lower() for k in p.keywords]
            ][:5]

            topics.append({
                "keyword": trend.keyword,
                "count": trend.count,
                "trend_percent": trend.trend_percent,
                "papers": [
                    {
                        "id": p.paper_id,
                        "title": p.title,
                        "arxiv_id": p.arxiv_id,
                    }
                    for p in related_papers
                ],
            })

        return topics

    def store_keyword_counts(self, papers: list[Paper], date: Optional[str] = None) -> None:
        """Store keyword counts for a date.

        Args:
            papers: Papers to extract keywords from
            date: Date string (YYYY-MM-DD), defaults to today
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        # Count keywords
        counts = Counter()
        for paper in papers:
            for kw in paper.keywords:
                counts[kw.lower()] += 1

        # Store in database
        for keyword, count in counts.items():
            self.db.insert_keyword(keyword, count, date)

    def detect_emerging_topics(self, days: int = 14) -> list[dict[str, Any]]:
        """Detect newly emerging topics.

        Args:
            days: Analysis period

        Returns:
            List of emerging topics
        """
        all_trends = self.detect_trends(days)

        # Filter for high-growth keywords
        emerging = [
            {
                "keyword": t.keyword,
                "count": t.count,
                "growth": t.trend_percent,
            }
            for t in all_trends
            if t.trend_percent >= 50  # 50%+ growth
        ]

        return emerging[:10]

    def get_keyword_summary(self) -> dict[str, Any]:
        """Get overall keyword statistics.

        Returns:
            Summary dict
        """
        # Get recent trends
        weekly_trends = self.detect_trends(7)
        monthly_trends = self.detect_trends(30)

        return {
            "weekly_top_keywords": [
                {"keyword": t.keyword, "count": t.count, "trend": t.trend_percent}
                for t in weekly_trends[:10]
            ],
            "monthly_top_keywords": [
                {"keyword": t.keyword, "count": t.count, "trend": t.trend_percent}
                for t in monthly_trends[:10]
            ],
            "emerging_topics": self.detect_emerging_topics(),
        }