// frontend/script.js

// Elements
const startInput = document.getElementById("startRoom");
const endInput = document.getElementById("endRoom");
const goBtn = document.getElementById("goBtn");
const mapContainer = document.querySelector(".map-container");
const placeholderText = document.querySelector(".placeholder-text");

// Function to display graph image
function loadGraphImage() {
  const img = document.createElement("img");
  img.src = "http://127.0.0.1:5000/graph-image";
  img.id = "hospital-map";
  img.style.maxWidth = "100%";
  img.style.borderRadius = "12px";
  img.alt = "Hospital Map";

  // Clear previous content and add image
  mapContainer.innerHTML = "";
  mapContainer.appendChild(img);
}

// Function to get shortest path from backend
async function getShortestPath(start, end) {
  try {
    const res = await fetch("http://127.0.0.1:5000/shortest-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start, end }),
    });
    const data = await res.json();
    return data;
  } catch (error) {
    console.error("Error fetching path:", error);
    return { error: "Unable to fetch path" };
  }
}

// Function to display path result
function displayPathResult(pathData) {
  mapContainer.innerHTML = ""; // Clear previous content

  if (pathData.error) {
    placeholderText.textContent = pathData.error;
    mapContainer.appendChild(placeholderText);
  } else {
    const pathList = document.createElement("div");
    pathList.style.padding = "20px";
    pathList.style.background = "#f0f8ff";
    pathList.style.border = "2px solid #0073e6";
    pathList.style.borderRadius = "12px";

    const title = document.createElement("h4");
    title.textContent = "Shortest Path:";
    title.style.color = "#003366";
    pathList.appendChild(title);

    const ul = document.createElement("ul");
    ul.style.paddingLeft = "20px";
    pathData.path.forEach((node) => {
      const li = document.createElement("li");
      li.textContent = node;
      ul.appendChild(li);
    });

    pathList.appendChild(ul);
    mapContainer.appendChild(pathList);

    // Also show the graph image below path
    loadGraphImage();
  }
}

// Event listener for Go button
goBtn.addEventListener("click", async () => {
  const start = startInput.value.trim();
  const end = endInput.value.trim();

  if (!start || !end) {
    alert("Please enter both start and end nodes");
    return;
  }

  placeholderText.textContent = "Calculating path...";
  mapContainer.innerHTML = "";
  mapContainer.appendChild(placeholderText);

  const pathData = await getShortestPath(start, end);
  displayPathResult(pathData);
});

// Initial load
loadGraphImage();
