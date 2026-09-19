from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uvicorn
import uuid
import shutil
import os
import base64
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker
from urllib.parse import quote_plus

DB_PASSWORD = "Bazarhaat@123"
DATABASE_URL_ENV = os.getenv("DATABASE_URL")

if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        DATABASE_URL = "sqlite:///./bazarhaat.db"
    else:
        DATABASE_URL = f"postgresql://postgres:{quote_plus(DB_PASSWORD)}@localhost:5433/bazarhaat"

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(String, primary_key=True)
    name = Column(String)
    owner = Column(String)
    phone = Column(String)
    address = Column(String)
    city = Column(String)
    orders = Column(Integer, default=0)
    isOnline = Column(Boolean, default=True)
    isActive = Column(Boolean, default=True)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    price = Column(Float)
    original_price = Column(Float, nullable=True)
    discount = Column(Float, default=0)
    offer_text = Column(String, default="")
    stock = Column(Integer, default=100)
    image = Column(Text)
    category = Column(String, default="General")
    vendor_id = Column(String)

class Rider(Base):
    __tablename__ = "riders"
    id = Column(String, primary_key=True)
    name = Column(String)
    phone = Column(String)
    vehicle = Column(String)
    bank_account = Column(String)
    ifsc = Column(String)
    upi = Column(String)
    rating = Column(Float, default=4.8)
    total_deliveries = Column(Integer, default=0)
    earning = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    otp = Column(String)
    store_qr = Column(String)
    amount = Column(Float)
    customer = Column(String)
    customer_phone = Column(String)
    phone = Column(String)
    address = Column(String)
    status = Column(String, default="New")
    earning = Column(Float, default=45)
    vendor_id = Column(String)
    rider_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class Payout(Base):
    __tablename__ = "payouts"
    id = Column(String, primary_key=True)
    rider_id = Column(String)
    amount = Column(Float)
    method = Column(String)
    upi_id = Column(String, nullable=True)
    bank_account = Column(String, nullable=True)
    ifsc = Column(String, nullable=True)
    status = Column(String, default="Processing")
    created_at = Column(DateTime, default=datetime.now)

class Customer(Base):
    __tablename__ = "customers"
    id = Column(String, primary_key=True)
    name = Column(String, default="BazarHaat Customer")
    phone = Column(String, unique=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

otp_store = {}

try:
    Base.metadata.create_all(bind=engine)
    print(f"✅ DB Connected: {DATABASE_URL}")
except Exception as e:
    print(f"❌ DB Error: {e}")

# FIXED MIGRATION FOR SQLITE + POSTGRES
try:
    with engine.connect() as conn:
        if "sqlite" in DATABASE_URL:
            for sql in [
                "ALTER TABLE products ADD COLUMN vendor_id VARCHAR",
                "ALTER TABLE products ADD COLUMN category VARCHAR DEFAULT 'General'",
                "ALTER TABLE products ADD COLUMN original_price FLOAT DEFAULT 0",
                "ALTER TABLE products ADD COLUMN discount FLOAT DEFAULT 0",
                "ALTER TABLE products ADD COLUMN offer_text VARCHAR DEFAULT ''",
            ]:
                try:
                    conn.execute(text(sql))
                except:
                    pass
        else:
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS vendor_id VARCHAR;"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR DEFAULT 'General';"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS original_price FLOAT DEFAULT 0;"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS discount FLOAT DEFAULT 0;"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS offer_text VARCHAR DEFAULT '';"))
        conn.commit()
        print("✅ Migration OK")
except Exception as e:
    print(f"DB Fix Note: {e}")

app = FastAPI(title="BazarHaat Backend", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
os.makedirs("uploads/riders", exist_ok=True)
os.makedirs("uploads/products", exist_ok=True)

FIXED_CATEGORIES = ["Vegetables", "Fruits", "Dairy", "Groceries", "Electronic Accessories", "Pharmacy", "Clothes", "Kids", "Beauty", "Pet Care", "Beverages"]
db_settings = {"isUserAppLive": True, "isVendorAppLive": True, "isRiderAppLive": True, "isMainWebsiteLive": True, "deliveryCharge": 20, "commission": 5, "appMessage": "Welcome to BazarHaat"}

def init_data():
    db = SessionLocal()
    try:
        if db.query(Vendor).count() == 0:
            db.add_all([
                Vendor(id="VENDOR-01", name="Goreswar Kirana", owner="Bikash", phone="9876543211", address="Goreswar Market", city="Goreswar", orders=42, isOnline=True, isActive=True),
                Vendor(id="VENDOR-02", name="Maa Store Pathsala", owner="Ramesh", phone="9876543212", address="Pathsala Market", city="Pathsala", orders=18, isOnline=True, isActive=True),
            ])
            db.commit()
        if db.query(Product).count() == 0:
            db.add_all([
                Product(name="Fresh Tomato 1kg", price=40, original_price=50, discount=20, offer_text="20% OFF", stock=100, image="https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=200", vendor_id="VENDOR-01", category="Vegetables"),
                Product(name="Amul Milk 1L", price=65, original_price=70, discount=7, offer_text="7% OFF", stock=50, image="https://images.unsplash.com/photo-1550583724-b2692b85b150?w=200", vendor_id="VENDOR-01", category="Dairy"),
            ])
            db.commit()
        if db.query(Rider).count() == 0:
            db.add(Rider(id="BH-RIDER-01", name="Rahul Rider", phone="9876543210", vehicle="Bike - AS-12-AB-1234", bank_account="HDFC ****1234", ifsc="HDFC0001234", upi="rahul@upi", rating=4.8, total_deliveries=22, earning=320.0))
            db.commit()
        if db.query(Order).count() == 0:
            db.add_all([
                Order(id="BH-102", otp="1234", store_qr="STORE-BH-102", amount=250, customer="Rahul Das", customer_phone="9876543210", phone="9876543210", address="Near College, Goreswar, 2.3km", status="New", earning=45, vendor_id="VENDOR-01"),
                Order(id="BH-103", otp="5678", store_qr="STORE-BH-103", amount=450, customer="Ankit Sharma", customer_phone="9876543211", phone="9876543211", address="Main Market, Baihata", status="New", earning=60, vendor_id="VENDOR-01"),
            ])
            db.commit()
    except Exception as e:
        print(f"Seed error: {e}")
        db.rollback()
    finally:
        db.close()
init_data()

class QrVerifyRequest(BaseModel):
    qr_code: str
    rider_id: str
class OtpVerifyRequest(BaseModel):
    order_id: str
    otp: str
class WithdrawRequest(BaseModel):
    rider_id: str
    amount: float
    method: str
    upi_id: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    vehicle: Optional[str] = None
    upi: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
class CustomerLoginRequest(BaseModel):
    phone: str
class CustomerVerifyRequest(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None

@app.get("/")
def home():
    return {"message": "BazarHaat Backend Running", "status": "OK", "docs": "/docs"}

@app.post("/api/customer/send-otp")
def send_customer_otp(req: CustomerLoginRequest):
    otp = "9876"
    otp_store[req.phone] = otp
    return {"success": True, "message": "OTP sent", "otp": otp}

@app.post("/api/customer/verify-otp")
def verify_customer_otp(req: CustomerVerifyRequest):
    db = SessionLocal()
    stored_otp = otp_store.get(req.phone)
    if stored_otp is None:
        db.close()
        raise HTTPException(status_code=400, detail="OTP not sent")
    if str(req.otp)!= str(stored_otp):
        db.close()
        raise HTTPException(status_code=400, detail="Wrong OTP")
    customer = db.query(Customer).filter(Customer.phone == req.phone).first()
    if not customer:
        customer = Customer(id=f"CUST-{uuid.uuid4().hex[:6].upper()}", phone=req.phone, name=req.name or "BazarHaat Customer")
        db.add(customer)
        db.commit()
        db.refresh(customer)
    otp_store.pop(req.phone, None)
    db.close()
    return {"success": True, "customer": {"id": customer.id, "phone": customer.phone, "name": customer.name}, "token": f"token_{customer.id}"}

@app.post("/api/customer/register")
def register_customer_full(data: dict):
    db = SessionLocal()
    phone = data.get("phone") or data.get("Phone Number") or ""
    name = data.get("name") or data.get("fullName") or "BazarHaat Customer"
    town = data.get("town") or data.get("city") or ""
    house = data.get("address") or data.get("house") or ""
    if not phone:
        db.close()
        raise HTTPException(status_code=400, detail="Phone required")
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if customer:
        customer.name = name
        customer.address = f"{house}, {town}"
        db.commit()
        db.refresh(customer)
    else:
        customer = Customer(id=f"CUST-{uuid.uuid4().hex[:6].upper()}", phone=phone, name=name, address=f"{house}, {town}")
        db.add(customer)
        db.commit()
        db.refresh(customer)
    db.close()
    return {"success": True, "customer": {"id": customer.id, "phone": customer.phone, "name": customer.name}, "token": f"token_{customer.id}"}

@app.get("/api/customers")
def get_customers():
    db = SessionLocal()
    c = db.query(Customer).all()
    db.close()
    return c

@app.get("/api/settings")
def get_settings():
    return db_settings

@app.post("/api/settings")
def update_settings(new_settings: dict):
    db_settings.update(new_settings)
    return {"status": "success", "settings": db_settings}

@app.get("/api/dashboard")
def admin_dashboard():
    db = SessionLocal()
    result = {"total_users": db.query(Customer).count(), "total_vendors": db.query(Vendor).count(), "total_riders": db.query(Rider).count(), "total_orders": db.query(Order).count(), "settings": db_settings, "vendors": db.query(Vendor).all()}
    db.close()
    return result

@app.get("/api/vendors")
def get_vendors():
    db = SessionLocal()
    v = db.query(Vendor).all()
    db.close()
    return v

@app.get("/api/vendor/stats/{vendor_id}")
def vendor_stats(vendor_id: str):
    db = SessionLocal()
    try:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found")
        all_orders = db.query(Order).filter(Order.vendor_id == vendor_id).all()
        total_orders = len(all_orders)
        pending_orders = len([o for o in all_orders if o.status == "New"])
        total_income = sum([o.amount or 0 for o in all_orders])
        today = datetime.now().date()
        today_list = [o for o in all_orders if o.created_at and o.created_at.date() == today]
        today_income = sum([o.amount or 0 for o in today_list])
        products_count = db.query(Product).filter(Product.vendor_id == vendor_id).count()
        vendor_dict = {"id": v.id, "name": v.name, "owner": v.owner, "phone": v.phone, "address": v.address, "city": v.city, "orders": v.orders, "isOnline": v.isOnline, "isActive": v.isActive}
        return {"vendor": vendor_dict, "total_orders": total_orders, "pending_orders": pending_orders, "total_income": total_income, "today_income": today_income, "today_orders": len(today_list), "products_count": products_count, "rating": 4.8}
    finally:
        db.close()

@app.post("/api/vendors/{vendor_id}/toggle")
def toggle_store(vendor_id: str):
    db = SessionLocal()
    v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not v:
        db.close()
        raise HTTPException(status_code=404, detail="Vendor not found")
    v.isOnline = not v.isOnline
    v.isActive = True
    db.commit()
    db.refresh(v)
    res = {"success": True, "vendor": {"id": v.id, "name": v.name, "isOnline": v.isOnline}, "status": "Online" if v.isOnline else "Offline"}
    db.close()
    return res

@app.post("/api/vendors/add")
def add_vendor(data: dict):
    db = SessionLocal()
    new_id = f"VENDOR-{db.query(Vendor).count()+1:02d}"
    new_v = Vendor(id=new_id, name=data.get("name", "New Store"), owner=data.get("owner", "Owner"), phone=data.get("phone", ""), address=data.get("address", ""), city=data.get("city", "Goreswar"), orders=0, isOnline=True, isActive=True)
    db.add(new_v)
    db.commit()
    db.refresh(new_v)
    db.close()
    return {"success": True, "vendor": {"id": new_v.id, "name": new_v.name}}

@app.get("/api/categories")
def get_categories():
    return ["All"] + FIXED_CATEGORIES

@app.get("/api/products")
def get_products(category: Optional[str] = None):
    db = SessionLocal()
    try:
        if category and category!= "All":
            products = db.query(Product).filter(Product.stock > 0, Product.category.ilike(f"%{category}%")).all()
        else:
            products = db.query(Product).filter(Product.stock > 0).all()
    finally:
        db.close()
    return products

@app.post("/api/vendor/products")
def vendor_add_product(product: dict):
    db = SessionLocal()
    try:
        price = product.get("price") or 0
        name = product.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="Product name required")
        image_data = product.get("image") or product.get("image_url") or ""
        final_image_path = image_data
        if image_data and image_data.startswith("data:image"):
            try:
                header, encoded = image_data.split(",", 1)
                ext = "jpg"
                filename = f"{uuid.uuid4().hex}.{ext}"
                file_location = f"uploads/products/{filename}"
                os.makedirs("uploads/products", exist_ok=True)
                with open(file_location, "wb") as f:
                    f.write(base64.b64decode(encoded))
                final_image_path = f"/{file_location}"
            except:
                final_image_path = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=400"
        p = Product(name=name, price=float(price), original_price=float(product.get("original_price", price)), discount=float(product.get("discount", 0)), offer_text=product.get("offer_text",""), stock=int(product.get("stock", 100)), image=str(final_image_path), vendor_id=product.get("vendor_id") or "VENDOR-01", category=product.get("category", "General"))
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"id": p.id, "name": p.name, "price": p.price, "original_price": p.original_price, "discount": p.discount}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/vendor/products/add-with-image")
async def add_product_with_image(
    name: str = Form(...),
    price: float = Form(...),
    original_price: float = Form(0),
    discount: float = Form(0),
    offer_text: str = Form(""),
    stock: int = Form(100),
    category: str = Form("General"),
    vendor_id: str = Form("VENDOR-01"),
    product_image: UploadFile = File(None),
    image: UploadFile = File(None),
):
    db = SessionLocal()
    try:
        file_obj = product_image if product_image and product_image.filename else image
        image_path = ""
        if file_obj and file_obj.filename:
            filename = f"{uuid.uuid4().hex}_{file_obj.filename}"
            file_location = f"uploads/products/{filename}"
            os.makedirs("uploads/products", exist_ok=True)
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file_obj.file, buffer)
            image_path = f"/{file_location}"
        if not image_path:
            image_path = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=400"

        if original_price > 0 and original_price > price and discount == 0:
            discount = round(((original_price - price) / original_price) * 100)
        if discount > 0 and not offer_text:
            offer_text = f"{int(discount)}% OFF"

        p = Product(name=name, price=float(price), original_price=float(original_price), discount=float(discount), offer_text=offer_text, stock=int(stock), image=image_path, vendor_id=vendor_id, category=category)
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"id": p.id, "name": p.name, "price": p.price, "original_price": p.original_price, "discount": p.discount, "offer_text": p.offer_text, "stock": p.stock, "image": p.image, "category": p.category, "vendor_id": p.vendor_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/vendor/products/{vendor_id}")
def get_vendor_products(vendor_id: str):
    db = SessionLocal()
    products = db.query(Product).filter(Product.vendor_id == vendor_id).all()
    db.close()
    return products

@app.get("/api/my-orders/{phone}")
def my_orders(phone: str):
    db = SessionLocal()
    orders = db.query(Order).filter((Order.customer_phone == phone) | (Order.phone == phone)).all()
    db.close()
    return orders

@app.get("/api/vendor/orders/{vendor_id}")
def vendor_orders(vendor_id: str):
    db = SessionLocal()
    orders = db.query(Order).filter(Order.vendor_id == vendor_id, Order.status == "New").all()
    db.close()
    return orders

@app.post("/api/vendor/orders/{order_id}/accept")
def vendor_accept(order_id: str):
    db = SessionLocal()
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        db.close()
        raise HTTPException(status_code=404, detail="Order not found")
    o.status = "Accepted_by_Vendor"
    db.commit()
    db.close()
    return {"success": True, "order_id": o.id}

@app.post("/api/orders")
def place_order(data: dict):
    db = SessionLocal()
    order_id = f"BH-{uuid.uuid4().hex[:3].upper()}"
    otp = str(uuid.uuid4().int)[:4]
    total = 0
    for i in data.get("items", []):
        prod = db.query(Product).filter(Product.id == i["product_id"]).first()
        if prod: total += prod.price * i["qty"]
    new_order = Order(id=order_id, otp=otp, store_qr=f"STORE-{order_id}", amount=total, customer=data.get("customer_name", "Customer"), customer_phone=data["customer_phone"], phone=data["customer_phone"], address=data.get("address", "Goreswar"), status="New", earning=45, vendor_id="VENDOR-01")
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    db.close()
    return {"id": new_order.id, "otp": new_order.otp, "amount": new_order.amount, "status": new_order.status}

@app.get("/rider/{rider_id}")
def get_rider(rider_id: str):
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.id == rider_id).first()
    db.close()
    if not rider: raise HTTPException(status_code=404, detail="Rider not found")
    return rider

@app.put("/rider/{rider_id}")
def update_rider(rider_id: str, data: ProfileUpdateRequest):
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider:
        db.close()
        raise HTTPException(status_code=404, detail="Rider not found")
    if data.name: rider.name = data.name
    if data.phone: rider.phone = data.phone
    if data.vehicle: rider.vehicle = data.vehicle
    if data.upi: rider.upi = data.upi
    if data.bank_account: rider.bank_account = data.bank_account
    if data.ifsc: rider.ifsc = data.ifsc
    db.commit()
    db.refresh(rider)
    db.close()
    return {"message": "Profile Updated"}

@app.get("/orders")
def get_orders(status: Optional[str] = None):
    db = SessionLocal()
    orders = db.query(Order).filter(Order.status == status).all() if status else db.query(Order).all()
    db.close()
    return orders

@app.get("/api/rider/orders")
def get_rider_available_orders():
    db = SessionLocal()
    orders = db.query(Order).filter(Order.status.in_(["New","Accepted_by_Vendor", "Assigned", "Picked Up", "Accepted_by_Rider"])).all()
    db.close()
    return orders

@app.post("/api/assign-rider")
def assign_rider(order_id: str, rider_id: str):
    db = SessionLocal()
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        db.close()
        raise HTTPException(status_code=404, detail="Order not found")
    o.rider_id = rider_id
    o.status = "Assigned"
    db.commit()
    db.close()
    return {"status": "success"}

@app.post("/verify-qr")
def verify_qr(req: QrVerifyRequest):
    db = SessionLocal()
    order = db.query(Order).filter(Order.store_qr == req.qr_code).first()
    if not order:
        db.close()
        raise HTTPException(status_code=400, detail="Invalid QR")
    order.status = "Picked Up"
    order.rider_id = req.rider_id
    db.commit()
    db.close()
    return {"success": True}

@app.post("/verify-otp")
def verify_otp(req: OtpVerifyRequest):
    db = SessionLocal()
    order = db.query(Order).filter(Order.id == req.order_id).first()
    if not order:
        db.close()
        raise HTTPException(status_code=404, detail="Order not found")
    if order.otp!= req.otp:
        db.close()
        raise HTTPException(status_code=400, detail="Wrong OTP")
    order.status = "Delivered"
    if order.rider_id:
        rider = db.query(Rider).filter(Rider.id == order.rider_id).first()
        if rider: rider.earning += order.earning
    db.commit()
    db.close()
    return {"success": True}

@app.post("/api/rider/orders/{order_id}/accept")
def rider_accept_order(order_id: str, data: dict):
    db = SessionLocal()
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        db.close()
        raise HTTPException(status_code=404, detail="Order not found")
    o.status = "Accepted_by_Rider"
    o.rider_id = data.get("rider_id", "RIDER-01")
    db.commit()
    db.close()
    return {"success": True}

@app.post("/api/rider/orders/{order_id}/deliver")
def rider_deliver_order(order_id: str, data: dict):
    db = SessionLocal()
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        db.close()
        raise HTTPException(status_code=404, detail="Order not found")
    if str(o.otp)!= str(data.get("otp")):
        db.close()
        raise HTTPException(status_code=400, detail="Wrong OTP")
    o.status = "Delivered"
    if o.rider_id:
        rider = db.query(Rider).filter(Rider.id == o.rider_id).first()
        if rider: rider.earning += o.earning
    db.commit()
    db.close()
    return {"success": True}

@app.post("/withdraw")
def withdraw_money(req: WithdrawRequest):
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.id == req.rider_id).first()
    if not rider:
        db.close()
        raise HTTPException(status_code=404, detail="Rider not found")
    if req.amount > rider.earning:
        db.close()
        raise HTTPException(status_code=400, detail="Insufficient Balance")
    rider.earning -= req.amount
    db.commit()
    db.close()
    return {"success": True}

@app.post("/api/rider/payout/request")
def request_payout(data: dict):
    db = SessionLocal()
    amount = data.get("amount", 0)
    if amount < 100:
        db.close()
        return {"success": False, "message": "Minimum ₹100"}
    payout = Payout(id=f"PAY-{uuid.uuid4().hex[:4].upper()}", rider_id=data.get("rider_id", "RIDER-01"), amount=amount, method=data.get("method","UPI"), upi_id=data.get("upi_id",""), bank_account=data.get("bank_account",""), ifsc=data.get("ifsc",""), status="Processing")
    db.add(payout)
    db.commit()
    db.close()
    return {"success": True}

@app.get("/api/rider/payouts/{rider_id}")
def get_payouts(rider_id: str):
    db = SessionLocal()
    p = db.query(Payout).filter(Payout.rider_id == rider_id).all()
    db.close()
    return p

@app.get("/api/admin/payouts")
def get_all_payouts():
    db = SessionLocal()
    p = db.query(Payout).all()
    db.close()
    return p

@app.post("/api/admin/payouts/{payout_id}/approve")
def approve_payout(payout_id: str):
    db = SessionLocal()
    p = db.query(Payout).filter(Payout.id == payout_id).first()
    if not p:
        db.close()
        raise HTTPException(status_code=404, detail="Not Found")
    p.status = "Completed"
    db.commit()
    db.close()
    return {"success": True}

rider_profiles = {}

@app.post("/api/rider/register")
async def register_rider(rider_id: str = Form(...), name: str = Form(...), phone: str = Form(...), bike_number: str = Form(...), photo: UploadFile = File(None), rc: UploadFile = File(None), license: UploadFile = File(None), aadhaar: UploadFile = File(None)):
    def save_file(f, prefix):
        if not f or not f.filename: return ""
        path = f"uploads/riders/{prefix}_{rider_id}_{f.filename}"
        with open(path, "wb") as buffer: shutil.copyfileobj(f.file, buffer)
        return f"/{path}"
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider:
        rider = Rider(id=rider_id, name=name, phone=phone, vehicle=bike_number, earning=0, is_verified=False)
        db.add(rider)
    else:
        rider.name = name
        rider.phone = phone
        rider.vehicle = bike_number
    db.commit()
    db.close()
    profile = {"rider_id": rider_id, "name": name, "phone": phone, "bike_number": bike_number, "photo_url": save_file(photo, "photo"), "rc_url": save_file(rc, "rc"), "license_url": save_file(license, "license"), "aadhaar_url": save_file(aadhaar, "aadhaar"), "is_verified": False}
    rider_profiles[rider_id] = profile
    return {"status": "success", "profile": profile}

@app.get("/api/admin/riders")
def admin_get_all_riders():
    db = SessionLocal()
    riders = db.query(Rider).all()
    db.close()
    return riders

@app.post("/api/admin/riders/{rider_id}/verify")
def admin_verify_rider_by_id(rider_id: str):
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider:
        db.close()
        raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_verified = True
    db.commit()
    db.close()
    return {"success": True}

@app.post("/api/admin/verify-rider/{rider_id}")
def verify_rider_old(rider_id: str):
    return admin_verify_rider_by_id(rider_id)

@app.post("/api/admin/orders/{order_id}/status")
def admin_update_order_status(order_id: str, data: dict):
    db = SessionLocal()
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        db.close()
        raise HTTPException(status_code=404, detail="Order not found")
    o.status = data.get("status", o.status)
    db.commit()
    db.close()
    return {"id": o.id, "status": o.status}

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)