"""Data models for PaperPulse."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PaperSource(Enum):
    """Paper source enumeration."""
    ARXIV = "arxiv"
    SEMANTIC_SCHOLOLAR = "semantic_scholar"
    PAPERS_WITH_CODE = "papers_with_code"
    OPENALEX = "openalex"


class DocumentType(Enum):
    """Document type enumeration."""
    LATEX = "latex"
    PDF = "pdf"
    MARKDOWN = "markdown"


class PaperStatus(Enum):
    """Paper processing status."""
    NEW = "new"
    DOWNLOADED = "downloaded"
    CONVERTED = "converted"
    ANALYZED = "analyzed"
    FAILED = "failed"


@dataclass
class Author:
    """Paper author."""
    name: str
    affiliation: str = ""


@dataclass
class Paper:
    """Paper metadata."""
    paper_id: str
    title: str
    authors: list[Author] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    venue: str = ""
    citation_count: int = 0
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    source: PaperSource = PaperSource.ARXIV
    status: PaperStatus = PaperStatus.NEW
    
    # Document paths
    pdf_path: str = ""
    latex_path: str = ""
    markdown_path: str = ""
    
    # Analysis results
    keywords: list[str] = field(default_factory=list)
    innovations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    
    # Notion sync status
    notion_synced: bool = False
    notion_url: str = ""
    notion_synced_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    published_date: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": [{"name": a.name, "affiliation": a.affiliation} for a in self.authors],
            "abstract": self.abstract,
            "year": self.year,
            "venue": self.venue,
            "citation_count": self.citation_count,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "source": self.source.value,
            "status": self.status.value,
            "pdf_path": self.pdf_path,
            "latex_path": self.latex_path,
            "markdown_path": self.markdown_path,
            "keywords": self.keywords,
            "innovations": self.innovations,
            "limitations": self.limitations,
            "notion_synced": self.notion_synced,
            "notion_url": self.notion_url,
            "notion_synced_at": self.notion_synced_at.isoformat() if self.notion_synced_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "published_date": self.published_date.isoformat() if self.published_date else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Paper:
        """Create from dictionary."""
        authors = [
            Author(name=a.get("name", ""), affiliation=a.get("affiliation", ""))
            for a in data.get("authors", [])
        ]
        
        return cls(
            paper_id=data.get("paper_id", ""),
            title=data.get("title", ""),
            authors=authors,
            abstract=data.get("abstract", ""),
            year=data.get("year", 0),
            venue=data.get("venue", ""),
            citation_count=data.get("citation_count", 0),
            doi=data.get("doi", ""),
            arxiv_id=data.get("arxiv_id", ""),
            url=data.get("url", ""),
            source=PaperSource(data.get("source", "arxiv")),
            status=PaperStatus(data.get("status", "new")),
            pdf_path=data.get("pdf_path", ""),
            latex_path=data.get("latex_path", ""),
            markdown_path=data.get("markdown_path", ""),
            keywords=data.get("keywords", []),
            innovations=data.get("innovations", []),
            limitations=data.get("limitations", []),
            notion_synced=data.get("notion_synced", False),
            notion_url=data.get("notion_url", ""),
            notion_synced_at=datetime.fromisoformat(data["notion_synced_at"]) if data.get("notion_synced_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            published_date=datetime.fromisoformat(data["published_date"]) if data.get("published_date") else None,
        )


@dataclass
class Idea:
    """Research idea."""
    idea_id: str
    title: str
    description: str
    score: float = 0.0
    
    # Scoring breakdown
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    impact_score: float = 0.0
    evidence_score: float = 0.0
    timing_score: float = 0.0
    
    # Related papers
    related_paper_ids: list[str] = field(default_factory=list)
    research_directions: list[str] = field(default_factory=list)
    
    # Status
    is_researched: bool = False
    researchclaw_run_id: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "idea_id": self.idea_id,
            "title": self.title,
            "description": self.description,
            "score": self.score,
            "novelty_score": self.novelty_score,
            "feasibility_score": self.feasibility_score,
            "impact_score": self.impact_score,
            "evidence_score": self.evidence_score,
            "timing_score": self.timing_score,
            "related_paper_ids": self.related_paper_ids,
            "research_directions": self.research_directions,
            "is_researched": self.is_researched,
            "researchclaw_run_id": self.researchclaw_run_id,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Idea:
        """Create from dictionary."""
        return cls(
            idea_id=data.get("idea_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            score=data.get("score", 0.0),
            novelty_score=data.get("novelty_score", 0.0),
            feasibility_score=data.get("feasibility_score", 0.0),
            impact_score=data.get("impact_score", 0.0),
            evidence_score=data.get("evidence_score", 0.0),
            timing_score=data.get("timing_score", 0.0),
            related_paper_ids=data.get("related_paper_ids", []),
            research_directions=data.get("research_directions", []),
            is_researched=data.get("is_researched", False),
            researchclaw_run_id=data.get("researchclaw_run_id", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
        )


@dataclass
class TrendKeyword:
    """Trend keyword with statistics."""
    keyword: str
    count: int = 0
    trend_percent: float = 0.0  # Percentage change
    period_start: datetime = field(default_factory=datetime.now)
    period_end: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "count": self.count,
            "trend_percent": self.trend_percent,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
        }