/**
 * Minimal DOM fixtures mirroring the real index.html / admin.html — just
 * enough for each script's top-level element lookups to resolve to real
 * elements instead of null, and for the specific functions under test to
 * find what they expect. Not a full copy of the page markup.
 */

export const APP_HTML = `
  <div class="header-search">
    <input id="searchInput" type="search" />
    <button id="searchBtn"></button>
    <ul id="searchSuggestions" hidden></ul>
  </div>
  <button id="scrapeBtn"></button>

  <select id="fieldFilter"></select>
  <select id="locationFilter"></select>
  <select id="sortSelect"></select>
  <p id="pageMeta"></p>

  <div id="loading" style="display:none"></div>
  <div id="emptyState" style="display:none">
    <p id="emptyMsg"></p>
    <button id="emptyBtn"></button>
  </div>
  <div id="grid"></div>
  <div id="pagination"></div>
  <p id="resultsMeta"></p>

  <div id="modal" style="display:none">
    <button id="closeModal"></button>
  </div>

  <div id="saveModal" style="display:none">
    <form id="saveForm">
      <input id="saveEmailInput" type="email" />
    </form>
    <button id="closeSaveModal"></button>
  </div>

  <button id="copyEmailBtn" data-email="hello@globalopportunities.app">
    <span class="copy-btn-label">Copy</span>
  </button>
`;

export const ADMIN_HTML = `
  <form id="keyForm"><button type="submit"></button></form>
  <button id="logoutBtn"></button>
  <button id="modRefresh"></button>
  <button id="modApproveAll"></button>
  <select id="trendsRange"></select>
  <button id="listingsRefresh"></button>
  <input id="listingsSearch" />
  <select id="listingsTypeFilter"></select>
  <button id="listingsAddBtn"></button>

  <div id="editModal" style="display:none">
    <h3 id="editModalTitle"></h3>
    <button id="closeEditModal"></button>
    <form id="editForm">
      <input id="editId" />
      <input id="editTitle" />
      <select id="editType">
        <option value="scholarship">Scholarship</option>
        <option value="other">Other</option>
      </select>
      <select id="editStatus">
        <option value="true">Active</option>
        <option value="false">Inactive</option>
      </select>
      <input id="editField" />
      <input id="editLocation" />
      <input id="editDeadline" />
      <input id="editDeadlineAt" />
      <input id="editSourceName" />
      <input id="editUrl" />
      <textarea id="editSummary"></textarea>
      <textarea id="editDescription"></textarea>
      <p id="editError" style="display:none"></p>
      <button id="editSubmitBtn" type="submit"></button>
    </form>
  </div>
`;
