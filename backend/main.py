from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import pandas as pd
import io
import math
from datetime import date
from typing import List, Optional

from models import SessionLocal, Asset, Transaction, PriceHistory, init_db
from sync import sync_asset_data
from portfolio import get_portfolio_allocation, calculate_equity_curve

app = FastAPI(title="TradeWise API - 智慧投资追踪系统")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/debug/transactions")
def debug_transactions(db: Session = Depends(get_db)):
    """Debug endpoint to check transaction count"""
    count = db.query(Transaction).count()
    txs = db.query(Transaction).all()
    return {
        "count": count,
        "transactions": [{"id": t.id, "asset_id": t.asset_id, "date": str(t.date), "type": t.type, "quantity": t.quantity} for t in txs]
    }

def safe_float(value: Optional[float]) -> Optional[float]:
    """Convert float value to JSON-safe format (handle inf, -inf, nan)."""
    if value is None:
        return None
    if math.isinf(value) or math.isnan(value):
        return None
    return value

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/assets")
def list_assets(db: Session = Depends(get_db)):
    return db.query(Asset).all()

@app.post("/assets/sync/{symbol}")
def sync_asset(symbol: str, asset_type: str = "stock", db: Session = Depends(get_db)):
    sync_asset_data(symbol, asset_type)
    
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    prices = db.query(PriceHistory).filter(PriceHistory.asset_id == asset.id).order_by(PriceHistory.date).all()
    
    return {
        "status": "success",
        "message": f"Synced {symbol}",
        "data": {
            "symbol": symbol,
            "name": asset.name,
            "type": asset.asset_type,
            "kline": [
                {
                    "time": str(p.date),
                    "open": safe_float(p.open),
                    "high": safe_float(p.high),
                    "low": safe_float(p.low),
                    "close": safe_float(p.close),
                    # 后复权数据
                    "adj_open": safe_float(p.adj_open),
                    "adj_high": safe_float(p.adj_high),
                    "adj_low": safe_float(p.adj_low),
                    "adj_close": safe_float(p.adj_close),
                    # 前复权数据
                    "qfq_open": safe_float(p.qfq_open),
                    "qfq_high": safe_float(p.qfq_high),
                    "qfq_low": safe_float(p.qfq_low),
                    "qfq_close": safe_float(p.qfq_close),
                    "volume": safe_float(p.volume)
                } for p in prices
            ]
        }
    }

@app.post("/transactions/import")
async def import_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Import transactions from CSV. 
    Expected format: date, symbol, type, quantity, price, fees
    """
    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
    
    imported_count = 0
    skipped_count = 0
    
    for _, row in df.iterrows():
        # Ensure asset exists
        asset = db.query(Asset).filter(Asset.symbol == str(row['symbol'])).first()
        if not asset:
            # Auto sync asset info if missing
            # In a real app, you might want more metadata
            asset = Asset(symbol=str(row['symbol']), asset_type='stock') # default to stock
            db.add(asset)
            db.commit()
            db.refresh(asset)
        
        # 解析交易数据
        tx_date = pd.to_datetime(row['date']).date()
        tx_type = str(row['type'])
        tx_quantity = float(row['quantity'])
        tx_price = float(row['price'])
        tx_fees = float(row.get('fees', 0.0))
        
        # 检查是否已存在完全相同的交易记录
        existing = db.query(Transaction).filter(
            Transaction.asset_id == asset.id,
            Transaction.date == tx_date,
            Transaction.type == tx_type,
            Transaction.quantity == tx_quantity,
            Transaction.price == tx_price,
            Transaction.fees == tx_fees
        ).first()
        
        if existing:
            # 已存在，跳过
            skipped_count += 1
            continue
        
        # 不存在，插入新记录
        tx = Transaction(
            asset_id=asset.id,
            date=tx_date,
            type=tx_type,
            quantity=tx_quantity,
            price=tx_price,
            fees=tx_fees
        )
        db.add(tx)
        imported_count += 1
    
    db.commit()
    
    result = {
        "status": "success",
        "total_rows": len(df),
        "imported": imported_count,
        "skipped_duplicates": skipped_count
    }
    
    if skipped_count > 0:
        result["message"] = f"导入完成，跳过了 {skipped_count} 条重复记录"
    
    return result

@app.get("/portfolio/summary")
def get_portfolio_summary(db: Session = Depends(get_db)):
    return get_portfolio_allocation(db)

@app.get("/portfolio/equity-curve")
def get_equity_curve(db: Session = Depends(get_db)):
    return calculate_equity_curve(db)

@app.get("/charts/{symbol}")
def get_chart_data(symbol: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    prices = db.query(PriceHistory).filter(PriceHistory.asset_id == asset.id).order_by(PriceHistory.date).all()
    txs = db.query(Transaction).filter(Transaction.asset_id == asset.id).all()
    
    return {
        "prices": [
            {
                "time": str(p.date),
                "open": safe_float(p.open),
                "high": safe_float(p.high),
                "low": safe_float(p.low),
                "close": safe_float(p.close),
                # 后复权数据
                "adj_open": safe_float(p.adj_open),
                "adj_high": safe_float(p.adj_high),
                "adj_low": safe_float(p.adj_low),
                "adj_close": safe_float(p.adj_close),
                # 前复权数据
                "qfq_open": safe_float(p.qfq_open),
                "qfq_high": safe_float(p.qfq_high),
                "qfq_low": safe_float(p.qfq_low),
                "qfq_close": safe_float(p.qfq_close),
                "volume": p.volume
            } for p in prices
        ],
        "markers": [{"time": str(t.date), "position": "belowBar" if t.type == "buy" else "aboveBar", "color": "red" if t.type == "buy" else "green", "shape": "arrowUp" if t.type == "buy" else "arrowDown", "text": f"{t.type} {t.quantity}"} for t in txs]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
