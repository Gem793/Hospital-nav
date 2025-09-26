// Button click + map highlight
document.getElementById('goBtn').addEventListener('click', function(){
  var start = document.getElementById('startRoom').value.trim();
  var end = document.getElementById('endRoom').value.trim();
  var mapContainer = document.querySelector('.map-container');

  if(!start || !end){
    alert("Enter start and end rooms!");
    return;
  }

  // Show visual feedback
  mapContainer.classList.add('active');
  mapContainer.innerHTML = `<p class="placeholder-text">Showing path from <strong>${start}</strong> to <strong>${end}</strong></p>`;

  // Remove highlight after 3 seconds
  setTimeout(() => {
    mapContainer.classList.remove('active');
    mapContainer.innerHTML = `<p class="placeholder-text">Map will appear here</p>`;
  }, 3000);

  console.log(`Fetch path from ${start} to ${end}`);
});

// Input focus background change
const inputs = document.querySelectorAll('.input-field');
inputs.forEach(input => {
  input.addEventListener('focus', () => input.style.backgroundColor = '#e6f0ff');
  input.addEventListener('blur', () => input.style.backgroundColor = '#f0f8ff');
});
