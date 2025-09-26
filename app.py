# backend/app.py

import json
import os
from flask import Flask, request, jsonify, send_file
import networkx as nx
import matplotlib.pyplot as plt
from flask import Flask, send_from_directory

# existing imports and code...

@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)


# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_PATH = os.path.join(BASE_DIR, "level_1_final_final_final.geojson")
GRAPH_IMAGE_PATH = os.path.join(BASE_DIR, "graph_image.png")

# Flask app
app = Flask(__name__)

# ----------------- Graph functions ----------------- #
def load_graph_from_geojson(geojson_path):
    """Load graph nodes and edges from GeoJSON"""
    with open(geojson_path) as f:
        data = json.load(f)

    G = nx.Graph()

    for feature in data['features']:
        # Extract node properties safely
        node_id = feature['properties'].get('id', None)
        if node_id is None:
            continue

        # Coordinates (ensure 2D tuple)
        coords = feature['geometry']['coordinates']
        if isinstance(coords[0], list):
            # if it's LineString or Polygon, pick first coordinate
            coords = coords[0]
        x, y = float(coords[0]), float(coords[1])

        G.add_node(node_id, x=x, y=y, **feature['properties'])

        # Optional: add edges if you have them in properties
        # Example: connect to neighbors if listed
        neighbors = feature['properties'].get('neighbors', [])
        for n in neighbors:
            G.add_edge(node_id, n)

    return G

def generate_graph_image(graph, output_path):
    """Generate and save graph image for frontend"""
    pos = {node: (data['x'], data['y']) for node, data in graph.nodes(data=True)}

    plt.figure(figsize=(12, 8))
    nx.draw(
        graph,
        pos,
        with_labels=True,
        node_size=600,
        node_color="#0073e6",
        font_color="white",
        edge_color="#888888"
    )
    plt.savefig(output_path)
    plt.close()

# ----------------- Initialize graph ----------------- #
graph = load_graph_from_geojson(GEOJSON_PATH)
generate_graph_image(graph, GRAPH_IMAGE_PATH)

# ----------------- Flask routes ----------------- #
@app.route("/graph-image")
def serve_graph_image():
    """Serve the graph image to frontend"""
    return send_file(GRAPH_IMAGE_PATH, mimetype='image/png')


@app.route("/shortest-path", methods=["POST"])
def shortest_path():
    """Return shortest path between two nodes"""
    data = request.json
    start = data.get("start")
    end = data.get("end")

    if not start or not end:
        return jsonify({"error": "Please provide start and end node IDs"}), 400

    try:
        path = nx.shortest_path(graph, source=start, target=end)
        return jsonify({"path": path})
    except nx.NetworkXNoPath:
        return jsonify({"error": f"No path found between {start} and {end}"}), 404
    except nx.NodeNotFound as e:
        return jsonify({"error": str(e)}), 404

# ----------------- Run Flask ----------------- #
if __name__ == "__main__":
    app.run(debug=True)
