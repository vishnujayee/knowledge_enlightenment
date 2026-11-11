"""
CRAWLER ORCHESTRATOR - Runs both EnhancedCrawler and ArchivalCrawler in parallel
Non-blocking, efficient, with batch processing
"""

import asyncio
import time
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawlers.auto_discovery import EnhancedCrawler
from crawlers.archival_crawler import ArchivalCrawler
from models.database import SessionLocal, KnowledgeItem

class CrawlerOrchestrator:
    """
    Manages both crawlers efficiently:
    - Runs in parallel
    - Batch database operations
    - Non-blocking for UI
    - Progress tracking
    """
    
    def __init__(self):
        self.enhanced_crawler = EnhancedCrawler()
        self.archival_crawler = ArchivalCrawler()
        self.is_running = False
        self.progress = {
            'enhanced': {'status': 'idle', 'items': 0},
            'archival': {'status': 'idle', 'items': 0}
        }
    
    async def run_enhanced_crawler_optimized(self):
        """Run enhanced crawler with batch commits"""
        self.progress['enhanced']['status'] = 'running'
        print("\n" + "="*50)
        print("🔷 ENHANCED CRAWLER STARTING (Optimized)")
        print("="*50)
        
        try:
            # Run RSS and URL crawling in parallel within enhanced crawler
            results = await asyncio.gather(
                self.enhanced_crawler.fetch_all_rss_feeds(),
                self.enhanced_crawler.crawl_pending_urls(),
                return_exceptions=True
            )
            
            total_items = sum(r for r in results if isinstance(r, int))
            self.progress['enhanced']['items'] = total_items
            self.progress['enhanced']['status'] = 'completed'
            
            print(f"\n✅ Enhanced crawler complete: {total_items} new items")
            
        except Exception as e:
            print(f"❌ Enhanced crawler error: {e}")
            self.progress['enhanced']['status'] = 'failed'
    
    async def run_archival_crawler_optimized(self):
        """Run archival crawler with rate limiting and batch commits"""
        self.progress['archival']['status'] = 'running'
        print("\n" + "="*50)
        print("🏛️ ARCHIVAL CRAWLER STARTING (All Time Periods)")
        print("="*50)
        
        try:
            # Run archival extractions sequentially but with delays to avoid rate limits
            total_items = 0
            
            # Academic papers (rate limited)
            print("\n📚 Extracting academic papers...")
            papers = await self.archival_crawler.extract_all_time_academic_papers()
            total_items += len(papers)
            await asyncio.sleep(2)
            
            # Science news
            print("\n📰 Extracting science news...")
            news = await self.archival_crawler.extract_all_time_science_news()
            total_items += len(news)
            await asyncio.sleep(2)
            
            # Books
            print("\n📖 Extracting books...")
            books = await self.archival_crawler.extract_all_time_books()
            total_items += len(books)
            await asyncio.sleep(2)
            
            # Patents
            print("\n🔬 Extracting patents...")
            patents = await self.archival_crawler.extract_all_time_patents()
            total_items += len(patents)
            await asyncio.sleep(2)
            
            # Blog archives (Wayback Machine)
            print("\n🕰️ Extracting blog archives...")
            blogs = await self.archival_crawler.extract_blog_archives_via_wayback()
            total_items += len(blogs)
            
            self.progress['archival']['items'] = total_items
            self.progress['archival']['status'] = 'completed'
            
            print(f"\n✅ Archival crawler complete: {total_items} new items")
            
        except Exception as e:
            print(f"❌ Archival crawler error: {e}")
            self.progress['archival']['status'] = 'failed'
    
    async def run_all_crawlers_parallel(self):
        """Run both crawlers in parallel"""
        if self.is_running:
            return {"error": "Crawlers already running"}
        
        self.is_running = True
        print("\n" + "🔥"*30)
        print("STARTING PARALLEL CRAWLING (Both Crawlers)")
        print("🔥"*30)
        
        start_time = time.time()
        
        # Run both crawlers in parallel
        results = await asyncio.gather(
            self.run_enhanced_crawler_optimized(),
            self.run_archival_crawler_optimized(),
            return_exceptions=True
        )
        
        elapsed = time.time() - start_time
        
        print("\n" + "="*60)
        print("📊 CRAWLING SUMMARY")
        print("="*60)
        print(f"⏱️  Total time: {elapsed/60:.1f} minutes")
        print(f"🔷 Enhanced crawler: {self.progress['enhanced']['items']} items ({self.progress['enhanced']['status']})")
        print(f"🏛️ Archival crawler: {self.progress['archival']['items']} items ({self.progress['archival']['status']})")
        print(f"📚 Total new items: {self.progress['enhanced']['items'] + self.progress['archival']['items']}")
        print("="*60)
        
        self.is_running = False
        return self.progress
    
    def get_progress(self):
        """Get current crawling progress"""
        return self.progress