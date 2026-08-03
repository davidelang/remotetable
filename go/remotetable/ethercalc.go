package remotetable

import (
	"encoding/csv"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// EtherCalcBackend talks socialcalc CSV over HTTP.
type EtherCalcBackend struct {
	BaseURL string
	Room    string
	Auth    string
	Client  *http.Client
}

func NewEtherCalc(baseURL, room, auth string) *EtherCalcBackend {
	if room == "" {
		room = "sheet"
	}
	return &EtherCalcBackend{
		BaseURL: strings.TrimRight(baseURL, "/"),
		Room:    room,
		Auth:    auth,
		Client:  &http.Client{Timeout: 60 * time.Second},
	}
}

func (e *EtherCalcBackend) BackendID() string { return BackendEthercalc }

func (e *EtherCalcBackend) headers() http.Header {
	h := make(http.Header)
	h.Set("Content-Type", "text/csv")
	if e.Auth != "" {
		h.Set("Authorization", "Bearer "+e.Auth)
	}
	return h
}

func (e *EtherCalcBackend) roomURL(suffix string) string {
	return e.BaseURL + "/" + e.Room + suffix
}

func (e *EtherCalcBackend) getCSV() (string, error) {
	req, err := http.NewRequest(http.MethodGet, e.roomURL(".csv"), nil)
	if err != nil {
		return "", err
	}
	req.Header = e.headers()
	resp, err := e.Client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body)[:min(200, len(body))])
	}
	return string(body), nil
}

func (e *EtherCalcBackend) putCSV(text string) error {
	req, err := http.NewRequest(http.MethodPut, e.roomURL(""), strings.NewReader(text))
	if err != nil {
		return err
	}
	req.Header = e.headers()
	resp, err := e.Client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return nil
	}
	// fallback POST append endpoint
	req2, err := http.NewRequest(http.MethodPost, e.BaseURL+"/_/"+e.Room, strings.NewReader(text))
	if err != nil {
		return err
	}
	req2.Header = e.headers()
	resp2, err := e.Client.Do(req2)
	if err != nil {
		return err
	}
	defer resp2.Body.Close()
	if resp2.StatusCode < 200 || resp2.StatusCode >= 300 {
		b, _ := io.ReadAll(resp2.Body)
		return fmt.Errorf("HTTP %d: %s", resp2.StatusCode, string(b)[:min(200, len(b))])
	}
	return nil
}

func parseCSVGrid(text string) (headers []string, rows [][]string, err error) {
	r := csv.NewReader(strings.NewReader(text))
	r.FieldsPerRecord = -1
	all, err := r.ReadAll()
	if err != nil {
		return nil, nil, err
	}
	// Skip blank / comma-only prefix rows (EtherCalc quirk).
	for len(all) > 0 {
		blank := true
		for _, c := range all[0] {
			if strings.TrimSpace(c) != "" {
				blank = false
				break
			}
		}
		if !blank {
			break
		}
		all = all[1:]
	}
	if len(all) == 0 {
		return nil, nil, nil
	}
	headers = all[0]
	if len(all) > 1 {
		rows = all[1:]
	}
	return headers, rows, nil
}

func encodeCSVGrid(headers []string, rows [][]string) string {
	var b strings.Builder
	w := csv.NewWriter(&b)
	_ = w.Write(headers)
	for _, row := range rows {
		_ = w.Write(row)
	}
	w.Flush()
	return b.String()
}

func (e *EtherCalcBackend) TestConnection() (bool, string) {
	if e.BaseURL == "" {
		return false, "missing base_url"
	}
	if _, err := e.getCSV(); err != nil {
		return false, err.Error()
	}
	return true, "ethercalc room=" + e.Room
}

func (e *EtherCalcBackend) ListTabs() []string {
	// Single-room model: room name is the only "tab".
	return []string{e.Room}
}

func (e *EtherCalcBackend) EnsureHeaders(tab string, headers []string) []string {
	curH, curRows := e.ReadRows(tab)
	if len(curH) == 0 {
		_ = e.putCSV(encodeCSVGrid(headers, nil))
		return headers
	}
	merged := append([]string{}, curH...)
	for _, h := range headers {
		found := false
		for _, c := range merged {
			if c == h {
				found = true
				break
			}
		}
		if !found {
			merged = append(merged, h)
			for i := range curRows {
				curRows[i] = append(curRows[i], "")
			}
		}
	}
	if len(merged) != len(curH) {
		_ = e.putCSV(encodeCSVGrid(merged, curRows))
	}
	return merged
}

func (e *EtherCalcBackend) ReadRows(tab string) ([]string, [][]string) {
	text, err := e.getCSV()
	if err != nil {
		return nil, nil
	}
	h, rows, err := parseCSVGrid(text)
	if err != nil {
		return nil, nil
	}
	return h, rows
}

func (e *EtherCalcBackend) WriteRows(tab string, headers []string, rows [][]string, mode string) int {
	e.EnsureHeaders(tab, headers)
	curH, curRows := e.ReadRows(tab)
	if len(curH) == 0 {
		curH = headers
	}
	// pad
	padded := make([][]string, len(rows))
	for i, r := range rows {
		nr := make([]string, len(curH))
		copy(nr, r)
		padded[i] = nr
	}
	out := padded
	if mode != "replace" {
		out = append(curRows, padded...)
	}
	_ = e.putCSV(encodeCSVGrid(curH, out))
	return len(padded)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
