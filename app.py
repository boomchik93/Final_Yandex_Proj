from flask import Flask, render_template, request, redirect, url_for, session
from data.db_session import get_db
from data.__all_models import User, Order

app = Flask(__name__)
app.secret_key = 'secret_key'


@app.route('/')
def home():
    return render_template('main.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = next(get_db())
        try:
            new_user = User(
                name=request.form['name'],
                surname=request.form['surname'],
                email=request.form['email'],
                password=request.form['password'],
                phone=request.form['phone']
            )
            db.add(new_user)
            db.commit()
            session['user_id'] = new_user.id
            return redirect(url_for('profile'))
        except Exception as e:
            db.rollback()
            return f"Ошибка: {str(e)}"
        finally:
            db.close()
    return render_template('registration.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = next(get_db())
        user = db.query(User).filter_by(email=request.form['email']).first()
        if user and user.password == request.form['password']:
            session['user_id'] = user.id
            return redirect(url_for('profile'))
        return "Неверные данные"
    return render_template('auth.html')


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = next(get_db())
    user = db.query(User).get(session['user_id'])
    return render_template('lk.html', user=user)


@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = next(get_db())
    user_orders = db.query(Order).filter_by(user_id=session['user_id']).all()
    return render_template('orders.html', orders=user_orders)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))


@app.route('/payment')
def payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    return render_template('payment.html')


if __name__ == '__main__':
    app.run(debug=True)
