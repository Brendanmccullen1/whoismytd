async function loadTD() {
  const pId = getQueryParam('id');
  const content = document.getElementById('content');

  if (!pId) {
    content.innerHTML = '<div class="empty"><p>No TD ID provided.</p></div>';
    return;
  }

  const data = await getTD(pId);
  if (data.error) {
    content.innerHTML = `<div class="error"><p>Error loading TD: ${data.error}</p></div>`;
    return;
  }

  const member = data.member;
  const votes = data.votes || [];

  if (!member) {
    content.innerHTML = '<div class="empty"><p>TD not found.</p></div>';
    return;
  }

  const fullName = member.name || member.full_name || 'Unknown';
  const initials = fullName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  const party = member.party_name || 'Independent';
  const constituency = member.constituency?.name || 'Unknown';

  const taCount = votes.filter(v => v.vote === 'Tá').length;
  const nilCount = votes.filter(v => v.vote === 'Níl').length;
  const staonCount = votes.filter(v => v.vote === 'Staon').length;

  const profileHTML = `
    <div class="card profile-card">
      <div class="profile-header">
        <div class="profile-avatar">${initials}</div>
        <div class="profile-info">
          <h1 class="profile-name">${fullName}</h1>
          <div class="profile-meta">
            <span class="badge badge-neutral">${party}</span>
            <span class="badge badge-neutral">${constituency}</span>
          </div>
        </div>
      </div>

      <div class="profile-stats">
        <div class="stat-col">
          <div class="stat-val" style="color: var(--vote-ta);">${taCount}</div>
          <div class="stat-lbl"><i>Tá</i> (Yes)</div>
        </div>
        <div class="stat-col">
          <div class="stat-val" style="color: var(--vote-nil);">${nilCount}</div>
          <div class="stat-lbl"><i>Níl</i> (No)</div>
        </div>
        <div class="stat-col">
          <div class="stat-val" style="color: var(--vote-staon);">${staonCount}</div>
          <div class="stat-lbl"><i>Staon</i> (Abstain)</div>
        </div>
      </div>
    </div>

    <div class="votes-header">
      <h3 class="votes-title">Recent Votes</h3>
      <span class="votes-count">${votes.length} votes</span>
    </div>

    <div class="card" style="padding: 0;">
      ${votes.slice(0, 50).map(vote => {
        const voteClass = vote.vote === 'Tá' ? 'ta' : vote.vote === 'Níl' ? 'nil' : 'staon';
        const voteLabel = vote.vote === 'Tá' ? '<i>Tá</i>' : vote.vote === 'Níl' ? '<i>Níl</i>' : '<i>Staon</i>';
        return `
          <div class="vote-item" onclick="goToDivision('${vote.division_id}')">
            <div class="vote-dot ${voteClass}"></div>
            <div class="vote-text">
              <div class="vote-subject">${vote.bill_name || vote.division_name || 'Division'}</div>
              <div class="vote-meta">${new Date(vote.date || Date.now()).toLocaleDateString()}</div>
            </div>
            <div style="text-align: right; color: var(--fg-3);">
              ${voteLabel}
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;

  content.innerHTML = profileHTML;
}

function goToDivision(divisionId) {
  window.location.href = `/bill.html?id=${encodeURIComponent(divisionId)}`;
}

loadTD();
