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


def _convert_latex_equations_to_notion(content: str) -> str:
    """Convert LaTeX equations to Notion-compatible format.
    
    Notion Markdown API format:
    - Inline equations: $...$ (kept as-is, Notion handles directly)
    - Block equations: $$...$$ to math code block
    
    Args:
        content: Markdown content with LaTeX equations
    
    Returns:
        Content with Notion-compatible equation format
    """
    import re
    
    # Convert block equations $$...$$ to ```math ... ```
    block_pattern = r'\$\$([\s\S]*?)\$\$'
    
    def replace_block_eq(match):
        eq_content = match.group(1).strip()
        return "```math\n" + eq_content + "\n```"
    
    content = re.sub(block_pattern, replace_block_eq, content)
    
    # Inline equations $...$ are handled directly by Notion
    # No conversion needed
    
    return content


def _convert_markdown_to_notion(content: str) -> str:
    """Convert Markdown content to Notion-compatible format.
    
    Handles:
    - LaTeX equations (inline and block)
    - Other Markdown elements that need conversion
    
    Args:
        content: Original Markdown content
    
    Returns:
        Notion-compatible content
    """
    # Convert equations
    content = _convert_latex_equations_to_notion(content)
    
    return content


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
        notion_config: Optional[Any] = None,  # NotionConfig from config.py
    ):
        """Initialize Notion sync.
        
        Args:
            api_key: Notion integration token (or read from NOTION_API_KEY env)
            target_page: Target page title or ID to sync to
            target_database: Target database title or ID (optional)
            create_new_pages: Create new pages instead of appending
            clear_previous: Clear previous pages with same title
            rate_limit_delay: Delay between API calls (seconds)
            notion_config: NotionConfig object with category rules and tags
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
        self.notion_config = notion_config
        
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
        existing_page_id: Optional[str] = None,  # Update existing page instead of creating new
    ) -> dict:
        """Sync a single Markdown file to Notion.
        
        Args:
            file_path: Path to Markdown file
            title: Page title (extracted from file if not provided)
            target_page: Override target page
            target_database: Override target database
            existing_page_id: If provided, update this page instead of creating new
        
        Returns:
            Result dict with url/success/error
        """
        file_path = Path(file_path).resolve()
        
        # Read file
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            
            # Convert LaTeX equations to Notion format
            content = _convert_markdown_to_notion(content)
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
                # Check if we should update existing page
                if existing_page_id:
                    # Update existing page
                    logger.info(f"Updating existing page: {existing_page_id}")
                    logger.debug(f"Page ID passed from sync_directory: {existing_page_id}")
                    
                    try:
                        # Convert existing_page_id to UUID format if needed
                        page_id = existing_page_id.replace("-", "")
                        
                        # Update page content using markdown API
                        if content:
                            markdown_data = {
                                "type": "replace_content",
                                "replace_content": {
                                    "new_str": content
                                }
                            }
                            await client._http.patch(f"pages/{page_id}/markdown", data=markdown_data)
                        
                        page_url = f"https://www.notion.so/{existing_page_id}"
                        
                        return {
                            "success": True,
                            "url": page_url,
                            "title": title,
                            "file": str(file_path),
                            "updated": True,
                        }
                    except Exception as e:
                        logger.error(f"Failed to update page: {e}")
                        return {"success": False, "error": f"Failed to update page: {e}"}
                
                # Create new page (no existing_page_id provided)
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
                from datetime import datetime
                
                slug_base = re.sub(r'[^a-zA-Z0-9\-]', '-', title.lower())[:50]
                slug_base = re.sub(r'-+', '-', slug_base).strip('-')
                
                # Use config for category and tags (if available)
                if self.notion_config:
                    category = self.notion_config.detect_category(title)
                    tag_keywords = self.notion_config.extract_tags(title)
                    summary_max_length = self.notion_config.summary_max_length
                    max_tags = self.notion_config.max_tags_per_page
                else:
                    # Fallback to hardcoded defaults (backward compatibility)
                    category = "Research"
                    title_lower = title.lower()
                    if any(kw in title_lower for kw in ['ai', 'llm', 'agent', 'neural', 'deep', 'machine learning', 'benchmark']):
                        category = "AI"
                    elif any(kw in title_lower for kw in ['compiler', 'cgra', 'scheduling', 'optimization', 'hardware']):
                        category = "Compiler"
                    elif any(kw in title_lower for kw in ['math', 'proof', 'equation', 'theorem', 'hyperbolic', 'particle', 'plasma']):
                        category = "Math"
                    elif any(kw in title_lower for kw in ['system', 'os', 'infrastructure', 'distributed']):
                        category = "System"
                    
                    common_tags = ['AI', 'LLM', 'Agent', 'Compiler', 'CGRA', 'Scheduling', 
                                   'Optimization', 'Research', 'Survey', 'Benchmark', 'Math']
                    tag_keywords = []
                    for tag in common_tags:
                        if tag.lower() in title_lower:
                            tag_keywords.append(tag)
                    if not tag_keywords:
                        tag_keywords = ['Research']
                    summary_max_length = 150
                    max_tags = 5
                
                # Generate summary from content
                summary = ""
                for line in content.split('\n')[:20]:
                    if line and not line.startswith('#') and len(line) > 50:
                        summary = line[:200].strip()
                        break
                
                create_data = {
                    "parent": {"data_source_id": ds_id_str},
                    "properties": {
                        "title": {
                            "title": [{"text": {"content": title}}]
                        },
                        # NotionNext required properties for blog posts
                        "type": {"select": {"name": "Post"}},
                        "status": {"select": {"name": "Published"}},
                        "slug": {"rich_text": [{"text": {"content": slug_base}}]},
                        "date": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
                        "category": {"select": {"name": category}},
                        "tags": {"multi_select": [{"name": t} for t in tag_keywords[:max_tags]]},
                        "summary": {"rich_text": [{"text": {"content": summary[:summary_max_length] if summary else title[:summary_max_length]}}]}
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
        skip_existing: bool = True,  # Skip already synced files
        sync_records_path: Optional[str] = None,  # Path to sync records file
    ) -> list[dict]:
        """Sync all Markdown files in a directory.
        
        Args:
            dir_path: Directory path
            pattern: File pattern (default *.md)
            recursive: Search recursively
            target_page: Override target page
            target_database: Override target database
            skip_existing: Skip files that have already been synced
            sync_records_path: Path to sync records JSON file
        
        Returns:
            List of results
        """
        import json
        from datetime import datetime
        
        dir_path = Path(dir_path).resolve()
        
        # Load sync records
        sync_records_file = Path(sync_records_path or "data/notion_sync_records.json")
        sync_records = {}
        if sync_records_file.exists():
            try:
                sync_records = json.loads(sync_records_file.read_text())
            except Exception:
                sync_records = {"synced_files": {}}
        else:
            sync_records = {"synced_files": {}}
        
        synced_files = sync_records.get("synced_files", {})
        
        # Find files
        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))
        
        if not files:
            logger.warning(f"No files found in {dir_path} matching {pattern}")
            return []
        
        # Filter already synced files if skip_existing
        if skip_existing:
            new_files = []
            skipped_files = []
            for f in files:
                file_key = str(f.relative_to(dir_path))
                if file_key in synced_files:
                    skipped_files.append(f)
                else:
                    new_files.append(f)
            
            if skipped_files:
                logger.info(f"Skipping {len(skipped_files)} already synced files")
            
            files = new_files
        else:
            # --force mode: update existing pages instead of creating new
            # Extract page_id from URL for each synced file
            import re
            for file_key, record in synced_files.items():
                url = record.get("url", "")
                if url:
                    # Extract page_id from URL
                    # URL format: https://www.notion.so/[title-]page_id
                    # page_id can be UUID format (with dashes) or 32 hex chars (without dashes)
                    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$', url)
                    if match:
                        page_id = match.group(1)
                    else:
                        match = re.search(r'([a-f0-9]{32})$', url)
                        if match:
                            raw_id = match.group(1)
                            page_id = f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"
                    if match:
                        record["page_id"] = page_id
                        logger.debug(f"Extracted page_id for {file_key}: {page_id}")
            
            logger.info(f"Force mode: Will update existing pages if found")
        
        if not files:
            logger.info("All files already synced, nothing to do")
            return []
        
        results = []
        total = len(files)
        
        if skip_existing:
            logger.info(f"Syncing {total} new files from {dir_path}")
        else:
            logger.info(f"Syncing {total} files (new or update existing)")
        
        for i, file in enumerate(files, 1):
            logger.info(f"  [{i}/{total}] {file.name}...")
            
            # Check if file was previously synced
            file_key = str(file.relative_to(dir_path))
            existing_page_id = synced_files.get(file_key, {}).get("page_id") if not skip_existing else None
            
            result = await self.sync_file(
                str(file),
                target_page=target_page,
                target_database=target_database,
                existing_page_id=existing_page_id,
            )
            
            if result.get("success"):
                logger.info(f"    ✅ {result.get('url', '')}")
                
                # Record sync
                file_key = str(file.relative_to(dir_path))
                url = result.get("url", "")
                
                # Extract page_id from URL and save
                page_id = None
                if url:
                    # Handle both UUID format (with dashes) and 32-char format (without dashes)
                    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$', url)
                    if match:
                        page_id = match.group(1)
                    else:
                        match = re.search(r'([a-f0-9]{32})$', url)
                        if match:
                            raw_id = match.group(1)
                            page_id = f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"
                
                synced_files[file_key] = {
                    "url": url,
                    "title": result.get("title", ""),
                    "synced_at": datetime.now().isoformat(),
                    "file_path": str(file),
                    "page_id": page_id,
                }
            else:
                logger.error(f"    ❌ {result.get('error', 'Unknown error')}")
            
            results.append(result)
            
            # Rate limit
            if i < total:
                await asyncio.sleep(self.rate_limit_delay)
        
        # Save sync records
        sync_records["synced_files"] = synced_files
        sync_records_file.parent.mkdir(parents=True, exist_ok=True)
        sync_records_file.write_text(json.dumps(sync_records, indent=2), encoding="utf-8")
        logger.info(f"Saved sync records to {sync_records_file}")
        
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