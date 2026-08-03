package remotetable

import "sort"

// MockBackend in-memory multi-tab store for conformance.
type MockBackend struct {
	Tabs map[string]*Tab
}

type Tab struct {
	Headers []string
	Rows    [][]string
}

func NewMockBackend() *MockBackend {
	return &MockBackend{Tabs: map[string]*Tab{}}
}

func (m *MockBackend) BackendID() string { return BackendMock }

func (m *MockBackend) TestConnection() (bool, string) {
	return true, "mock"
}

func (m *MockBackend) ListTabs() []string {
	out := make([]string, 0, len(m.Tabs))
	for k := range m.Tabs {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func (m *MockBackend) EnsureHeaders(tab string, headers []string) []string {
	if m.Tabs == nil {
		m.Tabs = map[string]*Tab{}
	}
	t, ok := m.Tabs[tab]
	if !ok {
		m.Tabs[tab] = &Tab{Headers: append([]string{}, headers...), Rows: nil}
		return headers
	}
	for _, h := range headers {
		found := false
		for _, c := range t.Headers {
			if c == h {
				found = true
				break
			}
		}
		if !found {
			t.Headers = append(t.Headers, h)
			for i := range t.Rows {
				t.Rows[i] = append(t.Rows[i], "")
			}
		}
	}
	return t.Headers
}

func (m *MockBackend) ReadRows(tab string) ([]string, [][]string) {
	t, ok := m.Tabs[tab]
	if !ok {
		return nil, nil
	}
	// defensive copies
	h := append([]string{}, t.Headers...)
	rows := make([][]string, len(t.Rows))
	for i, r := range t.Rows {
		rows[i] = append([]string{}, r...)
	}
	return h, rows
}

func (m *MockBackend) WriteRows(tab string, headers []string, rows [][]string, mode string) int {
	m.EnsureHeaders(tab, headers)
	t := m.Tabs[tab]
	// pad rows to header width
	padded := make([][]string, len(rows))
	for i, r := range rows {
		nr := make([]string, len(t.Headers))
		copy(nr, r)
		padded[i] = nr
	}
	if mode == "replace" {
		t.Rows = padded
		return len(padded)
	}
	t.Rows = append(t.Rows, padded...)
	return len(padded)
}
