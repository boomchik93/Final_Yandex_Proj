# app.py (обновленная версия)
from flask import Flask, render_template, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key'


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


if __name__ == '__main__':
    app.run(debug=True)
