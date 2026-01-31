import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from models import SessionLocal, Asset, PriceHistory, init_db
from sqlalchemy.exc import IntegrityError

def validate_price_data(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Validate and clean price data.
    Remove rows with negative prices, NaN values, or invalid data.
    """
    if df is None or df.empty:
        return df

    original_count = len(df)

    # Check all price columns (including adjusted prices)
    price_cols = ['open', 'high', 'low', 'close',
                  'qfq_open', 'qfq_high', 'qfq_low', 'qfq_close',
                  'adj_open', 'adj_high', 'adj_low', 'adj_close']

    for col in price_cols:
        if col in df.columns:
            # Remove rows with negative or zero prices (adjusted prices must be > 0)
            df = df[df[col] > 0]
            # Remove rows with NaN or inf
            df = df[df[col].notna()]
            df = df[~np.isinf(df[col])]

    # Check volume if present (volume can be 0 but not negative)
    if 'volume' in df.columns:
        df = df[df['volume'] >= 0]
        df = df[df['volume'].notna()]
        df = df[~np.isinf(df['volume'])]

    removed_count = original_count - len(df)
    if removed_count > 0:
        print(f"  {source}: Removed {removed_count} invalid records (negative/zero prices, NaN, or inf)")

    return df

def get_stock_data(symbol: str, start_date: str = "20000101", name: Optional[str] = None):
    """
    Fetch historical data for A-shares with consistent format.
    Priority: East Money (full data) -> Tencent (adj data) -> Sina (raw data)
    """
    print(f"Fetching data for Stock: {symbol} from {start_date}")
    
    # Try East Money first (has both raw and adjusted data)
    try:
        print("  Trying East Money...")
        # Raw data (not adjusted)
        df_raw = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, adjust="", timeout=30)
        if df_raw is None or df_raw.empty:
            raise Exception("East Money returned empty raw data")
        df_raw['date'] = pd.to_datetime(df_raw['日期']).dt.date
        df_raw = df_raw[['date', '开盘', '收盘', '最高', '最低', '成交量']]
        df_raw.columns = ['date', 'open', 'close', 'high', 'low', 'volume']

        # 前复权数据 (qfq)
        df_qfq = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, adjust="qfq", timeout=30)
        if df_qfq is None or df_qfq.empty:
            raise Exception("East Money returned empty qfq data")
        df_qfq['date'] = pd.to_datetime(df_qfq['日期']).dt.date
        df_qfq = df_qfq[['date', '开盘', '收盘', '最高', '最低']]
        df_qfq.columns = ['date', 'qfq_open', 'qfq_close', 'qfq_high', 'qfq_low']

        # 后复权数据 (hfq)
        df_hfq = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, adjust="hfq", timeout=30)
        if df_hfq is None or df_hfq.empty:
            raise Exception("East Money returned empty hfq data")
        df_hfq['date'] = pd.to_datetime(df_hfq['日期']).dt.date
        df_hfq = df_hfq[['date', '开盘', '收盘', '最高', '最低']]
        df_hfq.columns = ['date', 'adj_open', 'adj_close', 'adj_high', 'adj_low']

        # Merge all data using outer join to avoid data loss
        df = pd.merge(df_raw, df_qfq, on='date', how='outer')
        df = pd.merge(df, df_hfq, on='date', how='outer')

        # Check if merged data is empty
        if df.empty:
            raise Exception("Merged data is empty after joining raw, qfq and hfq data")

        # Validate data before returning
        df = validate_price_data(df, "East Money")

        if df.empty:
            raise Exception("All data was filtered out as invalid")

        print(f"  East Money success! Got {len(df)} records")
        return df
    except Exception as e:
        print(f"  East Money failed: {str(e)}")
        
    # Try Tencent (has adjusted data but no volume)
    try:
        print("  Trying Tencent...")
        prefix = "sz" if symbol.startswith("0") or symbol.startswith("3") else "sh"

        # 前复权数据
        df_qfq = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{symbol}", start_date=start_date, end_date="20301231", adjust="qfq")
        if df_qfq is None or df_qfq.empty:
            raise Exception("Tencent returned empty qfq data")
        df_qfq['date'] = pd.to_datetime(df_qfq['date']).dt.date
        df_qfq = df_qfq[['date', 'open', 'close', 'high', 'low', 'amount']]
        df_qfq.columns = ['date', 'qfq_open', 'qfq_close', 'qfq_high', 'qfq_low', 'amount']

        # 后复权数据
        df_hfq = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{symbol}", start_date=start_date, end_date="20301231", adjust="hfq")
        if df_hfq is None or df_hfq.empty:
            raise Exception("Tencent returned empty hfq data")
        df_hfq['date'] = pd.to_datetime(df_hfq['date']).dt.date
        df_hfq = df_hfq[['date', 'open', 'close', 'high', 'low']]
        df_hfq.columns = ['date', 'adj_open', 'adj_close', 'adj_high', 'adj_low']

        # 合并数据使用outer join
        df = pd.merge(df_qfq, df_hfq, on='date', how='outer')

        if df.empty:
            raise Exception("Merged data is empty after joining qfq and hfq data")

        # Copy qfq to raw columns (Tencent only has adj data)
        df['open'] = df['qfq_open']
        df['close'] = df['qfq_close']
        df['high'] = df['qfq_high']
        df['low'] = df['qfq_low']

        # Estimate volume from amount (amount = price * volume * 100)
        df['volume'] = (df['amount'] / df['qfq_close'] / 100).fillna(0)
        df = df.drop(columns=['amount'])

        # Validate data before returning
        df = validate_price_data(df, "Tencent")

        if df.empty:
            raise Exception("All Tencent data was filtered out as invalid")

        print(f"  Tencent success! Got {len(df)} records")
        return df
    except Exception as e:
        print(f"  Tencent failed: {str(e)}")
        
    # Fall back to Sina (only has raw data)
    try:
        print("  Trying Sina...")
        prefix = "sz" if symbol.startswith("0") or symbol.startswith("3") else "sh"
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{symbol}", start_date=start_date, end_date="20301231")
        if df is None or df.empty:
            raise Exception("Sina returned empty data")
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
        # Sina 只有原始数据，前复权和后复权都用原始数据填充
        df['qfq_open'] = df['open']
        df['qfq_high'] = df['high']
        df['qfq_low'] = df['low']
        df['qfq_close'] = df['close']
        df['adj_open'] = df['open']
        df['adj_high'] = df['high']
        df['adj_low'] = df['low']
        df['adj_close'] = df['close']

        # Validate data before returning
        df = validate_price_data(df, "Sina")

        if df.empty:
            raise Exception("All Sina data was filtered out as invalid")

        print(f"  Sina success! Got {len(df)} records")
        return df
    except Exception as e:
        print(f"  Sina failed: {str(e)}")
        raise Exception(f"All data sources failed for {symbol}: {str(e)}")

def get_fund_data(symbol: str, start_date: str = "20000101", name: Optional[str] = None):
    """
    Fetch historical data for Funds from East Money.
    """
    print(f"Fetching data for Fund: {symbol} from {start_date}")
    # fund_etf_hist_em is from East Money
    # 前复权数据
    df_qfq = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, adjust="qfq")
    if df_qfq is None or df_qfq.empty:
        raise Exception("East Money returned empty qfq data for fund")
    df_qfq['date'] = pd.to_datetime(df_qfq['日期']).dt.date
    df_qfq = df_qfq[['date', '开盘', '收盘', '最高', '最低', '成交量']]
    df_qfq.columns = ['date', 'qfq_open', 'qfq_close', 'qfq_high', 'qfq_low', 'volume']

    # 后复权数据
    df_hfq = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, adjust="hfq")
    if df_hfq is None or df_hfq.empty:
        raise Exception("East Money returned empty hfq data for fund")
    df_hfq['date'] = pd.to_datetime(df_hfq['日期']).dt.date
    df_hfq = df_hfq[['date', '开盘', '收盘', '最高', '最低']]
    df_hfq.columns = ['date', 'adj_open', 'adj_close', 'adj_high', 'adj_low']

    # 不复权数据（基金通常直接用前复权）
    df_raw = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, adjust="")
    if df_raw is None or df_raw.empty:
        raise Exception("East Money returned empty raw data for fund")
    df_raw['date'] = pd.to_datetime(df_raw['日期']).dt.date
    df_raw = df_raw[['date', '开盘', '收盘', '最高', '最低']]
    df_raw.columns = ['date', 'open', 'close', 'high', 'low']

    # 合并所有数据使用outer join
    df = pd.merge(df_raw, df_qfq, on='date', how='outer')
    df = pd.merge(df, df_hfq, on='date', how='outer')

    if df.empty:
        raise Exception("Merged fund data is empty")

    # Validate data before returning
    df = validate_price_data(df, "Fund")

    if df.empty:
        raise Exception("All fund data was filtered out as invalid")

    print(f"  Fund data success! Got {len(df)} records")
    return df

def sync_asset_data(symbol: str, asset_type: str, name: Optional[str] = None, start_date: str = "20000101"):
    db = SessionLocal()
    
    # Fetch stock name if not provided
    if not name and asset_type == 'stock':
        try:
            stock_info = ak.stock_individual_info_em(symbol=symbol)
            if isinstance(stock_info, pd.DataFrame):
                stock_name_row = stock_info[stock_info['item'] == '股票简称']
                if not stock_name_row.empty:
                    name = stock_name_row['value'].values[0]
                    print(f"Found stock name: {name} for symbol {symbol}")
        except Exception as e:
            print(f"Failed to fetch stock name for {symbol}: {str(e)}")
    
    # Validate: must have name to proceed
    if not name or not name.strip():
        print(f"Error: Cannot sync {symbol} - failed to get stock name. Please check the symbol and try again.")
        db.close()
        raise Exception(f"Failed to get stock name for {symbol}. Sync aborted.")
    
    # Check or create asset
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        asset = Asset(symbol=symbol, name=name, asset_type=asset_type)
        db.add(asset)
        db.commit()
        db.refresh(asset)
    elif not asset.name:
        asset.name = name
        db.commit()
    
    if asset_type == 'stock':
        df = get_stock_data(symbol, start_date)
    elif asset_type == 'fund':
        df = get_fund_data(symbol, start_date)
    else:
        print(f"Unsupported asset type: {asset_type}")
        db.close()
        return

    # Bulk insert price history
    for index, row in df.iterrows():
        price_record = PriceHistory(
            asset_id=asset.id,
            date=row['date'],
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            # 后复权数据
            adj_open=row['adj_open'],
            adj_high=row['adj_high'],
            adj_low=row['adj_low'],
            adj_close=row['adj_close'],
            # 前复权数据
            qfq_open=row.get('qfq_open'),
            qfq_high=row.get('qfq_high'),
            qfq_low=row.get('qfq_low'),
            qfq_close=row.get('qfq_close'),
            volume=row['volume']
        )
        db.merge(price_record)
    
    try:
        db.commit()
        print(f"Successfully synced {len(df)} records for {symbol}")
    except Exception as e:
        db.rollback()
        print(f"Error syncing {symbol}: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    # Example sync
    # sync_asset_data("600519", "stock", "贵州茅台")
