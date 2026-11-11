import asyncio
import aiohttp
import feedparser
import hashlib
import trafilatura
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin, urlparse
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import SessionLocal, KnowledgeItem, RssFeed, TargetUrl

class EnhancedCrawler:
    """Combines RSS feeds + Deep URL crawling + Auto-discovery"""
    
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.visited_urls = set()
    
    async def fetch_all_rss_feeds(self):
        """Fetch all active RSS feeds"""
        print("\n📡 Fetching RSS feeds...")
        db = SessionLocal()
        
        feeds = db.query(RssFeed).filter(RssFeed.is_active == True).all()
        new_count = 0
        
        for feed in feeds:
            try:
                print(f"  Reading: {feed.name}...")
                parsed = feedparser.parse(feed.url)
                
                for entry in parsed.entries[:30]:
                    # Check existing
                    exists = db.query(KnowledgeItem).filter(
                        KnowledgeItem.url == entry.link
                    ).first()
                    
                    if not exists:
                        content = entry.summary if hasattr(entry, 'summary') else ''
                        curiosity = self._calculate_curiosity(entry.title, content)
                        
                        knowledge = KnowledgeItem(
                            title=entry.title[:500],
                            url=entry.link,
                            content_hash=hashlib.sha256((entry.title + content[:500]).encode()).hexdigest(),
                            content_text=content[:10000],
                            content_summary=content[:300],
                            author=feed.name,
                            source_type='rss',
                            content_type=feed.content_type,
                            primary_field=feed.field,
                            discovered_date=datetime.now(),
                            curiosity_score=curiosity
                        )
                        db.add(knowledge)
                        new_count += 1
                
                db.commit()
                print(f"    ✅ Added {len(parsed.entries[:30])} items")
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"    ❌ Error: {e}")
        
        db.close()
        print(f"📚 Total new RSS items: {new_count}")
        return new_count
    
    async def crawl_url_deeply(self, url: str, max_depth: int = 3, current_depth: int = 0):
        """Crawl a URL deeply including archives/old content"""
        if current_depth > max_depth or url in self.visited_urls:
            return []
        
        self.visited_urls.add(url)
        results = []
        
        try:
            print(f"  {'  ' * current_depth}🔍 Depth {current_depth}: {url[:80]}...")
            response = requests.get(url, headers=self.headers, timeout=30)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract content
            title = soup.find('title')
            title_text = title.text.strip() if title else 'Untitled'
            
            paragraphs = soup.find_all('p')
            content = ' '.join([p.text for p in paragraphs[:30]])
            
            # Extract date
            published_date = self._extract_date(soup)
            
            # Extract image
            img_tag = soup.find('img')
            image_url = img_tag.get('src') if img_tag else None
            if image_url and not image_url.startswith('http'):
                image_url = urljoin(url, image_url)
            
            curiosity = self._calculate_curiosity(title_text, content)
            
            # Save to database
            db = SessionLocal()
            exists = db.query(KnowledgeItem).filter(KnowledgeItem.url == url).first()
            
            if not exists and len(content) > 100:  # Only save if substantial content
                knowledge = KnowledgeItem(
                    title=title_text[:500],
                    url=url,
                    content_hash=hashlib.sha256((title_text + content[:500]).encode()).hexdigest(),
                    content_text=content[:10000],
                    content_summary=content[:300],
                    source_type='crawled',
                    content_type='writing',  # Can be updated later
                    publication_date=published_date,
                    discovered_date=datetime.now(),
                    curiosity_score=curiosity,
                    image_url=image_url
                )
                db.add(knowledge)
                db.commit()
                results.append({'url': url, 'title': title_text, 'depth': current_depth})
            
            db.close()
            
            # Recursively crawl links for archive content
            if current_depth < max_depth:
                links = self._extract_internal_links(soup, url)
                for link in links[:15]:  # Limit to 15 per page
                    sub_results = await self.crawl_url_deeply(link, max_depth, current_depth + 1)
                    results.extend(sub_results)
                    await asyncio.sleep(0.3)
            
        except Exception as e:
            print(f"    ❌ Error: {e}")
        
        return results
    
    def _extract_internal_links(self, soup, base_url):
        """Extract internal links from page"""
        links = []
        base_domain = urlparse(base_url).netloc
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            
            if urlparse(full_url).netloc == base_domain:
                # Skip non-content patterns
                skip = ['login', 'signup', 'register', 'cart', 'checkout', 
                       'comment', 'reply', 'feed', 'rss', 'print', 'pdf', 'tag', 'category']
                if not any(p in full_url.lower() for p in skip):
                    links.append(full_url)
        
        return list(set(links))[:30]
    
    def _extract_date(self, soup):
        """Extract publication date"""
        # Meta tags
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            if meta.get('property') in ['article:published_time', 'datePublished']:
                return meta.get('content')
        
        # Common patterns
        import re
        text = soup.get_text()
        patterns = [r'\d{4}-\d{2}-\d{2}', r'\d{2}/\d{2}/\d{4}', r'[A-Za-z]+\s\d{1,2},\s\d{4}']
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()
        
        return None
    
    def _calculate_curiosity(self, title, content):
        """Calculate curiosity score"""
        score = 0.5
        exciting = ['discovery', 'breakthrough', 'amazing', 'why', 'how', 'secret', 
                   'mystery', 'surprising', 'incredible', 'fascinating', 'new']
        
        text = (title + ' ' + content).lower()
        for word in exciting:
            if word in text:
                score += 0.05
        
        if '?' in text:
            score += 0.1
        if len(title) > 60:
            score += 0.05
        
        return min(score, 1.0)
    
    async def add_target_url(self, url: str, depth: int = 3):
        """Add URL to crawl queue"""
        db = SessionLocal()
        exists = db.query(TargetUrl).filter(TargetUrl.url == url).first()
        
        if not exists:
            target = TargetUrl(url=url, crawl_depth=depth, status='pending')
            db.add(target)
            db.commit()
            db.close()
            return True
        db.close()
        return False
    
    async def crawl_pending_urls(self):
        """Crawl all pending user URLs"""
        print("\n🔍 Checking pending URLs...")
        db = SessionLocal()
        
        pending = db.query(TargetUrl).filter(TargetUrl.status == 'pending').all()
        
        for target in pending:
            print(f"\n🌐 Crawling: {target.url} (depth {target.crawl_depth})")
            self.visited_urls = set()
            
            results = await self.crawl_url_deeply(target.url, max_depth=target.crawl_depth)
            
            target.status = 'completed' if results else 'failed'
            target.last_crawled = datetime.now()
            db.commit()
            
            print(f"   ✅ Crawled {len(results)} pages")
            await asyncio.sleep(2)
        
        db.close()
    
    async def run_all(self):
        """Run all crawling tasks"""
        print("="*60)
        print("🤖 ENHANCED CRAWLER STARTING")
        print("="*60)
        
        await self.fetch_all_rss_feeds()
        await self.crawl_pending_urls()
        
        print("\n✅ Crawler finished!")
        print("="*60)