from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from jose import jwt
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, ForeignKey, JSON, text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import uuid
import razorpay
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sarax-ecommerce.netlify.app",  # Your Netlify URL
        "https://e-commerce-backend-2-4b0u.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Replace the DATABASE_URL line (around line 30-35)
DATABASE_URL = "postgresql://neondb_owner:npg_mun7TDZ0XFae@ep-dark-paper-a4qa0gc7.us-east-1.aws.neon.tech/neondb?sslmode=require"
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Razorpay credentials
RAZORPAY_KEY_ID = "rzp_test_Sec3sayV6NwGlY"
RAZORPAY_KEY_SECRET = "is4k79MqGlOr3aysm6KYTWdJ"

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    password_salt = Column(String(64), nullable=False)
    phone = Column(String(20), nullable=True)
    date_of_birth = Column(String(20), nullable=True)
    gender = Column(String(20), nullable=True)
    address = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    
    cart_items = relationship("Cart", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    upi_payments = relationship("UpiPayment", back_populates="user", cascade="all, delete-orphan")
    wishlist_items = relationship("Wishlist", back_populates="user", cascade="all, delete-orphan")


class Cart(Base):
    __tablename__ = "cart"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)
    product_price = Column(Float, nullable=False)
    product_image = Column(String(500), nullable=True)
    quantity = Column(Integer, default=1)
    size = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="cart_items")


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_name = Column(String(255), nullable=False)
    user_email = Column(String(255), nullable=False)
    total_amount = Column(Float, nullable=False)
    shipping_address = Column(JSON, nullable=False)
    payment_method = Column(String(50), nullable=False)
    payment_status = Column(String(50), default="pending")
    order_status = Column(String(50), default="processing")
    items = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)
    delivery_otp = Column(String(10), nullable=True)
    rating = Column(Integer, default=0)
    rating_comment = Column(String(500), nullable=True)
    
    user = relationship("User", back_populates="orders")


class UpiPayment(Base):
    __tablename__ = "upi_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(100), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    upi_id = Column(String(100), nullable=False)
    upi_app = Column(String(50), nullable=True)
    amount = Column(Float, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    status = Column(String(20), default="pending")
    payment_status = Column(String(20), default="initiated")
    razorpay_payment_id = Column(String(100), nullable=True)
    razorpay_order_id = Column(String(100), nullable=True)
    transaction_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(String(500), nullable=True)
    payment_metadata = Column(JSON, nullable=True)
    
    user = relationship("User", back_populates="upi_payments")


class Wishlist(Base):
    __tablename__ = "wishlist"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)
    product_price = Column(Float, nullable=False)
    product_original_price = Column(Float, nullable=False)
    product_discount = Column(Integer, nullable=False)
    product_rating = Column(Float, nullable=False)
    product_reviews = Column(Integer, nullable=False)
    product_image = Column(String(500), nullable=True)
    product_brand = Column(String(255), nullable=False)
    product_category = Column(String(255), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="wishlist_items")


# OTP Storage (in production, use Redis)
otp_storage = {}


# Function to add missing columns without dropping tables
def add_missing_columns():
    try:
        with engine.connect() as conn:
            # Check and add delivery_otp column
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='orders' AND column_name='delivery_otp'
            """))
            if not result.fetchone():
                print("📝 Adding delivery_otp column to orders table...")
                conn.execute(text("ALTER TABLE orders ADD COLUMN delivery_otp VARCHAR(10)"))
                conn.commit()
                print("✅ delivery_otp column added successfully!")
            else:
                print("✅ delivery_otp column already exists")
            
            # Check and add rating column
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='orders' AND column_name='rating'
            """))
            if not result.fetchone():
                print("📝 Adding rating column to orders table...")
                conn.execute(text("ALTER TABLE orders ADD COLUMN rating INTEGER DEFAULT 0"))
                conn.commit()
                print("✅ rating column added successfully!")
            else:
                print("✅ rating column already exists")
            
            # Check and add rating_comment column
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='orders' AND column_name='rating_comment'
            """))
            if not result.fetchone():
                print("📝 Adding rating_comment column to orders table...")
                conn.execute(text("ALTER TABLE orders ADD COLUMN rating_comment VARCHAR(500)"))
                conn.commit()
                print("✅ rating_comment column added successfully!")
            else:
                print("✅ rating_comment column already exists")
                
    except Exception as e:
        print(f"⚠️ Error adding columns: {e}")


# Create tables (only creates if they don't exist)
def init_db():
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables verified successfully!")
        
        # Add missing columns to existing tables
        add_missing_columns()
        
    except Exception as e:
        print(f"⚠️ Database initialization error: {e}")

# Run database initialization
init_db()


# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# JWT configuration
SECRET_KEY = "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Pydantic models
class SignupRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    
    @validator('full_name')
    def validate_full_name(cls, v):
        if len(v.strip()) < 3:
            raise ValueError('Full name must be at least 3 characters')
        return v.strip()
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    full_name: str


class UpiPaymentRequest(BaseModel):
    user_id: int
    upi_id: str
    upi_app: str
    amount: float
    order_details: dict


class RazorpayOrderRequest(BaseModel):
    amount: int
    currency: str = "INR"
    receipt: Optional[str] = None


class PaymentVerificationRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    user_id: int
    shipping_address: dict
    payment_method: str
    total_amount: str


class AddToWishlistRequest(BaseModel):
    user_id: int
    product_id: int
    product_name: str
    product_price: float
    product_original_price: float
    product_discount: int
    product_rating: float
    product_reviews: int
    product_image: str
    product_brand: str
    product_category: str


class UpdateLocationRequest(BaseModel):
    partner_id: int
    lat: float
    lng: float


class OTPVerifyRequest(BaseModel):
    otp: str


class RatingRequest(BaseModel):
    rating: int
    comment: Optional[str] = ""


class ReturnRequest(BaseModel):
    reason: str


# Helper functions
def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return password_hash, salt


def verify_password(plain_password: str, hashed_password: str, salt: str) -> bool:
    return hashlib.sha256((plain_password + salt).encode()).hexdigest() == hashed_password


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def generate_otp():
    return f"{random.randint(100000, 999999)}"


# ==================== AUTH ENDPOINTS ====================

@app.post("/signup")
async def signup(user: SignupRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")
    
    password_hash, salt = hash_password(user.password)
    
    new_user = User(
        full_name=user.full_name,
        email=user.email,
        password_hash=password_hash,
        password_salt=salt
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "user_id": new_user.id}


@app.post("/login")
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    print(f"Login attempt for: {login_data.email}")
    
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user:
        print(f"User not found: {login_data.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(login_data.password, user.password_hash, user.password_salt):
        print(f"Invalid password for: {login_data.email}")
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=5)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=access_token_expires
    )
    
    print(f"Login successful for: {login_data.email}")
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        full_name=user.full_name
    )


# ==================== CART ENDPOINTS ====================

@app.post("/cart/add")
async def add_to_cart(
    user_id: int,
    product_id: int,
    product_name: str,
    product_price: float,
    product_image: str = None,
    quantity: int = 1,
    size: str = None,
    color: str = None,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    existing_item = db.query(Cart).filter(
        Cart.user_id == user_id,
        Cart.product_id == product_id,
        Cart.size == size,
        Cart.color == color
    ).first()
    
    if existing_item:
        existing_item.quantity += quantity
        db.commit()
        db.refresh(existing_item)
        return {"message": "Cart updated", "cart_item": existing_item}
    else:
        cart_item = Cart(
            user_id=user_id,
            product_id=product_id,
            product_name=product_name,
            product_price=product_price,
            product_image=product_image,
            quantity=quantity,
            size=size,
            color=color
        )
        db.add(cart_item)
        db.commit()
        db.refresh(cart_item)
        return {"message": "Item added to cart", "cart_item": cart_item}


@app.get("/cart/{user_id}")
async def get_cart(user_id: int, db: Session = Depends(get_db)):
    cart_items = db.query(Cart).filter(Cart.user_id == user_id).all()
    
    total = sum(item.product_price * item.quantity for item in cart_items)
    
    return {
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_price": item.product_price,
                "product_image": item.product_image,
                "quantity": item.quantity,
                "size": item.size,
                "color": item.color
            }
            for item in cart_items
        ],
        "total": total,
        "item_count": len(cart_items)
    }


@app.put("/cart/update/{cart_item_id}")
async def update_cart_item(cart_item_id: int, quantity: int, db: Session = Depends(get_db)):
    cart_item = db.query(Cart).filter(Cart.id == cart_item_id).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    if quantity <= 0:
        db.delete(cart_item)
        message = "Item removed from cart"
    else:
        cart_item.quantity = quantity
        message = "Cart updated"
    
    db.commit()
    return {"message": message}


@app.delete("/cart/remove/{cart_item_id}")
async def remove_from_cart(cart_item_id: int, db: Session = Depends(get_db)):
    cart_item = db.query(Cart).filter(Cart.id == cart_item_id).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    db.delete(cart_item)
    db.commit()
    return {"message": "Item removed from cart"}


@app.delete("/cart/clear/{user_id}")
async def clear_cart(user_id: int, db: Session = Depends(get_db)):
    db.query(Cart).filter(Cart.user_id == user_id).delete()
    db.commit()
    return {"message": "Cart cleared"}


# ==================== ORDER ENDPOINTS ====================

@app.post("/order/create")
async def create_order(
    user_id: int,
    shipping_address: dict,
    payment_method: str,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cart_items = db.query(Cart).filter(Cart.user_id == user_id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    total_amount = sum(item.product_price * item.quantity for item in cart_items)
    
    items_data = []
    for item in cart_items:
        items_data.append({
            "product_id": item.product_id,
            "product_name": item.product_name,
            "product_price": item.product_price,
            "product_image": item.product_image,
            "quantity": item.quantity,
            "size": item.size,
            "color": item.color
        })
    
    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    
    new_order = Order(
        order_number=order_number,
        user_id=user_id,
        user_name=user.full_name,
        user_email=user.email,
        total_amount=total_amount,
        shipping_address=shipping_address,
        payment_method=payment_method,
        payment_status="completed" if payment_method == "cod" else "pending",
        order_status="processing",
        items=items_data
    )
    
    db.add(new_order)
    db.query(Cart).filter(Cart.user_id == user_id).delete()
    db.commit()
    db.refresh(new_order)
    
    return {
        "message": "Order created successfully",
        "order": {
            "id": new_order.id,
            "order_number": new_order.order_number,
            "total_amount": new_order.total_amount,
            "order_status": new_order.order_status,
            "created_at": new_order.created_at
        }
    }


@app.get("/orders/{user_id}")
async def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()
    
    return {
        "orders": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "total_amount": order.total_amount,
                "order_status": order.order_status,
                "payment_status": order.payment_status,
                "items": order.items,
                "created_at": order.created_at,
                "delivery_otp": order.delivery_otp,
                "shipping_address": order.shipping_address,
                "rating": order.rating or 0,
                "rating_comment": order.rating_comment
            }
            for order in orders
        ],
        "total_orders": len(orders)
    }


@app.get("/order/{order_id}")
async def get_order_details(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order


# ==================== DELIVERY & OTP ENDPOINTS ====================

@app.put("/order/deliver/{order_id}")
async def deliver_order(order_id: int, db: Session = Depends(get_db)):
    """Mark order as delivered after OTP verification"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.order_status != "out_for_delivery":
        raise HTTPException(status_code=400, detail="Order is not out for delivery")
    
    order.order_status = "delivered"
    order.payment_status = "completed"
    order.delivered_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    
    # Clear OTP after delivery
    order.delivery_otp = None
    if order_id in otp_storage:
        del otp_storage[order_id]
    
    db.commit()
    
    return {"message": "Order delivered successfully", "order_id": order_id}


@app.post("/order/generate-otp/{order_id}")
async def generate_delivery_otp(order_id: int, db: Session = Depends(get_db)):
    """Generate OTP for order delivery"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    otp = generate_otp()
    
    # Store OTP
    order.delivery_otp = otp
    otp_storage[order_id] = otp
    db.commit()
    
    return {"otp": otp, "expires_in": 10, "message": "OTP generated successfully"}


@app.post("/order/verify-otp/{order_id}")
async def verify_otp(order_id: int, verification: OTPVerifyRequest, db: Session = Depends(get_db)):
    """Verify OTP for delivery"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check stored OTP
    stored_otp = order.delivery_otp or otp_storage.get(order_id)
    
    if not stored_otp:
        return {"valid": False, "message": "No OTP found for this order. Please generate OTP first."}
    
    if verification.otp == stored_otp:
        return {"valid": True, "message": "OTP verified successfully"}
    else:
        return {"valid": False, "message": f"Invalid OTP"}


@app.post("/order/resend-otp/{order_id}")
async def resend_otp(order_id: int, db: Session = Depends(get_db)):
    """Resend OTP for delivery"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    otp = generate_otp()
    
    # Update OTP
    order.delivery_otp = otp
    otp_storage[order_id] = otp
    db.commit()
    
    return {"otp": otp, "message": "OTP resent successfully"}


@app.put("/order/update-status/{order_id}")
async def update_order_status(
    order_id: int, 
    status: str, 
    db: Session = Depends(get_db)
):
    """Update order status"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    valid_statuses = ["processing", "confirmed", "shipped", "out_for_delivery", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")
    
    old_status = order.order_status
    order.order_status = status
    order.updated_at = datetime.utcnow()
    
    # If moving to out_for_delivery, generate OTP
    if status == "out_for_delivery" and old_status != "out_for_delivery":
        otp = generate_otp()
        order.delivery_otp = otp
        otp_storage[order_id] = otp
    
    if status == "delivered":
        order.delivered_at = datetime.utcnow()
        order.payment_status = "completed"
        # Clear OTP after delivery
        order.delivery_otp = None
        if order_id in otp_storage:
            del otp_storage[order_id]
    
    if status == "cancelled":
        order.payment_status = "cancelled"
    
    db.commit()
    
    response_data = {"message": f"Order status updated to {status}"}
    if status == "out_for_delivery" and order.delivery_otp:
        response_data["otp"] = order.delivery_otp
    
    return response_data


@app.post("/order/out-for-delivery/{order_id}")
async def mark_out_for_delivery(order_id: int, db: Session = Depends(get_db)):
    """Mark order as out for delivery and generate OTP"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.order_status != "confirmed":
        order.order_status = "confirmed"
    
    order.order_status = "out_for_delivery"
    order.updated_at = datetime.utcnow()
    
    # Generate OTP
    otp = generate_otp()
    order.delivery_otp = otp
    otp_storage[order_id] = otp
    
    db.commit()
    
    return {"otp": otp, "message": "Order is now out for delivery", "order_id": order_id}


@app.post("/order/simulate-delivery/{order_id}")
async def simulate_delivery(order_id: int, db: Session = Depends(get_db)):
    """Simulate delivery for testing"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    otp = generate_otp()
    
    order.order_status = "out_for_delivery"
    order.delivery_otp = otp
    order.updated_at = datetime.utcnow()
    otp_storage[order_id] = otp
    
    db.commit()
    
    return {
        "message": "Delivery simulated",
        "order_id": order_id,
        "otp": otp,
        "order_status": "out_for_delivery"
    }


@app.get("/orders/delivery/{partner_id}")
async def get_delivery_orders(partner_id: int, db: Session = Depends(get_db)):
    """Get orders assigned to delivery partner"""
    orders = db.query(Order).filter(
        Order.order_status.in_(["confirmed", "out_for_delivery"])
    ).order_by(Order.created_at.desc()).all()
    
    # Enhance orders with customer details
    result = []
    for order in orders:
        user = db.query(User).filter(User.id == order.user_id).first()
        result.append({
            "id": order.id,
            "order_number": order.order_number,
            "total_amount": order.total_amount,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "items": order.items,
            "created_at": order.created_at,
            "customer_name": user.full_name if user else "Customer",
            "customer_phone": user.phone if user else "+91 98765 43210",
            "shipping_address": order.shipping_address,
            "delivery_otp": order.delivery_otp
        })
    
    return {"orders": result}


@app.post("/delivery/update-location")
async def update_delivery_location(location: UpdateLocationRequest):
    """Update delivery partner's live location"""
    print(f"📍 Partner {location.partner_id} location: {location.lat}, {location.lng}")
    return {"message": "Location updated", "status": "success"}


@app.get("/order/track/{order_id}")
async def track_order(order_id: int, db: Session = Depends(get_db)):
    """Get real-time tracking info for order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    delivery_partner = {
        "id": 1,
        "name": "Rahul Sharma",
        "phone": "+91 98765 43210",
        "rating": 4.8,
        "vehicle_number": "KA-01-AB-1234",
        "current_lat": 12.9716 + (order_id % 100) / 1000,
        "current_lng": 77.5946 + (order_id % 100) / 1000,
        "profile_pic": "https://randomuser.me/api/portraits/men/1.jpg",
        "eta_minutes": 25
    }
    
    tracking_updates = [
        {"status": "Order Confirmed", "location": "Warehouse", "timestamp": order.created_at, "description": "Your order has been confirmed"},
        {"status": "Order Packed", "location": "Warehouse", "timestamp": order.updated_at, "description": "Your items have been packed"}
    ]
    
    if order.order_status == "shipped":
        tracking_updates.append({"status": "Shipped", "location": "In Transit", "timestamp": datetime.utcnow(), "description": "Your order is on the way"})
    elif order.order_status == "out_for_delivery":
        tracking_updates.append({"status": "Out for Delivery", "location": "Nearby", "timestamp": datetime.utcnow(), "description": "Delivery partner is on the way"})
    elif order.order_status == "delivered":
        tracking_updates.append({"status": "Delivered", "location": "Your Address", "timestamp": order.delivered_at, "description": "Order delivered successfully"})
    
    return {
        "order": order,
        "delivery_partner": delivery_partner,
        "tracking_updates": tracking_updates,
        "current_location": {"lat": delivery_partner["current_lat"], "lng": delivery_partner["current_lng"]}
    }


@app.put("/order/cancel/{order_id}")
async def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """Cancel order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.order_status in ["delivered", "out_for_delivery"]:
        raise HTTPException(status_code=400, detail="Cannot cancel order that is already out for delivery or delivered")
    
    order.order_status = "cancelled"
    order.payment_status = "cancelled"
    order.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Order cancelled successfully", "order_id": order_id}


@app.post("/order/rate/{order_id}")
async def rate_order(order_id: int, rating_data: RatingRequest, db: Session = Depends(get_db)):
    """Submit rating for order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.order_status != "delivered":
        raise HTTPException(status_code=400, detail="Can only rate delivered orders")
    
    if rating_data.rating < 1 or rating_data.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    order.rating = rating_data.rating
    order.rating_comment = rating_data.comment
    db.commit()
    
    return {"message": "Rating submitted successfully"}


@app.post("/order/return/{order_id}")
async def return_order(order_id: int, return_data: ReturnRequest, db: Session = Depends(get_db)):
    """Submit return request"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.order_status != "delivered":
        raise HTTPException(status_code=400, detail="Can only return delivered orders")
    
    # In production, create a return record in database
    print(f"Return request for order {order_id}: {return_data.reason}")
    
    return {"message": "Return request submitted successfully", "order_id": order_id}


# ==================== PROFILE ENDPOINTS ====================

@app.get("/user/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": getattr(user, 'phone', None),
        "date_of_birth": getattr(user, 'date_of_birth', None),
        "gender": getattr(user, 'gender', None),
        "address": getattr(user, 'address', None),
        "created_at": user.created_at,
        "last_login": user.last_login
    }


@app.put("/user/{user_id}")
async def update_user(user_id: int, user_data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    allowed_fields = ['full_name', 'phone', 'date_of_birth', 'gender', 'address']
    
    for key, value in user_data.items():
        if key in allowed_fields and value is not None:
            setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User updated successfully",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": getattr(user, 'phone', None),
            "date_of_birth": getattr(user, 'date_of_birth', None),
            "gender": getattr(user, 'gender', None)
        }
    }


@app.post("/user/change-password")
async def change_password(
    user_id: int, 
    current_password: str, 
    new_password: str, 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not verify_password(current_password, user.password_hash, user.password_salt):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not re.search(r'[A-Z]', new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")
    
    new_hash, new_salt = hash_password(new_password)
    user.password_hash = new_hash
    user.password_salt = new_salt
    db.commit()
    
    return {"message": "Password changed successfully"}


# ==================== WISHLIST ENDPOINTS ====================

@app.post("/wishlist/add")
async def add_to_wishlist(request: AddToWishlistRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    existing = db.query(Wishlist).filter(
        Wishlist.user_id == request.user_id,
        Wishlist.product_id == request.product_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Item already in wishlist")
    
    wishlist_item = Wishlist(
        user_id=request.user_id,
        product_id=request.product_id,
        product_name=request.product_name,
        product_price=request.product_price,
        product_original_price=request.product_original_price,
        product_discount=request.product_discount,
        product_rating=request.product_rating,
        product_reviews=request.product_reviews,
        product_image=request.product_image,
        product_brand=request.product_brand,
        product_category=request.product_category
    )
    
    db.add(wishlist_item)
    db.commit()
    db.refresh(wishlist_item)
    
    return {"message": "Added to wishlist", "wishlist_item": wishlist_item}


@app.get("/wishlist/{user_id}")
async def get_wishlist(user_id: int, db: Session = Depends(get_db)):
    wishlist_items = db.query(Wishlist).filter(Wishlist.user_id == user_id).all()
    
    return {
        "items": [
            {
                "id": item.product_id,
                "name": item.product_name,
                "price": item.product_price,
                "originalPrice": item.product_original_price,
                "discount": item.product_discount,
                "rating": item.product_rating,
                "reviews": item.product_reviews,
                "image": item.product_image,
                "brand": item.product_brand,
                "category": item.product_category,
                "inStock": True,
                "wishlist_id": item.id
            }
            for item in wishlist_items
        ],
        "count": len(wishlist_items)
    }


@app.delete("/wishlist/{user_id}/{product_id}")
async def remove_from_wishlist(user_id: int, product_id: int, db: Session = Depends(get_db)):
    wishlist_item = db.query(Wishlist).filter(
        Wishlist.user_id == user_id,
        Wishlist.product_id == product_id
    ).first()
    
    if not wishlist_item:
        raise HTTPException(status_code=404, detail="Item not found in wishlist")
    
    db.delete(wishlist_item)
    db.commit()
    
    return {"message": "Removed from wishlist"}


@app.delete("/wishlist/clear/{user_id}")
async def clear_wishlist(user_id: int, db: Session = Depends(get_db)):
    db.query(Wishlist).filter(Wishlist.user_id == user_id).delete()
    db.commit()
    return {"message": "Wishlist cleared"}


# ==================== UPI PAYMENT ENDPOINTS ====================

upi_payment_requests = {}


@app.post("/upi-payment-request")
async def upi_payment_request(
    payment_request: UpiPaymentRequest,
    db: Session = Depends(get_db)
):
    request_id = f"UPI_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{payment_request.user_id}_{uuid.uuid4().hex[:6].upper()}"
    
    upi_payment = UpiPayment(
        request_id=request_id,
        user_id=payment_request.user_id,
        upi_id=payment_request.upi_id,
        upi_app=payment_request.upi_app,
        amount=payment_request.amount,
        status="pending",
        payment_status="initiated",
        payment_metadata=payment_request.order_details
    )
    
    db.add(upi_payment)
    db.commit()
    db.refresh(upi_payment)
    
    upi_payment_requests[request_id] = {
        "status": "pending",
        "user_id": payment_request.user_id,
        "upi_id": payment_request.upi_id,
        "upi_app": payment_request.upi_app,
        "amount": payment_request.amount,
        "created_at": datetime.utcnow(),
        "db_id": upi_payment.id
    }
    
    return {
        "request_id": request_id, 
        "status": "initiated",
        "payment_id": upi_payment.id
    }


@app.get("/upi-payment-status/{request_id}")
async def get_upi_payment_status(request_id: str, db: Session = Depends(get_db)):
    payment = upi_payment_requests.get(request_id)
    
    if payment:
        return {
            "status": payment["status"],
            "request_id": request_id,
            "amount": payment["amount"]
        }
    
    db_payment = db.query(UpiPayment).filter(UpiPayment.request_id == request_id).first()
    if db_payment:
        return {
            "status": db_payment.status,
            "request_id": request_id,
            "amount": db_payment.amount,
            "payment_id": db_payment.id
        }
    
    raise HTTPException(status_code=404, detail="Payment request not found")


@app.post("/upi-payment-webhook")
async def upi_payment_webhook(payment_data: dict, db: Session = Depends(get_db)):
    request_id = payment_data.get("request_id")
    status = payment_data.get("status")
    transaction_id = payment_data.get("transaction_id")
    
    if not request_id:
        raise HTTPException(status_code=400, detail="Request ID required")
    
    if request_id in upi_payment_requests:
        upi_payment_requests[request_id]["status"] = status
    
    db_payment = db.query(UpiPayment).filter(UpiPayment.request_id == request_id).first()
    if db_payment:
        db_payment.status = status
        db_payment.payment_status = "completed" if status == "success" else "failed"
        db_payment.transaction_id = transaction_id
        db_payment.completed_at = datetime.utcnow()
        db_payment.updated_at = datetime.utcnow()
        
        if status == "success":
            user = db.query(User).filter(User.id == db_payment.user_id).first()
            cart_items = db.query(Cart).filter(Cart.user_id == db_payment.user_id).all()
            
            if cart_items and user:
                items_data = []
                for item in cart_items:
                    items_data.append({
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "product_price": item.product_price,
                        "product_image": item.product_image,
                        "quantity": item.quantity,
                        "size": item.size,
                        "color": item.color
                    })
                
                order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                shipping_address = user.address if user.address else {}
                
                new_order = Order(
                    order_number=order_number,
                    user_id=user.id,
                    user_name=user.full_name,
                    user_email=user.email,
                    total_amount=db_payment.amount,
                    shipping_address=shipping_address,
                    payment_method="upi",
                    payment_status="completed",
                    order_status="confirmed",
                    items=items_data
                )
                
                db.add(new_order)
                db.flush()
                db_payment.order_id = new_order.id
                db.query(Cart).filter(Cart.user_id == user.id).delete()
                db.commit()
                
                return {
                    "message": "Webhook received and order created",
                    "order_id": new_order.id,
                    "order_number": order_number
                }
        
        db.commit()
    
    return {"message": "Webhook received"}


# ==================== RAZORPAY ENDPOINTS ====================

@app.post("/create-razorpay-order")
async def create_razorpay_order(order_request: RazorpayOrderRequest):
    try:
        amount_in_paise = order_request.amount * 100
        
        order_data = {
            'amount': amount_in_paise,
            'currency': order_request.currency,
            'receipt': order_request.receipt or f"order_{datetime.utcnow().timestamp()}",
            'payment_capture': 1
        }
        
        order = razorpay_client.order.create(data=order_data)
        
        return {
            "id": order['id'],
            "amount": order['amount'],
            "currency": order['currency'],
            "key": RAZORPAY_KEY_ID
        }
    except Exception as e:
        print(f"Error creating Razorpay order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify-payment")
async def verify_payment(verification_request: PaymentVerificationRequest, db: Session = Depends(get_db)):
    try:
        params_dict = {
            'razorpay_order_id': verification_request.razorpay_order_id,
            'razorpay_payment_id': verification_request.razorpay_payment_id,
            'razorpay_signature': verification_request.razorpay_signature
        }
        
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        user = db.query(User).filter(User.id == verification_request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        cart_items = db.query(Cart).filter(Cart.user_id == verification_request.user_id).all()
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        total_amount_float = float(verification_request.total_amount)
        
        items_data = []
        for item in cart_items:
            items_data.append({
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_price": item.product_price,
                "product_image": item.product_image,
                "quantity": item.quantity,
                "size": item.size,
                "color": item.color
            })
        
        order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        new_order = Order(
            order_number=order_number,
            user_id=verification_request.user_id,
            user_name=user.full_name,
            user_email=user.email,
            total_amount=total_amount_float,
            shipping_address=verification_request.shipping_address,
            payment_method=verification_request.payment_method,
            payment_status="completed",
            order_status="confirmed",
            items=items_data
        )
        
        db.add(new_order)
        db.query(Cart).filter(Cart.user_id == verification_request.user_id).delete()
        db.commit()
        db.refresh(new_order)
        
        return {
            "status": "success",
            "message": "Payment verified and order created",
            "order": {
                "id": new_order.id,
                "order_number": new_order.order_number,
                "total_amount": new_order.total_amount
            }
        }
        
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")
    except Exception as e:
        print(f"Payment verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ROOT & HEALTH ENDPOINTS ====================

@app.get("/")
async def root():
    return {"message": "E-Commerce API is running with PostgreSQL", "status": "active"}


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# ==================== SEARCH ENDPOINT ====================

@app.get("/search")
async def search_products(q: str, db: Session = Depends(get_db)):
    products_data = [
        {"id": 1, "name": "boAt Rockerz 450", "price": 1999, "originalPrice": 3990, "discount": 50, "rating": 4.3, "image": "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=300", "brand": "boAt", "category": "Electronics"},
        {"id": 2, "name": "iPhone 15 Pro", "price": 129900, "originalPrice": 139900, "discount": 7, "rating": 4.8, "image": "https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=300", "brand": "Apple", "category": "Mobiles"},
        {"id": 3, "name": "Samsung Galaxy S24", "price": 79999, "originalPrice": 89999, "discount": 11, "rating": 4.7, "image": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=300", "brand": "Samsung", "category": "Mobiles"},
        {"id": 4, "name": "Nike Running Shoes", "price": 3999, "originalPrice": 7999, "discount": 50, "rating": 4.5, "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=300", "brand": "Nike", "category": "Fashion"},
        {"id": 5, "name": "Men's Casual Shirt", "price": 899, "originalPrice": 2499, "discount": 64, "rating": 4.2, "image": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=300", "brand": "Roadster", "category": "Fashion"},
    ]
    
    results = [p for p in products_data if q.lower() in p["name"].lower() or q.lower() in p["brand"].lower()]
    
    return {"results": results, "query": q, "count": len(results)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)