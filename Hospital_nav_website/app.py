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

ROOM_TYPE = "Room Type"
floor_gdfs = {
    "Level_1": gpd.read_file("geojsons/Level_1.geojson"),
    "Level_2": gpd.read_file("geojsons/Level_2.geojson"),
    "Level_3": gpd.read_file("geojsons/Level_3.geojson"),
}
def build_floor_graph(gdf):
    corridors = gdf[gdf[ROOM_TYPE].str.startswith("c", na=False)].boundary
    G = nx.Graph()
    for geom in corridors:
        if geom.is_empty:
            continue
        lines = [geom] if geom.geom_type=="LineString" else geom.geoms
        for part in lines:
            coords = list(part.coords)
            for i in range(len(coords)-1):
                p1, p2 = Point(coords[i]), Point(coords[i+1])
                G.add_edge((p1.x,p1.y),(p2.x,p2.y),weight=p1.distance(p2))
    return G

def connect_to_corridor(point, G):
    nearest, min_dist = None, float("inf")
    for node in G.nodes:
        d = point.distance(Point(node))
        if d < min_dist:
            min_dist = d
            nearest = node
    return nearest

def add_stairs(G, gdf):
    stairs = gdf[gdf[ROOM_TYPE].str.contains("stair", case=False)]
    stair_nodes = []
    for _, row in stairs.iterrows():
        centroid = row.geometry.centroid
        nearest_node = connect_to_corridor(centroid, G)
        if nearest_node:
            G.add_edge((centroid.x,centroid.y), nearest_node, weight=0.5)
        stair_nodes.append((centroid.x, centroid.y))
    return stair_nodes
floor_graphs = {}
floor_stairs = {}
for floor, gdf in floor_gdfs.items():
    G = build_floor_graph(gdf)
    floor_graphs[floor] = G
    floor_stairs[floor] = add_stairs(G, gdf)

# Merge floors
G_all = nx.Graph()
for floor,G in floor_graphs.items():
    for node in G.nodes:
        G_all.add_node((floor,node))
    for u,v,data in G.edges(data=True):
        G_all.add_edge((floor,u),(floor,v),weight=data["weight"])
for s1,s2 in zip(floor_stairs["Level_1"], floor_stairs["Level_2"]):
    G_all.add_edge(("Level_1",s1),("Level_2",s2),weight=1.0)
for s2,s3 in zip(floor_stairs["Level_2"], floor_stairs["Level_3"]):
    G_all.add_edge(("Level_2",s2),("Level_3",s3),weight=1.0)

all_rooms = []
for floor, gdf in floor_gdfs.items():
    rooms = gdf[~gdf[ROOM_TYPE].str.startswith("c", na=False)]
    for _, row in rooms.iterrows():
        centroid = row.geometry.centroid
        all_rooms.append({
            "floor": floor,
            "room_type": row[ROOM_TYPE],
            "coords": (centroid.x, centroid.y)
        })

# ---------- Helper Functions ----------
def find_node_by_type(room_type_input):
    for floor, gdf in floor_gdfs.items():
        rooms = gdf[~gdf[ROOM_TYPE].str.startswith("c", na=False)]
        geom = rooms[rooms[ROOM_TYPE]==room_type_input].geometry
        if not geom.empty:
            centroid = geom.iloc[0].centroid
            node = connect_to_corridor(centroid, floor_graphs[floor])
            return (floor, node), centroid
    return None, None

def find_nearest_exit(start_node):
    exits = [r for r in all_rooms if "emergency exit" in r["room_type"].lower()]
    min_length = float("inf")
    best_exit = None
    best_centroid = None
    for r in exits:
        floor = r["floor"]
        coords = r["coords"]
        exit_node = connect_to_corridor(Point(coords), floor_graphs[floor])
        if exit_node:
            try:
                full_exit_node = (floor, exit_node)
                path = nx.astar_path(G_all, start_node, full_exit_node, weight="weight")
                length = sum(Point(u[1]).distance(Point(v[1])) for u,v in zip(path,path[1:]))
                if length < min_length:
                    min_length = length
                    best_exit = full_exit_node
                    best_centroid = Point(coords)
            except nx.NetworkXNoPath:
                continue
    return best_exit, best_centroid

# ---------- Routes ----------
@app.route("/get_rooms")
def get_rooms():
    return jsonify(sorted(list(set([r["room_type"] for r in all_rooms]))))

@app.route("/get_path", methods=["POST"])
def get_path():
    data = request.json
    start_type = data.get("start")
    end_type = data.get("end")

    start_node, start_centroid = find_node_by_type(start_type)
    if not start_node:
        return jsonify({"error":"Start room type not found"}),400

    if end_type.lower() == "emergency exit":
        end_node, end_centroid = find_nearest_exit(start_node)
        if not end_node:
            return jsonify({"error":"No reachable emergency exit"}),400
    else:
        end_node, end_centroid = find_node_by_type(end_type)
        if not end_node:
            return jsonify({"error":"End room type not found"}),400

    # A* Path
    path_nodes = nx.astar_path(G_all, start_node, end_node, weight="weight")

    # Split path per floor
    floor_paths = {}
    current_floor = path_nodes[0][0]
    floor_paths[current_floor] = [path_nodes[0][1]]
    for f,node in path_nodes[1:]:
        if f != current_floor:
            current_floor = f
            floor_paths[current_floor] = []
        floor_paths[current_floor].append(node)

    # Draw map
    fig, axes = plt.subplots(len(floor_paths),1,figsize=(12,12*len(floor_paths)))
    if len(floor_paths)==1: axes=[axes]
    for ax,(floor,nodes) in zip(axes,floor_paths.items()):
        gdf=floor_gdfs[floor]
        gdf.plot(ax=ax,color="lightgrey",edgecolor="black")
        for i in range(len(nodes)-1):
            line = LineString([nodes[i],nodes[i+1]])
            ax.plot(*line.xy,color="red",linewidth=2,linestyle="--")
        for sx,sy in floor_stairs[floor]:
            ax.scatter(sx,sy,color="yellow",edgecolor="black",s=80)
        if floor==start_node[0]:
            ax.scatter(start_centroid.x,start_centroid.y,color="green",s=100)
        if floor==end_node[0]:
            ax.scatter(end_centroid.x,end_centroid.y,color="blue",s=100)
        rooms = gdf[~gdf[ROOM_TYPE].str.startswith("c", na=False)]
        for _,row in rooms.iterrows():
            c = row.geometry.centroid
            ax.text(c.x,c.y,row[ROOM_TYPE],fontsize=8,ha="center",va="center",color="black")

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf,format="png")
    buf.seek(0)
    plt.close(fig)
    return send_file(buf,mimetype="image/png")

if __name__=="__main__":
    app.run(debug=True,use_reloader=False)










