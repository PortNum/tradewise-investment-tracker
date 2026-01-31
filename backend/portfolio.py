from sqlalchemy.orm import Session
from models import Transaction, PriceHistory, Asset
from datetime import date
import pandas as pd
from collections import defaultdict

def calculate_portfolio_holdings(db: Session):
    """
    Calculate current holdings for each asset.
    """
    txs = db.query(Transaction).all()
    holdings = defaultdict(float)
    for tx in txs:
        asset = tx.asset
        if tx.type == 'buy':
            holdings[asset.symbol] += tx.quantity
        elif tx.type == 'sell':
            holdings[asset.symbol] -= tx.quantity
    
    # Filter out closed positions
    return {s: q for s, q in holdings.items() if q > 0}

def get_portfolio_allocation(db: Session):
    """
    Calculate current value and percentage for each asset.
    """
    holdings = calculate_portfolio_holdings(db)
    
    # 如果没有持仓，直接返回空
    if not holdings:
        return {"items": [], "total_value": 0}
    
    allocation = []
    total_value = 0
    
    for symbol, quantity in holdings.items():
        asset = db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            continue
            
        # Get latest price
        latest_price = db.query(PriceHistory).filter(PriceHistory.asset_id == asset.id).order_by(PriceHistory.date.desc()).first()
        
        price = latest_price.close if latest_price else 0
        value = quantity * price
        total_value += value
        
        # 跳过没有名称的资产
        if not asset.name or not asset.name.strip():
            continue
            
        allocation.append({
            "symbol": symbol,
            "name": asset.name,
            "quantity": quantity,
            "price": price,
            "value": value
        })
    
    # Calculate percentages
    for item in allocation:
        item["percentage"] = (item["value"] / total_value * 100) if total_value > 0 else 0
        
    return {"items": allocation, "total_value": total_value}

def calculate_equity_curve(db: Session):
    """
    Calculate the total portfolio value over time.
    """
    # This is a bit complex. We need to:
    # 1. Get all dates where we had transactions or prices.
    # 2. Iterate through dates, maintain a running balance of holdings.
    # 3. Multiply holdings by prices on each date.
    
    txs = db.query(Transaction).order_by(Transaction.date).all()
    if not txs:
        return []
    
    start_date = txs[0].date
    end_date = date.today()
    
    # Get all price dates
    price_dates = db.query(PriceHistory.date).distinct().filter(PriceHistory.date >= start_date).order_by(PriceHistory.date).all()
    all_dates = [d[0] for d in price_dates]
    
    equity_curve = []
    current_holdings = defaultdict(float)
    tx_idx = 0
    
    for d in all_dates:
        # Update holdings with transactions on or before this date
        while tx_idx < len(txs) and txs[tx_idx].date <= d:
            t = txs[tx_idx]
            asset_symbol = t.asset.symbol
            if t.type == 'buy':
                current_holdings[asset_symbol] += t.quantity
            else:
                current_holdings[asset_symbol] -= t.quantity
            tx_idx += 1
            
        # Calculate daily value
        daily_value = 0
        for symbol, qty in current_holdings.items():
            if qty == 0: continue
            asset = db.query(Asset).filter(Asset.symbol == symbol).first()
            p = db.query(PriceHistory).filter(PriceHistory.asset_id == asset.id, PriceHistory.date == d).first()
            if p:
                daily_value += qty * p.close
            else:
                # If no price for this exact date, try to find the most recent one before it
                p_last = db.query(PriceHistory).filter(PriceHistory.asset_id == asset.id, PriceHistory.date < d).order_by(PriceHistory.date.desc()).first()
                if p_last:
                    daily_value += qty * p_last.close
                    
        equity_curve.append({"time": str(d), "value": daily_value})
        
    return equity_curve
