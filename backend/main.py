from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import pandas as pd
import io
import math
from datetime import date
from typing import List, Optional
from pydantic import BaseModel

from models import SessionLocal, Asset, Transaction, PriceHistory, init_db
from sync import sync_asset_data
from portfolio import get_portfolio_allocation, calculate_equity_curve

# Pydantic models for request validation
class TransactionCreate(BaseModel):
    symbol: str
    date: str  # YYYY-MM-DD
    type: str  # 'buy' or 'sell'
    quantity: float
    price: float
    fees: float = 0.0
    notes: Optional[str] = None

class TransactionUpdate(BaseModel):
    symbol: Optional[str] = None
    date: Optional[str] = None
    type: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    fees: Optional[float] = None
    notes: Optional[str] = None

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

@app.get("/transactions")
def get_transactions(symbol: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all transactions with asset information, optionally filter by symbol"""
    query = db.query(Transaction).join(Asset)
    
    if symbol:
        query = query.filter(Asset.symbol == symbol)
    
    txs = query.order_by(Transaction.date.desc()).all()
    return [
        {
            "id": t.id,
            "symbol": t.asset.symbol,
            "name": t.asset.name,
            "date": str(t.date),
            "type": t.type,
            "quantity": t.quantity,
            "price": t.price,
            "fees": t.fees,
            "notes": t.notes
        }
        for t in txs
    ]

@app.post("/transactions")
def create_transaction(tx: TransactionCreate, db: Session = Depends(get_db)):
    """Create a new transaction manually"""
    # Ensure asset exists
    asset = db.query(Asset).filter(Asset.symbol == tx.symbol).first()
    if not asset:
        asset = Asset(symbol=tx.symbol, name='', asset_type='stock')
        db.add(asset)
        db.commit()
        db.refresh(asset)
    
    # Parse date
    tx_date = pd.to_datetime(tx.date).date()
    
    new_tx = Transaction(
        asset_id=asset.id,
        date=tx_date,
        type=tx.type,
        quantity=tx.quantity,
        price=tx.price,
        fees=tx.fees,
        notes=tx.notes
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    
    return {
        "id": new_tx.id,
        "symbol": asset.symbol,
        "name": asset.name,
        "date": str(new_tx.date),
        "type": new_tx.type,
        "quantity": new_tx.quantity,
        "price": new_tx.price,
        "fees": new_tx.fees,
        "notes": new_tx.notes
    }

@app.put("/transactions/{tx_id}")
def update_transaction(tx_id: int, tx: TransactionUpdate, db: Session = Depends(get_db)):
    """Update an existing transaction"""
    existing_tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not existing_tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Update asset if symbol changed
    if tx.symbol:
        asset = db.query(Asset).filter(Asset.symbol == tx.symbol).first()
        if not asset:
            asset = Asset(symbol=tx.symbol, name='', asset_type='stock')
            db.add(asset)
            db.commit()
            db.refresh(asset)
        existing_tx.asset_id = asset.id
    
    # Update other fields
    if tx.date:
        existing_tx.date = pd.to_datetime(tx.date).date()
    if tx.type:
        existing_tx.type = tx.type
    if tx.quantity is not None:
        existing_tx.quantity = tx.quantity
    if tx.price is not None:
        existing_tx.price = tx.price
    if tx.fees is not None:
        existing_tx.fees = tx.fees
    if tx.notes is not None:
        existing_tx.notes = tx.notes
    
    db.commit()
    db.refresh(existing_tx)
    
    return {
        "id": existing_tx.id,
        "symbol": existing_tx.asset.symbol,
        "name": existing_tx.asset.name,
        "date": str(existing_tx.date),
        "type": existing_tx.type,
        "quantity": existing_tx.quantity,
        "price": existing_tx.price,
        "fees": existing_tx.fees,
        "notes": existing_tx.notes
    }

@app.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: int, db: Session = Depends(get_db)):
    """Delete a transaction"""
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    db.delete(tx)
    db.commit()
    
    return {"status": "success", "message": "Transaction deleted"}

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
    Import transactions from CSV or Excel file.
    Expected formats:
    - CSV: date, symbol, type, quantity, price, fees
    - Excel (券商交割单): 交割日期, 证券代码, 证券名称, 业务类型, 成交价格, 成交数量, 佣金, 印花税, 过户费
      注意：只导入"证券买入"和"证券卖出"的记录，其他业务类型会被自动过滤
    Supports: .csv, .xls, .xlsx
    """
    contents = await file.read()
    filename = file.filename.lower()
    
    # 根据文件类型读取
    if filename.endswith('.csv'):
        try:
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        except:
            df = pd.read_csv(io.StringIO(contents.decode('gbk')))
    elif filename.endswith(('.xls', '.xlsx')):
        try:
            df = pd.read_excel(io.BytesIO(contents))
        except:
            df = pd.read_csv(io.StringIO(contents.decode('gbk')), sep='\t')
    else:
        raise HTTPException(status_code=400, detail="只支持 CSV 和 Excel 文件格式")
    
    # 处理带引号的列名（如 ="交割日期" -> 交割日期）
    if any('=' in str(col) for col in df.columns):
        df.columns = df.columns.astype(str).str.replace(r'^="|"$', '', regex=True)
        # 同时清理数据中的引号格式（只清理字符串列，数字列保持不变）
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col].dtype):
                df[col] = df[col].astype(str).str.replace(r'^="|"$', '', regex=True)
    
    # 检测是否是券商交割单格式
    if '交割日期' in df.columns and '证券代码' in df.columns:
        # 券商交割单格式
        
        # 记录过滤前的行数
        total_rows_before = len(df)
        
        # 过滤只保留"证券买入"和"证券卖出"的行
        df = df[df['业务类型'].isin(['证券买入', '证券卖出'])].copy()
        
        # 记录被过滤的行数
        filtered_count = total_rows_before - len(df)
        
        # 重命名列
        df = df.rename(columns={
            '交割日期': 'date',
            '证券代码': 'symbol',
            '证券名称': 'asset_name',
            '业务类型': 'type',
            '成交价格': 'price',
            '成交数量': 'quantity',
            '佣金': 'comm',
            '印花税': 'tax',
            '过户费': 'fee'
        })
        # 处理业务类型: 证券买入->buy, 证券卖出->sell
        df['type'] = df['type'].apply(lambda x: 'buy' if '买入' in str(x) else 'sell')
        # 计算总费用
        df['fees'] = df['comm'].fillna(0) + df['tax'].fillna(0) + df['fee'].fillna(0)
        df['symbol'] = df['symbol'].astype(str).str.zfill(6) # 补齐6位
        # 处理日期格式 (如 20260113 -> 2026-01-13，这里可能是13日但pandas解析为1970年)
        # 检查是否需要特殊处理
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d', errors='coerce').dt.date
    else:
        # 标准CSV格式: date, symbol, type, quantity, price, fees
        # 标准CSV不过滤
        filtered_count = 0
        
        df = df.rename(columns={
            'date': 'date',
            'symbol': 'symbol',
            'type': 'type',
            'quantity': 'quantity',
            'price': 'price',
            'fees': 'fees'
        })
    
    imported_count = 0
    skipped_count = 0
    
    # 初始化 filtered_count 变量（非交割单格式时为0）
    if 'filtered_count' not in locals():
        filtered_count = 0
    
    for _, row in df.iterrows():
        # Ensure asset exists
        asset = db.query(Asset).filter(Asset.symbol == str(row['symbol'])).first()
        if not asset:
            # 获取证券名称
            asset_name = str(row.get('asset_name', '')) if 'asset_name' in row else ''
            asset = Asset(symbol=str(row['symbol']), name=asset_name, asset_type='stock')
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
        "skipped_duplicates": skipped_count,
        "filtered_non_trading": filtered_count
    }
    
    if skipped_count > 0 or filtered_count > 0:
        messages = []
        if skipped_count > 0:
            messages.append(f"跳过 {skipped_count} 条重复记录")
        if filtered_count > 0:
            messages.append(f"过滤 {filtered_count} 条非交易记录")
        result["message"] = "导入完成，" + "、".join(messages)
    
    return result

@app.get("/portfolio/summary")
def get_portfolio_summary(db: Session = Depends(get_db)):
    return get_portfolio_allocation(db)

@app.get("/portfolio/equity-curve")
def get_equity_curve(db: Session = Depends(get_db)):
    return calculate_equity_curve(db)

@app.get("/assets/with-transactions")
def list_assets_with_transactions(db: Session = Depends(get_db)):
    """
    Return only assets that have at least one transaction.
    """
    # Get all asset IDs that have transactions
    asset_ids_with_tx = db.query(Transaction.asset_id).distinct().all()
    asset_ids = [id[0] for id in asset_ids_with_tx]
    
    # Get the actual assets
    assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    return assets

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
                "volume": safe_float(p.volume)
            } for p in prices
        ],
        "markers": [{"time": str(t.date), "position": "belowBar" if t.type == "buy" else "aboveBar", "color": "red" if t.type == "buy" else "green", "shape": "arrowUp" if t.type == "buy" else "arrowDown", "text": f"{t.type} {t.quantity}", "notes": t.notes} for t in txs]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
