let allTDs = {};

async function loadTDs() {
  const listing = document.getElementById('listing');
  listing.innerHTML = '<div class="loading"><p>Loading TDs...</p></div>';

  const data = await getTDs();
  if (data.error) {
    listing.innerHTML = `<div class="error"><p>Error: ${data.error}</p></div>`;
    return;
  }

  allTDs = data.constituencies || {};
  renderTDs(allTDs);
}

function renderTDs(constituencies) {
  const listing = document.getElementById('listing');

  if (Object.keys(constituencies).length === 0) {
    listing.innerHTML = '<div class="empty"><p>No TDs found.</p></div>';
    return;
  }

  let html = '';
  const sorted = Object.keys(constituencies).sort();

  for (const constituency of sorted) {
    const members = constituencies[constituency];
    html += `
      <div class="constituency-group">
        <h4 class="constituency-name">${constituency}</h4>
        <div class="td-grid">
          ${members.map(m => `
            <div class="card td-card" onclick="goToTD('${m.member_id || m.id}')">
              <div class="td-name">${m.name || m.full_name || 'Unknown'}</div>
              <div class="td-meta">
                ${m.party_name ? `<span class="badge badge-neutral">${m.party_name}</span>` : ''}
              </div>
              <p class="caption">${m.house_name || 'Dáil Éireann'}</p>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  listing.innerHTML = html;
}

function filterTDs() {
  const query = document.getElementById('searchInput').value.toLowerCase();

  const filtered = {};
  for (const [const_name, members] of Object.entries(allTDs)) {
    const matchConst = const_name.toLowerCase().includes(query);
    const matchedMembers = members.filter(m => {
      const name = (m.name || m.full_name || '').toLowerCase();
      return name.includes(query) || matchConst;
    });

    if (matchedMembers.length > 0) {
      filtered[const_name] = matchedMembers;
    }
  }

  renderTDs(filtered);
}

function goToTD(pId) {
  window.location.href = `/td.html?id=${encodeURIComponent(pId)}`;
}

document.getElementById('searchInput').addEventListener('input', filterTDs);
loadTDs();
