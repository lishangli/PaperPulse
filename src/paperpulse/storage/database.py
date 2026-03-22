"""SQLite database operations for PaperPulse."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .models import (
    Author,
    Idea,
    Paper,
    PaperSource,
    PaperStatus,
    TrendKeyword,
)


class Database:
    """SQLite database manager for PaperPulse."""

    def __init__(self, db_path: str | Path):
        """Initialize database connection."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Initialize database tables."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Papers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,
                abstract TEXT,
                year INTEGER,
                venue TEXT,
                citation_count INTEGER DEFAULT 0,
                doi TEXT,
                arxiv_id TEXT,
                url TEXT,
                source TEXT,
                status TEXT,
                pdf_path TEXT,
                latex_path TEXT,
                markdown_path TEXT,
                keywords TEXT,
                innovations TEXT,
                limitations TEXT,
                created_at TEXT,
                updated_at TEXT,
                published_date TEXT
            )
        """)

        # Ideas table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ideas (
                idea_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                score REAL,
                novelty_score REAL,
                feasibility_score REAL,
                impact_score REAL,
                evidence_score REAL,
                timing_score REAL,
                related_paper_ids TEXT,
                research_directions TEXT,
                is_researched INTEGER DEFAULT 0,
                researchclaw_run_id TEXT,
                created_at TEXT
            )
        """)

        # Keywords trend table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                source TEXT
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_date ON keywords(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword)")

        conn.commit()

    # ================================
    # Paper operations
    # ================================

    def insert_paper(self, paper: Paper) -> None:
        """Insert a new paper."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO papers (
                paper_id, title, authors, abstract, year, venue,
                citation_count, doi, arxiv_id, url, source, status,
                pdf_path, latex_path, markdown_path, keywords,
                innovations, limitations, created_at, updated_at, published_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper.paper_id,
            paper.title,
            json.dumps([{"name": a.name, "affiliation": a.affiliation} for a in paper.authors]),
            paper.abstract,
            paper.year,
            paper.venue,
            paper.citation_count,
            paper.doi,
            paper.arxiv_id,
            paper.url,
            paper.source.value,
            paper.status.value,
            paper.pdf_path,
            paper.latex_path,
            paper.markdown_path,
            json.dumps(paper.keywords),
            json.dumps(paper.innovations),
            json.dumps(paper.limitations),
            paper.created_at.isoformat(),
            paper.updated_at.isoformat(),
            paper.published_date.isoformat() if paper.published_date else None,
        ))
        conn.commit()

    def insert_papers(self, papers: list[Paper]) -> int:
        """Insert multiple papers. Returns count of new papers."""
        for paper in papers:
            self.insert_paper(paper)
        return len(papers)

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        """Get paper by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
        row = cursor.fetchone()

        if row:
            return self._row_to_paper(row)
        return None

    def get_paper_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        """Get paper by arXiv ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,))
        row = cursor.fetchone()

        if row:
            return self._row_to_paper(row)
        return None

    def get_papers(
        self,
        status: Optional[PaperStatus] = None,
        source: Optional[PaperSource] = None,
        year_min: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Paper]:
        """Get papers with filters."""
        conn = self._get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM papers WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if source:
            query += " AND source = ?"
            params.append(source.value)

        if year_min > 0:
            query += " AND year >= ?"
            params.append(year_min)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [self._row_to_paper(row) for row in rows]

    def update_paper(self, paper: Paper) -> None:
        """Update paper."""
        paper.updated_at = datetime.now()
        self.insert_paper(paper)  # INSERT OR REPLACE

    def get_papers_count(self, status: Optional[PaperStatus] = None) -> int:
        """Get total paper count."""
        conn = self._get_conn()
        cursor = conn.cursor()

        if status:
            cursor.execute("SELECT COUNT(*) FROM papers WHERE status = ?", (status.value,))
        else:
            cursor.execute("SELECT COUNT(*) FROM papers")

        return cursor.fetchone()[0]

    def get_recent_papers(self, days: int = 7, limit: int = 100) -> list[Paper]:
        """Get papers from recent days."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM papers
            WHERE date(created_at) >= date('now', ?)
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"-{days} days", limit))

        rows = cursor.fetchall()
        return [self._row_to_paper(row) for row in rows]

    def search_papers(self, query: str, limit: int = 20) -> list[Paper]:
        """Search papers by title or abstract."""
        conn = self._get_conn()
        cursor = conn.cursor()

        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT * FROM papers
            WHERE title LIKE ? OR abstract LIKE ?
            ORDER BY citation_count DESC
            LIMIT ?
        """, (search_pattern, search_pattern, limit))

        rows = cursor.fetchall()
        return [self._row_to_paper(row) for row in rows]

    def _row_to_paper(self, row: sqlite3.Row) -> Paper:
        """Convert database row to Paper object."""
        authors_data = json.loads(row["authors"]) if row["authors"] else []
        authors = [
            Author(name=a.get("name", ""), affiliation=a.get("affiliation", ""))
            for a in authors_data
        ]

        return Paper(
            paper_id=row["paper_id"],
            title=row["title"],
            authors=authors,
            abstract=row["abstract"] or "",
            year=row["year"] or 0,
            venue=row["venue"] or "",
            citation_count=row["citation_count"] or 0,
            doi=row["doi"] or "",
            arxiv_id=row["arxiv_id"] or "",
            url=row["url"] or "",
            source=PaperSource(row["source"]) if row["source"] else PaperSource.ARXIV,
            status=PaperStatus(row["status"]) if row["status"] else PaperStatus.NEW,
            pdf_path=row["pdf_path"] or "",
            latex_path=row["latex_path"] or "",
            markdown_path=row["markdown_path"] or "",
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            innovations=json.loads(row["innovations"]) if row["innovations"] else [],
            limitations=json.loads(row["limitations"]) if row["limitations"] else [],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
            published_date=datetime.fromisoformat(row["published_date"]) if row["published_date"] else None,
        )

    # ================================
    # Idea operations
    # ================================

    def insert_idea(self, idea: Idea) -> None:
        """Insert a new idea."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO ideas (
                idea_id, title, description, score,
                novelty_score, feasibility_score, impact_score,
                evidence_score, timing_score, related_paper_ids,
                research_directions, is_researched, researchclaw_run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            idea.idea_id,
            idea.title,
            idea.description,
            idea.score,
            idea.novelty_score,
            idea.feasibility_score,
            idea.impact_score,
            idea.evidence_score,
            idea.timing_score,
            json.dumps(idea.related_paper_ids),
            json.dumps(idea.research_directions),
            1 if idea.is_researched else 0,
            idea.researchclaw_run_id,
            idea.created_at.isoformat(),
        ))
        conn.commit()

    def get_idea(self, idea_id: str) -> Optional[Idea]:
        """Get idea by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ideas WHERE idea_id = ?", (idea_id,))
        row = cursor.fetchone()

        if row:
            return self._row_to_idea(row)
        return None

    def get_ideas(self, limit: int = 20, offset: int = 0) -> list[Idea]:
        """Get all ideas."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM ideas ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = cursor.fetchall()

        return [self._row_to_idea(row) for row in rows]

    def get_top_ideas(self, min_score: float = 0.0, limit: int = 10) -> list[Idea]:
        """Get top ideas by score."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM ideas WHERE score >= ? ORDER BY score DESC LIMIT ?",
            (min_score, limit)
        )
        rows = cursor.fetchall()

        return [self._row_to_idea(row) for row in rows]

    def _row_to_idea(self, row: sqlite3.Row) -> Idea:
        """Convert database row to Idea object."""
        return Idea(
            idea_id=row["idea_id"],
            title=row["title"],
            description=row["description"] or "",
            score=row["score"] or 0.0,
            novelty_score=row["novelty_score"] or 0.0,
            feasibility_score=row["feasibility_score"] or 0.0,
            impact_score=row["impact_score"] or 0.0,
            evidence_score=row["evidence_score"] or 0.0,
            timing_score=row["timing_score"] or 0.0,
            related_paper_ids=json.loads(row["related_paper_ids"]) if row["related_paper_ids"] else [],
            research_directions=json.loads(row["research_directions"]) if row["research_directions"] else [],
            is_researched=bool(row["is_researched"]),
            researchclaw_run_id=row["researchclaw_run_id"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    # ================================
    # Keyword operations
    # ================================

    def insert_keyword(self, keyword: str, count: int, date: str, source: str = "") -> None:
        """Insert keyword count for a date."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO keywords (keyword, count, date, source)
            VALUES (?, ?, ?, ?)
        """, (keyword.lower(), count, date, source))
        conn.commit()

    def get_keyword_trends(self, days: int = 7) -> list[TrendKeyword]:
        """Get keyword trends for recent days."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Get current period keywords
        cursor.execute("""
            SELECT keyword, SUM(count) as total
            FROM keywords
            WHERE date >= date('now', ?)
            GROUP BY keyword
            ORDER BY total DESC
            LIMIT 50
        """, (f"-{days} days",))

        current_keywords = {row["keyword"]: row["total"] for row in cursor.fetchall()}

        # Get previous period keywords
        cursor.execute("""
            SELECT keyword, SUM(count) as total
            FROM keywords
            WHERE date >= date('now', ?) AND date < date('now', ?)
            GROUP BY keyword
        """, (f"-{days * 2} days", f"-{days} days"))

        prev_keywords = {row["keyword"]: row["total"] for row in cursor.fetchall()}

        # Calculate trends
        trends = []
        for keyword, count in current_keywords.items():
            prev_count = prev_keywords.get(keyword, 0)
            if prev_count > 0:
                trend_percent = ((count - prev_count) / prev_count) * 100
            else:
                trend_percent = 100.0 if count > 0 else 0.0

            trends.append(TrendKeyword(
                keyword=keyword,
                count=count,
                trend_percent=round(trend_percent, 1),
            ))

        # Sort by count
        trends.sort(key=lambda x: x.count, reverse=True)
        return trends[:20]

    # ================================
    # Statistics
    # ================================

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()

        stats = {}

        # Paper counts
        cursor.execute("SELECT COUNT(*) FROM papers")
        stats["total_papers"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM papers WHERE status = 'downloaded'")
        stats["downloaded_papers"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM papers WHERE status = 'analyzed'")
        stats["analyzed_papers"] = cursor.fetchone()[0]

        # Idea counts
        cursor.execute("SELECT COUNT(*) FROM ideas")
        stats["total_ideas"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ideas WHERE is_researched = 1")
        stats["researched_ideas"] = cursor.fetchone()[0]

        # Recent activity
        cursor.execute("SELECT COUNT(*) FROM papers WHERE date(created_at) = date('now')")
        stats["papers_today"] = cursor.fetchone()[0]

        return stats

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None