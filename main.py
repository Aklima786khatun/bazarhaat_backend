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
import random
import time
import base64
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker
from urllib.parse import quote_plus

import os
from urllib.parse import quote_plus

DB_PASSWORD = os.getenv("DB_PASSWORD", "Bazarhaat@123")
DATABASE_URL_ENV = os.getenv("DATABASE_URL")

if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        # Render pe DATABASE_URL compulsory hai - SQLite allow nahi
        raise Exception("❌ DATABASE_URL not set on Render! Go to Environment and add Postgres Internal URL")
    else:
        # Local laptop ke liye
        DATABASE_URL = f"postgresql://postgres:{quote_plus(DB_PASSWORD)}@localhost:5433/bazarhaat"

print(f"🔗 Using DB: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

# Engine creation - ye add karna mat bhoolna
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

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
    name = Column(String, default="")
    phone = Column(String, unique=True, index=True)
    is_verified = Column(Boolean, default=False)
    user_type = Column(String, default="RIDER")
    vehicle = Column(String, default="")
    bike_number = Column(String, default="")
    bank_account = Column(String, default="")
    ifsc = Column(String, default="")
    upi = Column(String, default="")
    rating = Column(Float, default=4.8)
    total_deliveries = Column(Integer, default=0)
    earning = Column(Float, default=0.0)
    photo_url = Column(String, default="")
    rc_url = Column(String, default="")
    license_url = Column(String, default="")
    aadhaar_url = Column(String, default="")

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
rider_otp_store = {}

try:
    Base.metadata.create_all(bind=engine)
    print(f"✅ DB Connected: {DATABASE_URL}")
except Exception as e:
    print(f"❌ DB Error: {e}")

try:
    with engine.connect() as conn:
        stmts = [
            "ALTER TABLE riders ADD COLUMN bike_number VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN user_type VARCHAR DEFAULT 'RIDER'",
            "ALTER TABLE riders ADD COLUMN photo_url VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN rc_url VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN license_url VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN aadhaar_url VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN bank_account VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN ifsc VARCHAR DEFAULT ''",
            "ALTER TABLE riders ADD COLUMN upi VARCHAR DEFAULT ''",
            "ALTER TABLE products ADD COLUMN vendor_id VARCHAR",
            "ALTER TABLE products ADD COLUMN category VARCHAR DEFAULT 'General'",
            "ALTER TABLE products ADD COLUMN original_price FLOAT DEFAULT 0",
            "ALTER TABLE products ADD COLUMN discount FLOAT DEFAULT 0",
            "ALTER TABLE products ADD COLUMN offer_text VARCHAR DEFAULT ''",
        ]
        if "sqlite" in DATABASE_URL:
            for s in stmts:
                try: conn.execute(text(s))
                except: pass
        else:
            for s in stmts:
                pg = s.replace("ADD COLUMN", "ADD COLUMN IF NOT EXISTS")
                try: conn.execute(text(pg))
                except: pass
        conn.commit()
        print("✅ Migration OK")
except Exception as e:
    print(f"Migration Note: {e}")

app = FastAPI(title="BazarHaat Backend", version="3.0.0")
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
            db.add(Rider(id="BH-RIDER-01", name="Rahul Rider", phone="9876543210", vehicle="Bike - AS-12-AB-1234", bike_number="AS-12-AB-1234", bank_account="HDFC ****1234", ifsc="HDFC0001234", upi="rahul@upi", rating=4.8, total_deliveries=22, earning=320.0, is_verified=True))
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

class RiderOtpRequest(BaseModel): phone: str
class RiderOtpVerify(BaseModel): phone: str; otp: str
class QrVerifyRequest(BaseModel): qr_code: str; rider_id: str
class OtpVerifyRequest(BaseModel): order_id: str; otp: str
class WithdrawRequest(BaseModel): rider_id: str; amount: float; method: str; upi_id: Optional[str] = None; account_number: Optional[str] = None; ifsc: Optional[str] = None
class ProfileUpdateRequest(BaseModel): name: Optional[str] = None; phone: Optional[str] = None; vehicle: Optional[str] = None; upi: Optional[str] = None; bank_account: Optional[str] = None; ifsc: Optional[str] = None
class CustomerLoginRequest(BaseModel): phone: str
class CustomerVerifyRequest(BaseModel): phone: str; otp: str; name: Optional[str] = None
class ApproveRiderRequest(BaseModel): rider_id: Optional[str] = None; id: Optional[str] = None; is_verified: Optional[bool] = True

@app.get("/")
def home():
    return {"message": "BazarHaat Backend Running v3.0 Rider Auth OK", "status": "OK", "docs": "/docs"}

@app.post("/api/rider/auth/send-otp")
def rider_send_otp(req: RiderOtpRequest):
    db = SessionLocal()
    if db.query(Customer).filter(Customer.phone == req.phone).first():
        db.close()
        return {"success": False, "message": "Ye number Customer App me hai"}
    rider = db.query(Rider).filter(Rider.phone == req.phone).first()
    is_new = rider is None
    db.close()
    otp = str(random.randint(100000, 999999))
    rider_otp_store[req.phone] = {"otp": otp, "time": time.time()}
    print(f"🔐 RIDER OTP {req.phone} = {otp}")
    return {"success": True, "message": "OTP sent", "otp": otp, "demo_otp": "123456", "isNewUser": is_new}

@app.post("/api/rider/auth/verify-otp")
def rider_verify_otp(req: RiderOtpVerify):
    if req.otp == "123456":
        db = SessionLocal()
        rider = db.query(Rider).filter(Rider.phone == req.phone).first()
        if not rider:
            new_id = f"RIDER-{req.phone[-4:]}-{uuid.uuid4().hex[:3].upper()}"
            rider = Rider(id=new_id, phone=req.phone, is_verified=False, earning=0)
            db.add(rider); db.commit(); db.refresh(rider); db.close()
            return {"success": True, "rider_id": rider.id, "isNewUser": True, "profileExists": False}
        rid, prof, ver = rider.id, bool(rider.name and rider.bike_number), rider.is_verified
        db.close()
        return {"success": True, "rider_id": rid, "isNewUser": False, "profileExists": prof, "is_verified": ver}
    saved = rider_otp_store.get(req.phone)
    if not saved: raise HTTPException(status_code=400, detail="OTP not sent")
    if time.time() - saved["time"] > 300: raise HTTPException(status_code=400, detail="Expired")
    if saved["otp"]!= req.otp: raise HTTPException(status_code=400, detail="Invalid OTP")
    del rider_otp_store[req.phone]
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.phone == req.phone).first()
    if not rider:
        new_id = f"RIDER-{req.phone[-4:]}-{uuid.uuid4().hex[:3].upper()}"
        rider = Rider(id=new_id, phone=req.phone, is_verified=False, earning=0)
        db.add(rider); db.commit(); db.refresh(rider); db.close()
        return {"success": True, "rider_id": rider.id, "isNewUser": True}
    rid = rider.id; db.close()
    return {"success": True, "rider_id": rid}

@app.get("/api/rider/profile/{rider_id}")
def get_rider_profile(rider_id: str):
    db = SessionLocal()
    rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider: rider = db.query(Rider).filter(Rider.phone == rider_id).first()
    db.close()
    if not rider: return {"not_found": True, "is_verified": False}
    return {"rider_id": rider.id, "phone": rider.phone, "name": rider.name, "bike_number": rider.bike_number, "is_verified": rider.is_verified, "earning": rider.earning}

@app.post("/api/customer/send-otp")
def send_customer_otp(req: CustomerLoginRequest):
    otp = "9876"; otp_store[req.phone] = otp
    return {"success": True, "message": "OTP sent", "otp": otp}

@app.post("/api/customer/verify-otp")
def verify_customer_otp(req: CustomerVerifyRequest):
    db = SessionLocal(); stored = otp_store.get(req.phone)
    if stored is None: db.close(); raise HTTPException(status_code=400, detail="OTP not sent")
    if str(req.otp)!= str(stored): db.close(); raise HTTPException(status_code=400, detail="Wrong OTP")
    customer = db.query(Customer).filter(Customer.phone == req.phone).first()
    if not customer:
        customer = Customer(id=f"CUST-{uuid.uuid4().hex[:6].upper()}", phone=req.phone, name=req.name or "BazarHaat Customer")
        db.add(customer); db.commit(); db.refresh(customer)
    otp_store.pop(req.phone, None); db.close()
    return {"success": True, "customer": {"id": customer.id, "phone": customer.phone, "name": customer.name}, "token": f"token_{customer.id}"}

@app.get("/api/vendors")
def get_vendors(): db = SessionLocal(); v = db.query(Vendor).all(); db.close(); return v

@app.get("/api/products")
def get_products(category: Optional[str] = None):
    db = SessionLocal()
    try:
        if category and category!= "All": products = db.query(Product).filter(Product.stock > 0, Product.category.ilike(f"%{category}%")).all()
        else: products = db.query(Product).filter(Product.stock > 0).all()
    finally: db.close()
    return products

@app.get("/api/rider/orders")
def get_rider_available_orders(): db = SessionLocal(); orders = db.query(Order).filter(Order.status.in_(["New","Accepted_by_Vendor", "Assigned", "Picked Up", "Accepted_by_Rider"])).all(); db.close(); return orders

@app.post("/api/rider/orders/{order_id}/accept")
def rider_accept_order(order_id: str, data: dict):
    db = SessionLocal(); o = db.query(Order).filter(Order.id == order_id).first()
    if not o: db.close(); raise HTTPException(status_code=404, detail="Order not found")
    o.status = "Accepted_by_Rider"; o.rider_id = data.get("rider_id", "RIDER-01"); db.commit(); db.close(); return {"success": True}

@app.post("/api/rider/orders/{order_id}/deliver")
def rider_deliver_order(order_id: str, data: dict):
    db = SessionLocal(); o = db.query(Order).filter(Order.id == order_id).first()
    if not o: db.close(); raise HTTPException(status_code=404, detail="Order not found")
    if str(o.otp)!= str(data.get("otp")): db.close(); raise HTTPException(status_code=400, detail="Wrong OTP")
    o.status = "Delivered"
    if o.rider_id:
        rider = db.query(Rider).filter(Rider.id == o.rider_id).first()
        if rider: rider.earning += o.earning
    db.commit(); db.close(); return {"success": True}

# ================= ADMIN & RIDER APPROVAL APIS - FINAL FIX =================
@app.get("/api/riders")
def get_all_riders_alias():
    db = SessionLocal(); r = db.query(Rider).all(); db.close(); return r

@app.get("/api/rider/all")
def get_rider_all():
    db = SessionLocal(); r = db.query(Rider).all(); db.close(); return r

@app.get("/api/admin/riders")
def admin_get_all_riders():
    db = SessionLocal(); r = db.query(Rider).all(); db.close(); return r

@app.post("/api/admin/riders/{rider_id}/verify")
def admin_verify_rider_by_id(rider_id: str):
    db = SessionLocal(); rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider: db.close(); raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_verified = True; db.commit(); db.close(); return {"success": True, "rider_id": rider_id, "is_verified": True}

@app.post("/api/rider/verify/{rider_id}")
def rider_verify_path(rider_id: str, req: Optional[ApproveRiderRequest] = None):
    db = SessionLocal(); rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider: rider = db.query(Rider).filter(Rider.phone == rider_id).first()
    if not rider: db.close(); raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_verified = True; db.commit(); db.refresh(rider); db.close()
    print(f"✅ Approved: {rider_id}")
    return {"success": True, "rider_id": rider.id, "is_verified": True}

@app.post("/api/riders/{rider_id}/verify")
def riders_verify_alias(rider_id: str):
    return rider_verify_path(rider_id)

@app.post("/api/admin/approve-rider")
def admin_approve_rider(req: ApproveRiderRequest):
    final_id = req.rider_id or req.id
    if not final_id: raise HTTPException(status_code=400, detail="rider_id required")
    db = SessionLocal(); rider = db.query(Rider).filter(Rider.id == final_id).first()
    if not rider: rider = db.query(Rider).filter(Rider.phone == final_id).first()
    if not rider: db.close(); raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_verified = True; db.commit(); db.close()
    return {"success": True, "rider_id": final_id, "is_verified": True}

@app.post("/api/rider/approve")
def rider_approve_body(req: ApproveRiderRequest):
    return admin_approve_rider(req)

@app.post("/api/rider/reject/{rider_id}")
def rider_reject(rider_id: str):
    db = SessionLocal(); rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider: db.close(); raise HTTPException(status_code=404, detail="Rider not found")
    rider.is_verified = False; db.commit(); db.close()
    return {"success": True, "rejected": True}

@app.post("/api/rider/penalty/{rider_id}")
def rider_penalty(rider_id: str, data: dict):
    return {"success": True, "message": f"Penalty applied to {rider_id}"}
@app.get("/api/settings")
def get_settings_api(): return db_settings

@app.post("/api/settings")
def update_settings_api(data: dict):
    db_settings.update(data)
    return {"success": True}
class ProductCreate(BaseModel):
    name: str
    price: float
    original_price: Optional[float] = None
    discount: Optional[float] = 0
    offer_text: Optional[str] = ""
    stock: Optional[int] = 100
    image: Optional[str] = ""
    category: Optional[str] = "Vegetables"
    vendor_id: str

@app.post("/api/products")
def create_product(product: ProductCreate):
    db = SessionLocal()
    try:
        if not product.vendor_id:
            raise HTTPException(status_code=400, detail="vendor_id required")
        new_product = Product(
            name=product.name,
            price=float(product.price),
            original_price=float(product.original_price or product.price),
            discount=float(product.discount or 0),
            offer_text=product.offer_text or "",
            stock=int(product.stock or 100),
            image=product.image or "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=200",
            category=product.category or "Vegetables",
            vendor_id=product.vendor_id
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        print(f"✅ Product Created: {new_product.id} - {new_product.name}")
        return new_product
    except Exception as e:
        db.rollback()
        print(f"❌ Product Create Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/vendor/products")
async def create_product_with_image(
    name: str = Form(...),
    price: float = Form(...),
    original_price: float = Form(None),
    stock: int = Form(100),
    category: str = Form("Vegetables"),
    vendor_id: str = Form(...),
    discount: float = Form(0),
    offer_text: str = Form(""),
    image: UploadFile = File(None)
):
    db = SessionLocal()
    try:
        image_url = ""
        if image and image.filename:
            os.makedirs("uploads/products", exist_ok=True)
            filename = f"{uuid.uuid4().hex}_{image.filename}"
            path = f"uploads/products/{filename}"
            with open(path, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            image_url = f"/{path}"
        else:
            image_url = "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=200"

        new_product = Product(
            name=name,
            price=float(price),
            original_price=float(original_price or price),
            discount=float(discount or 0),
            offer_text=offer_text or "",
            stock=int(stock),
            image=image_url,
            category=category,
            vendor_id=vendor_id
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        print(f"✅ Product Created (with image): {new_product.id} - {new_product.name}")
        return new_product
    except Exception as e:
        db.rollback()
        print(f"❌ Product Create Error (vendor): {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/rider/register")
async def register_rider(rider_id: str = Form(...), name: str = Form(...), phone: str = Form(...), bike_number: str = Form(...), photo: UploadFile = File(None), rc: UploadFile = File(None), license: UploadFile = File(None), aadhaar: UploadFile = File(None)):
    def save_file(f, prefix):
        if not f or not f.filename: return ""
        path = f"uploads/riders/{prefix}_{rider_id}_{f.filename}"
        with open(path, "wb") as buffer: shutil.copyfileobj(f.file, buffer)
        return f"/{path}"
    db = SessionLocal(); rider = db.query(Rider).filter(Rider.id == rider_id).first()
    if not rider: rider = Rider(id=rider_id, name=name, phone=phone, vehicle=bike_number, bike_number=bike_number, earning=0, is_verified=False); db.add(rider)
    else: rider.name=name; rider.phone=phone; rider.vehicle=bike_number; rider.bike_number=bike_number
    if photo and photo.filename: rider.photo_url = save_file(photo, "photo")
    if rc and rc.filename: rider.rc_url = save_file(rc, "rc")
    if license and license.filename: rider.license_url = save_file(license, "license")
    if aadhaar and aadhaar.filename: rider.aadhaar_url = save_file(aadhaar, "aadhaar")
    db.commit(); db.refresh(rider)
    profile = {"rider_id": rider.id, "name": rider.name, "phone": rider.phone, "bike_number": rider.bike_number, "is_verified": rider.is_verified}
    db.close()
    return {"status": "success", "profile": profile}

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
