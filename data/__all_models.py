from sqlalchemy import Column, Integer, String, Text, ForeignKey, DECIMAL, TIMESTAMP, Boolean
from sqlalchemy.orm import relationship, declarative_base
import pytz
from datetime import datetime

Base = declarative_base()


def moscow_time():
    return datetime.now(pytz.timezone('Europe/Moscow'))


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=moscow_time)
    orders = relationship("Order", back_populates="user", lazy='dynamic')
    cart = relationship("Cart", uselist=False, back_populates="user")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(DECIMAL(10, 2), nullable=False)
    stock_quantity = Column(Integer, default=0)
    image_url = Column(String(255))
    category_id = Column(Integer, ForeignKey('categories.id'))
    category = relationship("Category", back_populates="products")
    cart_items = relationship("CartItem", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    products = relationship("Product", back_populates="category")


class Cart(Base):
    __tablename__ = "carts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship("User", back_populates="cart")
    items = relationship("CartItem", back_populates="cart")


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True)
    quantity = Column(Integer, nullable=False)
    cart_id = Column(Integer, ForeignKey('carts.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    cart = relationship("Cart", back_populates="items")
    product = relationship("Product", lazy='joined')


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(TIMESTAMP, default=moscow_time)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")
    delivery_address = relationship("DeliveryAddress", uselist=False, back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    quantity = Column(Integer, nullable=False)
    price_at_purchase = Column(DECIMAL(10, 2), nullable=False)
    order_id = Column(Integer, ForeignKey('orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class DeliveryAddress(Base):
    __tablename__ = "delivery_addresses"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True)
    country = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    street = Column(String(200), nullable=False)
    house = Column(String(20), nullable=False)
    apartment = Column(String(20))
    additional_info = Column(Text)
    phone = Column(String(20), nullable=False)
    order = relationship("Order", back_populates="delivery_address")
