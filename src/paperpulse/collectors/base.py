"""Base collector class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from ..storage.models import Author, Paper, PaperSource


class BaseCollector(ABC):
    """Abstract base class for paper collectors."""

    source: PaperSource = PaperSource.ARXIV

    @abstractmethod
    def collect(self, **kwargs) -> list[Paper]:
        """Collect papers from the source."""
        pass

    @abstractmethod
    def get_recent(self, days: int = 1, **kwargs) -> list[Paper]:
        """Get recent papers from the source."""
        pass

    def _parse_date(self, date_str: str, fmt: str = "%Y-%m-%d") -> Optional[datetime]:
        """Parse date string."""
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            return None

    def _clean_text(self, text: str) -> str:
        """Clean text by removing extra whitespace."""
        if not text:
            return ""
        return " ".join(text.split())