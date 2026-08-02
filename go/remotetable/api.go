// Package remotetable is the Go M1 API surface (mock-backed conformance).
package remotetable

// Backend is the provider interface.
type Backend interface {
	TestConnection() (ok bool, message string)
	ListTabs() []string
	EnsureHeaders(tab string, headers []string) []string
	ReadRows(tab string) (headers []string, rows [][]string)
	WriteRows(tab string, headers []string, rows [][]string, mode string) int
}

// RemoteTable facade.
type RemoteTable struct {
	B Backend
}

func (rt *RemoteTable) TestConnection() map[string]interface{} {
	ok, msg := rt.B.TestConnection()
	return map[string]interface{}{"ok": ok, "message": msg}
}

func (rt *RemoteTable) ListTabs() map[string]interface{} {
	return map[string]interface{}{"tabs": rt.B.ListTabs()}
}
