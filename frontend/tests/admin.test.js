import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadScript } from './support/loadScript.js';
import { ADMIN_HTML } from './support/fixtures.js';

beforeAll(() => {
  document.body.innerHTML = ADMIN_HTML;
  loadScript('js/admin.js');
});

describe('openAddModal', () => {
  it('clears every field and labels the modal for creation', () => {
    document.getElementById('editId').value = '99';
    document.getElementById('editTitle').value = 'Stale title';

    openAddModal();

    expect(document.getElementById('editId').value).toBe('');
    expect(document.getElementById('editTitle').value).toBe('');
    expect(document.getElementById('editType').value).toBe('scholarship');
    expect(document.getElementById('editModalTitle').textContent).toBe('Add opportunity');
    expect(document.getElementById('editSubmitBtn').textContent).toBe('Add opportunity');
    expect(document.getElementById('editModal').style.display).toBe('flex');
  });
});

describe('openEditModal', () => {
  it('populates fields from the given listing and labels the modal for editing', () => {
    openEditModal({
      id: 7,
      title: 'Chevening Scholarships',
      opportunity_type: 'scholarship',
      is_active: false,
      field: 'Law',
      location: 'UK',
      url: 'https://example.org/chevening',
    });

    expect(document.getElementById('editId').value).toBe('7');
    expect(document.getElementById('editTitle').value).toBe('Chevening Scholarships');
    expect(document.getElementById('editStatus').value).toBe('false');
    expect(document.getElementById('editModalTitle').textContent).toBe('Edit listing');
    expect(document.getElementById('editSubmitBtn').textContent).toBe('Save changes');
  });
});

describe('onEditSubmit', () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    // onEditSubmit fires this (unawaited) on success to refresh the table;
    // its own DOM requirements (the listings table/section) are out of
    // scope for testing onEditSubmit's request-branching logic.
    global.loadListings = vi.fn();
  });

  it('POSTs to the create endpoint and omits is_active when #editId is empty', async () => {
    openAddModal();
    document.getElementById('editTitle').value = 'New Fellowship';
    document.getElementById('editUrl').value = 'https://example.org/new-fellowship';

    await onEditSubmit({ preventDefault: () => {} });

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toMatch(/\/admin\/opportunities\/$/);
    expect(options.method).toBe('POST');
    const body = JSON.parse(options.body);
    expect(body.title).toBe('New Fellowship');
    expect(body).not.toHaveProperty('is_active');
  });

  it('PATCHes to the item endpoint and includes is_active when #editId is set', async () => {
    openEditModal({
      id: 123,
      title: 'Existing Grant',
      opportunity_type: 'grant',
      is_active: true,
      url: 'https://example.org/existing-grant',
    });

    await onEditSubmit({ preventDefault: () => {} });

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toMatch(/\/admin\/opportunities\/123$/);
    expect(options.method).toBe('PATCH');
    const body = JSON.parse(options.body);
    expect(body).toHaveProperty('is_active', true);
  });

  it('shows the server-provided error message on failure instead of submitting silently', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: 'That URL has already been added.' }),
    });
    openAddModal();
    document.getElementById('editUrl').value = 'https://example.org/dup';

    await onEditSubmit({ preventDefault: () => {} });

    const errorEl = document.getElementById('editError');
    expect(errorEl.textContent).toBe('That URL has already been added.');
    expect(errorEl.style.display).toBe('block');
  });
});
