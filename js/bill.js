async function loadBill() {
  const billId = getQueryParam('id');
  const content = document.getElementById('content');

  if (!billId) {
    content.innerHTML = '<div class="empty"><p>No bill ID provided.</p></div>';
    return;
  }

  const billData = await getBill(billId);
  if (billData.error) {
    content.innerHTML = `<div class="error"><p>Error loading bill: ${billData.error}</p></div>`;
    return;
  }

  const bill = billData.bill;
  const divisions = billData.divisions || [];

  if (!bill) {
    content.innerHTML = '<div class="empty"><p>Bill not found.</p></div>';
    return;
  }

  const billTitle = bill.title || bill.bill_name || 'Bill';
  const billDate = bill.date || bill.effective_date || new Date().toISOString();

  let summaryHTML = '<div style="opacity: 0.6; padding: var(--space-6); text-align: center;"><p>Loading summary...</p></div>';

  const summaryData = await getBillSummary(billId);
  if (!summaryData.error && summaryData.summary) {
    summaryHTML = `
      <div class="ai-label">
        <div class="ai-icon">✨</div>
        <span style="font-weight: var(--weight-medium); color: var(--fg-1);">AI Summary</span>
      </div>
      <div class="ai-text">${summaryData.summary}</div>
    `;
  }

  let breakdownHTML = '<p style="padding: var(--space-4); color: var(--fg-3);">No votes recorded.</p>';

  if (divisions.length > 0) {
    const totalVotes = divisions.reduce((sum, d) => sum + (d.member_votes?.length || 0), 0);
    const taCounts = divisions.map(d => {
      const ta = (d.member_votes || []).filter(v => v.vote === 'Tá').length;
      const nil = (d.member_votes || []).filter(v => v.vote === 'Níl').length;
      const staon = (d.member_votes || []).filter(v => v.vote === 'Staon').length;
      return { ta, nil, staon };
    });

    if (taCounts.length > 0) {
      const combined = taCounts.reduce((a, b) => ({
        ta: a.ta + b.ta,
        nil: a.nil + b.nil,
        staon: a.staon + b.staon
      }), { ta: 0, nil: 0, staon: 0 });

      const total = combined.ta + combined.nil + combined.staon;

      breakdownHTML = `
        <div class="breakdown-bars">
          <div class="bar-row">
            <div class="bar-label"><i>Tá</i></div>
            <div class="bar-track">
              <div class="bar-fill ta" style="width: ${(combined.ta / total * 100) || 0}%"></div>
            </div>
            <div class="bar-count">${combined.ta}</div>
          </div>
          <div class="bar-row">
            <div class="bar-label"><i>Níl</i></div>
            <div class="bar-track">
              <div class="bar-fill nil" style="width: ${(combined.nil / total * 100) || 0}%"></div>
            </div>
            <div class="bar-count">${combined.nil}</div>
          </div>
          <div class="bar-row">
            <div class="bar-label"><i>Staon</i></div>
            <div class="bar-track">
              <div class="bar-fill staon" style="width: ${(combined.staon / total * 100) || 0}%"></div>
            </div>
            <div class="bar-count">${combined.staon}</div>
          </div>
        </div>
      `;
    }
  }

  const billHTML = `
    <div class="bill-header">
      <div class="bill-meta">
        <span style="color: var(--fg-3);">Division</span>
        <span class="bill-meta-dot">·</span>
        <span style="color: var(--fg-3);">${new Date(billDate).toLocaleDateString()}</span>
      </div>
      <h1 class="bill-title">${billTitle}</h1>
    </div>

    <div class="ai-summary">
      ${summaryHTML}
    </div>

    <div class="vote-breakdown">
      <h3 class="breakdown-title">Vote Breakdown</h3>
      ${breakdownHTML}
    </div>
  `;

  content.innerHTML = billHTML;
}

loadBill();
