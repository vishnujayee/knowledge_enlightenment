from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class KnowledgeItem(Base):
    __tablename__ = 'knowledge_items'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), index=True)
    url = Column(String(500), unique=True, index=True)
    content_hash = Column(String(64), unique=True, index=True)
    content_text = Column(Text)
    content_summary = Column(Text)
    
    # Metadata
    author = Column(String(200))
    source_type = Column(String(50), index=True)  # rss, crawled, paper, blog, patent, book, news, wikipedia
    content_type = Column(String(20), default='academic')  # academic or writing (NEW)
    publication_date = Column(DateTime)
    discovered_date = Column(DateTime, default=datetime.utcnow)
    
    # Categorization
    primary_field = Column(String(100), index=True)
    secondary_fields = Column(JSON)
    
    # Quality scores
    relevance_score = Column(Float, default=0.5)
    curiosity_score = Column(Float, default=0.5, index=True)
    
    # Media
    image_url = Column(String(500))
    
    # User interaction
    times_viewed = Column(Integer, default=0)
    saved_for_later = Column(Boolean, default=False, index=True)
    
    __table_args__ = (
        Index('idx_field_type', 'primary_field', 'source_type'),
        Index('idx_content_type', 'content_type', 'curiosity_score'),
    )

class TargetUrl(Base):  # NEW TABLE for user URLs
    __tablename__ = 'target_urls'
    
    id = Column(Integer, primary_key=True)
    url = Column(String(500), unique=True, index=True)
    added_date = Column(DateTime, default=datetime.utcnow)
    crawl_depth = Column(Integer, default=3)
    last_crawled = Column(DateTime)
    status = Column(String(20), default='pending')  # pending, completed, failed

class RssFeed(Base):  # NEW TABLE for RSS feeds
    __tablename__ = 'rss_feeds'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    url = Column(String(500), unique=True)
    content_type = Column(String(20))  # academic or writing
    field = Column(String(100))
    is_active = Column(Boolean, default=True)

# Use SQLite
engine = create_engine('sqlite:///knowledge.db', connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# Initialize default RSS feeds
def init_default_feeds():
    db = SessionLocal()
    
    default_feeds = [
        ('MIT News', 'http://news.mit.edu/rss', 'academic', 'technology'),
        ('ScienceDaily', 'https://www.sciencedaily.com/rss/all.xml', 'academic', 'science'),
        ('Nature', 'https://www.nature.com/nature.rss', 'academic', 'science'),
        ('arXiv Physics', 'http://export.arxiv.org/rss/physics', 'academic', 'physics'),
        ('arXiv CS', 'http://export.arxiv.org/rss/cs', 'academic', 'computerscience'),
        ('Cambridge News', 'https://www.cam.ac.uk/news/feed', 'academic', 'general'),
        ('Oxford News', 'https://www.ox.ac.uk/news/feed', 'academic', 'general'),
        ('Wait But Why', 'https://waitbutwhy.com/feed', 'writing', 'ideas'),
        ('Ribbonfarm', 'https://www.ribbonfarm.com/feed/', 'writing', 'complexity'),
        ('Marginal Revolution', 'https://marginalrevolution.com/feed/', 'writing', 'economics'),
        ('Astral Codex Ten', 'https://astralcodexten.substack.com/feed', 'writing', 'psychology'),
        ('Farnam Street', 'https://fs.blog/feed/', 'writing', 'mentalmodels'),
    ]
    
    for name, url, content_type, field in default_feeds:
        exists = db.query(RssFeed).filter(RssFeed.url == url).first()
        if not exists:
            feed = RssFeed(name=name, url=url, content_type=content_type, field=field)
            db.add(feed)
    
    db.commit()
    db.close()

init_default_feeds()