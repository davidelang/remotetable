// Command remotetable — Go host CLI (mock + ethercalc).
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/davidelang/remotetable/remotetable"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	args = normalize(args)
	backend := "mock"
	fixture := ""
	baseURL := ""
	room := "sheet"
	tokenFile := ""
	var positional []string
	for i := 0; i < len(args); i++ {
		a := args[i]
		switch {
		case a == "--backend" && i+1 < len(args):
			backend = args[i+1]
			i++
		case strings.HasPrefix(a, "--backend="):
			backend = strings.TrimPrefix(a, "--backend=")
		case a == "--fixture" && i+1 < len(args):
			fixture = args[i+1]
			i++
		case strings.HasPrefix(a, "--fixture="):
			fixture = strings.TrimPrefix(a, "--fixture=")
		case a == "--base-url" && i+1 < len(args):
			baseURL = args[i+1]
			i++
		case strings.HasPrefix(a, "--base-url="):
			baseURL = strings.TrimPrefix(a, "--base-url=")
		case a == "--room" && i+1 < len(args):
			room = args[i+1]
			i++
		case strings.HasPrefix(a, "--room="):
			room = strings.TrimPrefix(a, "--room=")
		case a == "--token-file" && i+1 < len(args):
			tokenFile = args[i+1]
			i++
		case strings.HasPrefix(a, "--token-file="):
			tokenFile = strings.TrimPrefix(a, "--token-file=")
		case a == "-h" || a == "--help":
			fmt.Fprintln(os.Stderr, "usage: remotetable [--backend mock|ethercalc] [--fixture path] [--base-url URL] [--room name] <cmd>")
			return 0
		default:
			positional = append(positional, a)
		}
	}
	if len(positional) == 0 {
		fmt.Fprintln(os.Stderr, "usage: remotetable [--backend mock|ethercalc] <test-connection|list-tabs|read-rows|write-rows> ...")
		return 2
	}
	cmd := positional[0]
	cmdArgs := positional[1:]

	be, err := buildBackend(backend, fixture, baseURL, room, tokenFile)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	rt := remotetable.New(be)

	switch cmd {
	case "test-connection":
		return printJSON(rt.TestConnection())
	case "list-tabs":
		return printJSON(rt.ListTabs())
	case "read-rows":
		tab := flagString(cmdArgs, "tab", "")
		if tab == "" {
			fmt.Fprintln(os.Stderr, "--tab required")
			return 2
		}
		return printJSON(rt.ReadRows(tab))
	case "write-rows":
		tab := flagString(cmdArgs, "tab", "")
		mode := flagString(cmdArgs, "mode", "append")
		if tab == "" {
			fmt.Fprintln(os.Stderr, "--tab required")
			return 2
		}
		headers, rows, err := loadJSONStdin()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 2
		}
		return printJSON(rt.WriteRows(tab, headers, rows, mode))
	default:
		fmt.Fprintln(os.Stderr, "unknown command:", cmd)
		return 2
	}
}

func buildBackend(backend, fixture, baseURL, room, tokenFile string) (remotetable.Backend, error) {
	switch backend {
	case remotetable.BackendMock:
		m := remotetable.NewMockBackend()
		if fixture != "" {
			raw, err := os.ReadFile(fixture)
			if err != nil {
				return nil, err
			}
			// Support { "tabs": { name: {headers,rows} } } and flat { name: {headers,rows} }
			type tabJSON struct {
				Headers []string   `json:"headers"`
				Rows    [][]string `json:"rows"`
			}
			var wrapped struct {
				Tabs map[string]tabJSON `json:"tabs"`
			}
			if err := json.Unmarshal(raw, &wrapped); err == nil && len(wrapped.Tabs) > 0 {
				for name, tab := range wrapped.Tabs {
					m.Tabs[name] = &remotetable.Tab{Headers: tab.Headers, Rows: tab.Rows}
				}
			} else {
				var book map[string]tabJSON
				if err := json.Unmarshal(raw, &book); err != nil {
					return nil, err
				}
				for name, tab := range book {
					if name == "tabs" {
						continue
					}
					m.Tabs[name] = &remotetable.Tab{Headers: tab.Headers, Rows: tab.Rows}
				}
			}
		}
		return m, nil
	case remotetable.BackendEthercalc:
		auth := ""
		if tokenFile != "" {
			raw, err := os.ReadFile(tokenFile)
			if err != nil {
				return nil, err
			}
			var cfg map[string]string
			if err := json.Unmarshal(raw, &cfg); err != nil {
				return nil, err
			}
			if baseURL == "" {
				baseURL = cfg["base_url"]
			}
			if r := cfg["room"]; r != "" && (room == "" || room == "sheet") {
				room = r
			}
			auth = cfg["auth"]
		}
		if baseURL == "" {
			return nil, fmt.Errorf("--base-url required for ethercalc")
		}
		return remotetable.NewEtherCalc(baseURL, room, auth), nil
	default:
		return nil, fmt.Errorf("go CLI: backend %q not implemented yet (use python scripts/remotetable)", backend)
	}
}

func printJSON(v interface{}) int {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func loadJSONStdin() ([]string, [][]string, error) {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		return nil, nil, err
	}
	if len(strings.TrimSpace(string(raw))) == 0 {
		return nil, nil, nil
	}
	var data struct {
		Headers []string   `json:"headers"`
		Rows    [][]string `json:"rows"`
	}
	if err := json.Unmarshal(raw, &data); err == nil && (len(data.Headers) > 0 || len(data.Rows) > 0) {
		return data.Headers, data.Rows, nil
	}
	r := csv.NewReader(strings.NewReader(string(raw)))
	r.FieldsPerRecord = -1
	all, err := r.ReadAll()
	if err != nil {
		return nil, nil, err
	}
	if len(all) == 0 {
		return nil, nil, nil
	}
	return all[0], all[1:], nil
}

func flagString(args []string, name, def string) string {
	long := "--" + name
	for i := 0; i < len(args); i++ {
		a := args[i]
		if a == long && i+1 < len(args) {
			return args[i+1]
		}
		if strings.HasPrefix(a, long+"=") {
			return strings.TrimPrefix(a, long+"=")
		}
	}
	return def
}

func normalize(argv []string) []string {
	cmds := map[string]bool{
		"test-connection": true, "list-tabs": true, "read-rows": true, "write-rows": true,
	}
	valueFlags := map[string]bool{
		"--backend": true, "--fixture": true, "--base-url": true, "--room": true, "--token-file": true,
	}
	cmdIdx := -1
	for i, a := range argv {
		if cmds[a] {
			cmdIdx = i
			break
		}
	}
	if cmdIdx < 0 {
		return argv
	}
	var globals, rest []string
	take := func(seq []string, i int) (int, bool) {
		a := seq[i]
		if valueFlags[a] {
			globals = append(globals, a)
			if i+1 < len(seq) && !strings.HasPrefix(seq[i+1], "-") {
				globals = append(globals, seq[i+1])
				return i + 2, true
			}
			return i + 1, true
		}
		if strings.HasPrefix(a, "--") && strings.Contains(a, "=") {
			key := strings.SplitN(a, "=", 2)[0]
			if valueFlags[key] {
				globals = append(globals, a)
				return i + 1, true
			}
		}
		return i, false
	}
	i := 0
	before := argv[:cmdIdx]
	for i < len(before) {
		if ni, ok := take(before, i); ok {
			i = ni
			continue
		}
		rest = append(rest, before[i])
		i++
	}
	cmd := argv[cmdIdx]
	after := argv[cmdIdx+1:]
	i = 0
	var sub []string
	for i < len(after) {
		if ni, ok := take(after, i); ok {
			i = ni
			continue
		}
		sub = append(sub, after[i])
		i++
	}
	out := append(append(append([]string{}, rest...), globals...), cmd)
	return append(out, sub...)
}
