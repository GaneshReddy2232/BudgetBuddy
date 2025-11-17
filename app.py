from flask import Flask, render_template, request, redirect, url_for, flash, Response, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import extract
from datetime import datetime, date, timedelta
import calendar
import os
import math
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- make a now() callable available inside Jinja templates ---
from typing import Optional

@app.context_processor
def inject_now():
    def now(fmt: Optional[str] = None):
        if fmt:
            return datetime.utcnow().strftime(fmt)
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    return {'now': now}

# ------------------------------------------------------------

# ------------------ Models ------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f"<User {self.username}>"

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)

    # associate expenses with a user (optional - per-user data)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # if you enable per-user expenses you can uncomment the relationship below
    # user = db.relationship('User', backref='expenses')

    def __repr__(self):
        return f"<Expense {self.title} - {self.amount}>"

# Create tables at startup (compatible with Flask 3+)
with app.app_context():
    db.create_all()


# ------------------ Auth helpers ------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to continue", "warning")
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapper

# Optional: get current user helper
def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

# Make user available in templates
@app.context_processor
def inject_user():
    return {'current_user': current_user()}

# ------------------ Auth routes ------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Please provide both username and password", "danger")
            return redirect(url_for('signup'))

        if User.query.filter_by(username=username).first():
            flash("Username already taken", "danger")
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password)
        user = User(username=username, password=hashed_pw)
        db.session.add(user)
        db.session.commit()

        flash("Account created — please log in", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # if already logged in, go to index
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash("Logged in successfully", "success")
            # redirect to next param if present
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
        else:
            flash("Invalid username or password", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for('login'))

# ------------------ Expense routes ------------------

@app.route('/')
@login_required
def index():
    """
    List expenses with server-side filtering via query params:
      - q: search query (title substring)
      - category: Food | Travel | Bills | all (default all)
      - month: 1-12 (optional)
      - year: YYYY (optional)
    The route returns the filtered rows and the total amount for those filtered rows.
    """
    # get query params
    q = request.args.get('q', '').strip()
    category = request.args.get('category', 'all').strip()
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)

    # build filters list (safe, reusable)
    filters = []

    # If you want expenses to be user-specific, uncomment and use current_user
    # user = current_user()
    # if user:
    #     filters.append(Expense.user_id == user.id)

    if q:
        filters.append(Expense.title.ilike(f'%{q}%'))

    if category and category.lower() != 'all':
        filters.append(Expense.category == category)

    if month and year:
        filters.append(extract('year', Expense.date) == year)
        filters.append(extract('month', Expense.date) == month)

    # apply filters to the main query
    if filters:
        expenses = Expense.query.filter(*filters).order_by(Expense.date.desc()).all()
    else:
        expenses = Expense.query.order_by(Expense.date.desc()).all()

    # compute total for the filtered results using the same filters
    sum_query = db.session.query(db.func.sum(Expense.amount))
    if filters:
        sum_query = sum_query.filter(*filters)
    month_total = sum_query.scalar() or 0.0
    month_total = round(month_total, 2)

    return render_template(
        'index.html',
        expenses=expenses,
        month_total=month_total,
        q=q,
        selected_category=category,
        filter_month=month,
        filter_year=year
    )


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        title = request.form['title']
        amount = request.form['amount']
        category = request.form['category']
        date_str = request.form.get('date', '')
        try:
            date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except Exception:
            date_val = datetime.utcnow().date()

        if not title or not amount or not category:
            flash('Please fill all required fields', 'danger')
            return redirect(url_for('add_expense'))

        exp = Expense(
            title=title,
            amount=float(amount),
            category=category,
            date=date_val,
            # user_id = session.get('user_id')  # enable if associating with user
        )
        db.session.add(exp)
        db.session.commit()
        flash('Expense added successfully', 'success')
        return redirect(url_for('index'))

    return render_template('add_edit.html', action='Add', expense=None)


@app.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    # if per-user data, ensure the user owns this expense:
    # if expense.user_id != session.get('user_id'):
    #     flash("Not authorized", "danger")
    #     return redirect(url_for('index'))

    if request.method == 'POST':
        expense.title = request.form['title']
        expense.amount = float(request.form['amount'])
        expense.category = request.form['category']
        date_str = request.form.get('date', '')
        try:
            expense.date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else expense.date
        except Exception:
            pass
        db.session.commit()
        flash('Expense updated successfully', 'success')
        return redirect(url_for('index'))

    return render_template('add_edit.html', action='Edit', expense=expense)


@app.route('/confirm_delete/<int:expense_id>', methods=['GET'])
@login_required
def confirm_delete_page(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    return render_template('confirm_delete.html', expense=expense)


@app.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted', 'info')
    return redirect(url_for('index'))


# ------------------ Summary & SVG code (unchanged, protected) ------------------

def totals_for_month(month: int, year: int):
    """Return (totals_by_category_dict, total_sum) for given month/year."""
    expenses = Expense.query.filter(
        extract('year', Expense.date) == year,
        extract('month', Expense.date) == month
    ).all()

    totals = {}
    total = 0.0
    for e in expenses:
        totals[e.category] = totals.get(e.category, 0.0) + e.amount
        total += e.amount
    return totals, total


def make_pie_paths(slices, total, cx=120, cy=120, r=100, colors=None):
    """
    Given `slices` as list of {'category':..., 'value':...} and their `total`,
    return list of dicts: {'d': path_data, 'color':..., 'label_x':x, 'label_y':y, 'label':..., 'value':..., 'pct':...}
    Coordinates are suitable for embedding in an inline SVG with viewBox large enough.
    """
    if not colors:
        # pleasant palette (repeats if more categories)
        colors = ['#3A9AD9', '#FF6B78', '#FFD166', '#6BCB77', '#8E63FF', '#FF9F80']

    paths = []
    if total <= 0:
        return paths

    start_angle = 0.0  # degrees
    for i, s in enumerate(slices):
        value = float(s['value'])
        if value <= 0:
            continue
        angle = (value / total) * 360.0
        end_angle = start_angle + angle

        # convert to radians for math
        start_rad = math.radians(start_angle - 90)  # -90 so 0 degrees is top
        end_rad = math.radians(end_angle - 90)

        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)

        large_arc = 1 if angle > 180 else 0

        # path: Move to center, line to start point, arc to end point, close path
        d = f"M {cx:.2f},{cy:.2f} L {x1:.2f},{y1:.2f} A {r:.2f},{r:.2f} 0 {large_arc},1 {x2:.2f},{y2:.2f} Z"

        # label at mid-angle
        mid_angle = start_angle + angle / 2.0
        mid_rad = math.radians(mid_angle - 90)
        label_r = r * 0.62  # label distance from center
        label_x = cx + label_r * math.cos(mid_rad)
        label_y = cy + label_r * math.sin(mid_rad)

        pct = round((value / total) * 100.0, 2)

        paths.append({
            'd': d,
            'color': colors[i % len(colors)],
            'label_x': label_x,
            'label_y': label_y,
            'label': s['category'],
            'value': round(value, 2),
            'pct': pct
        })

        start_angle = end_angle

    return paths


@app.route('/summary')
@login_required
def monthly_summary():
    # Default primary month = current month
    today = datetime.utcnow().date()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    # Default compare month = previous month (automatically roll over year)
    compare_month = request.args.get('compare_month', None, type=int)
    compare_year = request.args.get('compare_year', None, type=int)

    if compare_month is None or compare_year is None:
        first_of_current = date(year, month, 1)
        prev_month_last_day = first_of_current - timedelta(days=1)
        compare_month = prev_month_last_day.month
        compare_year = prev_month_last_day.year

    # Get totals
    primary_totals_map, primary_total = totals_for_month(month, year)
    compare_totals_map, compare_total = totals_for_month(compare_month, compare_year)

    # Build combined category set
    categories = sorted(set(list(primary_totals_map.keys()) + list(compare_totals_map.keys())))

    # Build comparison rows: category -> {primary, compare, diff, pct_change}
    comparison = []
    primary_slices = []
    compare_slices = []
    for cat in categories:
        p = round(primary_totals_map.get(cat, 0.0), 2)
        c = round(compare_totals_map.get(cat, 0.0), 2)
        diff = round(p - c, 2)
        # percent change relative to compare_month (if compare is 0 and primary >0, mark as "inf")
        pct = None
        if c == 0:
            pct = None if p == 0 else "inf"
        else:
            pct = round((diff / c) * 100, 2)
        comparison.append({
            'category': cat,
            'primary': p,
            'compare': c,
            'diff': diff,
            'pct_change': pct
        })
        primary_slices.append({'category': cat, 'value': p})
        compare_slices.append({'category': cat, 'value': c})

    # Overall diff and pct
    overall_diff = round(primary_total - compare_total, 2)
    if compare_total == 0:
        overall_pct = None if primary_total == 0 else "inf"
    else:
        overall_pct = round((overall_diff / compare_total) * 100, 2)

    # Month names for display
    month_name = calendar.month_name[month]
    compare_month_name = calendar.month_name[compare_month]

    # compute max value to scale bar chart (existing)
    max_bar_value = 0.0
    for r in comparison:
        max_bar_value = max(max_bar_value, r['primary'], r['compare'])
    if max_bar_value == 0:
        max_bar_value = max(primary_total, compare_total, 1.0)
    max_bar_value = float(max_bar_value)

    # --- NEW: make pie path data for both months (SVG path strings)
    # Choose SVG canvas size (these values are for template viewBox)
    cx, cy, r = 120, 120, 100
    primary_pie = make_pie_paths(primary_slices, primary_total, cx=cx, cy=cy, r=r)
    compare_pie = make_pie_paths(compare_slices, compare_total, cx=cx, cy=cy, r=r)

    return render_template(
        'summary.html',
        comparison=comparison,
        primary_total=round(primary_total, 2),
        compare_total=round(compare_total, 2),
        overall_diff=overall_diff,
        overall_pct=overall_pct,
        month=month,
        year=year,
        compare_month=compare_month,
        compare_year=compare_year,
        month_name=month_name,
        compare_month_name=compare_month_name,
        max_bar_value=max_bar_value,
        primary_pie=primary_pie,
        compare_pie=compare_pie
    )


@app.route('/download_summary_svg')
@login_required
def download_summary_svg():
    """
    Returns a downloadable SVG that contains:
      - the bar chart (category comparison)
      - two pie charts (primary and compare)
    """
    # read month/year params (same logic as monthly_summary)
    today = datetime.utcnow().date()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    compare_month = request.args.get('compare_month', None, type=int)
    compare_year = request.args.get('compare_year', None, type=int)

    if compare_month is None or compare_year is None:
        first_of_current = date(year, month, 1)
        prev_month_last_day = first_of_current - timedelta(days=1)
        compare_month = prev_month_last_day.month
        compare_year = prev_month_last_day.year

    # compute comparison data (reuse totals_for_month)
    primary_totals_map, primary_total = totals_for_month(month, year)
    compare_totals_map, compare_total = totals_for_month(compare_month, compare_year)
    categories = sorted(set(list(primary_totals_map.keys()) + list(compare_totals_map.keys())))

    comparison = []
    primary_slices = []
    compare_slices = []
    for cat in categories:
        p = round(primary_totals_map.get(cat, 0.0), 2)
        c = round(compare_totals_map.get(cat, 0.0), 2)
        diff = round(p - c, 2)
        pct = None
        if c == 0:
            pct = None if p == 0 else "inf"
        else:
            pct = round((diff / c) * 100, 2)
        comparison.append({'category': cat, 'primary': p, 'compare': c, 'diff': diff, 'pct_change': pct})
        primary_slices.append({'category': cat, 'value': p})
        compare_slices.append({'category': cat, 'value': c})

    max_bar_value = 0.0
    for r in comparison:
        max_bar_value = max(max_bar_value, r['primary'], r['compare'])
    if max_bar_value == 0:
        max_bar_value = max(primary_total, compare_total, 1.0)
    max_bar_value = float(max_bar_value)

    # PIE path data
    primary_pie = make_pie_paths(primary_slices, primary_total, cx=120, cy=120, r=100)
    compare_pie = make_pie_paths(compare_slices, compare_total, cx=120, cy=120, r=100)

    # Build SVG: include bar chart at left and pies stacked at right
    vg_width = 1200
    row_h = 56
    top_margin = 42
    left_padding = 320
    right_padding = 40
    rows = len(comparison)
    bar_area_height = top_margin + (rows * row_h) + 40
    pie_area_height = 280
    vg_height = max(bar_area_height, pie_area_height + 40)

    bar_max_width = vg_width - left_padding - (vg_width // 3) - 40  # leave space for pies on right

    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vg_width} {vg_height}">')

    # Title
    parts.append(f'<text x="20" y="24" font-family="Arial, sans-serif" font-size="18" fill="#222">Comparison: {calendar.month_name[month]} {year} vs {calendar.month_name[compare_month]} {compare_year}</text>')

    # Legend for bars
    parts.append(f'<g transform="translate(20,32)" font-family="Arial, sans-serif" font-size="12">')
    parts.append(f'<rect x="0" y="0" width="14" height="10" fill="#3A9AD9"></rect><text x="20" y="9">{calendar.month_name[month]} {year}</text>')
    parts.append(f'<rect x="220" y="0" width="14" height="10" fill="#FF6B78"></rect><text x="244" y="9">{calendar.month_name[compare_month]} {compare_year}</text>')
    parts.append('</g>')

    # Bars area
    y = top_margin
    for row in comparison:
        p = row['primary']; c = row['compare']
        p_w = (p / max_bar_value) * bar_max_width if max_bar_value else 0
        c_w = (c / max_bar_value) * bar_max_width if max_bar_value else 0
        # category label
        parts.append(f'<text x="20" y="{y+10}" font-family="Arial, sans-serif" font-size="13" fill="#222">{row["category"]}</text>')
        # primary bar
        parts.append(f'<rect x="{left_padding}" y="{y-8}" width="{p_w:.2f}" height="14" rx="6" fill="#3A9AD9"/>')
        parts.append(f'<text x="{left_padding + p_w + 10}" y="{y+2}" font-family="Arial, sans-serif" font-size="12" fill="#222">{"₹{:.2f}".format(p) if p>0 else "-"}</text>')
        # compare bar
        parts.append(f'<rect x="{left_padding}" y="{y+12}" width="{c_w:.2f}" height="14" rx="6" fill="#FF6B78"/>')
        parts.append(f'<text x="{left_padding + c_w + 10}" y="{y+22}" font-family="Arial, sans-serif" font-size="12" fill="#222">{"₹{:.2f}".format(c) if c>0 else "-"}</text>')
        y += row_h

    # bars axis (min/max)
    parts.append(f'<g transform="translate({left_padding}, {vg_height - 22})" font-family="Arial, sans-serif" font-size="12" fill="#444">')
    parts.append(f'<text x="0" y="12">0</text>')
    parts.append(f'<text x="{bar_max_width}" y="12" text-anchor="end">₹{max_bar_value:.2f}</text>')
    parts.append('</g>')

    # PIE charts (place on right side)
    pie_left = left_padding + bar_max_width + 40
    # primary pie
    parts.append(f'<g transform="translate({pie_left}, 40)">')
    parts.append(f'<text x="0" y="0" font-family="Arial, sans-serif" font-size="13" fill="#222">{calendar.month_name[month]} {year} (Total ₹{primary_total:.2f})</text>')
    parts.append(f'<svg x="0" y="12" viewBox="0 0 240 240" width="240" height="240" xmlns="http://www.w3.org/2000/svg">')
    if primary_pie:
        for s in primary_pie:
            parts.append(f'<path d="{s["d"]}" fill="{s["color"]}" stroke="#fff" stroke-width="1"></path>')
        for s in primary_pie:
            parts.append(f'<text x="{s["label_x"]:.2f}" y="{s["label_y"]:.2f}" font-family="Arial, sans-serif" font-size="10" fill="#111" text-anchor="middle" dominant-baseline="middle">{s["pct"]}%</text>')
    else:
        parts.append('<circle cx="120" cy="120" r="90" fill="#f1f3f5"></circle>')
        parts.append('<text x="120" y="120" text-anchor="middle" dominant-baseline="middle" font-family="Arial, sans-serif" font-size="12" fill="#666">No data</text>')
    parts.append('</svg>')
    parts.append('</g>')

    # compare pie
    pie2_top = 320
    parts.append(f'<g transform="translate({pie_left}, {pie2_top})">')
    parts.append(f'<text x="0" y="0" font-family="Arial, sans-serif" font-size="13" fill="#222">{calendar.month_name[compare_month]} {compare_year} (Total ₹{compare_total:.2f})</text>')
    parts.append(f'<svg x="0" y="12" viewBox="0 0 240 240" width="240" height="240" xmlns="http://www.w3.org/2000/svg">')
    if compare_pie:
        for s in compare_pie:
            parts.append(f'<path d="{s["d"]}" fill="{s["color"]}" stroke="#fff" stroke-width="1"></path>')
        for s in compare_pie:
            parts.append(f'<text x="{s["label_x"]:.2f}" y="{s["label_y"]:.2f}" font-family="Arial, sans-serif" font-size="10" fill="#111" text-anchor="middle" dominant-baseline="middle">{s["pct"]}%</text>')
    else:
        parts.append('<circle cx="120" cy="120" r="90" fill="#f1f3f5"></circle>')
        parts.append('<text x="120" y="120" text-anchor="middle" dominant-baseline="middle" font-family="Arial, sans-serif" font-size="12" fill="#666">No data</text>')
    parts.append('</svg>')
    parts.append('</g>')

    # Legend for pies (small)
    parts.append(f'<g transform="translate({pie_left}, {vg_height - 80})" font-family="Arial, sans-serif" font-size="12">')
    legend_colors = ['#3A9AD9', '#FF6B78', '#FFD166', '#6BCB77', '#8E63FF', '#FF9F80']
    for i, cat in enumerate(categories):
        col = legend_colors[i % len(legend_colors)]
        parts.append(f'<rect x="{(i*160)}" y="0" width="12" height="10" fill="{col}"></rect>')
        parts.append(f'<text x="{(i*160)+18}" y="9">{cat}</text>')
    parts.append('</g>')

    parts.append('</svg>')
    svg_text = '\n'.join(parts)

    filename = f'comparison_{year}_{month}_vs_{compare_year}_{compare_month}.svg'
    return Response(svg_text, mimetype='image/svg+xml', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

# ------------------ Run ------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
