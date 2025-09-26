import json
import os
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point
import io

# Initialize Flask app
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, '../frontend'))
GEOJSON_PATH = os.path.join(BASE_DIR, "level_1_final_final_final.geojson")

# Store graph and room data
graph = None
room_data = []  # Store room information by room number
room_types = set()  # Track all room types
floors_data = {}  # Store data by floor level
floor_graphs = {}  # Dictionary to hold graphs for each floor

# ----------------- Graph functions ----------------- #
def load_graph_from_geojson(geojson_path):
    """Load graph nodes and edges from GeoJSON with proper attribute handling"""
    global room_data, room_types, floors_data, floor_graphs
    
    if not os.path.exists(geojson_path):
        print(f"Error: GeoJSON file not found: {geojson_path}")
        return None
        
    try:
        gdf = gpd.read_file(geojson_path)
        # Assume columns: "Room Type", "Room No", "geometry"
        room_data = []
        room_types.clear()
        floors_data.clear()
        floor_graphs.clear()
        
        for level in gdf['level'].unique():
            floor_gdf = gdf[gdf['level'] == level]
            G = nx.Graph()
            
            for idx, row in floor_gdf.iterrows():
                props = row
                room_type = props.get("Room Type", "")
                room_no = props.get("Room No", "")
                geometry = props.geometry
                # You may need to add a "level" property to your geojson or infer it
                level = props.get("level", "1")
                room_types.add(room_type)
                room_data.append({
                    "room_type": room_type,
                    "room_no": room_no,
                    "geometry": geometry,
                    "level": level,
                    "node_id": idx
                })
                # Build graph: connect centroids of rooms (simplified)
                if geometry is not None and not geometry.is_empty:
                    centroid = geometry.centroid
                    G.add_node((centroid.x, centroid.y), 
                               room_no=room_no, 
                               room_type=room_type, 
                               level=level,
                               x=centroid.x,
                               y=centroid.y)
                    # Optionally, connect to previous node (for demo)
                    if idx > 0:
                        prev = floor_gdf.iloc[idx-1].geometry.centroid
                        G.add_edge((centroid.x, centroid.y), (prev.x, prev.y), weight=centroid.distance(prev))
                # Organize by floor
                if level not in floors_data:
                    floors_data[level] = []
                floors_data[level].append(room_no)
            
            floor_graphs[str(level)] = G  # Store the graph for this floor
        
        print(f"✓ Graph loaded successfully: {len(G.nodes())} nodes, {len(G.edges())} edges")
        print(f"✓ Room types found: {len(room_types)} types")
        print(f"✓ Floors loaded: {list(floors_data.keys())}")
        
        # Print room types for verification
        print("Available room types:")
        for room_type in sorted(room_types):
            print(f"  - {room_type}")
            
        return G
        
    except Exception as e:
        print(f"Error loading graph: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_graph_image(graph, level="1"):
    """Generate graph image with room labels"""
    try:
        plt.figure(figsize=(15, 12))
        
        if graph is None or len(graph.nodes()) == 0:
            plt.text(0.5, 0.5, f"Level {level}\nNo graph data available", 
                    ha='center', va='center', fontsize=16)
            plt.axis('off')
        else:
            # Filter nodes for the current level
            level_nodes = [node for node in graph.nodes() if graph.nodes[node].get('level') == level]
            
            if not level_nodes:
                plt.text(0.5, 0.5, f"Level {level}\nNo data for this level", 
                        ha='center', va='center', fontsize=16)
                plt.axis('off')
            else:
                # Create subgraph for this level
                level_graph = graph.subgraph(level_nodes)
                pos = {node: (graph.nodes[node].get('x', 0), graph.nodes[node].get('y', 0)) 
                       for node in level_nodes}
                
                # Color nodes by room type
                node_colors = []
                color_map = {
                    'corridor': 'lightgray',
                    'Elevators': 'yellow',
                    'Staircase': 'orange',
                    'Washroom': 'lightblue',
                    'Emergency Exit': 'red',
                    'Surgery': 'pink',
                    'Emergency': 'red',
                    'MRI': 'purple',
                    'Radiology': 'lightgreen',
                    'ICU': 'lightcoral',
                    'default': 'lightblue'
                }
                
                for node in level_nodes:
                    room_type = graph.nodes[node].get('room_type', 'Unknown')
                    color = color_map.get(room_type, color_map.get('default'))
                    node_colors.append(color)
                
                # Draw the graph
                nx.draw_networkx_nodes(level_graph, pos, node_size=300, 
                                     node_color=node_colors, alpha=0.8)
                nx.draw_networkx_edges(level_graph, pos, edge_color='gray', alpha=0.6)
                
                # Add labels with room numbers
                labels = {}
                for node in level_nodes:
                    room_no = graph.nodes[node].get('room_no', '')
                    room_type = graph.nodes[node].get('room_type', '')
                    if room_no and room_no != 'NULL':
                        labels[node] = f"{room_no}\n({room_type[:10]}...)" if len(room_type) > 10 else f"{room_no}\n{room_type}"
                    else:
                        labels[node] = room_type[:15] + '...' if len(room_type) > 15 else room_type
                
                nx.draw_networkx_labels(level_graph, pos, labels, font_size=6)
                
                plt.title(f"Hospital Map - Level {level}\n(Color-coded by Room Type)", fontsize=14)
                plt.axis('on')
                plt.grid(True, alpha=0.3)
                
                # Add legend
                from matplotlib.patches import Patch
                legend_elements = []
                for room_type, color in color_map.items():
                    if room_type != 'default':
                        legend_elements.append(Patch(color=color, label=room_type))
                
                plt.legend(handles=legend_elements, loc='upper right', fontsize=8)
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
        
    except Exception as e:
        print(f"Error generating graph image: {e}")
        plt.figure(figsize=(10, 8))
        plt.text(0.5, 0.5, f"Error generating map\n{str(e)}", 
                ha='center', va='center', fontsize=12)
        plt.axis('off')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close()
        return buf

# ----------------- Flask routes ----------------- #
@app.route('/')
def serve_frontend():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)

@app.route("/graph-image/<level>")
def serve_graph_image(level):
    """Serve the graph image for a specific level"""
    try:
        image_buffer = generate_graph_image(graph, level)
        return send_file(image_buffer, mimetype='image/png')
    except Exception as e:
        return jsonify({"error": f"Failed to generate image: {str(e)}"}), 500

@app.route("/api/rooms")
def get_all_rooms():
    """Get all rooms with their attributes"""
    if graph is None:
        return jsonify({"error": "Graph not loaded"}), 500
    
    rooms = []
    for node_id, data in graph.nodes(data=True):
        rooms.append({
            'node_id': node_id,
            'room_no': data.get('room_no', ''),
            'room_type': data.get('room_type', 'Unknown'),
            'level': data.get('level', '1'),
            'x': data.get('x', 0),
            'y': data.get('y', 0)
        })
    
    return jsonify({"rooms": rooms})

@app.route("/api/rooms/<level>")
def get_rooms_by_level(level):
    """Get rooms for a specific level"""
    if graph is None:
        return jsonify({"error": "Graph not loaded"}), 500
    
    rooms = []
    for node_id, data in graph.nodes(data=True):
        if data.get('level') == level:
            rooms.append({
                'node_id': node_id,
                'room_no': data.get('room_no', ''),
                'room_type': data.get('room_type', 'Unknown'),
                'x': data.get('x', 0),
                'y': data.get('y', 0)
            })
    
    return jsonify({"level": level, "rooms": rooms})

@app.route("/api/room-types")
def get_room_types():
    """Get all available room types"""
    return jsonify({"room_types": sorted(list(room_types))})

@app.route("/api/room-types/<room_type>")
def get_rooms_by_type(room_type):
    """Get all rooms of a specific type"""
    if graph is None:
        return jsonify({"error": "Graph not loaded"}), 500
    
    rooms = []
    for node_id, data in graph.nodes(data=True):
        if data.get('room_type', '').lower() == room_type.lower():
            rooms.append({
                'node_id': node_id,
                'room_no': data.get('room_no', ''),
                'room_type': data.get('room_type', 'Unknown'),
                'level': data.get('level', '1'),
                'x': data.get('x', 0),
                'y': data.get('y', 0)
            })
    
    return jsonify({"room_type": room_type, "rooms": rooms})

@app.route("/api/search-rooms")
def search_rooms():
    """Search rooms by number, type, or other criteria"""
    if graph is None:
        return jsonify({"error": "Graph not loaded"}), 500
    
    query = request.args.get('q', '').lower()
    room_type = request.args.get('type', '').lower()
    level = request.args.get('level', '')
    
    results = []
    for node_id, data in graph.nodes(data=True):
        # Filter by level if specified
        if level and data.get('level') != level:
            continue
            
        # Filter by room type if specified
        if room_type and data.get('room_type', '').lower() != room_type:
            continue
            
        # Search in room number and room type
        room_no = data.get('room_no', '').lower()
        r_type = data.get('room_type', '').lower()
        
        if (query in room_no or query in r_type or 
            query in node_id.lower() or not query):
            results.append({
                'node_id': node_id,
                'room_no': data.get('room_no', ''),
                'room_type': data.get('room_type', 'Unknown'),
                'level': data.get('level', '1'),
                'x': data.get('x', 0),
                'y': data.get('y', 0)
            })
    
    return jsonify({"results": results[:50]})  # Limit results

@app.route("/api/floors")
def get_floors():
    """Get available floors and their statistics"""
    floors_info = []
    for level, data in floors_data.items():
        floors_info.append({
            'level': level,
            'room_count': len(data['rooms']),
            'room_types': list(data['room_types']),
            'room_numbers': list(data['room_numbers'])
        })
    
    return jsonify({"floors": floors_info})

@app.route("/shortest-path", methods=["POST"])
def shortest_path():
    """Return shortest path between two rooms"""
    if graph is None:
        return jsonify({"error": "Graph not loaded"}), 500
        
    data = request.json
    start = data.get("start")  # Can be room number or node ID
    end = data.get("end")
    level = data.get("level", "1")

    if not start or not end:
        return jsonify({"error": "Please provide start and end room numbers"}), 400

    try:
        # Find nodes by room number or use directly as node ID
        start_node = None
        end_node = None
        
        # Search for rooms by number
        for node_id, data in graph.nodes(data=True):
            if data.get('room_no') == start or node_id == start:
                start_node = node_id
            if data.get('room_no') == end or node_id == end:
                end_node = node_id
        
        if not start_node:
            return jsonify({"error": f"Start room '{start}' not found"}), 404
        if not end_node:
            return jsonify({"error": f"End room '{end}' not found"}), 404

        path = nx.shortest_path(graph, source=start_node, target=end_node)
        
        # Format path with room information
        formatted_path = []
        for node_id in path:
            node_data = graph.nodes[node_id]
            formatted_path.append({
                'node_id': node_id,
                'room_no': node_data.get('room_no', ''),
                'room_type': node_data.get('room_type', 'Unknown'),
                'level': node_data.get('level', '1'),
                'x': node_data.get('x', 0),
                'y': node_data.get('y', 0)
            })
        
        return jsonify({
            "path": path,
            "formatted_path": formatted_path,
            "distance": len(path) - 1,
            "start_room": graph.nodes[start_node].get('room_no', ''),
            "end_room": graph.nodes[end_node].get('room_no', '')
        })
        
    except nx.NetworkXNoPath:
        return jsonify({"error": f"No path found between {start} and {end}"}), 404
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route("/api/health")
def health_check():
    """Health check endpoint"""
    status = "healthy" if graph is not None else "error"
    return jsonify({
        "status": status,
        "graph_loaded": graph is not None,
        "total_rooms": len(graph.nodes()) if graph else 0,
        "room_types_count": len(room_types),
        "floors_loaded": list(floors_data.keys()) if graph else []
    })

# Initialize the graph when the app starts
print("=" * 60)
print("Initializing Hospital Navigation System...")
print("=" * 60)

graph = load_graph_from_geojson(GEOJSON_PATH)

if graph:
    print("✓ System initialized successfully!")
    print(f"✓ Total rooms: {len(graph.nodes())}")
    print(f"✓ Room types: {len(room_types)}")
    print(f"✓ Floors: {list(floors_data.keys())}")
else:
    print("✗ Failed to initialize system!")

print("Starting Flask server on http://localhost:5000")
print("=" * 60)

if __name__ == "__main__":
    app.run(debug=True, port=5000)