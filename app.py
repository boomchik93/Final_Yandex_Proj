from flask import Flask, render_template, request, redirect, url_for, session, flash
from data.db_session import get_db
from data.__all_models import User, Product, Category, Cart, CartItem, Order, OrderItem
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
import os
import pytz
from datetime import datetime

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'img', 'products')


@app.context_processor
def inject_cart_items_count():
    if 'user_id' in session:
        try:
            db = next(get_db())
            cart = db.query(Cart).filter_by(user_id=session['user_id']).first()
            if cart:
                count = sum(item.quantity for item in cart.items)
                return {'cart_items_count': count}
        except:
            pass
    return {'cart_items_count': 0}


@app.context_processor
def inject_timezone():
    return {'tz': MOSCOW_TZ}


@app.context_processor
def inject_user():
    if 'user_id' in session:
        db = next(get_db())
        user = db.query(User).get(session['user_id'])
        return {'current_user': user}
    return {'current_user': None}


@app.route('/')
def home():
    db = next(get_db())
    categories = db.query(Category).options(joinedload(Category.products)).all()
    return render_template('main.html', categories=categories)


@app.route('/update_cart/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        new_quantity = int(request.form['quantity'])
        item = db.query(CartItem).get(item_id)

        if not item or item.cart.user_id != session['user_id']:
            flash('Элемент не найден', 'danger')
            return redirect(url_for('view_cart'))

        if new_quantity < 0:
            flash('Некорректное количество', 'danger')
            return redirect(url_for('view_cart'))

        if new_quantity > 0:
            item.quantity = new_quantity
        else:
            db.delete(item)

        db.commit()
        flash('Корзина обновлена', 'success')

    except ValueError:
        flash('Введите число', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(url_for('view_cart'))


@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        cart = db.query(Cart).filter_by(user_id=session['user_id']).first()
        if not cart or not cart.items:
            return redirect(url_for('view_cart'))
        error_messages = []
        for item in cart.items:
            product = db.query(Product).get(item.product_id)
            if not product:
                error_messages.append(f"Товар {item.product.name} был удален")
                continue

            if product.stock_quantity < item.quantity:
                error_messages.append(
                    f"Недостаточно товара {product.name}. Доступно: {product.stock_quantity}"
                )

        if error_messages:
            for msg in error_messages:
                flash(msg, 'danger')
            return redirect(url_for('view_cart'))

        for item in cart.items:
            product = db.query(Product).get(item.product_id)
            product.stock_quantity -= item.quantity
            if product.stock_quantity < 0:
                raise ValueError("Отрицательный остаток после списания")

        new_order = Order(
            user_id=session['user_id'],
            total_amount=sum(item.product.price * item.quantity for item in cart.items)
        )
        db.query(CartItem).filter_by(cart_id=cart.id).delete()
        db.add(new_order)
        db.commit()

        flash('Заказ успешно оформлен!', 'success')
        return redirect(url_for('orders'))

    except Exception as e:
        db.rollback()
        flash(f'Ошибка оформления: {str(e)}', 'danger')
        return redirect(url_for('view_cart'))
    finally:
        db.close()


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = next(get_db())
        try:
            if request.form['password'] != request.form['confirm_password']:
                flash('Пароли не совпадают', 'danger')
                return redirect(url_for('register'))

            new_user = User(
                name=request.form['name'],
                surname=request.form['surname'],
                email=request.form['email'],
                password=request.form['password'],
                phone=request.form['phone'],
                is_admin=False
            )

            db.add(new_user)
            db.commit()
            session['user_id'] = new_user.id
            return redirect(url_for('profile'))

        except IntegrityError:
            db.rollback()
            flash('Пользователь с таким email уже существует', 'danger')
        except Exception as e:
            db.rollback()
            flash(f'Ошибка: {str(e)}', 'danger')
        finally:
            db.close()
    return render_template('registration.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = next(get_db())
        try:
            user = db.query(User).filter_by(email=request.form['email']).first()
            if user and user.password == request.form['password']:
                session['user_id'] = user.id
                return redirect(url_for('profile'))
            flash('Неверный email или пароль', 'danger')
        finally:
            db.close()
    return render_template('auth.html')


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    user = db.query(User).get(session['user_id'])
    return render_template('lk.html', user=user)


@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        cart = db.query(Cart).filter_by(user_id=session['user_id']).first()
        if not cart or not cart.items:
            return render_template('cart.html', cart_items=[], total=0)

        total = sum(item.product.price * item.quantity for item in cart.items)
        return render_template('cart.html', cart_items=cart.items, total=total)
    finally:
        db.close()


@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        product = db.query(Product).get(product_id)
        if not product or product.stock_quantity < 1:
            flash('Товар недоступен', 'danger')
            return redirect(request.referrer)

        cart = db.query(Cart).filter_by(user_id=session['user_id']).first()
        if not cart:
            cart = Cart(user_id=session['user_id'])
            db.add(cart)
            db.commit()

        cart_item = db.query(CartItem).filter_by(
            cart_id=cart.id,
            product_id=product_id
        ).first()

        if cart_item:
            cart_item.quantity += 1
        else:
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=product_id,
                quantity=1
            )
            db.add(cart_item)

        db.commit()
        flash('Товар добавлен в корзину', 'success')

    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(request.referrer)


@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        item = db.query(CartItem).get(item_id)
        if item and item.cart.user_id == session['user_id']:
            item.product.stock_quantity += item.quantity
            db.delete(item)
            db.commit()
            flash('Товар удалён из корзины', 'success')
        else:
            flash('Элемент не найден', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(url_for('view_cart'))


@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    orders = db.query(Order).filter_by(user_id=session['user_id']).all()
    return render_template('orders.html', orders=orders)


@app.route('/admin')
def admin_panel():
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])
        if not user.is_admin:
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('home'))

        stats = {
            'users': db.query(User).count(),
            'products': db.query(Product).count(),
            'orders': db.query(Order).count(),
            'categories': db.query(Category).count()
        }

        products = db.query(Product).options(joinedload(Product.category)).all()
        categories = db.query(Category).all()

        return render_template(
            'admin.html',
            stats=stats,
            products=products,
            categories=categories
        )
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('home'))
    finally:
        db.close()


@app.route('/admin/add_product', methods=['POST'])
def add_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])
        if not user.is_admin:
            return render_template('access_denied.html')

        new_product = Product(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            stock_quantity=int(request.form['stock_quantity']),
            category_id=int(request.form['category_id']),
            image_url=request.form.get('image_url')
        )

        db.add(new_product)
        db.commit()
        flash('Товар успешно добавлен', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(url_for('admin_panel'))


@app.route('/admin/add_category', methods=['POST'])
def add_category():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])
        if not user.is_admin:
            return render_template('access_denied.html')

        new_category = Category(name=request.form['name'])
        db.add(new_category)
        db.commit()
        flash('Категория успешно добавлена', 'success')
    except IntegrityError:
        db.rollback()
        flash('Категория с таким названием уже существует', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])
        if not user.is_admin:
            return render_template('access_denied.html')

        product = db.query(Product).get(product_id)
        if product:
            db.query(CartItem).filter_by(product_id=product_id).delete()
            db.query(OrderItem).filter_by(product_id=product_id).delete()

            if product.image_url and product.image_url.startswith('/static'):
                try:
                    os.remove(os.path.join(app.root_path, product.image_url[1:]))
                except Exception as e:
                    print(f"Error deleting image: {str(e)}")

            db.delete(product)
            db.commit()
            flash('Товар и все связанные данные удалены', 'success')
        return redirect(url_for('admin_panel'))
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('admin_panel'))
    finally:
        db.close()


@app.route('/payment')
def payment():
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))
    return render_template('payment.html')


@app.route('/admin/delete_category/<int:category_id>', methods=['POST'])
def delete_category(category_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])
        if not user.is_admin:
            return render_template('access_denied.html')

        category = db.query(Category).get(category_id)
        if category:
            db.query(Product).filter_by(category_id=category_id).delete()
            db.delete(category)
            db.commit()
            flash('Категория и связанные товары удалены', 'success')
        return redirect(url_for('admin_panel'))
    except Exception as e:
        db.rollback()
        flash(f'Ошибка удаления: {str(e)}', 'danger')
        return redirect(url_for('admin_panel'))
    finally:
        db.close()


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
