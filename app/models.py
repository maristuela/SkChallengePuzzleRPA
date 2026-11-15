from datetime import date
from sqlalchemy import String, Integer, Float, Boolean, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Region(Base):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    region_name: Mapped[str] = mapped_column(String, index=True)
    regional_center: Mapped[str] = mapped_column(String, nullable=True)

    clients: Mapped[list["Client"]] = relationship(back_populates="region")
    outlets: Mapped[list["Outlet"]] = relationship(back_populates="region")

class Client(Base):
    __tablename__ = "clients"

    client_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_name: Mapped[str] = mapped_column(String, index=True)
    inn: Mapped[str] = mapped_column(String, nullable=True)
    segment: Mapped[str] = mapped_column(String, nullable=True, index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.region_id"))
    registered_date: Mapped[date] = mapped_column(Date, nullable=True)
    is_key_client: Mapped[bool] = mapped_column(Boolean, default=False)

    region: Mapped["Region"] = relationship(back_populates="clients")
    contracts: Mapped[list["Contract"]] = relationship(back_populates="client")
    sales: Mapped[list["Sale"]] = relationship(back_populates="client")
    discounts: Mapped[list["Discount"]] = relationship(back_populates="client")

class Outlet(Base):
    __tablename__ = "outlets"

    outlet_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    outlet_name: Mapped[str] = mapped_column(String, index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.region_id"))
    city: Mapped[str] = mapped_column(String, nullable=True)
    outlet_type: Mapped[str] = mapped_column(String, nullable=True)
    address: Mapped[str] = mapped_column(String, nullable=True)
    opened_date: Mapped[date] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date] = mapped_column(Date, nullable=True)

    region: Mapped["Region"] = relationship(back_populates="outlets")
    sales: Mapped[list["Sale"]] = relationship(back_populates="outlet")
    plans: Mapped[list["Plan"]] = relationship(back_populates="outlet")

class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_name: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String, nullable=True)
    launch_date: Mapped[date] = mapped_column(Date, nullable=True)
    discontinued_date: Mapped[date] = mapped_column(Date, nullable=True)

    # Связи
    sales: Mapped[list["Sale"]] = relationship(back_populates="product")
    plans: Mapped[list["Plan"]] = relationship(back_populates="product")

class Contract(Base):
    __tablename__ = "contracts"

    contract_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    contract_number: Mapped[str] = mapped_column(String, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.client_id"))
    start_date: Mapped[date] = mapped_column(Date, nullable=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=True)
    base_discount_pct: Mapped[float] = mapped_column(Float, nullable=True)

    client: Mapped["Client"] = relationship(back_populates="contracts")

class Sale(Base):
    __tablename__ = "sales"

    sale_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sale_date: Mapped[date] = mapped_column(Date, index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.contract_id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.client_id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.outlet_id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    quantity: Mapped[float] = mapped_column(Float, nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=True)

    client: Mapped["Client"] = relationship(back_populates="sales")
    outlet: Mapped["Outlet"] = relationship(back_populates="sales")
    product: Mapped["Product"] = relationship(back_populates="sales")
    discounts: Mapped[list["Discount"]] = relationship(back_populates="sale")

class Plan(Base):
    __tablename__ = "sales_plan"  # ← ИЗМЕНИЛИ ЗДЕСЬ (было "plans")

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_month: Mapped[date] = mapped_column(Date, index=True)

    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.outlet_id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    plan_amount: Mapped[float] = mapped_column(Float, nullable=True)
    plan_qty: Mapped[float] = mapped_column(Float, nullable=True)

    outlet: Mapped["Outlet"] = relationship(back_populates="plans")
    product: Mapped["Product"] = relationship(back_populates="plans")

class Discount(Base):
    __tablename__ = "discounts"

    discount_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.sale_id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.client_id"))
    discount_date: Mapped[date] = mapped_column(Date, nullable=True)
    discount_amount: Mapped[float] = mapped_column(Float, nullable=True)
    discount_pct: Mapped[float] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String, nullable=True)

    sale: Mapped["Sale"] = relationship(back_populates="discounts")
    client: Mapped["Client"] = relationship(back_populates="discounts")