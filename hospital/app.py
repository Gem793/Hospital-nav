import matplotlib
matplotlib.use("Agg")  

from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
import os
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString
import matplotlib.pyplot as plt
import io
from openai import OpenAI
import tempfile
import re

# Set OpenAI API key
# openai.api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI()

app = Flask(__name__)
CORS(app)

# Configuration
room_type = "Room Type"
room_no = "Room No"

print("Loading GeoJSON files...")
try:
    # Load GeoJSON files - make sure paths are correct
    gdf1 = gpd.read_file("geojsons/Level_1_final_final_final.geojson")
    gdf2 = gpd.read_file("geojsons/Level_2.geojson")
    gdf3 = gpd.read_file("geojsons/Level_3.geojson")
    floor_gdfs = {"Level_1": gdf1, "Level_2": gdf2, "Level_3": gdf3}
    print("GeoJSON files loaded successfully!")
    
    # Print available room types for debugging
    for floor, gdf in floor_gdfs.items():
        print(f"{floor} room types: {gdf[room_type].unique()}")
        
except Exception as e:
    print(f"Error loading GeoJSON files: {e}")
    # Create dummy data for testing if files can't be loaded
    floor_gdfs = {"Level_1": None, "Level_2": None, "Level_3": None}

def build_floor_graph(gdf):
    """Build graph from corridor geometries"""
    if gdf is None:
        return nx.Graph()
        
    try:
        corridors = gdf[gdf[room_type].str.startswith("c", na=False)].boundary
        G = nx.Graph()
        for geom in corridors:
            if geom.is_empty:
                continue
            lines = [geom] if geom.geom_type == "LineString" else geom.geoms
            for part in lines:
                coords = list(part.coords)
                for i in range(len(coords)-1):
                    p1, p2 = Point(coords[i]), Point(coords[i+1])
                    G.add_edge((p1.x, p1.y), (p2.x, p2.y), weight=p1.distance(p2))
        return G
    except Exception as e:
        print(f"Error building graph: {e}")
        return nx.Graph()

def connect_to_corridor(point, G):
    """Find nearest corridor node to a point"""
    nearest, min_dist = None, float("inf")
    for node in G.nodes:
        d = point.distance(Point(node))
        if d < min_dist:
            min_dist, nearest = d, node
    return nearest

def add_stairs(G, gdf):
    """Add stair connections to graph"""
    if gdf is None:
        return []
        
    try:
        stairs = gdf[gdf[room_type].str.contains("stair", case=False, na=False)]
        stair_nodes = []
        for _, row in stairs.iterrows():
            centroid = row.geometry.centroid
            nearest_node = connect_to_corridor(centroid, G)
            if nearest_node:
                G.add_edge((centroid.x, centroid.y), nearest_node, weight=0.5)
            stair_nodes.append((centroid.x, centroid.y))
        return stair_nodes
    except Exception as e:
        print(f"Error adding stairs: {e}")
        return []

# Build floor graphs
print("Building floor graphs...")
try:
    G1 = build_floor_graph(gdf1)
    G2 = build_floor_graph(gdf2)
    G3 = build_floor_graph(gdf3)
    
    stairs1 = add_stairs(G1, gdf1)
    stairs2 = add_stairs(G2, gdf2)
    stairs3 = add_stairs(G3, gdf3)
    
    floor_graphs = {"Level_1": G1, "Level_2": G2, "Level_3": G3}
    floor_stairs = {"Level_1": stairs1, "Level_2": stairs2, "Level_3": stairs3}

    # Merge all floors
    G_all = nx.Graph()
    for floor, G in floor_graphs.items():
        for node in G.nodes:
            G_all.add_node((floor, node))
        for u, v, data in G.edges(data=True):
            G_all.add_edge((floor, u), (floor, v), weight=data["weight"])

    # Connect stairs between floors
    for s1, s2 in zip(stairs1, stairs2):
        G_all.add_edge(("Level_1", s1), ("Level_2", s2), weight=1.0)
    for s2, s3 in zip(stairs2, stairs3):
        G_all.add_edge(("Level_2", s2), ("Level_3", s3), weight=1.0)
        
    print("Floor graphs built successfully!")
    
except Exception as e:
    print(f"Error building floor graphs: {e}")
    # Create empty graphs for fallback
    floor_graphs = {"Level_1": nx.Graph(), "Level_2": nx.Graph(), "Level_3": nx.Graph()}
    floor_stairs = {"Level_1": [], "Level_2": [], "Level_3": []}
    G_all = nx.Graph()

def find_node(room_name):
    """Find room node in the graph"""
    for floor, gdf in floor_gdfs.items():
        if gdf is None:
            continue
        try:
            rooms = gdf[~gdf[room_type].str.startswith("c", na=False)]
            # Try to match by room type or room number
            geom = rooms[(rooms[room_type] == room_name) | (rooms[room_no] == room_name)].geometry
            if not geom.empty:
                centroid = geom.iloc[0].centroid
                node = connect_to_corridor(centroid, floor_graphs[floor])
                return (floor, node), centroid
        except Exception as e:
            print(f"Error finding node for {room_name} on {floor}: {e}")
            continue
    return None, None

def parse_rooms_from_text(text):
    """Parse room names from transcribed text"""
    text = text.lower().strip()
    print(f"Parsing rooms from: '{text}'")
    
    # Common patterns
    patterns = [
        r'from\s+([^\s]+)\s+to\s+([^\s]+)',
        r'([^\s]+)\s+to\s+([^\s]+)',
        r'room\s+(\w+)\s+to\s+room\s+(\w+)',
        r'(\w+)\s+(\w+)$'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            start, end = match.group(1).strip(), match.group(2).strip()
            print(f"Matched pattern: start='{start}', end='{end}'")
            return start, end
    
    # Fallback: take first two words
    words = text.split()
    if len(words) >= 2:
        return words[0], words[1]
    
    return None, None

@app.route("/")
def home():
    """Serve the main page"""
    return render_template("index.html")

@app.route("/get_path", methods=["POST"])
def get_path():
    """Find path between two rooms"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        start_room = data.get("start", "").strip()
        end_room = data.get("end", "").strip()
        
        if not start_room or not end_room:
            return jsonify({"error": "Both start and end rooms are required"}), 400

        print(f"Finding path from '{start_room}' to '{end_room}'")
        
        start_node, start_centroid = find_node(start_room)
        end_node, end_centroid = find_node(end_room)
        
        if start_node is None:
            return jsonify({"error": f"Start room '{start_room}' not found"}), 400
        if end_node is None:
            return jsonify({"error": f"End room '{end_room}' not found"}), 400

        # Find shortest path
        path_nodes = nx.shortest_path(G_all, source=start_node, target=end_node, weight="weight")

        # Split path by floor
        floor_paths = {}
        current_floor = path_nodes[0][0]
        floor_paths[current_floor] = [path_nodes[0][1]]
        for f, node in path_nodes[1:]:
            if f != current_floor:
                current_floor = f
                floor_paths[current_floor] = []
            floor_paths[current_floor].append(node)

        # Generate visualization
        fig, axes = plt.subplots(len(floor_paths), 1, figsize=(10, 8 * len(floor_paths)))
        if len(floor_paths) == 1:
            axes = [axes]

        for ax, (floor, nodes) in zip(axes, floor_paths.items()):
            gdf_floor = floor_gdfs[floor]
            if gdf_floor is not None:
                gdf_floor.plot(ax=ax, color="lightgrey", edgecolor="black")

            # Draw path
            for i in range(len(nodes)-1):
                line = LineString([nodes[i], nodes[i+1]])
                ax.plot(*line.xy, color="red", linewidth=3)

            # Mark stairs
            for sx, sy in floor_stairs[floor]:
                ax.scatter(sx, sy, color="orange", s=100, edgecolor="black", zorder=5)

            # Mark start and end
            if floor == start_node[0]:
                ax.scatter(start_centroid.x, start_centroid.y, color="green", s=150, zorder=5, label="Start")
            if floor == end_node[0]:
                ax.scatter(end_centroid.x, end_centroid.y, color="blue", s=150, zorder=5, label="End")

            ax.set_title(f"Path on {floor}: {start_room} → {end_room}")
            ax.legend()

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return send_file(buf, mimetype="image/png")

    except Exception as e:
        print(f"Error in get_path: {e}")
        return jsonify({"error": f"Path finding error: {str(e)}"}), 500

@app.route("/voice_path", methods=["POST"])
def voice_path():
    """Handle voice-based path finding"""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file received"}), 400

    audio_file = request.files["audio"]

    try:
        # Transcribe audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
            audio_file.save(temp_audio.name)
            
            with open(temp_audio.name, 'rb') as audio:
                transcript = openai.Audio.transcribe(
                    model="whisper-1",
                    file=audio,
                    response_format="text"
                )
            
            os.unlink(temp_audio.name)

        text = transcript.strip()
        print(f"Voice transcription: '{text}'")

        # Parse rooms from text
        start_room, end_room = parse_rooms_from_text(text)
        
        if not start_room or not end_room:
            return jsonify({"error": f"Could not understand: '{text}'. Try 'Room 101 to Room 305'"}), 400

        # Use the same logic as get_path
        start_node, start_centroid = find_node(start_room)
        end_node, end_centroid = find_node(end_room)
        
        if start_node is None:
            return jsonify({"error": f"Start room '{start_room}' not found"}), 400
        if end_node is None:
            return jsonify({"error": f"End room '{end_room}' not found"}), 400

        path_nodes = nx.shortest_path(G_all, source=start_node, target=end_node, weight="weight")

        # Generate visualization (same as get_path)
        floor_paths = {}
        current_floor = path_nodes[0][0]
        floor_paths[current_floor] = [path_nodes[0][1]]
        for f, node in path_nodes[1:]:
            if f != current_floor:
                current_floor = f
                floor_paths[current_floor] = []
            floor_paths[current_floor].append(node)

        fig, axes = plt.subplots(len(floor_paths), 1, figsize=(10, 8 * len(floor_paths)))
        if len(floor_paths) == 1:
            axes = [axes]

        for ax, (floor, nodes) in zip(axes, floor_paths.items()):
            gdf_floor = floor_gdfs[floor]
            if gdf_floor is not None:
                gdf_floor.plot(ax=ax, color="lightgrey", edgecolor="black")

            for i in range(len(nodes)-1):
                line = LineString([nodes[i], nodes[i+1]])
                ax.plot(*line.xy, color="red", linewidth=3)

            for sx, sy in floor_stairs[floor]:
                ax.scatter(sx, sy, color="orange", s=100, edgecolor="black", zorder=5)

            if floor == start_node[0]:
                ax.scatter(start_centroid.x, start_centroid.y, color="green", s=150, zorder=5, label="Start")
            if floor == end_node[0]:
                ax.scatter(end_centroid.x, end_centroid.y, color="blue", s=150, zorder=5, label="End")

            ax.set_title(f"Voice Path on {floor}: {start_room} → {end_room}")
            ax.legend()

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return send_file(buf, mimetype="image/png")

    except Exception as e:
        print(f"Error in voice_path: {e}")
        return jsonify({"error": f"Voice processing error: {str(e)}"}), 500

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    print("=" * 50)
    print("🚀 Hospital Navigator Server Starting...")
    print("📁 GeoJSON files loaded successfully!")
    print("🗺  Floor graphs built successfully!")
    print("🌐 Server is running at: http://127.0.0.1:5000")
    print("👉 Open this URL in your web browser!")
    print("=" * 50)
    
    app.run(debug=True, host='127.0.0.1', port=5000)