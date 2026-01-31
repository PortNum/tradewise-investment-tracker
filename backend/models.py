from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine

Base = declarative_base()

class Asset(Base):
    __tablename__ = 'assets'
    id = Column(Integer, primary_key=True)
    symbol = Column(String, unique=True, nullable=False) # e.g., '600519'
    name = Column(String)
    asset_type = Column(String) # 'stock', 'fund', 'future'
    
    prices = relationship("PriceHistory", back_populates="asset", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="asset")

class PriceHistory(Base):
    __tablename__ = 'price_history'
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey('assets.id'), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    # 后复权数据 (hfq)
    adj_open = Column(Float)
    adj_high = Column(Float)
    adj_low = Column(Float)
    adj_close = Column(Float)
    # 前复权数据 (qfq)
    qfq_open = Column(Float)
    qfq_high = Column(Float)
    qfq_low = Column(Float)
    qfq_close = Column(Float)
    volume = Column(Float)

    asset = relationship("Asset", back_populates="prices")

    __table_args__ = (UniqueConstraint('asset_id', 'date', name='_asset_date_uc'),)

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey('assets.id'), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String) # 'buy', 'sell'
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fees = Column(Float, default=0.0)
    
    asset = relationship("Asset", back_populates="transactions")

# Database setup
DATABASE_URL = "sqlite:///./investments.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
