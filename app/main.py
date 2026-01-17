from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import os
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict

from app.ai_processor import ReceiptProcessor
from app.database import get_db, engine
from app.models import Base, Receipt, ReceiptItem
from app.schemas import ReceiptResponse

# Load environment variables
load_dotenv()

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Global AI processor
processor: ReceiptProcessor | None = None


# -------------------- LIFESPAN --------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global processor

    # ---------- STARTUP ----------
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

    try:
        processor = ReceiptProcessor()
        print("✅ AI processor initialized")
    except Exception as e:
        processor = None
        print(f"⚠️  AI processor initialization failed: {e}")

    print(f"✅ Upload directory: {UPLOAD_DIR.absolute()}")

    yield  # ---- APP RUNS HERE ----

    # ---------- SHUTDOWN ----------
    print("👋 Shutting down SmartReceipt API")


# -------------------- APP --------------------
app = FastAPI(
    title="SmartReceipt API",
    description="AI-powered receipt processing API (100% FREE)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# -------------------- CORS --------------------
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:5174",
    "https://*.vercel.app",
    "https://vercel.app",
]

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔒 lock in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- ROUTES --------------------
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "SmartReceipt API is running!",
        "version": "1.0.0",
        "ai_model": "Google Gemini 2.5 Flash" if processor else "Not initialized",
        "cost": "100% FREE",
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"

    ai_status = "healthy" if processor else "not initialized"
    upload_status = "healthy" if UPLOAD_DIR.exists() else "missing"

    return {
        "status": "healthy"
        if all(
            s == "healthy" for s in [db_status, ai_status, upload_status]
        )
        else "degraded",
        "components": {
            "database": db_status,
            "ai_processor": ai_status,
            "upload_directory": upload_status,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# -------------------- UPLOAD --------------------
@app.post("/upload", response_model=ReceiptResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not processor:
        raise HTTPException(status_code=503, detail="AI processor not available")

    if file.content_type not in {"image/jpeg", "image/jpg", "image/png"}:
        raise HTTPException(status_code=400, detail="Invalid image type")

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)

    if size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
    filename = f"receipt_{timestamp}_{safe_name}"
    path = UPLOAD_DIR / filename

    try:
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = processor.process_receipt(str(path))
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error"))

        receipt = Receipt(
            merchant_name=result.get("merchant_name", "Unknown"),
            date=result.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            time=result.get("time"),
            subtotal=float(result.get("subtotal", 0)),
            tax=float(result.get("tax", 0)),
            total=float(result.get("total", 0)),
            payment_method=result.get("payment_method"),
            category=result.get("category", "other"),
            filename=filename,
            file_path=str(path),
            ai_model=result.get("ai_model", "gemini-2.5-flash"),
        )

        for item in result.get("items", []):
            if item.get("name") and item.get("price") is not None:
                receipt.items.append(
                    ReceiptItem(
                        name=item["name"],
                        quantity=int(item.get("quantity", 1)),
                        price=float(item["price"]),
                    )
                )

        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        return receipt

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        if path.exists():
            path.unlink()
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- RECEIPTS --------------------
@app.get("/receipts", response_model=List[ReceiptResponse])
def get_receipts(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Receipt)

    if category:
        query = query.filter(Receipt.category == category.lower())

    if search:
        query = query.filter(Receipt.merchant_name.ilike(f"%{search}%"))

    return (
        query.order_by(Receipt.processed_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
        .all()
    )


@app.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@app.delete("/receipts/{receipt_id}")
def delete_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if os.path.exists(receipt.file_path):
        os.remove(receipt.file_path)

    db.delete(receipt)
    db.commit()

    return {"success": True}


# -------------------- ERRORS --------------------
@app.exception_handler(404)
async def not_found(_, __):
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found"},
    )


@app.exception_handler(500)
async def server_error(_, __):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"},
    )

@app.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """
    Get spending analytics
    
    Returns:
    - Total receipts count
    - Total amount spent
    - Spending by category
    - Spending by month
    - Recent receipts
    """
    receipts = db.query(Receipt).all()
    
    # Calculate totals
    total_receipts = len(receipts)
    total_spent = sum(r.total for r in receipts)
    
    # By category
    by_category = defaultdict(float)
    for r in receipts:
        by_category[r.category] += r.total
    
    # By month
    by_month = defaultdict(float)
    for r in receipts:
        try:
            month_key = r.date[:7]  # YYYY-MM
            by_month[month_key] += r.total
        except:
            pass
    
    # Recent receipts (last 5)
    recent = db.query(Receipt).order_by(Receipt.processed_at.desc()).limit(5).all()
    
    return {
        "total_receipts": total_receipts,
        "total_spent": round(total_spent, 2),
        "average_receipt": round(total_spent / total_receipts, 2) if total_receipts > 0 else 0,
        "by_category": dict(by_category),
        "by_month": dict(sorted(by_month.items(), reverse=True)),
        "recent_receipts": [r.to_dict() for r in recent]
    }