from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from datetime import datetime
from typing import Optional
import sys
import os
import random
import asyncio
from sqlalchemy import func, desc

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.database import SessionLocal, KnowledgeItem, TargetUrl, RssFeed
from crawlers.orchestrator import CrawlerOrchestrator

app = FastAPI(title="Knowledge Infinity - Optimized Parallel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator
orchestrator = CrawlerOrchestrator()

# Track background tasks
active_tasks = set()

@app.on_event("startup")
async def startup_event():
    print("="*60)
    print("📚 KNOWLEDGE INFINITY - PARALLEL CRAWLER VERSION")
    print("="*60)
    print("✅ Server: http://localhost:8000")
    print("="*60)
    
    # Quick RSS fetch on startup (fast, non-blocking)
    asyncio.create_task(quick_rss_fetch())
    
    return {"status": "starting"}

async def quick_rss_fetch():
    """Quick initial RSS fetch (only recent items)"""
    print("📡 Quick initial RSS fetch...")
    try:
        db = SessionLocal()
        feeds = db.query(RssFeed).filter(RssFeed.is_active == True).limit(5).all()
        db.close()
        
        for feed in feeds:
            try:
                import feedparser
                parsed = feedparser.parse(feed.url)
                print(f"  ✅ {feed.name}: {len(parsed.entries[:10])} recent items ready")
            except:
                pass
    except:
        pass

# ============ API ENDPOINTS ============

@app.get("/")
async def serve_frontend():
    """Serve the main UI"""
    html_content = get_ui_html()
    return HTMLResponse(content=html_content)

@app.get("/api/feed")
async def get_feed(limit: int = 20, offset: int = 0):
    """Fast feed retrieval - direct from database"""
    db = SessionLocal()
    try:
        items = db.query(KnowledgeItem).order_by(
            desc(KnowledgeItem.discovered_date)
        ).offset(offset).limit(limit).all()
        db.close()
        
        return [{
            'id': i.id,
            'title': i.title[:200] if i.title else 'Untitled',
            'content_type': getattr(i, 'content_type', 'academic'),
            'source_type': i.source_type or 'unknown',
            'primary_field': i.primary_field or 'general',
            'discovered_date': i.discovered_date.isoformat() if i.discovered_date else datetime.now().isoformat(),
            'curiosity_score': i.curiosity_score or 0.5,
            'summary': (i.content_summary or (i.content_text[:200] if i.content_text else ''))[:150]
        } for i in items]
    except Exception as e:
        print(f"Feed error: {e}")
        db.close()
        return []

@app.get("/api/random")
async def get_random():
    """Fast random retrieval"""
    db = SessionLocal()
    try:
        total = db.query(KnowledgeItem).count()
        
        if total == 0:
            db.close()
            return {"error": "No content yet. Click 'Start Both Crawlers' to begin!"}
        
        offset = random.randint(0, total - 1)
        item = db.query(KnowledgeItem).offset(offset).first()
        db.close()
        
        return {
            'current': {
                'id': item.id,
                'title': item.title or 'Untitled',
                'content': (item.content_text[:2000] if item.content_text else 'No content available'),
                'summary': item.content_summary or '',
                'author': item.author or 'Unknown',
                'source_type': item.source_type or 'unknown',
                'content_type': getattr(item, 'content_type', 'academic'),
                'url': item.url or '',
                'primary_field': item.primary_field or 'general',
                'year': item.publication_date.year if item.publication_date else 'Unknown'
            }
        }
    except Exception as e:
        db.close()
        return {"error": str(e)}

@app.post("/api/crawl/start-all")
async def start_both_crawlers():
    """Start both crawlers in parallel (non-blocking)"""
    if orchestrator.is_running:
        raise HTTPException(400, "Crawlers already running")
    
    # Run in background
    task = asyncio.create_task(orchestrator.run_all_crawlers_parallel())
    active_tasks.add(task)
    task.add_done_callback(active_tasks.discard)
    
    return {
        "message": "Both crawlers started in parallel!",
        "crawlers": ["Enhanced (RSS + Deep URL)", "Archival (1500s → Present)"],
        "note": "UI remains responsive. Check stats for progress."
    }

@app.get("/api/crawl/progress")
async def get_crawl_progress():
    """Get current crawling progress"""
    return orchestrator.get_progress()

@app.get("/api/crawl/status")
async def get_crawl_status():
    """Get crawler status"""
    return {
        'is_running': orchestrator.is_running,
        'active_tasks': len(active_tasks),
        'progress': orchestrator.get_progress()
    }

@app.post("/api/crawl/url")
async def add_crawl_url(url: str, depth: int = 3):
    """Add URL to crawl queue"""
    db = SessionLocal()
    exists = db.query(TargetUrl).filter(TargetUrl.url == url).first()
    
    if exists:
        db.close()
        raise HTTPException(400, "URL already in queue")
    
    target = TargetUrl(url=url, crawl_depth=depth, status='pending')
    db.add(target)
    db.commit()
    db.close()
    
    return {"message": f"URL added! Will crawl to depth {depth}"}

@app.post("/api/knowledge/save/{item_id}")
async def save_for_later(item_id: int):
    db = SessionLocal()
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not item:
        db.close()
        raise HTTPException(404, "Item not found")
    item.saved_for_later = True
    db.commit()
    db.close()
    return {"status": "saved"}

@app.get("/api/knowledge/saved")
async def get_saved():
    db = SessionLocal()
    items = db.query(KnowledgeItem).filter(KnowledgeItem.saved_for_later == True).order_by(desc(KnowledgeItem.discovered_date)).limit(50).all()
    db.close()
    return [{'id': i.id, 'title': i.title or 'Untitled'} for i in items]

@app.get("/api/stats")
async def get_stats():
    db = SessionLocal()
    try:
        total = db.query(KnowledgeItem).count()
        pending = db.query(TargetUrl).filter(TargetUrl.status == 'pending').count()
        
        # Get counts by source type
        by_source = db.query(
            KnowledgeItem.source_type, 
            func.count(KnowledgeItem.id)
        ).group_by(KnowledgeItem.source_type).limit(10).all()
        
        db.close()
        
        return {
            'total_items': total,
            'pending_urls': pending,
            'crawlers_running': orchestrator.is_running,
            'by_source': [{'type': s[0] or 'unknown', 'count': s[1]} for s in by_source]
        }
    except Exception as e:
        db.close()
        return {
            'total_items': 0,
            'pending_urls': 0,
            'crawlers_running': False,
            'by_source': []
        }

@app.get("/api/fields")
async def get_fields():
    db = SessionLocal()
    try:
        fields = db.query(
            KnowledgeItem.primary_field, 
            func.count(KnowledgeItem.id).label('count')
        ).group_by(KnowledgeItem.primary_field).limit(30).all()
        db.close()
        return [{'name': f[0] or 'general', 'count': f[1]} for f in fields if f[0]]
    except Exception as e:
        db.close()
        return []

@app.get("/api/timeline")
async def get_timeline():
    """Get content distribution across time periods"""
    db = SessionLocal()
    try:
        centuries = {
            '1500s': 0, '1600s': 0, '1700s': 0, '1800s': 0,
            '1900s': 0, '2000s': 0, '2010s': 0, '2020s': 0
        }
        
        items = db.query(KnowledgeItem.publication_date).all()
        for item in items:
            if item.publication_date:
                year = item.publication_date.year
                if year < 1600: centuries['1500s'] += 1
                elif year < 1700: centuries['1600s'] += 1
                elif year < 1800: centuries['1700s'] += 1
                elif year < 1900: centuries['1800s'] += 1
                elif year < 2000: centuries['1900s'] += 1
                elif year < 2010: centuries['2000s'] += 1
                elif year < 2020: centuries['2010s'] += 1
                else: centuries['2020s'] += 1
        
        db.close()
        return centuries
    except Exception as e:
        db.close()
        return {}

# ============ UI HTML ============
def get_ui_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knowledge Infinity</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .gradient-bg {
            background: linear-gradient(-45deg, #1a1a2e, #16213e, #0f3460, #533483);
            background-size: 400% 400%;
            animation: gradient 15s ease infinite;
        }
        @keyframes gradient {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        .glass-card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }
        .glass-card:hover {
            transform: translateY(-3px);
            background: rgba(255, 255, 255, 0.15);
        }
    </style>
</head>
<body class="gradient-bg min-h-screen">
    <nav class="fixed top-0 left-0 right-0 bg-black/50 backdrop-blur-lg z-50 border-b border-white/10">
        <div class="container mx-auto px-6 py-3">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <div class="text-3xl">🌌</div>
                    <h1 class="text-xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">Knowledge Infinity</h1>
                </div>
                <div class="flex gap-2">
                    <button onclick="showTab('feed')" class="tab-btn px-3 py-1 rounded text-white hover:bg-white/10">Feed</button>
                    <button onclick="showTab('random')" class="tab-btn px-3 py-1 rounded text-white hover:bg-white/10">Random</button>
                    <button onclick="showTab('fields')" class="tab-btn px-3 py-1 rounded text-white hover:bg-white/10">Fields</button>
                    <button onclick="showTab('saved')" class="tab-btn px-3 py-1 rounded text-white hover:bg-white/10">Saved</button>
                    <button onclick="showTab('crawl')" class="tab-btn px-3 py-1 rounded text-white hover:bg-white/10">Crawl</button>
                </div>
            </div>
        </div>
    </nav>

    <div class="container mx-auto px-6 pt-20 pb-12">
        <!-- Stats Bar -->
        <div class="glass-card rounded-xl p-3 mb-6">
            <div class="flex justify-between items-center flex-wrap gap-3">
                <div class="flex gap-4 text-white text-sm">
                    <div>📚 <span id="total-count">0</span> items</div>
                    <div>⏳ <span id="pending-count">0</span> pending</div>
                </div>
                <div class="flex gap-2">
                    <button onclick="startBothCrawlers()" class="bg-purple-600 hover:bg-purple-700 px-3 py-1 rounded text-sm transition">
                        🚀 Start Both Crawlers
                    </button>
                    <button onclick="refreshStats()" class="bg-gray-600 hover:bg-gray-700 px-3 py-1 rounded text-sm transition">
                        🔄 Refresh
                    </button>
                </div>
            </div>
        </div>

        <!-- Feed Tab -->
        <div id="feed-tab" class="tab-content">
            <div id="feed-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
            <div id="loading-trigger" class="text-center py-4">
                <div class="inline-block w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <p class="text-gray-400 text-sm mt-2">Loading more...</p>
            </div>
        </div>

        <!-- Random Tab -->
        <div id="random-tab" class="tab-content hidden">
            <div class="text-center mb-6">
                <button onclick="loadRandom()" class="bg-purple-600 hover:bg-purple-700 px-6 py-2 rounded-lg text-white transition">
                    🎲 Get Random Knowledge
                </button>
            </div>
            <div id="random-container" class="max-w-3xl mx-auto"></div>
        </div>

        <!-- Fields Tab -->
        <div id="fields-tab" class="tab-content hidden">
            <h2 class="text-2xl font-bold text-white mb-4">📚 Knowledge Fields</h2>
            <div id="fields-container" class="grid grid-cols-2 md:grid-cols-3 gap-3"></div>
        </div>

        <!-- Saved Tab -->
        <div id="saved-tab" class="tab-content hidden">
            <h2 class="text-2xl font-bold text-white mb-4">⭐ Saved Items</h2>
            <div id="saved-container" class="grid grid-cols-1 md:grid-cols-2 gap-3"></div>
        </div>

        <!-- Crawl Tab -->
        <div id="crawl-tab" class="tab-content hidden">
            <div class="glass-card rounded-xl p-6 max-w-md mx-auto">
                <h2 class="text-xl font-bold text-white mb-3">🔍 Add URL to Crawl</h2>
                <input type="url" id="crawl-url" placeholder="https://example.com/blog" class="w-full px-3 py-2 rounded bg-gray-800 text-white mb-3">
                <select id="crawl-depth" class="w-full px-3 py-2 rounded bg-gray-800 text-white mb-3">
                    <option value="2">Depth 2 (Fast)</option>
                    <option value="3" selected>Depth 3 (Recommended)</option>
                    <option value="4">Depth 4 (Deep)</option>
                </select>
                <button onclick="submitCrawl()" class="w-full bg-purple-600 hover:bg-purple-700 py-2 rounded text-white transition">
                    Add to Crawl Queue
                </button>
                <div class="mt-4 p-3 bg-gray-800/50 rounded-lg">
                    <p class="text-gray-300 text-xs">⚡ Both crawlers run in parallel</p>
                    <p class="text-gray-400 text-xs mt-1">• Enhanced: RSS + Deep URL</p>
                    <p class="text-gray-400 text-xs">• Archival: Ancient → Present</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentTab = 'feed';
        let currentOffset = 0;
        let isLoading = false;
        let hasMore = true;
        
        async function refreshStats() {
            try {
                const resp = await fetch('/api/stats');
                const stats = await resp.json();
                document.getElementById('total-count').innerText = stats.total_items || 0;
                document.getElementById('pending-count').innerText = stats.pending_urls || 0;
            } catch(e) {
                console.error('Stats error:', e);
            }
        }
        
        async function startBothCrawlers() {
            const resp = await fetch('/api/crawl/start-all', { method: 'POST' });
            const data = await resp.json();
            alert('🚀 Both crawlers started! They will run in parallel.');
            setTimeout(refreshStats, 3000);
        }
        
        async function loadFeed(reset = true) {
            if (reset) {
                currentOffset = 0;
                hasMore = true;
                document.getElementById('feed-container').innerHTML = '';
            }
            if (isLoading || !hasMore) return;
            isLoading = true;
            
            try {
                const resp = await fetch(`/api/feed?limit=15&offset=${currentOffset}`);
                const items = await resp.json();
                
                if (items.length === 0) {
                    hasMore = false;
                } else {
                    const container = document.getElementById('feed-container');
                    const html = items.map(item => `
                        <div class="glass-card rounded-xl p-4 cursor-pointer hover:scale-[1.02] transition" onclick="viewItem(${item.id})">
                            <div class="flex justify-between items-start mb-2">
                                <span class="text-xs px-2 py-0.5 rounded ${item.content_type === 'academic' ? 'bg-purple-600' : 'bg-pink-600'}">
                                    ${item.content_type === 'academic' ? '🎓 Academic' : '✍️ Writing'}
                                </span>
                                <span class="text-xs text-yellow-400">⭐ ${Math.round(item.curiosity_score * 100)}%</span>
                            </div>
                            <h3 class="text-white font-semibold text-sm mb-1">${escapeHtml(item.title || 'Untitled')}</h3>
                            <p class="text-gray-400 text-xs">${item.source_type} • ${item.primary_field}</p>
                            <button onclick="event.stopPropagation(); saveItem(${item.id})" class="mt-2 text-yellow-500 text-xs">⭐ Save</button>
                        </div>
                    `).join('');
                    container.insertAdjacentHTML('beforeend', html);
                    currentOffset += items.length;
                }
            } catch(e) {
                console.error('Load error:', e);
            }
            isLoading = false;
        }
        
        async function loadRandom() {
            const resp = await fetch('/api/random');
            const data = await resp.json();
            
            if (data.error) {
                document.getElementById('random-container').innerHTML = `<div class="glass-card p-6 text-center text-white">${data.error}</div>`;
                return;
            }
            
            const item = data.current;
            document.getElementById('random-container').innerHTML = `
                <div class="glass-card rounded-2xl p-6">
                    <div class="flex justify-between items-center mb-3">
                        <span class="text-xs px-2 py-0.5 rounded ${item.content_type === 'academic' ? 'bg-purple-600' : 'bg-pink-600'}">${item.content_type}</span>
                        <span class="text-gray-400 text-xs">📅 ${item.year}</span>
                    </div>
                    <h1 class="text-xl font-bold text-white mb-3">${escapeHtml(item.title)}</h1>
                    <div class="text-gray-300 text-sm leading-relaxed max-h-80 overflow-y-auto">
                        ${escapeHtml((item.content || '').substring(0, 1500))}
                    </div>
                    <div class="mt-4 flex gap-3">
                        <a href="${item.url}" target="_blank" class="bg-blue-600 px-4 py-2 rounded text-white text-sm">🔗 Read Original</a>
                        <button onclick="saveItem(${item.id})" class="bg-yellow-600 px-4 py-2 rounded text-white text-sm">⭐ Save</button>
                    </div>
                </div>
            `;
        }
        
        async function loadFields() {
            const resp = await fetch('/api/fields');
            const fields = await resp.json();
            document.getElementById('fields-container').innerHTML = fields.map(f => `
                <div class="glass-card rounded-xl p-3">
                    <div class="text-white font-medium text-sm">${escapeHtml(f.name)}</div>
                    <div class="text-gray-400 text-xs">${f.count} items</div>
                </div>
            `).join('');
        }
        
        async function loadSaved() {
            const resp = await fetch('/api/knowledge/saved');
            const items = await resp.json();
            document.getElementById('saved-container').innerHTML = items.map(item => `
                <div class="glass-card rounded-xl p-3 cursor-pointer" onclick="viewItem(${item.id})">
                    <h3 class="text-white text-sm">${escapeHtml(item.title)}</h3>
                </div>
            `).join('');
        }
        
        async function viewItem(id) { 
            window.open(`/knowledge/${id}`, '_blank'); 
        }
        
        async function saveItem(id) { 
            await fetch(`/api/knowledge/save/${id}`, { method: 'POST' }); 
            alert('Saved!'); 
        }
        
        async function submitCrawl() {
            const url = document.getElementById('crawl-url').value;
            const depth = document.getElementById('crawl-depth').value;
            if (!url) { alert('Enter a URL'); return; }
            
            const resp = await fetch(`/api/crawl/url?url=${encodeURIComponent(url)}&depth=${depth}`, { method: 'POST' });
            if (resp.ok) {
                alert(`✅ URL added! Will crawl to depth ${depth}`);
                document.getElementById('crawl-url').value = '';
                refreshStats();
            } else {
                alert('❌ URL already in queue');
            }
        }
        
        function showTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.getElementById(`${tab}-tab`).classList.remove('hidden');
            if (tab === 'feed') loadFeed(true);
            else if (tab === 'random') loadRandom();
            else if (tab === 'fields') loadFields();
            else if (tab === 'saved') loadSaved();
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Infinite scroll
        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !isLoading && hasMore && currentTab === 'feed') {
                loadFeed(false);
            }
        });
        
        setTimeout(() => {
            const trigger = document.getElementById('loading-trigger');
            if (trigger) observer.observe(trigger);
        }, 500);
        
        // Initialize
        refreshStats();
        loadFeed(true);
        setInterval(refreshStats, 15000);
    </script>
</body>
</html>
    """
# Add this to your main.py - Detail page endpoint
@app.get("/knowledge/{item_id}")
async def view_knowledge_detail(item_id: int):
    """Display a single knowledge item in full detail"""
    db = SessionLocal()
    
    try:
        item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
        
        if not item:
            db.close()
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Not Found</title></head>
            <body style="background:#1a1a2e; color:white; text-align:center; padding:50px;">
                <h1>Item Not Found</h1>
                <p>The requested knowledge item does not exist.</p>
                <a href="/" style="color:#a855f7;">← Back to Home</a>
            </body>
            </html>
            """, status_code=404)
        
        # Increment view count
        item.times_viewed = (item.times_viewed or 0) + 1
        db.commit()
        
        # Get similar items
        similar = db.query(KnowledgeItem).filter(
            KnowledgeItem.primary_field == item.primary_field,
            KnowledgeItem.id != item.id
        ).order_by(desc(KnowledgeItem.curiosity_score)).limit(5).all()
        
        db.close()
        
        # Helper functions for escaping
        def escape(text):
            if not text:
                return ''
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        def format_paragraphs(text):
            if not text:
                return '<p>No content available.</p>'
            paragraphs = text.split('\n\n')
            result = []
            for p in paragraphs:
                p = p.strip()
                if p:
                    result.append(f'<p class="mb-4">{escape(p)}</p>')
            return '\n'.join(result) if result else f'<p>{escape(text[:1000])}</p>'
        
        # Generate similar items HTML
        similar_html = ""
        if similar:
            similar_items_html = []
            for s in similar:
                similar_items_html.append(f'''
                    <a href="/knowledge/{s.id}" class="glass-card rounded-xl p-4 hover:bg-white/10 transition block">
                        <h3 class="text-white font-semibold">{escape(s.title or 'Untitled')}</h3>
                        <p class="text-gray-400 text-sm mt-1">{s.source_type or 'Unknown'} • {s.primary_field or 'General'}</p>
                    </a>
                ''')
            similar_html = f'''
            <div class="glass-card rounded-2xl p-8 mt-6">
                <h2 class="text-2xl font-bold text-white mb-4">📖 Similar Knowledge</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {''.join(similar_items_html)}
                </div>
            </div>
            '''
        
        # Build the full HTML page
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(item.title)} - Knowledge Infinity</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .gradient-bg {{
            background: linear-gradient(-45deg, #1a1a2e, #16213e, #0f3460, #533483);
            background-size: 400% 400%;
            animation: gradient 15s ease infinite;
        }}
        @keyframes gradient {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        .glass-card {{
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        .content-text {{
            line-height: 1.8;
            font-size: 1.05rem;
        }}
    </style>
</head>
<body class="gradient-bg min-h-screen">
    <nav class="fixed top-0 left-0 right-0 bg-black/50 backdrop-blur-lg z-50 border-b border-white/10">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <a href="/" class="flex items-center space-x-3">
                    <div class="text-3xl">🌌</div>
                    <h1 class="text-xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">Knowledge Infinity</h1>
                </a>
                <a href="/" class="text-white hover:text-purple-300 transition">← Back to Feed</a>
            </div>
        </div>
    </nav>

    <div class="container mx-auto px-6 pt-24 pb-12">
        <div class="max-w-4xl mx-auto">
            <!-- Main Content Card -->
            <div class="glass-card rounded-2xl p-8">
                <div class="flex justify-between items-start mb-4 flex-wrap gap-3">
                    <span class="text-xs px-3 py-1 rounded-full {'bg-purple-600' if item.content_type == 'academic' else 'bg-pink-600'} text-white">
                        {'ACADEMIC' if item.content_type == 'academic' else 'WRITING'}
                    </span>
                    <div class="flex gap-2">
                        <span class="text-xs bg-gray-700 text-white px-3 py-1 rounded-full">📚 {item.source_type or 'Unknown'}</span>
                        <span class="text-xs bg-gray-700 text-white px-3 py-1 rounded-full">⭐ {round((item.curiosity_score or 0.5) * 100)}% Curiosity</span>
                    </div>
                </div>
                
                <h1 class="text-3xl md:text-4xl font-bold text-white mb-4">{escape(item.title)}</h1>
                
                <div class="flex flex-wrap gap-4 text-gray-400 text-sm mb-6 pb-4 border-b border-white/10">
                    <div>✍️ Author: {escape(item.author or 'Unknown')}</div>
                    <div>📅 Discovered: {item.discovered_date.strftime('%Y-%m-%d') if item.discovered_date else 'Unknown'}</div>
                    {f'<div>📖 Published: {item.publication_date.strftime("%Y-%m-%d") if item.publication_date else "Unknown"}</div>' if item.publication_date else ''}
                    <div>🏷️ Field: {escape(item.primary_field or 'General')}</div>
                    <div>👁️ Views: {item.times_viewed or 0}</div>
                </div>
                
                <div class="content-text text-gray-300 leading-relaxed space-y-4">
                    {format_paragraphs(item.content_text or 'No content available.')}
                </div>
                
                <div class="mt-8 flex gap-4">
                    <a href="{item.url}" target="_blank" class="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg text-white transition">
                        🔗 Read Original Source
                    </a>
                    <button onclick="saveItem({item.id})" class="bg-yellow-600 hover:bg-yellow-700 px-6 py-3 rounded-lg text-white transition">
                        ⭐ Save for Later
                    </button>
                </div>
            </div>
            
            {similar_html}
        </div>
    </div>

    <script>
        async function saveItem(id) {{
            const response = await fetch(`/api/knowledge/save/${{id}}`, {{ method: 'POST' }});
            if (response.ok) {{
                alert('✨ Saved to your reading list!');
            }}
        }}
    </script>
</body>
</html>
        """
        
        return HTMLResponse(content=html)
        
    except Exception as e:
        if 'db' in locals():
            db.close()
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Error</title></head>
        <body style="background:#1a1a2e; color:white; text-align:center; padding:50px;">
            <h1>Error Loading Content</h1>
            <p>{str(e)}</p>
            <a href="/" style="color:#a855f7;">← Back to Home</a>
        </body>
        </html>
        """, status_code=500)
if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🌌 KNOWLEDGE INFINITY")
    print("="*60)
    print("\n🚀 Starting: http://localhost:8000")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)