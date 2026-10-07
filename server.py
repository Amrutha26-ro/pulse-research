import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Database Configuration
DATABASE_URL = "sqlite:///./pulse.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Paper(Base):
    __tablename__ = "papers"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    authors = Column(String(500), nullable=False)
    abstract = Column(Text, nullable=False)
    url = Column(String(500), nullable=True)
    tags = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI Application
app = FastAPI(title="Pulse Research Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache Control Middleware to force fresh data every request
@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Schemas
class PaperCreate(BaseModel):
    title: str
    authors: str
    abstract: str
    url: Optional[str] = None
    tags: Optional[str] = None

class PaperResponse(PaperCreate):
    id: int
    class Config:
        orm_mode = True

# External Scraper Function
def fetch_arxiv_papers(query: str, max_results: int = 5):
    url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    
    soup = BeautifulSoup(response.content, "xml")
    entries = soup.find_all("entry")
    results = []
    
    for entry in entries:
        title = entry.title.text.strip().replace("\n", " ")
        summary = entry.summary.text.strip().replace("\n", " ")
        authors = ", ".join([a.find("name").text for a in entry.find_all("author")])
        link = entry.id.text.strip()
        results.append({
            "id": 0,
            "title": title,
            "authors": authors,
            "abstract": summary,
            "url": link,
            "tags": "arXiv"
        })
    return results

# Endpoints
@app.post("/api/papers", response_model=PaperResponse)
def create_paper(paper: PaperCreate, db: Session = Depends(get_db)):
    db_paper = Paper(**paper.dict())
    db.add(db_paper)
    db.commit()
    db.refresh(db_paper)
    return db_paper

@app.get("/api/papers", response_model=List[PaperResponse])
def get_papers(db: Session = Depends(get_db)):
    return db.query(Paper).order_by(Paper.id.desc()).all()

@app.get("/api/search/external")
def search_external(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="Query string is required")
    return fetch_arxiv_papers(query)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)