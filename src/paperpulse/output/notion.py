"""Notion sync using notionary library.

This module provides functionality to sync Markdown reports to Notion
using the official Notion API via the notionary library.

Usage:
    from paperpulse.output.notion import NotionSync
    
    sync = NotionSync(api_key="secret_xxx")
    url = await sync.sync_report("report.md", "Paper Analysis")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import notionary to avoid import errors if not installed
_notionary = None


def _get_notionary():
    """Lazy load notionary module."""
    global _notionary
    if _notionary is None:
        try:
            from notionary import Notionary, DataSource, Page
            _notionary = (Notionary, DataSource, Page)
        except ImportError as e:
            raise ImportError(
                "notionary is not installed. "
                "Install it with: pip install notionary or uv pip install notionary"
            ) from e
    return _notionary


class NotionSync:
    """Sync Markdown content to Notion using notionary."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        target_page: Optional[str] = None,
        target_database: Optional[str] = None,
        create_new_pages: bool = True,
        clear_previous: bool = False,
        rate_limit_delay: float = 0.5,
    ):
        """Initialize Notion sync.
        
        Args:
            api_key: Notion integration token (or read from NOTION_API_KEY env)
            target_page: Target page title or ID to sync to
            target_database: Target database title or ID (optional)
            create_new_pages: Create new pages instead of appending
            clear_previous: Clear previous pages with same title
            rate_limit_delay: Delay between API calls (seconds)
        """
        self.api_key = api_key or os.environ.get("NOTION_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "No Notion API key provided. "
                "Set NOTION_API_KEY environment variable or pass api_key parameter."
            )
        
        self.target_page = target_page
        self.target_database = target_database
        self.create_new_pages = create_new_pages
        self.clear_previous = clear_previous
        self.rate_limit_delay = rate_limit_delay
        
        # Notionary client (created lazily)
        self._client = None
    
    async def _get_client(self):
        """Get or create Notionary client."""
        if self._client is None:
            Notionary, _, _ = _get_notionary()
            self._client = Notionary(api_key=self.api_key)
        return self._client
    
    async def close(self):
        """Close the Notionary client."""
        if self._client:
            await self._client.close()
            self._client = None
    
    async def __aenter__(self):
        await self._get_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def sync_file(
        self,
        file_path: str,
        title: Optional[str] = None,
        target_page: Optional[str] = None,
        target_database: Optional[str] = None,
    ) -> dict:
        """Sync a single Markdown file to Notion.
        
        Args:
            file_path: Path to Markdown file
            title: Page title (extracted from file if not provided)
            target_page: Override target page
            target_database: Override target database
        
        Returns:
            Result dict with url/success/error
        """
        file_path = Path(file_path).resolve()
        
        # Read file
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}"}
        
        # Extract title from first # heading
        if not title:
            for line in content.split("\n"):
                if line.startswith("#"):
                    title = line.lstrip("#").strip()
                    break
            if not title:
                title = file_path.stem
        
        # Use provided or default target
        target_page = target_page or self.target_page
        target_database = target_database or self.target_database
        
        if not target_page and not target_database:
            return {"success": False, "error": "No target page or database specified"}
        
        try:
            Notionary, DataSource, Page = _get_notionary()
            client = await self._get_client()
            
            # Find or create target
            page_url = None
            
            if target_database:
                # Use database (DataSource) - Note: Notion uses 'data_source_id' for DataSources
                # First get the data_source info
                ds_id_str = target_database
                
                # Try to find by title first, then use direct ID
                try:
                    # Check if it's a UUID
                    from uuid import UUID
                    try:
                        ds_id = UUID(target_database)
                    except ValueError:
                        # Search by title
                        ds_list = await client.data_sources.list(query=target_database, page_size=10)
                        if not ds_list:
                            return {"success": False, "error": f"Database not found: {target_database}"}
                        ds = ds_list[0]
                        ds_id = ds.id
                        ds_id_str = str(ds_id)
                    
                    # Get data source info directly via HTTP
                    ds_response = await client._http.get(f"data_sources/{ds_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to get data source: {e}")
                    return {"success": False, "error": f"Database not found: {target_database}"}
                
                # Create new page using data_source_id (not database_id)
                # Generate slug from title (remove special chars, lowercase)
                import re
                slug_base = re.sub(r'[^a-zA-Z0-9\-]', '-', title.lower())[:50]
                slug_base = re.sub(r'-+', '-', slug_base).strip('-')
                
                create_data = {
                    "parent": {"data_source_id": ds_id_str},
                    "properties": {
                        "title": {
                            "title": [
                                {"text": {"content": title}}
                            ]
                        },
                        # NotionNext required properties for blog posts
                        "type": {
                            "select": {"name": "Post"}
                        },
                        "status": {
                            "select": {"name": "Published"}
                        },
                        "slug": {
                            "rich_text": [{"text": {"content": slug_base}}]
                        }
                    }
                }
                
                try:
                    result = await client._http.post("pages", data=create_data)
                    page_id = result.get("id")
                    page_url = result.get("url")
                    
                    # Write content using markdown API
                    if content:
                        # Use correct request format
                        markdown_data = {
                            "type": "replace_content",
                            "replace_content": {
                                "new_str": content
                            }
                        }
                        await client._http.patch(f"pages/{page_id}/markdown", data=markdown_data)
                    
                    return {
                        "success": True,
                        "url": page_url,
                        "title": title,
                        "file": str(file_path),
                    }
                except Exception as e:
                    logger.error(f"Failed to create page: {e}")
                    return {"success": False, "error": str(e)}
                
            elif target_page:
                # Use target page
                if self.create_new_pages:
                    # Find parent page and create child
                    try:
                        parent = await client.pages.find(target_page)
                    except Exception:
                        # Try as UUID
                        from uuid import UUID
                        try:
                            parent = await client.pages.from_id(UUID(target_page))
                        except ValueError:
                            return {"success": False, "error": f"Page not found: {target_page}"}
                    
                    # Clear previous if requested
                    if self.clear_previous:
                        # List child pages and remove matching title
                        children = await client.pages.list(query=title, page_size=100)
                        for child in children:
                            if child.title.lower() == title.lower():
                                logger.info(f"Removing previous page: {child.title}")
                                await child.trash()
                                await asyncio.sleep(self.rate_limit_delay)
                    
                    # Note: notionary doesn't have direct create child page API
                    # We need to use data_sources or append to existing page
                    # For now, we'll append to the found page
                    await parent.append(f"\n\n---\n\n# {title}\n\n{content}")
                    page_url = parent.url
                    
                else:
                    # Append to existing page
                    try:
                        page = await client.pages.find(target_page)
                    except Exception:
                        from uuid import UUID
                        try:
                            page = await client.pages.from_id(UUID(target_page))
                        except ValueError:
                            return {"success": False, "error": f"Page not found: {target_page}"}
                    
                    await page.append(f"\n\n---\n\n# {title}\n\n{content}")
                    page_url = page.url
            
            # Rate limit delay
            await asyncio.sleep(self.rate_limit_delay)
            
            return {
                "success": True,
                "url": page_url,
                "title": title,
                "file": str(file_path),
            }
            
        except Exception as e:
            logger.error(f"Notion sync failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def sync_directory(
        self,
        dir_path: str,
        pattern: str = "*.md",
        recursive: bool = False,
        target_page: Optional[str] = None,
        target_database: Optional[str] = None,
    ) -> list[dict]:
        """Sync all Markdown files in a directory.
        
        Args:
            dir_path: Directory path
            pattern: File pattern (default *.md)
            recursive: Search recursively
            target_page: Override target page
            target_database: Override target database
        
        Returns:
            List of results
        """
        dir_path = Path(dir_path).resolve()
        
        # Find files
        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))
        
        if not files:
            logger.warning(f"No files found in {dir_path} matching {pattern}")
            return []
        
        results = []
        total = len(files)
        
        logger.info(f"Syncing {total} files from {dir_path}")
        
        for i, file in enumerate(files, 1):
            logger.info(f"  [{i}/{total}] {file.name}...")
            
            result = await self.sync_file(
                str(file),
                target_page=target_page,
                target_database=target_database,
            )
            
            if result.get("success"):
                logger.info(f"    ✅ {result.get('url', '')}")
            else:
                logger.error(f"    ❌ {result.get('error', 'Unknown error')}")
            
            results.append(result)
            
            # Rate limit
            if i < total:
                await asyncio.sleep(self.rate_limit_delay)
        
        return results
    
    async def test_connection(self) -> dict:
        """Test Notion API connection.
        
        Returns:
            Result dict with success/error and user info
        """
        try:
            Notionary, _, _ = _get_notionary()
            client = await self._get_client()
            
            # Get current user/bot
            me = await client.users.me()
            
            return {
                "success": True,
                "user": me.name if hasattr(me, 'name') else str(me),
                "bot_id": str(me.id) if hasattr(me, 'id') else None,
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def list_pages(self, query: Optional[str] = None) -> list[dict]:
        """List accessible pages.
        
        Args:
            query: Optional search query
        
        Returns:
            List of page info dicts
        """
        try:
            Notionary, _, _ = _get_notionary()
            client = await self._get_client()
            
            pages = await client.pages.list(query=query, page_size=100)
            
            return [
                {
                    "title": page.title,
                    "url": page.url,
                    "id": str(page.id) if hasattr(page, 'id') else None,
                }
                for page in pages
            ]
            
        except Exception as e:
            logger.error(f"Failed to list pages: {e}")
            return []
    
    async def list_data_sources(self, query: Optional[str] = None) -> list[dict]:
        """List accessible data sources (databases).
        
        Args:
            query: Optional search query
        
        Returns:
            List of data source info dicts
        """
        try:
            Notionary, _, _ = _get_notionary()
            client = await self._get_client()
            
            data_sources = await client.data_sources.list(query=query, page_size=100)
            
            return [
                {
                    "title": ds.title,
                    "url": ds.url,
                    "id": str(ds.id) if hasattr(ds, 'id') else None,
                }
                for ds in data_sources
            ]
            
        except Exception as e:
            logger.error(f"Failed to list data sources: {e}")
            return []


def run_sync(
    file_path: Optional[str] = None,
    dir_path: Optional[str] = None,
    api_key: Optional[str] = None,
    target_page: Optional[str] = None,
    target_database: Optional[str] = None,
    pattern: str = "*.md",
    recursive: bool = False,
    rate_limit_delay: float = 0.5,
) -> list[dict]:
    """Run sync synchronously (wrapper for async).
    
    Args:
        file_path: Single file to sync
        dir_path: Directory to sync
        api_key: Notion API key
        target_page: Target page
        target_database: Target database
        pattern: File pattern
        recursive: Search recursively
        rate_limit_delay: Rate limit delay
    
    Returns:
        List of results
    """
    async def _run():
        async with NotionSync(
            api_key=api_key,
            target_page=target_page,
            target_database=target_database,
            rate_limit_delay=rate_limit_delay,
        ) as sync:
            if file_path:
                return [await sync.sync_file(file_path)]
            elif dir_path:
                return await sync.sync_directory(
                    dir_path,
                    pattern=pattern,
                    recursive=recursive,
                )
            else:
                return []
    
    return asyncio.run(_run())


def test_connection(api_key: Optional[str] = None) -> dict:
    """Test Notion API connection synchronously.
    
    Args:
        api_key: Notion API key
    
    Returns:
        Result dict
    """
    async def _test():
        async with NotionSync(api_key=api_key) as sync:
            return await sync.test_connection()
    
    return asyncio.run(_test())


def list_pages(api_key: Optional[str] = None, query: Optional[str] = None) -> list[dict]:
    """List accessible pages synchronously."""
    async def _list():
        async with NotionSync(api_key=api_key) as sync:
            return await sync.list_pages(query=query)
    
    return asyncio.run(_list())


def list_data_sources(api_key: Optional[str] = None, query: Optional[str] = None) -> list[dict]:
    """List accessible data sources synchronously."""
    async def _list():
        async with NotionSync(api_key=api_key) as sync:
            return await sync.list_data_sources(query=query)
    
    return asyncio.run(_list())