from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict

from app.ai_processor import ReceiptProcessor
from app.database import get_db, init_db, engine
from app.models import Base, Receipt, ReceiptItem
from app.schemas import ReceiptResponse, AnalyticsResponse

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="SmartReceipt API",
    description="AI-powered receipt processing API (100% FREE)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS - Updated for production
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:5174",
    "https://*.vercel.app",
    "https://vercel.app",
]

# If FRONTEND_URL is set in environment, add it
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize AI processor
processor = None

@app.on_event("startup")
async def startup_event():
    """Initialize database and AI processor on startup"""
    global processor
    
    # Initialize database
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
    
    # Initialize AI processor
    try:
        processor = ReceiptProcessor()
        print("✅ AI processor initialized")
    except Exception as e:
        print(f"⚠️  AI processor initialization failed: {e}")
        print("    App will run but receipt processing will fail")
    
    # Log upload directory
    print(f"✅ Upload directory: {UPLOAD_DIR.absolute()}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 Shutting down SmartReceipt API")


@app.get("/")
def root():
    """API health check"""
    return {
        "status": "online",
        "message": "SmartReceipt API is running!",
        "version": "1.0.0",
        "ai_model": "Google Gemini 2.5 Flash" if processor else "Not initialized",
        "cost": "100% FREE - No credit card required",
        "endpoints": {
            "GET /": "Health check",
            "POST /upload": "Upload and process receipt",
            "GET /receipts": "Get all receipts",
            "GET /receipts/{id}": "Get specific receipt",
            "DELETE /receipts/{id}": "Delete receipt",
            "GET /analytics": "Get spending analytics",
            "GET /categories": "Get available categories",
            "GET /health": "Detailed health check",
            "GET /docs": "API documentation"
        }
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Detailed health check"""
    try:
        # Check database
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check AI processor
    ai_status = "healthy" if processor else "not initialized"
    
    # Check upload directory
    upload_dir_status = "healthy" if UPLOAD_DIR.exists() else "missing"
    
    return {
        "status": "healthy" if all([
            db_status == "healthy",
            ai_status == "healthy",
            upload_dir_status == "healthy"
        ]) else "degraded",
        "components": {
            "database": db_status,
            "ai_processor": ai_status,
            "upload_directory": upload_dir_status
        },
        "timestamp": datetime.now().isoformat()
    }


@app.post("/upload", response_model=ReceiptResponse)
async def upload_receipt(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """
    Upload and process a receipt image
    
    **Accepts:**
    - JPG, JPEG, PNG images
    - Maximum file size: 10MB
    
    **Returns:**
    - Extracted receipt data with all items
    - Stored in database for future reference
    
    **Processing:**
    - Uses Google Gemini AI (free tier)
    - Extracts merchant, date, items, total, category
    - Cost: $0.00 per receipt
    """
    
    # Check if AI processor is initialized
    if not processor:
        raise HTTPException(
            status_code=503,
            detail="AI processor not initialized. Please contact administrator."
        )
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.content_type}'. Allowed: JPG, JPEG, PNG"
        )
    
    # Validate file size (10MB limit)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({file_size / 1024 / 1024:.2f}MB). Maximum size: 10MB"
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Empty file received"
        )
    
    try:
        # Save uploaded file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize filename
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
        filename = f"receipt_{timestamp}_{safe_filename}"
        file_path = UPLOAD_DIR / filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        print(f"✅ Saved file: {file_path} ({file_size / 1024:.2f} KB)")
        
        # Process receipt with AI
        print(f"🤖 Processing with Gemini AI...")
        receipt_data = processor.process_receipt(str(file_path))
        
        if not receipt_data.get("success"):
            # Delete failed upload
            if os.path.exists(file_path):
                os.remove(file_path)
            
            error_msg = receipt_data.get("error", "Unknown error occurred")
            print(f"❌ Processing failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process receipt: {error_msg}"
            )
        
        # Validate extracted data
        if not receipt_data.get("merchant_name"):
            receipt_data["merchant_name"] = "Unknown Merchant"
        
        if not receipt_data.get("total") or receipt_data["total"] <= 0:
            raise HTTPException(
                status_code=500,
                detail="Could not extract total amount from receipt"
            )
        
        # Create receipt in database
        receipt = Receipt(
            merchant_name=receipt_data.get("merchant_name", "Unknown"),
            date=receipt_data.get("date", datetime.now().strftime("%Y-%m-%d")),
            time=receipt_data.get("time"),
            subtotal=float(receipt_data.get("subtotal", 0.0)),
            tax=float(receipt_data.get("tax", 0.0)),
            total=float(receipt_data.get("total", 0.0)),
            payment_method=receipt_data.get("payment_method"),
            category=receipt_data.get("category", "other"),
            filename=filename,
            file_path=str(file_path),
            ai_model=receipt_data.get("ai_model", "gemini-2.5-flash")
        )
        
        # Add items
        items_added = 0
        for item_data in receipt_data.get("items", []):
            if item_data.get("name") and item_data.get("price") is not None:
                item = ReceiptItem(
                    name=item_data.get("name", "Unknown Item"),
                    quantity=int(item_data.get("quantity", 1)),
                    price=float(item_data.get("price", 0.0))
                )
                receipt.items.append(item)
                items_added += 1
        
        # Save to database
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        
        print(f"✅ Receipt saved (ID: {receipt.id}, Items: {items_added})")
        
        return receipt
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        db.rollback()
        
        # Clean up uploaded file on error
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/receipts", response_model=List[ReceiptResponse])
def get_receipts(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all receipts with optional filtering
    
    **Parameters:**
    - skip: Number of receipts to skip (pagination)
    - limit: Maximum receipts to return (max 100)
    - category: Filter by category (groceries, restaurant, etc.)
    - search: Search in merchant name or items
    """
    query = db.query(Receipt)
    
    # Filter by category
    if category:
        query = query.filter(Receipt.category == category.lower())
    
    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(Receipt.merchant_name.ilike(search_term))
    
    # Order by most recent first
    receipts = query.order_by(Receipt.processed_at.desc()).offset(skip).limit(min(limit, 100)).all()
    
    return receipts


@app.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    """
    Get a specific receipt by ID
    
    **Parameters:**
    - receipt_id: Unique receipt identifier
    """
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    
    if not receipt:
        raise HTTPException(
            status_code=404, 
            detail=f"Receipt with ID {receipt_id} not found"
        )
    
    return receipt


@app.delete("/receipts/{receipt_id}")
def delete_receipt(receipt_id: int, db: Session = Depends(get_db)):
    """
    Delete a receipt and its associated file
    
    **Parameters:**
    - receipt_id: Unique receipt identifier
    """
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    
    if not receipt:
        raise HTTPException(
            status_code=404, 
            detail=f"Receipt with ID {receipt_id} not found"
        )
    
    # Delete physical file
    try:
        if os.path.exists(receipt.file_path):
            os.remove(receipt.file_path)
            print(f"✅ Deleted file: {receipt.file_path}")
    except Exception as e:
        print(f"⚠️  Could not delete file {receipt.file_path}: {e}")
    
    # Delete from database
    db.delete(receipt)
    db.commit()
    
    print(f"✅ Deleted receipt ID {receipt_id}")
    
    return {
        "success": True, 
        "message": f"Receipt {receipt_id} deleted successfully"
    }


@app.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """
    Get comprehensive spending analytics
    
    **Returns:**
    - Total number of receipts
    - Total amount spent
    - Spending breakdown by category
    - Spending breakdown by month
    - 5 most recent receipts
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
        except Exception as e:
            print(f"Warning: Could not parse date for receipt {r.id}: {e}")
    
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


@app.get("/categories")
def get_categories():
    """
    Get list of available receipt categories
    
    **Returns:**
    - List of category names
    """
    return {
        "categories": [
            "groceries",
            "restaurant",
            "gas",
            "shopping",
            "entertainment",
            "health",
            "transport",
            "other"
        ]
    }


@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """
    Get quick statistics
    
    **Returns:**
    - Count of receipts by category
    - Total items processed
    """
    receipts = db.query(Receipt).all()
    
    # Count by category
    category_counts = defaultdict(int)
    total_items = 0
    
    for r in receipts:
        category_counts[r.category] += 1
        total_items += len(r.items)
    
    return {
        "total_receipts": len(receipts),
        "total_items": total_items,
        "receipts_by_category": dict(category_counts),
        "upload_directory_size_mb": sum(
            f.stat().st_size for f in UPLOAD_DIR.glob("*") if f.is_file()
        ) / (1024 * 1024)
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "path": str(request.url)
        }
    )


@app.exception_handler(500)
async def server_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 Starting SmartReceipt API")
    print("=" * 60)
    print("\n📍 Server: http://localhost:8000")
    print("📄 API Docs: http://localhost:8000/docs")
    print("🔍 ReDoc: http://localhost:8000/redoc")
    print("💰 Cost: $0.00 (100% FREE)")
    print("\n🤖 AI Model: Google Gemini 2.5 Flash (Free Tier)")
    print("💾 Database: SQLite (Local)")
    print("📁 Uploads: ./uploads/")
    print("\n" + "=" * 60)
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )