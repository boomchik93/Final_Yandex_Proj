from flask import Flask, render_template, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key'


# Существующие маршруты
@app.route('/')
def home():
    return render_template('main.html')


@app.route('/login')
def login():
    return render_template('auth.html')


@app.route('/register')
def register():
    return render_template('registration.html')


@app.route('/profile')
def profile():
    return render_template('lk.html')


@app.route('/orders')
def orders():
    return render_template('orders.html')


@app.route('/payment')
def payment():
    return render_template('payment.html')


@app.route('/logout')
def logout():
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
