from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uvicorn, uuid, shutil, random, time, os
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker
from urllib.parse import quote_plus

# ============= FIREBASE =============
import firebase_admin
from firebase_admin import auth as firebase_auth
if not firebase_admin._apps:
    try:
        firebase_admin.initialize_app()
        print("✅ Firebase Admin OK")
    except Exception as e:
        print(f"⚠️ Firebase Admin: {e}")
# ============= END FIREBASE =============

DB_PASSWORD = os.getenv("DB_PASSWORD", "Bazarhaat@123")
DATABASE_URL_ENV = os.getenv("DATABASE_URL")
if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        raise Exception("❌ DATABASE_URL not set on Render!")
    else:
        DATABASE_URL = f"postgresql://postgres:{quote_plus(DB_PASSWORD)}@localhost:5433/bazarhaat"

print(f"🔗 Using DB: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

def clean_phone(p: str) -> str:
    if not p: return ""
    p = p.replace("+91","").replace(" ","").replace("-","").strip()
    return p[-10:] if len(p) >= 10 else p

class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(String, primary_key=True); name = Column(String); owner = Column(String); phone = Column(String)
    address = Column(String); city = Column(String); orders = Column(Integer, default=0)
    isOnline = Column(Boolean, default=True); isActive = Column(Boolean, default=True)
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True); name = Column(String); price = Column(Float)
    original_price = Column(Float, nullable=True); discount = Column(Float, default=0); offer_text = Column(String, default="")
    stock = Column(Integer, default=100); image = Column(Text); category = Column(String, default="General"); vendor_id = Column(String)
class Rider(Base):
    __tablename__ = "riders"
    id = Column(String, primary_key=True); name = Column(String, default=""); phone = Column(String, unique=True, index=True)
    is_verified = Column(Boolean, default=False); user_type = Column(String, default="RIDER"); vehicle = Column(String, default="")
    bike_number = Column(String, default=""); bank_account = Column(String, default=""); ifsc = Column(String, default="")
    upi = Column(String, default=""); rating = Column(Float, default=4.8); total_deliveries = Column(Integer, default=0)
    earning = Column(Float, default=0.0); photo_url = Column(String, default=""); rc_url = Column(String, default="")
    license_url = Column(String, default=""); aadhaar_url = Column(String, default="")
class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True); otp = Column(String); store_qr = Column(String); amount = Column(Float)
    customer = Column(String); customer_phone = Column(String); phone = Column(String); address = Column(String)
    status = Column(String, default="New"); earning = Column(Float, default=45); vendor_id = Column(String)
    rider_id = Column(String, nullable=True); created_at = Column(DateTime, default=datetime.now)
class Payout(Base):
    __tablename__ = "payouts"
    id = Column(String, primary_key=True); rider_id = Column(String); amount = Column(Float); method = Column(String)
    upi_id = Column(String, nullable=True); bank_account = Column(String, nullable=True); ifsc = Column(String, nullable=True)
    status = Column(String, default="Processing"); created_at = Column(DateTime, default=datetime.now)
# ============= LIVE LOCATION TABLE - YAHAN ADD KARO =============
class RiderLocation(Base):
    __tablename__ = "rider_locations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, index=True)
    rider_id = Column(String, index=True)
    lat = Column(Float)
    lng = Column(Float)
    updated_at = Column(DateTime, default=datetime.now)
# ============= END LOCATION TABLE =============


class Customer(Base):
    __tablename__ = "customers"
    id = Column(String, primary_key=True)
    name = Column(String, default="BazarHaat Customer")
    phone = Column(String, unique=True, index=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    town = Column(String, nullable=True, default="Hatidhura")
    pincode = Column(String, nullable=True, default="783332")
    created_at = Column(DateTime, default=datetime.now)

otp_store = {}; rider_otp_store = {}

try:
    Base.metadata.create_all(bind=engine)
    print("✅ DB Connected")
except Exception as e: print(f"❌ DB Error: {e}")

try:
    with engine.connect() as conn:
        # 1. ALTER wale
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
            "ALTER TABLE customers ADD COLUMN town VARCHAR DEFAULT 'Hatidhura'",
            "ALTER TABLE customers ADD COLUMN pincode VARCHAR DEFAULT '783332'",
        ]
        for s in stmts:
            pg = s.replace("ADD COLUMN", "ADD COLUMN IF NOT EXISTS") if "sqlite" not in DATABASE_URL else s
            try: 
                conn.execute(text(pg))
            except Exception as ex:
                print(f"Migration skip: {pg} -> {ex}")
        
        # 2. CREATE TABLE alag se - 100% safe
        try:
            if "sqlite" not in DATABASE_URL:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS rider_locations (
                        id SERIAL PRIMARY KEY, 
                        order_id VARCHAR, 
                        rider_id VARCHAR, 
                        lat FLOAT, 
                        lng FLOAT, 
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS rider_locations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        order_id VARCHAR, 
                        rider_id VARCHAR, 
                        lat FLOAT, 
                        lng FLOAT, 
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            print("✅ rider_locations table OK")
        except Exception as ex:
            print(f"rider_locations create skip: {ex}")

        conn.commit()
        print("✅ Migration OK")
except Exception as e: 
    print(f"Migration Note: {e}")

app = FastAPI(title="BazarHaat Backend v4 Final", version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
os.makedirs("uploads/riders", exist_ok=True)
os.makedirs("uploads/products", exist_ok=True)

def init_data():
    db = SessionLocal()
    try:
        if db.query(Vendor).count() == 0:
            db.add_all([Vendor(id="VENDOR-01", name="Goreswar Kirana", owner="Bikash", phone="9876543211", address="Goreswar Market", city="Goreswar", orders=42, isOnline=True, isActive=True),Vendor(id="VENDOR-02", name="Maa Store Pathsala", owner="Ramesh", phone="9876543212", address="Pathsala Market", city="Pathsala", orders=18, isOnline=True, isActive=True),]); db.commit()
        if db.query(Product).count() == 0:
            db.add_all([Product(name="Fresh Tomato 1kg", price=40, original_price=50, discount=20, offer_text="20% OFF", stock=100, image="https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=200", vendor_id="VENDOR-01", category="Vegetables"),Product(name="Amul Milk 1L", price=65, original_price=70, discount=7, offer_text="7% OFF", stock=50, image="https://images.unsplash.com/photo-1550583724-b2692b85b150?w=200", vendor_id="VENDOR-01", category="Dairy"),]); db.commit()
        if db.query(Rider).count() == 0:
            db.add(Rider(id="BH-RIDER-01", name="Rahul Rider", phone="9876543210", vehicle="Bike - AS-12-AB-1234", bike_number="AS-12-AB-1234", bank_account="HDFC ****1234", ifsc="HDFC0001234", upi="rahul@upi", rating=4.8, total_deliveries=22, earning=320.0, is_verified=True)); db.commit()
        if db.query(Order).count() == 0:
            db.add_all([Order(id="BH-102", otp="1234", store_qr="STORE-BH-102", amount=250, customer="Rahul Das", customer_phone="9876543210", phone="9876543210", address="Near College, Goreswar, 2.3km", status="New", earning=45, vendor_id="VENDOR-01"),Order(id="BH-103", otp="5678", store_qr="STORE-BH-103", amount=450, customer="Ankit Sharma", customer_phone="9876543211", phone="9876543211", address="Main Market, Baihata", status="New", earning=60, vendor_id="VENDOR-01"),]); db.commit()
    except Exception as e: print(f"Seed error: {e}"); db.rollback()
    finally: db.close()
init_data()

class RiderOtpRequest(BaseModel): phone: str
class RiderOtpVerify(BaseModel): phone: str; otp: str
class FirebaseVerifyRequest(BaseModel): idToken: str; phone: str
class CustomerLoginRequest(BaseModel): phone: str
class CustomerVerifyRequest(BaseModel): phone: str; otp: str; name: Optional[str] = None
class CustomerRegisterRequest(BaseModel): phone: str; name: str; town: Optional[str] = "Hatidhura"; address: Optional[str] = ""; pincode: Optional[str] = "783332"
class PlaceOrderRequest(BaseModel): phone: str; cart: List[dict]; total: float; address: Optional[str] = ""; payment_id: Optional[str] = "COD"
class ApproveRiderRequest(BaseModel): rider_id: Optional[str] = None; id: Optional[str] = None; is_verified: Optional[bool] = True

@app.get("/")
def home(): return {"message": "BazarHaat Backend v4 Final - All Fixed", "status": "OK", "docs": "/docs"}

# --- RIDER APIS ---
@app.post("/api/rider/auth/firebase-verify")
def firebase_verify_rider(req: FirebaseVerifyRequest):
    db = SessionLocal()
    try:
        phone = clean_phone(req.phone)
        try:
            decoded = firebase_auth.verify_id_token(req.idToken)
            phone = clean_phone(decoded.get("phone_number",""))
        except: pass
        if len(phone)!=10: raise HTTPException(status_code=400, detail=f"Invalid phone: {phone}")
        rider = db.query(Rider).filter(Rider.phone == phone).first()
        if not rider:
            new_id = f"RIDER-{phone[-4:]}-{uuid.uuid4().hex[:3].upper()}"
            rider = Rider(id=new_id, phone=phone, is_verified=False, earning=0, name="")
            db.add(rider); db.commit(); db.refresh(rider)
            return {"success": True, "rider_id": rider.id, "isNewUser": True, "profileExists": False}
        return {"success": True, "rider_id": rider.id, "isNewUser": False, "profileExists": bool(rider.name and rider.bike_number), "is_verified": rider.is_verified}
    finally: db.close()

@app.post("/api/rider/auth/send-otp")
def rider_send_otp(req: RiderOtpRequest):
    phone = clean_phone(req.phone)
    otp = str(random.randint(100000, 999999))
    rider_otp_store[phone] = {"otp": otp, "time": time.time()}
    print(f"🔐 RIDER OTP {phone} = {otp}")
    return {"success": True, "message": "OTP sent", "otp": otp, "demo_otp": "123456", "phone": phone}

@app.post("/api/rider/auth/verify-otp")
def rider_verify_otp(req: RiderOtpVerify):
    phone = clean_phone(req.phone)
    if req.otp == "123456":
        db = SessionLocal()
        try:
            rider = db.query(Rider).filter(Rider.phone == phone).first()
            if not rider:
                new_id = f"RIDER-{phone[-4:]}-{uuid.uuid4().hex[:3].upper()}"
                rider = Rider(id=new_id, phone=phone, is_verified=False, earning=0)
                db.add(rider); db.commit(); db.refresh(rider)
                return {"success": True, "rider_id": rider.id, "isNewUser": True, "profileExists": False}
            return {"success": True, "rider_id": rider.id, "isNewUser": False, "profileExists": bool(rider.name and rider.bike_number), "is_verified": rider.is_verified}
        finally: db.close()
    saved = rider_otp_store.get(phone)
    if not saved: raise HTTPException(status_code=400, detail="OTP not sent")
    if time.time() - saved["time"] > 300: raise HTTPException(status_code=400, detail="Expired")
    if saved["otp"]!= req.otp: raise HTTPException(status_code=400, detail="Invalid OTP")
    del rider_otp_store[phone]
    db = SessionLocal()
    try:
        rider = db.query(Rider).filter(Rider.phone == phone).first()
        if not rider:
            new_id = f"RIDER-{phone[-4:]}-{uuid.uuid4().hex[:3].upper()}"
            rider = Rider(id=new_id, phone=phone, is_verified=False, earning=0)
            db.add(rider); db.commit(); db.refresh(rider)
        return {"success": True, "rider_id": rider.id}
    finally: db.close()

@app.get("/api/rider/profile/{rider_id}")
def get_rider_profile(rider_id: str):
    db = SessionLocal()
    try:
        clean = clean_phone(rider_id)
        rider = db.query(Rider).filter(Rider.id == rider_id).first()
        if not rider: rider = db.query(Rider).filter(Rider.phone == clean).first()
        if not rider: rider = db.query(Rider).filter(Rider.phone == rider_id).first()
        if not rider: return {"not_found": True, "is_verified": False}
        
        # Full earning data
        return {
            "rider_id": rider.id, 
            "phone": rider.phone, 
            "name": rider.name, 
            "bike_number": rider.bike_number, 
            "is_verified": rider.is_verified, 
            "earning": float(rider.earning or 0),  # <--- YE IMPORTANT
            "total_deliveries": int(rider.total_deliveries or 0),
            "rating": float(rider.rating or 4.8),
            "vehicle": rider.vehicle or "",
            "upi": rider.upi or "",
            "bank_account": rider.bank_account or "",
            "ifsc": rider.ifsc or ""
        }
    finally: db.close()
# --- CUSTOMER APIS - FINAL COMBINED ---
@app.post("/api/customer/register")
def register_customer(req: CustomerRegisterRequest):
    phone = clean_phone(req.phone)
    if len(phone)!=10: raise HTTPException(status_code=400, detail="Invalid phone - 10 digit required")
    db = SessionLocal()
    try:
        existing = db.query(Customer).filter(Customer.phone == phone).first()
        if existing:
            existing.name=req.name; existing.town=req.town; existing.address=req.address; existing.pincode=req.pincode or "783332"
            db.commit(); db.refresh(existing)
            return {"success": True, "message": "Already registered", "customer": {"id": existing.id, "phone": existing.phone, "name": existing.name, "town": existing.town, "pincode": existing.pincode}}
        new_customer = Customer(id=f"CUST-{uuid.uuid4().hex[:6].upper()}", phone=phone, name=req.name, town=req.town or "Hatidhura", address=req.address or "", pincode=req.pincode or "783332")
        db.add(new_customer); db.commit(); db.refresh(new_customer)
        print(f"✅ NEW CUSTOMER REGISTERED: {phone} - {req.name}")
        return {"success": True, "customer": {"id": new_customer.id, "phone": new_customer.phone, "name": new_customer.name, "town": new_customer.town, "pincode": new_customer.pincode, "address": new_customer.address}}
    finally: db.close()

@app.post("/api/customer/send-otp")
def send_customer_otp(req: CustomerLoginRequest):
    phone = clean_phone(req.phone)
    if len(phone)!=10: raise HTTPException(status_code=400, detail="Invalid phone")
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer:
            print(f"❌ OTP DENIED - Phone {phone} not registered")
            raise HTTPException(status_code=404, detail="Number not registered - Pehle Create Account karo")
        otp = str(random.randint(1000, 9999))
        otp_store[phone] = {"otp": otp, "time": time.time()}
        print(f"🔐 CUSTOMER OTP {phone} = {otp} (10 min valid) - {customer.name}")
        return {"success": True, "message": "OTP sent - 10 min valid", "otp": otp, "phone": phone, "name": customer.name}
    finally: db.close()

@app.post("/api/customer/verify-otp")
def verify_customer_otp(req: CustomerVerifyRequest):
    phone = clean_phone(req.phone)
    db = SessionLocal()
    try:
        saved = otp_store.get(phone)
        if saved is None: raise HTTPException(status_code=400, detail="OTP not sent - Send OTP first")
        if isinstance(saved, dict):
            if time.time() - saved["time"] > 600:
                otp_store.pop(phone, None)
                raise HTTPException(status_code=400, detail="OTP expired - 10 min over, Resend karo")
            stored_otp = saved["otp"]
        else: stored_otp = saved
        if str(req.otp)!=str(stored_otp): raise HTTPException(status_code=400, detail="Wrong OTP")
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer: raise HTTPException(status_code=404, detail="Number not registered")
        otp_store.pop(phone, None)
        return {"success": True, "customer": {"id": customer.id, "phone": customer.phone, "name": customer.name, "town": customer.town or "Hatidhura", "pincode": customer.pincode or "783332", "address": customer.address or ""}, "token": f"token_{customer.id}_{int(time.time())}"}
    finally: db.close()

@app.post("/api/customer/place-order")
def customer_place_order(req: PlaceOrderRequest):
    phone = clean_phone(req.phone)
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer: raise HTTPException(status_code=404, detail="Customer not found")
        order_id = f"BH-{random.randint(100,999)}-{uuid.uuid4().hex[:3].upper()}"
        otp = str(random.randint(1000,9999))
        total = req.total or sum([float(i.get('price',0)) for i in req.cart])
        new_order = Order(id=order_id, otp=otp, store_qr=f"STORE-{order_id}", amount=total, customer=customer.name, customer_phone=phone, phone=phone, address=req.address or customer.address or customer.town, status="New", earning=45, vendor_id="VENDOR-01")
        db.add(new_order); db.commit()
        print(f"🛒 NEW ORDER {order_id} - {customer.name} - ₹{total} - OTP {otp} - VENDOR WILL VIBRATE NOW")
        return {"success": True, "id": order_id, "order_id": order_id, "otp": otp, "total": total, "message": "Order Placed - Vendor notified"}
    finally: db.close()
class OrderItemRequest(BaseModel):
    vendor_id: Optional[str] = "VENDOR-01"
    customerName: Optional[str] = "User"
    customerPhone: Optional[str] = ""
    total: Optional[float] = 0
    items: Optional[List[dict]] = []
    address: Optional[str] = ""
    status: Optional[str] = "New"
    otp: Optional[str] = None
    phone: Optional[str] = ""

@app.post("/api/orders")
def place_order_generic(req: OrderItemRequest):
    db = SessionLocal()
    try:
        phone = clean_phone(req.customerPhone or req.phone or "9876543210")
        order_id = f"BH-{random.randint(100,999)}-{uuid.uuid4().hex[:3].upper()}"
        otp = str(req.otp) if req.otp else str(random.randint(1000,9999))
        total = req.total or 0
        if total == 0 and req.items:
            total = sum([float(i.get('price',0)) * int(i.get('qty',1) if 'qty' in i else 1) for i in req.items])
        vendor_id = req.vendor_id or "VENDOR-01"
        new_order = Order(id=order_id, otp=otp, store_qr=f"STORE-{order_id}", amount=total, customer=req.customerName, customer_phone=phone, phone=phone, address=req.address, status="New", earning=45, vendor_id=vendor_id)
        db.add(new_order); db.commit()
        print(f"🛒 NEW ORDER via /api/orders {order_id} - {req.customerName} - ₹{total} - Vendor: {vendor_id} - OTP {otp}")
        return {"success": True, "id": order_id, "order_id": order_id, "otp": otp, "total": total}
    except Exception as e:
        db.rollback()
        print(f"❌ /api/orders Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally: db.close()
@app.get("/api/customer/orders/{phone}")
def get_customer_orders(phone: str):
    clean = clean_phone(phone)
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(Order.customer_phone == clean).order_by(Order.created_at.desc()).all()
        return [{"id": o.id, "otp": o.otp, "total": o.amount, "status": o.status, "date": o.created_at.isoformat() if o.created_at else "", "count": 1} for o in orders]
    finally: db.close()
@app.post("/api/rider/location")
def update_rider_location(data: dict):
    db = SessionLocal()
    try:
        order_id = str(data.get("orderId") or data.get("order_id") or "")
        rider_id = str(data.get("rider_id") or "")
        lat = float(data.get("lat") or 0)
        lng = float(data.get("lng") or 0)
        if not order_id:
            raise HTTPException(status_code=400, detail="orderId required")
        db.query(RiderLocation).filter(RiderLocation.order_id == order_id).delete()
        new_loc = RiderLocation(order_id=order_id, rider_id=rider_id, lat=lat, lng=lng)
        db.add(new_loc)
        db.commit()
        print(f"📍 LIVE {order_id} - {rider_id} => {lat},{lng}")
        return {"success": True, "orderId": order_id, "lat": lat, "lng": lng}
    finally:
        db.close()

@app.get("/api/rider/location/{order_id}")
def get_rider_location(order_id: str):
    db = SessionLocal()
    try:
        loc = db.query(RiderLocation).filter(RiderLocation.order_id == order_id).order_by(RiderLocation.updated_at.desc()).first()
        if not loc:
            return {"found": False, "order_id": order_id}
        return {"found": True, "order_id": loc.order_id, "rider_id": loc.rider_id, "lat": loc.lat, "lng": loc.lng, "updated_at": loc.updated_at.isoformat() if loc.updated_at else ""}
    finally:
        db.close()
# ============= END LIVE API =============
# --- VENDOR & OTHER APIS ---
@app.get("/api/vendors")
def get_vendors(): db=SessionLocal(); v=db.query(Vendor).all(); db.close(); return v
@app.get("/api/products")
def get_products(category: Optional[str]=None):
    db=SessionLocal()
    try:
        if category and category!="All": return db.query(Product).filter(Product.stock>0, Product.category.ilike(f"%{category}%")).all()
        return db.query(Product).filter(Product.stock>0).all()
    finally: db.close()
@app.get("/api/vendor/products/{vendor_id}")
def get_vendor_products(vendor_id: str): db=SessionLocal(); p=db.query(Product).filter(Product.vendor_id==vendor_id).all(); db.close(); return p
@app.get("/api/vendor/orders/{vendor_id}")
def get_vendor_orders(vendor_id: str):
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(Order.vendor_id == vendor_id).order_by(Order.created_at.desc()).all()
        result = []
        for o in orders:
            result.append({
                "id": o.id,
                "orderId": o.id,
                "customer": o.customer,
                "customerName": o.customer,
                "amount": o.amount,
                "total": o.amount,
                "otp": o.otp,
                "store_qr": o.store_qr,
                "status": o.status,
                "address": o.address,
                "customer_phone": o.customer_phone,
                "phone": o.phone
            })
        return result
    finally:
        db.close()

@app.get("/api/vendor/stats/{vendor_id}")
def vendor_stats(vendor_id: str):
    db = SessionLocal()
    try:
        pc = db.query(Product).filter(Product.vendor_id == vendor_id).count()
        orders = db.query(Order).filter(Order.vendor_id == vendor_id).all()
        today = datetime.now().date()
        today_orders = [o for o in orders if o.created_at and o.created_at.date() == today]
        return {
            "product_count": pc,
            "total_orders": len(orders),
            "new_orders": len([o for o in orders if o.status == "New"]),
            "pending_orders": len([o for o in orders if o.status == "New"]),
            "today_income": sum([o.amount for o in today_orders]),
            "today_orders": len(today_orders),
            "total_income": sum([o.amount for o in orders]),
            "earnings": sum([o.amount for o in orders if o.status == "Delivered"]),
            "vendor_id": vendor_id,
            "rating": 4.8
        }
    finally:
        db.close()
@app.post("/api/vendor/orders/{order_id}/accept")
def vendor_accept_order(order_id: str):
    db = SessionLocal()
    try:
        o = db.query(Order).filter(Order.id == order_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="Order not found")
        o.status = "Accepted_by_Vendor"
        db.commit()
        print(f"✅ Vendor Accepted {order_id}")
        return {"success": True, "order_id": order_id, "status": "Accepted_by_Vendor"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/vendor/orders/{order_id}/reject")
def vendor_reject_order(order_id: str):
    db = SessionLocal()
    try:
        o = db.query(Order).filter(Order.id == order_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="Order not found")
        o.status = "Rejected_by_Vendor"
        db.commit()
        return {"success": True}
    finally:
        db.close()

@app.get("/api/rider/orders")
def get_rider_available_orders():
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(Order.status.in_(
            ["New","Accepted_by_Vendor","Assigned","Picked Up","Accepted_by_Rider"]
        )).order_by(Order.created_at.desc()).all()
        return [
            {
                "id": o.id, 
                "customer": o.customer, 
                "amount": o.amount, 
                "otp": o.otp, 
                "store_qr": o.store_qr, 
                "status": o.status, 
                "address": o.address,
                "customer_phone": o.customer_phone,
                "vendor_id": o.vendor_id,
                "rider_id": o.rider_id
            } 
            for o in orders
        ]
    finally:
        db.close()
@app.post("/api/rider/orders/{order_id}/accept")
def rider_accept_order(order_id: str, data: dict):
    db = SessionLocal()
    try:
        o = db.query(Order).filter(Order.id == order_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="Order not found")
        o.status = "Accepted_by_Rider"
        o.rider_id = data.get("rider_id", "RIDER-01")
        db.commit()
        return {"success": True}
    finally:
        db.close()
@app.post("/api/rider/orders/{order_id}/deliver")
def rider_deliver_order(order_id: str, data: dict):
    db=SessionLocal()
    try:
        o=db.query(Order).filter(Order.id==order_id).first()
        if not o: raise HTTPException(status_code=404, detail="Order not found")
        if str(o.otp)!=str(data.get("otp")): raise HTTPException(status_code=400, detail="Wrong OTP")
        o.status="Delivered"
        if o.rider_id:
            r=db.query(Rider).filter(Rider.id==o.rider_id).first()
            if r: 
                r.earning = (r.earning or 0) + (o.earning or 45)
                r.total_deliveries = (r.total_deliveries or 0) + 1
        db.commit(); 
        print(f"✅ Delivered {order_id} - Rider earning +{o.earning}")
        return {"success":True}
    finally: db.close()
@app.get("/api/riders")
def get_all_riders_alias(): db=SessionLocal(); r=db.query(Rider).all(); db.close(); return r
@app.get("/api/rider/all")
def get_rider_all(): db=SessionLocal(); r=db.query(Rider).all(); db.close(); return r
@app.get("/api/admin/riders")
def admin_get_all_riders(): db=SessionLocal(); r=db.query(Rider).all(); db.close(); return r
@app.post("/api/admin/riders/{rider_id}/verify")
def admin_verify_rider_by_id(rider_id: str):
    db=SessionLocal()
    try:
        r=db.query(Rider).filter(Rider.id==rider_id).first()
        if not r: raise HTTPException(status_code=404, detail="Rider not found")
        r.is_verified=True; db.commit(); return {"success":True, "rider_id":rider_id, "is_verified":True}
    finally: db.close()
@app.post("/api/rider/verify/{rider_id}")
def rider_verify_path(rider_id: str):
    db=SessionLocal()
    try:
        r=db.query(Rider).filter(Rider.id==rider_id).first()
        if not r: r=db.query(Rider).filter(Rider.phone==rider_id).first()
        if not r: raise HTTPException(status_code=404, detail="Rider not found")
        r.is_verified=True; db.commit(); return {"success":True, "rider_id":r.id, "is_verified":True}
    finally: db.close()
@app.post("/api/riders/{rider_id}/verify")
def riders_verify_alias(rider_id: str): return rider_verify_path(rider_id)
@app.post("/api/admin/approve-rider")
def admin_approve_rider(req: ApproveRiderRequest):
    fid=req.rider_id or req.id
    if not fid: raise HTTPException(status_code=400, detail="rider_id required")
    db=SessionLocal()
    try:
        r=db.query(Rider).filter(Rider.id==fid).first()
        if not r: r=db.query(Rider).filter(Rider.phone==fid).first()
        if not r: raise HTTPException(status_code=404, detail="Rider not found")
        r.is_verified=True; db.commit(); return {"success":True, "rider_id":fid, "is_verified":True}
    finally: db.close()
@app.post("/api/rider/approve")
def rider_approve_body(req: ApproveRiderRequest): return admin_approve_rider(req)
@app.post("/api/rider/reject/{rider_id}")
def rider_reject(rider_id: str):
    db=SessionLocal()
    try:
        r=db.query(Rider).filter(Rider.id==rider_id).first()
        if not r: raise HTTPException(status_code=404, detail="Rider not found")
        r.is_verified=False; db.commit(); return {"success":True, "rejected":True}
    finally: db.close()
@app.get("/api/settings")
def get_settings_api(): return {"isUserAppLive": True, "isVendorAppLive": True, "isRiderAppLive": True}
@app.post("/api/settings")
def update_settings_api(data: dict): return {"success":True}
@app.get("/api/rider/payouts/{rider_id}")
def get_payouts(rider_id: str): db=SessionLocal(); p=db.query(Payout).filter(Payout.rider_id==rider_id).all(); db.close(); return p
@app.post("/api/rider/payout/request")
def request_payout(data: dict):
    db=SessionLocal()
    try:
        new_id=f"PAYOUT-{uuid.uuid4().hex[:6].upper()}"
        payout=Payout(id=new_id, rider_id=data.get("rider_id"), amount=data.get("amount"), method=data.get("method"), upi_id=data.get("upi_id"), bank_account=data.get("bank_account"), ifsc=data.get("ifsc"), status="Processing")
        db.add(payout); db.commit(); return {"success":True, "payout_id":new_id}
    finally: db.close()
@app.post("/api/rider/register")
async def register_rider(rider_id: str = Form(...), name: str = Form(...), phone: str = Form(...), bike_number: str = Form(...), photo: UploadFile = File(None), rc: UploadFile = File(None), license: UploadFile = File(None), aadhaar: UploadFile = File(None)):
    def save_file(f, prefix):
        if not f or not f.filename: return ""
        path=f"uploads/riders/{prefix}_{rider_id}_{f.filename}"
        with open(path, "wb") as buffer: shutil.copyfileobj(f.file, buffer)
        return f"/{path}"
    db=SessionLocal()
    try:
        clean=clean_phone(phone)
        rider=db.query(Rider).filter(Rider.id==rider_id).first()
        if not rider: rider=Rider(id=rider_id, name=name, phone=clean, vehicle=bike_number, bike_number=bike_number, earning=0, is_verified=False); db.add(rider)
        else: rider.name=name; rider.phone=clean; rider.vehicle=bike_number; rider.bike_number=bike_number
        if photo and photo.filename: rider.photo_url=save_file(photo,"photo")
        if rc and rc.filename: rider.rc_url=save_file(rc,"rc")
        if license and license.filename: rider.license_url=save_file(license,"license")
        if aadhaar and aadhaar.filename: rider.aadhaar_url=save_file(aadhaar,"aadhaar")
        db.commit(); db.refresh(rider)
        return {"status":"success", "profile":{"rider_id":rider.id, "name":rider.name, "phone":rider.phone, "bike_number":rider.bike_number, "is_verified":rider.is_verified}}
    finally: db.close()
# ============= VENDOR ADD PRODUCT =============
@app.post("/api/vendor/products")
async def vendor_add_product(
    vendor_id: str = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    original_price: float = Form(0),
    discount: float = Form(0),
    stock: int = Form(100),
    category: str = Form("General"),
    offer_text: str = Form(""),
    image: UploadFile = File(None)
):
    db = SessionLocal()
    try:
        image_url = ""
        if image and image.filename:
            filename = f"{uuid.uuid4().hex[:8]}_{image.filename}"
            path = f"uploads/products/{filename}"
            os.makedirs("uploads/products", exist_ok=True)
            with open(path, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            image_url = f"/{path}"
            print(f"📸 Product image saved: {path}")
        else:
            image_url = f"https://images.unsplash.com/photo-1542838132-92c53300491e?w=200"

        new_product = Product(
            name=name,
            price=price,
            original_price=original_price,
            discount=discount,
            offer_text=offer_text or f"{int(discount)}% OFF" if discount else "",
            stock=stock,
            image=image_url,
            category=category,
            vendor_id=vendor_id
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        print(f"✅ PRODUCT ADDED: {name} - ₹{price} - {category} - {vendor_id}")
        return {"success": True, "product_id": new_product.id, "message": "Product Added", "product": {"id": new_product.id, "name": new_product.name}}
    except Exception as e:
        db.rollback()
        print(f"❌ Add product error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
@app.post("/api/rider/notify/{order_id}")
def rider_notify(order_id: str, data: dict = {}):
    print(f"🔔 Rider Notify for {order_id} - {data}")
    return {"success": True, "order_id": order_id, "message": "Riders notified"}

@app.post("/api/rider/verify-pickup")
def verify_pickup(data: dict):
    db = SessionLocal()
    try:
        order_id = str(data.get("order_id") or data.get("orderId") or "").strip()
        store_qr = str(data.get("store_qr") or data.get("storeQr") or "").strip()
        rider_id = str(data.get("rider_id") or "")
        
        print(f"🔍 VERIFY REQ: order={order_id} qr={store_qr} rider={rider_id}")

        if not order_id or not store_qr:
            raise HTTPException(status_code=400, detail="order_id and store_qr required")

        expected_qr = f"STORE-{order_id}"
        
        if store_qr != expected_qr and store_qr.replace("STORE-","") != order_id:
            if f"STORE-{store_qr}" != expected_qr and store_qr != order_id:
                 raise HTTPException(status_code=400, detail=f"QR Mismatch! Expected {expected_qr}, got {store_qr}")

        o = db.query(Order).filter(Order.id == order_id).first()
        if not o:
            raise HTTPException(status_code=404, detail="Order not found")
        
        o.status = "Picked_by_Rider"
        if rider_id:
            o.rider_id = rider_id
        
        db.commit()
        print(f"✅ PICKUP VERIFIED {order_id} by {rider_id}")
        return {"success": True, "order_id": order_id, "status": "Picked_by_Rider"}

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"❌ Verify error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
if __name__=="__main__": uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
