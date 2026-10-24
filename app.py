from flask import Flask, render_template_string

app = Flask(__name__)

MENU = {
    "Coffee": [
        {"name": "Espresso", "price": 90},
        {"name": "Americano", "price": 100},
        {"name": "Caffe Latte", "price": 130},
        {"name": "Iced Caramel Macchiato", "price": 150},
    ],
    "Brownies": [
        {"name": "Classic Fudge Brownie", "price": 85},
        {"name": "Walnut Brownie", "price": 95},
    ],
    "Cookies": [
        {"name": "Chocolate Chip Cookie", "price": 65},
        {"name": "Oatmeal Raisin Cookie", "price": 65},
    ],
    "Pasta": [
        {"name": "Creamy Carbonara", "price": 180},
        {"name": "Spaghetti Bolognese", "price": 170},
        {"name": "Aglio e Olio", "price": 160},
        {"name": "Pesto Pasta", "price": 149},
        {"name": "Carbonara", "price": 149}
    ],
}

PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Our Menu</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: auto; padding: 16px; background: #faf6f1; }
    h1 { text-align: center; color: #4b2e1e; }
    h2 { color: #6f4e37; border-bottom: 2px solid #d9c3ad; padding-bottom: 4px; }
    .item { display: flex; justify-content: space-between; padding: 6px 0; }
  </style>
</head>
<body>
  <h1>☕ Our Menu</h1>
  {% for category, items in menu.items() %}
    <h2>{{ category }}</h2>
    {% for item in items %}
      <div class="item"><span>{{ item.name }}</span><span>₱{{ item.price }}</span></div>
    {% endfor %}
  {% endfor %}
</body>
</html>
"""

@app.route("/")
def menu():
    return render_template_string(PAGE, menu=MENU)

if __name__ == "__main__":
    app.run(debug=True)