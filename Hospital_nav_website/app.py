import matplotlib
matplotlib.use("Agg")  

from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString
import matplotlib.pyplot as plt
import io

app = Flask(__name__)
CORS(app)

room_type="Room Type"
room_no="Room No"

gdf1=gpd.read_file("geojsons/Level_1.geojson")
gdf2=gpd.read_file("geojsons/Level_2.geojson")
gdf3=gpd.read_file("geojsons/Level_3.geojson")
floor_gdfs={"Level_1": gdf1, "Level_2": gdf2, "Level_3": gdf3}

def build_floor_graph(gdf):
    corridors=gdf[gdf[room_type].str.startswith("c", na=False)].boundary
    G=nx.Graph()
    for geom in corridors:
        if geom.is_empty:
            continue

        elif geom.geom_type == "LineString":
            lines = [geom]
        else:
            lines = geom.geoms

        for part in lines:
            coords=list(part.coords)
            for i in range(len(coords)-1):
                p1,p2=Point(coords[i]), Point(coords[i+1])
                G.add_edge((p1.x, p1.y),(p2.x, p2.y),weight=p1.distance(p2))
    return G

def connect_to_corridor(point,G):
    nearest=None
    min_dist=float("inf")
    for node in G.nodes:
        d=point.distance(Point(node))
        if d<min_dist:
            min_dist=d
            nearest=node
    return nearest

def add_stairs(G, gdf):
    stairs = gdf[gdf[room_type].str.contains("stair", case=False)]
    stair_nodes = []
    for _, row in stairs.iterrows():
        centroid = row.geometry.centroid
        nearest_node = connect_to_corridor(centroid, G)
        if nearest_node:
            G.add_edge((centroid.x, centroid.y), nearest_node, weight=0.5)
        stair_nodes.append((centroid.x, centroid.y))
    return stair_nodes

G1 = build_floor_graph(gdf1)
G2 = build_floor_graph(gdf2)
G3 = build_floor_graph(gdf3)
stairs1 = add_stairs(G1, gdf1)
stairs2 = add_stairs(G2, gdf2)
stairs3 = add_stairs(G3, gdf3)
floor_graphs = {"Level_1": G1, "Level_2": G2, "Level_3": G3}
floor_stairs = {"Level_1": stairs1, "Level_2": stairs2, "Level_3": stairs3}

G_all = nx.Graph()
for floor, G in floor_graphs.items():
    for node in G.nodes:
        G_all.add_node((floor, node))
    for u, v, data in G.edges(data=True):
        G_all.add_edge((floor, u), (floor, v), weight=data["weight"])

for s1, s2 in zip(stairs1, stairs2):
    G_all.add_edge(("Level_1", s1), ("Level_2", s2), weight=1.0)
for s2, s3 in zip(stairs2, stairs3):
    G_all.add_edge(("Level_2", s2), ("Level_3", s3), weight=1.0)

# ---------- Helper ----------
def find_node(room_name):
    for floor, gdf in floor_gdfs.items():
        rooms = gdf[~gdf[room_type].str.startswith("c", na=False)]
        geom = rooms[(rooms[room_type] == room_name) | (rooms[room_no] == room_name)].geometry
        if not geom.empty:
            centroid = geom.iloc[0].centroid
            node = connect_to_corridor(centroid, floor_graphs[floor])
            return (floor, node), centroid
    return None, None

@app.route("/get_path", methods=["POST"])
def get_path():
    data = request.json
    start_room = data.get("start")
    end_room = data.get("end")

    start_node, start_centroid = find_node(start_room)
    end_node, end_centroid = find_node(end_room)
    if start_node is None or end_node is None:
        return jsonify({"error": "Start or end room not found"}), 400

    # ---------- Compute path ----------
    path_nodes = nx.astar_path(G_all, source=start_node, target=end_node, weight="weight")

    # Split path per floor
    floor_paths = {}
    current_floor = path_nodes[0][0]
    floor_paths[current_floor] = [path_nodes[0][1]]
    for f, node in path_nodes[1:]:
        if f != current_floor:
            current_floor = f
            floor_paths[current_floor] = []
        floor_paths[current_floor].append(node)

    # ---------- Generate image ----------
    fig, axes = plt.subplots(len(floor_paths), 1, figsize=(12,12*len(floor_paths)))
    if len(floor_paths) == 1:
        axes = [axes]

    for ax, (floor, nodes) in zip(axes, floor_paths.items()):
        gdf_floor = floor_gdfs[floor]
        gdf_floor.plot(ax=ax, color="lightgrey", edgecolor="black")

        # Plot path
        for i in range(len(nodes) - 1):
            line = LineString([nodes[i], nodes[i + 1]])
            ax.plot(*line.xy, color="red", linewidth=2, linestyle="--")

        # Plot stairs
        for sx, sy in floor_stairs[floor]:
            ax.scatter(sx, sy, color="yellow", edgecolor="black", s=80)

        # Start/end points
        if floor == start_node[0]:
            ax.scatter(start_centroid.x, start_centroid.y, color="green", s=100)
        if floor == end_node[0]:
            ax.scatter(end_centroid.x, end_centroid.y, color="blue", s=100)

        # Annotate room names
        rooms = gdf_floor[~gdf_floor[room_type].str.startswith("c", na=False)]
        for _, row in rooms.iterrows():
            centroid = row.geometry.centroid
            ax.text(
                centroid.x,
                centroid.y,
                f"{row[room_no]}\n{row[room_type]}",
                fontsize=8,
                ha="center",
                va="center",
                color="black"
            )
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return send_file(buf, mimetype="image/png")
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)







