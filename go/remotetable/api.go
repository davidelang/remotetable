// Package remotetable is the Go API surface (mock + live backends + CLI).
package remotetable

// Backend is the provider interface.
type Backend interface {
	BackendID() string
	TestConnection() (ok bool, message string)
	ListTabs() []string
	EnsureHeaders(tab string, headers []string) []string
	ReadRows(tab string) (headers []string, rows [][]string)
	WriteRows(tab string, headers []string, rows [][]string, mode string) int
}

// Backend IDs (stable wire strings).
const (
	BackendMock         = "mock"
	BackendGoogleSheets = "google-sheets"
	BackendExcelGraph   = "excel-graph"
	BackendEthercalc    = "ethercalc"
	BackendBaserow      = "baserow"
	BackendNocoDB       = "nocodb"
	BackendPocketBase   = "pocketbase"
	BackendSupabase     = "supabase"
	BackendAirtable     = "airtable"
)

// RemoteTable facade.
type RemoteTable struct {
	B Backend
}

func New(b Backend) *RemoteTable { return &RemoteTable{B: b} }

func (rt *RemoteTable) BackendID() string {
	if rt.B == nil {
		return ""
	}
	return rt.B.BackendID()
}

func (rt *RemoteTable) TestConnection() map[string]interface{} {
	ok, msg := rt.B.TestConnection()
	return map[string]interface{}{"ok": ok, "message": msg}
}

func (rt *RemoteTable) ListTabs() map[string]interface{} {
	return map[string]interface{}{"tabs": rt.B.ListTabs()}
}

func (rt *RemoteTable) EnsureHeaders(tab string, headers []string) map[string]interface{} {
	h := rt.B.EnsureHeaders(tab, headers)
	return map[string]interface{}{"ok": true, "headers": h}
}

func (rt *RemoteTable) ReadRows(tab string) map[string]interface{} {
	h, rows := rt.B.ReadRows(tab)
	return map[string]interface{}{"headers": h, "rows": rows}
}

func (rt *RemoteTable) WriteRows(tab string, headers []string, rows [][]string, mode string) map[string]interface{} {
	n := rt.B.WriteRows(tab, headers, rows, mode)
	return map[string]interface{}{"written": n, "mode": mode}
}
