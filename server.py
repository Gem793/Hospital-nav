# server.py

from flask import Flask, request, send_from_directory, jsonify
import geopandas as gpd
import os

app = Flask(__name__)

@app.route('/path_image', methods=['POST'])
def path_image():
    data = request.get_json()
    start = data.get('start')
    end = data.get('end')

    if not start or not end:
        return jsonify({"error": "Start or end room missing"}), 400

    # For now, return a placeholder image or URL
    # Replace this later with your actual path generation logic
    dummy_path_url = "/static/dummy_path.png"  # Make sure this image exists
    return jsonify({"path_image": dummy_path_url})

if __name__ == '__main__':
    app.run(debug=True)
