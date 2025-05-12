from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask import abort, Response
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'



class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='user')  # 'admin' или 'user'
    notifications = db.relationship('Notification', backref='user', lazy=True)
    full_name = db.Column(db.String(200), nullable=True)
    avatar_data = db.Column(db.LargeBinary, nullable=True)
    avatar_mime = db.Column(db.String(50), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    # Связь с таблицей изображений
    images = db.relationship('ProductImage', backref='product', lazy=True)

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=True)  # храним бинарные данные изображения

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'accepted', 'sold', 'cancelled'
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    product = db.relationship('Product')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)



with app.app_context():
    db.create_all()

    # Создаём учётную запись администратора, если не существует
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(username='admin', email='admin@example.com', role='admin')
        admin_user.set_password('adminpass')
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created: admin / adminpass")


    DEFAULT_CATEGORIES = [
        "Процессоры",
        "Видеокарты",
        "Материнские платы",
        "Оперативная память",
        "Жесткие диски/SSD",
        "Корпуса",
        "Блоки питания",
        "Кулеры",
        "Мониторы",
        "Ноутбуки",
        "Прочее"
    ]
    for cat_name in DEFAULT_CATEGORIES:
        if not Category.query.filter_by(name=cat_name).first():
            db.session.add(Category(name=cat_name))
    db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Возвращает количество непрочитанных уведомлений для текущего пользователя
@app.context_processor
def inject_unread_notifications_count():
    if current_user.is_authenticated:
        count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
        return dict(unread_notifications_count=count)
    return dict(unread_notifications_count=0)



# Маршрут для отдачи бинарных изображений
@app.route('/product_image/<int:image_id>')
def product_image(image_id):
    image = ProductImage.query.get_or_404(image_id)
    if image.image_data:
        return Response(image.image_data, mimetype='image/jpeg')
    return "No image data", 404

# Стартовая страница
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

# Аутентификация

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        # Ищем пользователя по email вместо username
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Вход выполнен успешно!", "success")
            return redirect(url_for('index'))
        else:
            flash("Неверный email или пароль", "danger")
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы вышли из аккаунта", "info")
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Пользователь с такими данными уже существует", "danger")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Регистрация прошла успешно!", "success")
            return redirect(url_for('login'))
    return render_template('register.html')

# Главная страница с товарами, поиском и фильтрацией
@app.route('/index')
@login_required
def index():
    query = request.args.get('q', '')
    category_id = request.args.get('category', type=int)
    products_query = Product.query
    if query:
        products_query = products_query.filter(Product.name.contains(query))
    if category_id:
        products_query = products_query.filter_by(category_id=category_id)
    products = products_query.all()
    categories = Category.query.all()
    return render_template('index.html', products=products, categories=categories, query=query,
                           selected_category=category_id)

from flask import abort, Response

@app.route('/avatar/<int:user_id>')
def avatar(user_id):
    user = User.query.get_or_404(user_id)
    if user.avatar_data:
        return Response(user.avatar_data, mimetype=user.avatar_mime)
    # Если аватар не загружен — возвращаем 404, шаблон покажет иконку 👤
    abort(404)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user

    if request.method == 'POST':
        # 1) Загрузка аватара
        avatar = request.files.get('avatar')
        if avatar and avatar.filename:
            data = avatar.read()
            user.avatar_data = data
            user.avatar_mime = avatar.mimetype
            db.session.commit()
            flash('Аватар обновлён.', 'success')
            return redirect(url_for('profile'))

        # 2) Обновление ФИО/email/логина
        if 'save_profile' in request.form:
            # безопасно достаём поля — если их нет, получим пустую строку
            full_name = request.form.get('full_name', '').strip() or None
            new_email = request.form.get('email', '').strip().lower()
            new_login = request.form.get('username', '').strip()

            # проверка уникальности
            if new_email and new_email != user.email:
                if User.query.filter(User.email == new_email, User.id != user.id).first():
                    flash('Этот email уже занят.', 'danger')
                    return redirect(url_for('profile'))
                user.email = new_email

            if new_login and new_login != user.username:
                if User.query.filter(User.username == new_login, User.id != user.id).first():
                    flash('Этот логин уже занят.', 'danger')
                    return redirect(url_for('profile'))
                user.username = new_login

            user.full_name = full_name
            db.session.commit()
            flash('Профиль обновлён.', 'success')
            return redirect(url_for('profile'))

        # 3) Смена пароля
        if 'change_password' in request.form:
            curr = request.form.get('current_password', '')
            np1  = request.form.get('new_password', '')
            np2  = request.form.get('new_password2', '')

            if not user.check_password(curr):
                flash('Текущий пароль неверный.', 'danger')
            elif not np1 or np1 != np2:
                flash('Новые пароли не совпадают.', 'danger')
            else:
                user.set_password(np1)
                db.session.commit()
                flash('Пароль изменён.', 'success')
            return redirect(url_for('profile'))

    # GET: просто отрисовать профиль
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.timestamp.desc()).all()
    return render_template('profile.html', user=user, orders=orders)


# Страница подробного просмотра товара
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@app.route('/cart/update/<int:product_id>', methods=['POST'])
@login_required
def update_cart(product_id):
    try:
        new_qty = int(request.form.get('quantity', 1))
    except ValueError:
        flash('Неверное количество', 'danger')
        return redirect(url_for('cart'))

    cart = session.get('cart', {})
    key = str(product_id)
    if key in cart:
        if new_qty > 0:
            cart[key] = new_qty
            flash('Количество обновлено', 'success')
        else:
            cart.pop(key)
            flash('Товар удалён из корзины', 'warning')
        session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    key = str(product_id)
    if key in cart:
        cart.pop(key)
        session['cart'] = cart
        flash('Товар удалён из корзины', 'success')
    else:
        flash('Такого товара в корзине нет', 'warning')
    return redirect(url_for('cart'))

# Добавление товара в корзину
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    if product.quantity <= 0:
        flash("Товара нет в наличии", "warning")
        return redirect(url_for('index'))
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + int(request.form.get('quantity', 1))
    session['cart'] = cart
    flash("Товар добавлен в корзину", "success")
    return redirect(url_for('index'))

# Страница корзины
@app.route('/cart')
@login_required
def cart():
    cart = session.get('cart', {})
    products_list = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            subtotal = product.price * quantity
            total += subtotal
            products_list.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    return render_template('cart.html', products=products_list, total=total)

# Оформление заказа
@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash("Корзина пуста", "warning")
        return redirect(url_for('index'))
    order = Order(user_id=current_user.id)
    db.session.add(order)
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product and product.quantity >= quantity:
            product.quantity -= quantity
            order_item = OrderItem(order=order, product_id=product.id, quantity=quantity)
            db.session.add(order_item)
            # Уведомление для админов
            admin_users = User.query.filter_by(role='admin').all()
            for admin in admin_users:
                note = Notification(
                    user_id=admin.id,
                    message=f"Пользователь {current_user.username} приобрел {product.name} (количество: {quantity})"
                )
                db.session.add(note)
        else:
            flash(f"Недостаточно товара {product.name}", "danger")
            return redirect(url_for('cart'))
    db.session.commit()
    session['cart'] = {}
    flash("Заказ оформлен, ожидайте подтверждения", "success")
    return redirect(url_for('orders'))

# Страница заказов пользователя
@app.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.timestamp.desc()).all()
    return render_template('orders.html', orders=orders)

# История покупок (заказы со статусом "sold")
@app.route('/purchase_history')
@login_required
def purchase_history():
    sold_orders = Order.query.filter(Order.user_id == current_user.id, Order.status == 'sold').order_by(Order.timestamp.desc()).all()
    return render_template('purchase_history.html', orders=sold_orders)

# Уведомления
@app.route('/notifications')
@login_required
def notifications():
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
    return render_template('notifications.html', notifications=notes)

# Административная панель
@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash("Доступ запрещен", "danger")
        return redirect(url_for('index'))
    all_orders = Order.query.order_by(Order.timestamp.desc()).all()
    products = Product.query.all()
    return render_template('admin_dashboard.html', orders=all_orders, products=products)

# Админ: добавление товара
@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if current_user.role != 'admin':
        flash("Доступ запрещен", "danger")
        return redirect(url_for('index'))

    categories = Category.query.all()
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        category_id = int(request.form['category_id'])

        product = Product(name=name, description=description, price=price,
                          quantity=quantity, category_id=category_id)
        db.session.add(product)
        db.session.commit()

        files = request.files.getlist('images')
        if not files or len(files) == 0:
            flash("Нужно загрузить хотя бы одно изображение", "danger")
            db.session.delete(product)
            db.session.commit()
            return redirect(url_for('admin_add_product'))

        if len(files) > 5:
            flash("Нельзя загружать более 5 изображений на один товар", "danger")
            db.session.delete(product)
            db.session.commit()
            return redirect(url_for('admin_add_product'))

        for f in files:
            if f and f.filename:
                image_data = f.read()
                product_image = ProductImage(product_id=product.id, image_data=image_data)
                db.session.add(product_image)
        db.session.commit()

        flash("Товар и изображения успешно добавлены!", "success")
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_product.html', categories=categories)

# Админ: редактирование товара
@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if current_user.role != 'admin':
        flash("Доступ запрещен", "danger")
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    categories = Category.query.all()
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.quantity = int(request.form['quantity'])
        product.category_id = int(request.form['category_id'])
        db.session.commit()

        # Если добавляем новые изображения
        files = request.files.getlist('images')
        if files and len(files) > 0 and files[0].filename != '':
            existing_count = len(product.images)
            if existing_count + len(files) > 5:
                flash("Всего не более 5 изображений на товар!", "danger")
                return redirect(url_for('admin_edit_product', product_id=product.id))

            for f in files:
                if f and f.filename:
                    image_data = f.read()
                    product_image = ProductImage(product_id=product.id, image_data=image_data)
                    db.session.add(product_image)
            db.session.commit()

        flash("Товар обновлён", "success")
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_edit_product.html', product=product, categories=categories)

# Админ: удаление товара
@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@login_required
def admin_delete_product(product_id):
    if current_user.role != 'admin':
        flash("Доступ запрещен", "danger")
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Товар удалён", "success")
    return redirect(url_for('admin_dashboard'))

# Админ: обновление статуса заказа
@app.route('/admin/order/update/<int:order_id>', methods=['POST'])
@login_required
def admin_update_order(order_id):
    if current_user.role != 'admin':
        flash("Доступ запрещен", "danger")
        return redirect(url_for('index'))
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['accepted', 'sold', 'cancelled']:
        order.status = new_status
        db.session.commit()
        note = Notification(
            user_id=order.user_id,
            message=f"Статус вашего заказа #{order.id} изменен на {new_status}"
        )
        db.session.add(note)
        db.session.commit()
        flash("Статус заказа обновлен", "success")
    else:
        flash("Неверный статус", "danger")
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
