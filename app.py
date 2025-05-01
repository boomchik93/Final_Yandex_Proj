from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from data.db_session import get_db
from data.__all_models import User, Product, Category, Cart, CartItem, Order, OrderItem, DeliveryAddress, PromoCode
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
import os
import pytz
import re
from datetime import datetime
from functools import wraps
from flask import abort
from decimal import Decimal


def calculate_cart_total(user_id):
    db = next(get_db())
    try:
        cart = db.query(Cart).options(
            joinedload(Cart.items).joinedload(CartItem.product)
        ).filter_by(user_id=user_id).first()

        if not cart or not cart.items:
            return 0

        return sum(
            item.product.price * item.quantity
            for item in cart.items
        )
    except Exception as e:
        app.logger.error(f"Error calculating cart total: {str(e)}")
        return 0
    finally:
        db.close()


def is_admin():
    if 'user_id' not in session:
        return False
    db = next(get_db())
    user = db.query(User).get(session['user_id'])
    db.close()
    return user and user.is_admin


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


MOSCOW_TZ = pytz.timezone('Europe/Moscow')
app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'img', 'products')


def format_phone_number(phone):
    cleaned = re.sub(r'\D', '', phone)

    if cleaned.startswith('8'):
        cleaned = '7' + cleaned[1:]

    if len(cleaned) == 10:
        cleaned = '7' + cleaned

    if len(cleaned) != 11 or not cleaned.startswith('7'):
        return None

    return f'+{cleaned}'


def regex_match(value, pattern):
    return re.match(pattern, value) is not None


app.jinja_env.tests['regex_match'] = regex_match


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


def validate_promo(code, user_id):
    db = next(get_db())
    try:
        promo = db.query(PromoCode).filter_by(code=code.upper()).first()
        if not promo or not promo.is_active:
            return None, "Недействительный промокод"

        if promo.end_date and promo.end_date < datetime.utcnow():
            return None, "Промокод истек"

        if promo.activations_count >= promo.max_activations:
            return None, "Лимит активаций исчерпан"

        if not promo.is_reusable:
            existing = db.query(Order).filter(
                Order.user_id == user_id,
                Order.promo_code == promo.code
            ).first()
            if existing:
                return None, "Вы уже использовали этот промокод"
        cart_total = calculate_cart_total(user_id)
        if cart_total < 1000:
            return None, "Минимальная сумма заказа для промокода 1000 руб."

        return promo, ""
    finally:
        db.close()
        return promo, ""


@app.route('/admin/promo/delete/<int:promo_id>', methods=['DELETE'])
def admin_delete_promo(promo_id):
    if not is_admin():
        return jsonify({'error': 'Доступ запрещён'}), 403

    db = next(get_db())
    try:
        promo = db.query(PromoCode).get(promo_id)
        if not promo:
            return jsonify({'error': 'Промокод не найден'}), 404

        db.delete(promo)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/apply_promo', methods=['POST'])
@app.route('/api/apply_promo', methods=['POST'])
def apply_promo():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    db = next(get_db())
    try:
        data = request.get_json()
        code = data.get('code', '').strip().upper()
        user_id = session['user_id']

        cart = db.query(Cart).options(
            joinedload(Cart.items).joinedload(CartItem.product)
        ).filter_by(user_id=user_id).first()

        if not cart or not cart.items:
            return jsonify({'error': 'Корзина пуста'}), 400

        cart_total = sum(
            Decimal(str(item.product.price)) * item.quantity
            for item in cart.items
        )

        promo = db.query(PromoCode).filter_by(code=code).first()
        if not promo or not promo.is_active:
            return jsonify({'error': 'Недействительный промокод'}), 400

        if promo.end_date and promo.end_date < datetime.utcnow():
            return jsonify({'error': 'Промокод истек'}), 400

        if promo.activations_count >= promo.max_activations:
            return jsonify({'error': 'Лимит активаций исчерпан'}), 400

        discount = Decimal(str(promo.discount)) / Decimal(100)
        new_total = cart_total * (Decimal(1) - discount)

        return jsonify({
            'code': promo.code,
            'discount': float(promo.discount),
            'original_total': float(cart_total),
            'new_total': float(new_total.quantize(Decimal('0.01'))),
            'remaining_uses': promo.max_activations - promo.activations_count
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/admin/promo')
def admin_promo_list():
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('home'))

    db = next(get_db())
    try:
        promos = db.query(PromoCode).order_by(PromoCode.id.desc()).all()
        return render_template('admin/promo_list.html', promos=promos)
    except Exception as e:
        flash(f'Ошибка загрузки промокодов: {str(e)}', 'danger')
        return redirect(url_for('home'))
    finally:
        db.close()


@app.route('/admin/promo/create', methods=['GET', 'POST'])
def admin_create_promo():
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('home'))

    db = next(get_db())

    if request.method == 'POST':
        try:
            end_date = datetime.fromisoformat(request.form['end_date']) if request.form.get('end_date') else None
            if end_date:
                end_date = end_date.astimezone(pytz.timezone('Europe/Moscow'))

            promo_data = {
                'code': request.form['code'].strip().upper(),
                'discount': float(request.form['discount']),
                'max_activations': int(request.form['max_activations']),
                'end_date': end_date,
                'is_active': 'is_active' in request.form,
                'is_reusable': 'is_reusable' in request.form
            }

            new_promo = PromoCode(**promo_data)
            db.add(new_promo)
            db.commit()

            flash('Промокод успешно создан', 'success')
            return redirect(url_for('admin_promo_list'))

        except Exception as e:
            db.rollback()
            flash(f'Ошибка создания промокода: {str(e)}', 'danger')
            return redirect(url_for('admin_promo_list'))
        finally:
            db.close()

    return render_template('admin/promo_form.html')


@app.route('/admin/promo/edit/<int:promo_id>', methods=['GET', 'POST'])
def admin_edit_promo(promo_id):
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('home'))

    db = next(get_db())
    try:
        promo = db.query(PromoCode).get(promo_id)
        if not promo:
            flash('Промокод не найден', 'danger')
            return redirect(url_for('admin_promo_list'))

        if request.method == 'POST':
            promo.code = request.form['code'].strip().upper()
            promo.discount = float(request.form['discount'])
            promo.max_activations = int(request.form['max_activations'])
            promo.end_date = datetime.fromisoformat(request.form['end_date']) if request.form['end_date'] else None
            promo.is_active = 'is_active' in request.form
            promo.is_reusable = 'is_reusable' in request.form

            db.commit()
            flash('Промокод успешно обновлён', 'success')
            return redirect(url_for('admin_promo_list'))

        return render_template('admin/promo_form.html', promo=promo)

    except ValueError as e:
        db.rollback()
        flash('Некорректные данные в форме', 'danger')
        return redirect(url_for('admin_edit_promo', promo_id=promo_id))
    except Exception as e:
        db.rollback()
        flash(f'Ошибка обновления промокода: {str(e)}', 'danger')
        return redirect(url_for('admin_edit_promo', promo_id=promo_id))
    finally:
        db.close()


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
        action = request.form.get('action')
        item = db.query(CartItem).get(item_id)

        if not item or item.cart.user_id != session['user_id']:
            flash('Элемент не найден', 'danger')
            return redirect(url_for('view_cart'))

        product = db.query(Product).get(item.product_id)

        if action == 'increment':
            if product.stock_quantity > item.quantity:
                item.quantity += 1
            else:
                flash(f'Максимальное количество товара {product.name} - {product.stock_quantity}', 'warning')
        elif action == 'decrement':
            if item.quantity > 1:
                item.quantity -= 1
            else:
                db.delete(item)
        else:
            flash('Некорректное действие', 'danger')

        db.commit()
        flash('Корзина обновлена', 'success')

    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    finally:
        db.close()

    return redirect(url_for('view_cart'))


@app.route('/delivery', methods=['GET', 'POST'])
def delivery():
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])

        if not user.phone or not re.match(r'^\+7\d{10}$', user.phone):
            flash('Проверьте номер телефона в профиле', 'danger')
            return redirect(url_for('profile'))

        if request.method == 'GET':
            cart = db.query(Cart).options(
                joinedload(Cart.items).joinedload(CartItem.product)
            ).filter_by(user_id=user.id).first()

            if not cart or not cart.items:
                flash('Корзина пуста', 'danger')
                return redirect(url_for('view_cart'))

            total = sum(
                Decimal(str(item.product.price)) * item.quantity
                for item in cart.items
            )

            return render_template('delivery.html',
                                   cart_items=cart.items,
                                   total=total,
                                   user=user)

        elif request.method == 'POST':
            promo_code = request.form.get('promo_code', '').strip().upper()
            cart = db.query(Cart).options(
                joinedload(Cart.items).joinedload(CartItem.product)
            ).filter_by(user_id=user.id).first()

            if not cart or not cart.items:
                flash('Корзина пуста', 'danger')
                return redirect(url_for('view_cart'))

            total = Decimal('0')
            for item in cart.items:
                product = db.query(Product).get(item.product_id)
                if product.stock_quantity < item.quantity:
                    flash(f'Недостаточно товара "{product.name}". Доступно: {product.stock_quantity}', 'danger')
                    return redirect(url_for('view_cart'))
                total += Decimal(str(product.price)) * item.quantity

            promo = None
            total_with_discount = total

            if promo_code:
                promo = db.query(PromoCode).filter_by(code=promo_code).first()

                if promo and promo.is_active:
                    if promo.end_date and promo.end_date < datetime.utcnow():
                        flash('Срок действия промокода истек', 'danger')
                    elif promo.activations_count >= promo.max_activations:
                        flash('Лимит активаций промокода исчерпан', 'danger')
                    else:
                        discount = Decimal(str(promo.discount)) / Decimal(100)
                        total_with_discount = total * (Decimal('1') - discount)

                        promo.activations_count += 1
                        if promo.activations_count >= promo.max_activations:
                            promo.is_active = False
                        db.commit()

            new_order = Order(
                user_id=user.id,
                total_amount=total_with_discount.quantize(Decimal('0.01')),
                status='Ожидает оплаты',
                promo_code=promo.code if promo else None,
                created_at=datetime.utcnow()
            )
            db.add(new_order)
            db.flush()

            for item in cart.items:
                product = db.query(Product).get(item.product_id)
                product.stock_quantity -= item.quantity

                order_item = OrderItem(
                    order_id=new_order.id,
                    product_id=product.id,
                    quantity=item.quantity,
                    price_at_purchase=product.price
                )
                db.add(order_item)

            delivery_address = DeliveryAddress(
                order_id=new_order.id,
                country=request.form['country'],
                city=request.form['city'],
                street=request.form['street'],
                house=request.form['house'],
                apartment=request.form.get('apartment', ''),
                phone=user.phone,
                additional_info=request.form.get('additional_info', '')
            )
            db.add(delivery_address)

            db.query(CartItem).filter_by(cart_id=cart.id).delete()
            db.commit()

            flash(f'Заказ №{new_order.id} успешно оформлен!', 'success')
            return redirect(url_for('orders'))

    except IntegrityError as e:
        db.rollback()
        flash('Ошибка при создании заказа', 'danger')
        return redirect(url_for('view_cart'))

    except Exception as e:
        db.rollback()
        flash(f'Критическая ошибка: {str(e)}', 'danger')
        return redirect(url_for('view_cart'))

    finally:
        db.close()


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = next(get_db())
        try:
            phone = format_phone_number(request.form['phone'])
            if not phone:
                flash('Неверный формат телефона', 'danger')
                return redirect(url_for('register'))
            if request.form['password'] != request.form['confirm_password']:
                flash('Пароли не совпадают', 'danger')
                return redirect(url_for('register'))

            new_user = User(
                name=request.form['name'],
                surname=request.form['surname'],
                email=request.form['email'],
                password=request.form['password'],
                phone=phone,
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


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    user = db.query(User).get(session['user_id'])

    if request.method == 'POST':
        try:
            user.name = request.form['name']
            user.surname = request.form['surname']
            user.email = request.form['email']

            new_phone = format_phone_number(request.form['phone'])
            if not new_phone:
                flash('Неверный формат телефона. Используйте российский номер', 'danger')
                return redirect(url_for('profile'))

            user.phone = new_phone

            if request.form['new_password']:
                if request.form['new_password'] != request.form['confirm_password']:
                    flash('Пароли не совпадают', 'danger')
                    return redirect(url_for('profile'))
                user.password = request.form['new_password']

            db.commit()
            flash('Профиль успешно обновлен', 'success')
            return redirect(url_for('profile'))

        except IntegrityError:
            db.rollback()
            flash('Пользователь с таким email уже существует', 'danger')
        except Exception as e:
            db.rollback()
            flash(f'Ошибка обновления: {str(e)}', 'danger')

    phone_warning = False
    if user.phone:
        phone_warning = not re.match(r'^\+7\d{10}$', user.phone)

    return render_template('lk.html',
                           user=user,
                           phone_warning=phone_warning)


@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        cart = db.query(Cart).options(
            joinedload(Cart.items).joinedload(CartItem.product)
        ).filter_by(user_id=session['user_id']).first()

        if not cart or not cart.items:
            return render_template('cart.html', cart_items=[], total=Decimal('0'))

        total = Decimal('0')
        for item in cart.items:
            price = Decimal(str(item.product.price))
            quantity = Decimal(str(item.quantity))
            total += price * quantity

        return render_template(
            'cart.html',
            cart_items=cart.items,
            total=total.quantize(Decimal('0.01')))

    except Exception as e:
        flash(f'Ошибка загрузки корзины: {str(e)}', 'danger')
        return redirect(url_for('home'))
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
    orders = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.product),
        joinedload(Order.delivery_address)
    ).filter_by(user_id=session['user_id']).all()

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


@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    try:
        user = db.query(User).get(session['user_id'])
        if not user.is_admin:
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('home'))

        product = db.query(Product).get(product_id)
        categories = db.query(Category).all()

        if request.method == 'POST':
            product.name = request.form['name']
            product.description = request.form['description']
            product.price = float(request.form['price'])
            product.stock_quantity = int(request.form['stock_quantity'])
            product.category_id = int(request.form['category_id'])
            product.image_url = request.form.get('image_url', product.image_url)

            db.commit()
            flash('Товар успешно обновлён', 'success')
            return redirect(url_for('admin_panel'))

        return render_template(
            'edit_product.html',
            product=product,
            categories=categories
        )
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('admin_panel'))
    finally:
        db.close()


if __name__ == '__main__':
    app.run(debug=True)
