"""
Dynamic Sitemap Generation API
Optimized for Cloudflare CDN caching and Railway backend
Handles thousands of pages with Redis/SQLite caching
"""

from fastapi import APIRouter, Response, HTTPException, Depends, Request
from fastapi.responses import Response as XMLResponse
from supabase import Client
from datetime import datetime, timezone
from typing import List, Optional, Dict
from pydantic import BaseModel
import xml.etree.ElementTree as ET
import hashlib
import json
import os
from functools import lru_cache
import asyncio
from redis import Redis
import aioredis

router = APIRouter(prefix="/sitemap", tags=["sitemap"])

# Configuration
SITE_URL = "https://testoza.com"
MAX_URLS_PER_SITEMAP = 45000  # Google limit
CACHE_TTL_SECONDS = 3600  # 1 hour
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Initialize Redis client (for Railway deployment)
redis_client: Optional[Redis] = None

async def get_redis() -> Optional[aioredis.Redis]:
    """Get Redis connection for caching"""
    global redis_client
    if redis_client is None:
        try:
            redis_client = await aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        except Exception as e:
            print(f"Redis connection failed: {e}")
            return None
    return redis_client

class SitemapConfig:
    """Sitemap configuration for different content types"""
    
    STATIC_PAGES = [
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        {"loc": "/pricing", "priority": "0.8", "changefreq": "weekly"},
        {"loc": "/support", "priority": "0.7", "changefreq": "monthly"},
        {"loc": "/about", "priority": "0.6", "changefreq": "monthly"},
        {"loc": "/privacy-policy", "priority": "0.3", "changefreq": "yearly"},
        {"loc": "/terms-and-conditions", "priority": "0.3", "changefreq": "yearly"},
        {"loc": "/tests", "priority": "0.9", "changefreq": "daily"},
    ]
    
    DISALLOWED_PATHS = [
        "/live/", "/admin", "/manage-tests", "/my-tests", "/history",
        "/results", "/create-test", "/edit-test/", "/generate-with-ai",
        "/dashboard", "/profile", "/settings", "/materials",
        "/notifications", "/update-password", "/onboarding", "/test-submitted", "/login"
    ]

class CacheManager:
    """Manages sitemap caching with Redis fallback to memory"""
    
    def __init__(self):
        self._memory_cache: Dict[str, tuple] = {}  # (content, timestamp)
    
    async def get(self, key: str) -> Optional[str]:
        """Get cached content"""
        # Try Redis first
        redis = await get_redis()
        if redis:
            cached = await redis.get(key)
            if cached:
                return cached
        
        # Fallback to memory cache
        if key in self._memory_cache:
            content, timestamp = self._memory_cache[key]
            if (datetime.now(timezone.utc) - timestamp).seconds < CACHE_TTL_SECONDS:
                return content
            else:
                del self._memory_cache[key]
        
        return None
    
    async def set(self, key: str, content: str, ttl: int = CACHE_TTL_SECONDS):
        """Set cached content"""
        # Try Redis first
        redis = await get_redis()
        if redis:
            await redis.setex(key, ttl, content)
        
        # Also store in memory as fallback
        self._memory_cache[key] = (content, datetime.now(timezone.utc))
    
    async def invalidate(self, pattern: str = "sitemap:*"):
        """Invalidate cache by pattern"""
        redis = await get_redis()
        if redis:
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
        
        # Clear memory cache
        self._memory_cache.clear()

cache_manager = CacheManager()

def escape_xml(text: str) -> str:
    """Escape XML special characters"""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))

def generate_url_element(url_data: dict) -> ET.Element:
    """Generate a single URL element for sitemap"""
    url_elem = ET.Element("url")
    
    loc = ET.SubElement(url_elem, "loc")
    loc.text = url_data["loc"] if url_data["loc"].startswith("http") else f"{SITE_URL}{url_data['loc']}"
    
    if "lastmod" in url_data:
        lastmod = ET.SubElement(url_elem, "lastmod")
        lastmod.text = url_data["lastmod"]
    
    if "changefreq" in url_data:
        changefreq = ET.SubElement(url_elem, "changefreq")
        changefreq.text = url_data["changefreq"]
    
    if "priority" in url_data:
        priority = ET.SubElement(url_elem, "priority")
        priority.text = url_data["priority"]
    
    # Add image if present
    if "image" in url_data:
        image = ET.SubElement(url_elem, "{http://www.google.com/schemas/sitemap-image/1.1}image")
        image_loc = ET.SubElement(image, "{http://www.google.com/schemas/sitemap-image/1.1}loc")
        image_loc.text = url_data["image"]
        if "image_title" in url_data:
            image_title = ET.SubElement(image, "{http://www.google.com/schemas/sitemap-image/1.1}title")
            image_title.text = escape_xml(url_data["image_title"])
    
    return url_elem

def build_sitemap_xml(urls: List[dict]) -> str:
    """Build complete sitemap XML"""
    root = ET.Element("urlset")
    root.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:image", "http://www.google.com/schemas/sitemap-image/1.1")
    root.set("xsi:schemaLocation", 
              "http://www.sitemaps.org/schemas/sitemap/0.9 "
              "http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd")
    
    for url_data in urls:
        url_elem = generate_url_element(url_data)
        root.append(url_elem)
    
    # Convert to string with proper formatting
    xml_string = ET.tostring(root, encoding="unicode")
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    
    return xml_declaration + xml_string

def build_sitemap_index(sitemaps: List[dict]) -> str:
    """Build sitemap index XML"""
    root = ET.Element("sitemapindex")
    root.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    for sitemap_data in sitemaps:
        sitemap_elem = ET.SubElement(root, "sitemap")
        
        loc = ET.SubElement(sitemap_elem, "loc")
        loc.text = sitemap_data["loc"]
        
        lastmod = ET.SubElement(sitemap_elem, "lastmod")
        lastmod.text = sitemap_data.get("lastmod", today)
    
    xml_string = ET.tostring(root, encoding="unicode")
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    
    return xml_declaration + xml_string

# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("/index.xml", response_class=XMLResponse)
async def get_sitemap_index(request: Request):
    """
    Main sitemap index file
    Lists all sub-sitemaps for different content types
    Cached: 1 hour
    """
    cache_key = "sitemap:index"
    
    # Check cache
    cached = await cache_manager.get(cache_key)
    if cached:
        return XMLResponse(
            content=cached,
            media_type="application/xml",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Cache": "HIT"
            }
        )
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    sitemaps = [
        {"loc": f"{SITE_URL}/sitemap/static.xml", "lastmod": today},
        {"loc": f"{SITE_URL}/sitemap/tests.xml", "lastmod": today},
        {"loc": f"{SITE_URL}/sitemap/categories.xml", "lastmod": today},
        {"loc": f"{SITE_URL}/sitemap/tags.xml", "lastmod": today},
        {"loc": f"{SITE_URL}/sitemap/creators.xml", "lastmod": today},
    ]
    
    xml_content = build_sitemap_index(sitemaps)
    
    # Cache the result
    await cache_manager.set(cache_key, xml_content)
    
    return XMLResponse(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Cache": "MISS"
        }
    )

@router.get("/static.xml", response_class=XMLResponse)
async def get_static_sitemap(request: Request):
    """
    Static pages sitemap
    Home, pricing, support, about, legal pages
    Cached: 24 hours (static content rarely changes)
    """
    cache_key = "sitemap:static"
    
    cached = await cache_manager.get(cache_key)
    if cached:
        return XMLResponse(
            content=cached,
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=86400", "X-Cache": "HIT"}
        )
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    urls = []
    for page in SitemapConfig.STATIC_PAGES:
        urls.append({
            **page,
            "lastmod": today
        })
    
    xml_content = build_sitemap_xml(urls)
    await cache_manager.set(cache_key, xml_content, ttl=86400)  # 24 hours
    
    return XMLResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=86400", "X-Cache": "MISS"}
    )

@router.get("/tests.xml", response_class=XMLResponse)
async def get_tests_sitemap(
    request: Request,
    db: Client = Depends(get_db)
):
    """
    Dynamic tests sitemap
    Fetches all public tests from Supabase
    Cached: 1 hour
    """
    cache_key = "sitemap:tests"
    
    cached = await cache_manager.get(cache_key)
    if cached:
        return XMLResponse(
            content=cached,
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "HIT"}
        )
    
    # Fetch public tests
    try:
        result = db.table("tests").select(
            "id, slug, title, created_at, updated_at, is_public, visibility"
        ).eq("is_public", True).neq("visibility", "private").execute()
        
        tests = result.data if result else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    urls = []
    for test in tests:
        # Use slug if available, otherwise ID-based URL
        url_path = f"/test/{test['slug']}" if test.get('slug') else f"/test-intro/{test['id']}"
        
        # Use updated_at if available, otherwise created_at
        lastmod = test.get('updated_at') or test.get('created_at')
        if lastmod:
            lastmod = lastmod[:10]  # Format: YYYY-MM-DD
        else:
            lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        urls.append({
            "loc": f"{SITE_URL}{url_path}",
            "lastmod": lastmod,
            "changefreq": "monthly",
            "priority": "0.8",
            "image": f"{SITE_URL}/default-og.png",
            "image_title": test.get('title', 'Test')[:100]  # Limit title length
        })
    
    xml_content = build_sitemap_xml(urls)
    await cache_manager.set(cache_key, xml_content)
    
    return XMLResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"}
    )

@router.get("/categories.xml", response_class=XMLResponse)
async def get_categories_sitemap(
    request: Request,
    db: Client = Depends(get_db)
):
    """
    Categories sitemap
    Fetches all categories from Supabase
    Cached: 6 hours (categories change infrequently)
    """
    cache_key = "sitemap:categories"
    
    cached = await cache_manager.get(cache_key)
    if cached:
        return XMLResponse(
            content=cached,
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=21600", "X-Cache": "HIT"}
        )
    
    try:
        result = db.table("categories").select("id, name, slug").execute()
        categories = result.data if result else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    urls = []
    for category in categories:
        slug = category.get('slug') or category['name'].lower().replace(' ', '-')
        urls.append({
            "loc": f"{SITE_URL}/tests/{slug}",
            "lastmod": today,
            "changefreq": "weekly",
            "priority": "0.7"
        })
    
    xml_content = build_sitemap_xml(urls)
    await cache_manager.set(cache_key, xml_content, ttl=21600)  # 6 hours
    
    return XMLResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=21600", "X-Cache": "MISS"}
    )

@router.get("/tags.xml", response_class=XMLResponse)
async def get_tags_sitemap(
    request: Request,
    db: Client = Depends(get_db)
):
    """
    Tags sitemap
    Fetches all tags from Supabase
    Cached: 6 hours
    """
    cache_key = "sitemap:tags"
    
    cached = await cache_manager.get(cache_key)
    if cached:
        return XMLResponse(
            content=cached,
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=21600", "X-Cache": "HIT"}
        )
    
    try:
        # Assuming you have a tags table or tags are stored in tests
        # Adjust query based on your actual schema
        result = db.table("tags").select("id, name, slug").execute()
        tags = result.data if result else []
    except Exception as e:
        # If tags table doesn't exist, return empty sitemap
        tags = []
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    urls = []
    for tag in tags:
        slug = tag.get('slug') or tag['name'].lower().replace(' ', '-')
        urls.append({
            "loc": f"{SITE_URL}/tag/{slug}",
            "lastmod": today,
            "changefreq": "weekly",
            "priority": "0.6"
        })
    
    xml_content = build_sitemap_xml(urls)
    await cache_manager.set(cache_key, xml_content, ttl=21600)
    
    return XMLResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=21600", "X-Cache": "MISS"}
    )

@router.get("/creators.xml", response_class=XMLResponse)
async def get_creators_sitemap(
    request: Request,
    db: Client = Depends(get_db)
):
    """
    Creators/Profiles sitemap
    Fetches all public creator profiles
    Cached: 6 hours
    """
    cache_key = "sitemap:creators"
    
    cached = await cache_manager.get(cache_key)
    if cached:
        return XMLResponse(
            content=cached,
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=21600", "X-Cache": "HIT"}
        )
    
    try:
        # Fetch verified creators or those with public tests
        result = db.table("profiles").select(
            "id, full_name, is_creator"
        ).eq("is_creator", True).execute()
        
        creators = result.data if result else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    urls = []
    for creator in creators:
        urls.append({
            "loc": f"{SITE_URL}/creator/{creator['id']}",
            "lastmod": today,
            "changefreq": "weekly",
            "priority": "0.6"
        })
    
    xml_content = build_sitemap_xml(urls)
    await cache_manager.set(cache_key, xml_content, ttl=21600)
    
    return XMLResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=21600", "X-Cache": "MISS"}
    )

@router.post("/invalidate")
async def invalidate_sitemap_cache(
    sitemap_type: Optional[str] = None,
    secret: str = None
):
    """
    Invalidate sitemap cache
    Requires secret key for security
    Call this when new content is published
    """
    expected_secret = os.getenv("SITEMAP_INVALIDATE_SECRET")
    
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid secret")
    
    if sitemap_type:
        await cache_manager.invalidate(f"sitemap:{sitemap_type}")
        return {"message": f"Cache invalidated for {sitemap_type}"}
    else:
        await cache_manager.invalidate("sitemap:*")
        return {"message": "All sitemap caches invalidated"}

# Health check endpoint
@router.get("/health")
async def sitemap_health():
    """Health check for sitemap service"""
    redis = await get_redis()
    return {
        "status": "healthy",
        "redis_connected": redis is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
