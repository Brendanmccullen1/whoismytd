const API = '/api';

async function fetchAPI(endpoint) {
  try {
    const response = await fetch(`${API}${endpoint}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`API error: ${endpoint}`, error);
    return { error: error.message };
  }
}

async function getTDs() {
  return fetchAPI('/tds');
}

async function getTD(pId) {
  return fetchAPI(`/td/${pId}`);
}

async function getBills() {
  return fetchAPI('/bills');
}

async function getBill(billId) {
  return fetchAPI(`/bill/${billId}`);
}

async function getBillSummary(billId) {
  return fetchAPI(`/summary/${billId}`);
}

async function getDivision(divisionId) {
  return fetchAPI(`/division/${divisionId}`);
}
