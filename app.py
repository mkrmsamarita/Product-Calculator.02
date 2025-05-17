from flask import Flask, render_template, request, send_file, session, jsonify
import math
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
import json
import io
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle, Frame
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = "your_secret_key"

UNIT_CONVERSION = {
    "kg": {"g": 1000, "kg": 1, "l": 1, "ml": 1000, "pcs": 1},
    "g": {"g": 1, "kg": 0.001, "l": 0.001, "ml": 1, "pcs": 1},
    "l": {"l": 1, "ml": 1000, "kg": 1, "g": 1000, "pcs": 1},
    "ml": {"ml": 1, "l": 0.001, "kg": 0.001, "g": 1, "pcs": 1},
    "pcs": {"pcs": 1, "kg": 1, "g": 1, "l": 1, "ml": 1}
}

SAVED_INGREDIENTS_FILE = "saved_ingredients.json"


def convert_unit(value, from_unit, to_unit):
    if from_unit in UNIT_CONVERSION and to_unit in UNIT_CONVERSION[from_unit]:
        return value * UNIT_CONVERSION[from_unit][to_unit]
    else:
        return None


def load_saved_ingredients():
    try:
        with open(SAVED_INGREDIENTS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_ingredients_list(name, ingredients):
    saved_lists = load_saved_ingredients()
    saved_lists.append({'name': name, 'ingredients': ingredients})
    with open(SAVED_INGREDIENTS_FILE, 'w') as f:
        json.dump(saved_lists, f, indent=4)



def get_ingredients_by_name(name):
    saved_lists = load_saved_ingredients()
    for item in saved_lists:
        if item['name'] == name:
            return item['ingredients']
    return None

def remove_ingredients_list(name):
    saved_lists = load_saved_ingredients()
    updated_lists = [item for item in saved_lists if item['name'] != name]
    with open(SAVED_INGREDIENTS_FILE, 'w') as f:
        json.dump(updated_lists, f, indent=4)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            product_name = request.form["product_name"].strip()
            selling_price = float(request.form["selling_price"])
            fixed_cost = float(request.form["fixed_cost"])

            ingredients = []
            names = request.form.getlist("name")
            available_qtys = request.form.getlist("available_qty")
            cost_per_units = request.form.getlist("cost_per_unit")
            required_per_units = request.form.getlist("required_per_unit")
            available_units = request.form.getlist("available_unit")
            required_units = request.form.getlist("required_unit")

            for i in range(len(names)):
                name = names[i].strip()
                available_qty = float(available_qtys[i])
                cost_per_unit = float(cost_per_units[i])
                required_per_unit = float(required_per_units[i])
                available_unit = available_units[i].strip()
                required_unit = required_units[i].strip()

                converted_available_qty = available_qty
                if available_unit != required_unit:
                    converted_qty = convert_unit(available_qty, available_unit, required_unit)
                    if converted_qty is None:
                        return "Error: Incompatible units provided."
                ingredients.append({
                    "name": name,
                    "available_qty": available_qty,
                    "cost_per_unit": cost_per_unit,
                    "required_per_unit": required_per_unit,
                    "required_unit": required_unit,
                    "available_unit": available_unit,
                })

            max_units = min(
                (ing["available_qty"] // ing["required_per_unit"] if ing["required_per_unit"] > 0 else float("inf"))
                for ing in ingredients
            )
            max_units = int(max_units)

            ingredient_summaries = []
            raw_total = 0

            for ing in ingredients:
                converted_required_per_unit = ing["required_per_unit"]
                if ing["required_unit"] != ing["available_unit"]:
                    converted_required_per_unit = convert_unit(ing["required_per_unit"], ing["required_unit"],
                                                                                    ing["available_unit"])
                    if converted_required_per_unit is None:
                        return "Error: Incompatible units provided."
                total_used = converted_required_per_unit * max_units
                remaining_qty = ing["available_qty"] - total_used
                total_cost = ing["cost_per_unit"] * total_used
                raw_total += total_cost
                ingredient_summaries.append({
                    "name": ing["name"],
                    "required_per_unit": ing["required_per_unit"],
                    "required_unit": ing["required_unit"],
                    "total_used": round(total_used, 2),
                    "total_cost": round(total_cost, 2),
                    "remaining_qty": round(remaining_qty, 2),
                    "available_unit": ing["available_unit"],
                })

            cost_per_unit = raw_total / max_units if max_units else 0
            revenue = max_units * selling_price
            profit = revenue - raw_total
            contribution_margin = selling_price - cost_per_unit
            break_even_units = math.ceil(fixed_cost / contribution_margin) if contribution_margin > 0 else float("inf")

            report_data = {
                'product_name': product_name,
                'max_units': max_units,
                'total_cost': round(raw_total, 2),
                'cost_per_unit': round(cost_per_unit, 2),
                'revenue': round(revenue, 2),
                'profit': round(profit, 2),
                'break_even_units': break_even_units,
                'ingredients': ingredient_summaries,
                'raw_total': round(raw_total, 2),
                'selling_price': selling_price,
                'fixed_cost': fixed_cost
            }
            session['report_data'] = report_data

            return render_template(
                "result.html",
                **report_data
            )
        except ValueError:
            return "Invalid input detected. Please use numeric values only."
        except Exception as e:
            return f"An error occurred: {e}"

    saved_ingredient_lists = load_saved_ingredients()
    return render_template("index.html", saved_lists=saved_ingredient_lists)

@app.route("/export/pdf")
def export_pdf():
    report_data = session.get('report_data')
    if not report_data:
        return "No report data available."

    buffer = BytesIO()
    doc = canvas.Canvas(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = styles['h1']
    title_style.alignment = 1

    normal_style = ParagraphStyle(name='Normal',
                                    fontName='Helvetica',
                                    fontSize=10,
                                    leading=14,
                                    spaceAfter=6)

    title = Paragraph(f"Production Report for {report_data['product_name']}", title_style)
    title.wrapOn(doc, letter[0], letter[1])
    title.drawOn(doc, letter[0] / 2.0 - title.width / 2.0, 750)

    y_position = 730
    doc.setFont("Helvetica-Bold", 12)
    doc.drawString(100, y_position, "Summary Metrics:")
    y_position -= 20
    doc.setFont("Helvetica", 10)
    metrics = [
        ("Max producible units", report_data['max_units']),
        ("Total cost", f"₱{report_data['total_cost']}"),
        ("Cost per unit", f"₱{report_data['cost_per_unit']}"),
        ("Revenue", f"₱{report_data['revenue']}"),
        ("Profit", f"₱{report_data['profit']}"),
        ("Break-even units", report_data['break_even_units'])
    ]
    for label, value in metrics:
        doc.drawString(120, y_position, f"{label}: {value}")
        y_position -= 15

    doc.setFont("Helvetica-Bold", 12)
    doc.drawString(100, y_position - 20, "Ingredient Usage:")
    y_position -= 30

    data = [
        ["Ingredient", "Required/Unit", "Total Used", "Remaining", "Cost"],
    ]
    for ing in report_data['ingredients']:
        data.append([
            ing['name'],
            f"{ing['required_per_unit']} {ing['required_unit']}",
            f"{ing['total_used']} {ing['available_unit']}",
            f"{ing['remaining_qty']} {ing['available_unit']}",
            f"₱{ing['total_cost']}",
        ])

    frame_width = letter[0] - 200
    available_height = letter[1] - y_position - 100
    frame = Frame(100, y_position - 100, frame_width, available_height, showBoundary=0)

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))

    table.wrapOn(doc, frame_width, available_height)
    frame.addFromList([table], doc)

    doc.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{report_data['product_name']}_report.pdf",
                    mimetype='application/pdf')



@app.route('/save_ingredients', methods=['POST'])
def save_ingredients():
    data = request.get_json()
    name = data.get('name')
    ingredients = data.get('ingredients')
    if name and ingredients:
        save_ingredients_list(name, ingredients)
        return jsonify({'message': 'Ingredients saved successfully!'})
    return jsonify({'error': 'Invalid data'}), 400

@app.route('/get_saved_ingredients')
def get_saved_ingredients():
    saved_lists = load_saved_ingredients()
    return jsonify(saved_lists)

@app.route('/load_ingredients/<name>')
def load_ingredients(name):
    ingredients = get_ingredients_by_name(name)
    if ingredients:
        return jsonify(ingredients)
    return jsonify({'error': 'List not found'}), 404

@app.route('/remove_ingredients/<name>', methods=['DELETE'])
def remove_ingredients(name):
    remove_ingredients_list(name)
    return jsonify({'message': 'List removed successfully!'})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
