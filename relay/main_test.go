package main

import (
	"context"
	"encoding/json"
	"github.com/gorilla/websocket"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func fakeWorkerRoot(t *testing.T, code string) (string, string) {
	t.Helper()
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 unavailable")
	}
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "remote"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "remote", "__init__.py"), nil, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "remote", "compute.py"), []byte(code), 0600); err != nil {
		t.Fatal(err)
	}
	return root, python
}

func TestSlowDrivingKeepsReceiptAcksAndUsesNewestPendingFrame(t *testing.T) {
	root, python := fakeWorkerRoot(t, `import json,sys,time
first=True
for line in sys.stdin:
    frame=json.loads(line)
    if frame['status']=='live' and first:
        first=False
        time.sleep(6)
    print(json.dumps({'type':'presentation','seq':frame['seq']}),flush=True)
`)
	s := &Server{pilotToken: strings.Repeat("p", 32), root: root, python: python}
	server := httptest.NewServer(http.HandlerFunc(s.pilot))
	defer server.Close()
	conn, _, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(server.URL, "http"), http.Header{
		"Authorization": {"Bearer " + s.pilotToken}, "X-Spotter-Ack": {"1"},
	})
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	send := func(seq int, status string) {
		t.Helper()
		if err := conn.WriteJSON(map[string]any{"seq": seq, "status": status}); err != nil {
			t.Fatal(err)
		}
		_ = conn.SetReadDeadline(time.Now().Add(time.Second))
		var ack struct {
			Type string
			Seq  int
		}
		if err := conn.ReadJSON(&ack); err != nil {
			t.Fatalf("ACK blocked by calculation: %v", err)
		}
		if ack.Type != "ack" || ack.Seq != seq {
			t.Fatalf("bad ACK: %+v", ack)
		}
	}
	send(0, "garage")
	awaitSeq := func(seq int) {
		t.Helper()
		deadline := time.Now().Add(9 * time.Second)
		for time.Now().Before(deadline) {
			s.mu.Lock()
			var state struct{ Seq int }
			_ = json.Unmarshal(s.state, &state)
			exists := len(s.state) > 0
			s.mu.Unlock()
			if exists && state.Seq == seq {
				return
			}
			time.Sleep(10 * time.Millisecond)
		}
		t.Fatalf("expected computed seq %d", seq)
	}
	awaitSeq(0)
	send(1, "live")
	time.Sleep(100 * time.Millisecond) // the fake worker is inside the six-second calculation
	for seq := 2; seq <= 8; seq++ {
		send(seq, "live")
	}
	awaitSeq(8)
	send(9, "live") // Same socket is usable after collector's previous 5 s limit.
	awaitSeq(9)
}

func TestTimedOutWorkerRestartsWithoutClosingSource(t *testing.T) {
	root, python := fakeWorkerRoot(t, `import json,sys,time,pathlib
marker=pathlib.Path('first-worker')
hang=not marker.exists()
marker.touch()
for line in sys.stdin:
    frame=json.loads(line)
    if hang: time.sleep(2)
    print(json.dumps({'type':'presentation','seq':frame['seq']}),flush=True)
`)
	worker, err := newWorker(root, python)
	if err != nil {
		t.Fatal(err)
	}
	worker.timeout = 100 * time.Millisecond
	s := &Server{root: root, python: python}
	ctx, cancel := context.WithCancel(context.Background())
	queue := make(chan capturedFrame, 1)
	done := make(chan error, 1)
	go func() { done <- s.calculateFrames(ctx, queue, worker) }()
	defer func() {
		cancel()
		if err := <-done; err != context.Canceled {
			t.Errorf("unexpected worker exit: %v", err)
		}
	}()
	offerLatest(queue, capturedFrame{raw: []byte(`{"seq":1}`), received: time.Now()})
	time.Sleep(200 * time.Millisecond)
	offerLatest(queue, capturedFrame{raw: []byte(`{"seq":2}`), received: time.Now()})
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		var state struct{ Seq int }
		_ = json.Unmarshal(s.state, &state)
		s.mu.Unlock()
		if state.Seq == 2 {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("calculation did not resume after replacing the timed-out worker")
}

func TestGarageThenColdDrivingCalculation(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 unavailable")
	}
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "remote"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "remote", "__init__.py"), nil, 0600); err != nil {
		t.Fatal(err)
	}
	code := `import json,sys,time
for line in sys.stdin:
    frame=json.loads(line)
    live=frame.get('status')=='live'
    if live: time.sleep(2.2)
    print(json.dumps({'type':'presentation','compute':{'overlaysReady':live}}),flush=True)
`
	if err := os.WriteFile(filepath.Join(root, "remote", "compute.py"), []byte(code), 0600); err != nil {
		t.Fatal(err)
	}
	worker, err := newWorker(root, python)
	if err != nil {
		t.Fatal(err)
	}
	defer worker.close()
	if _, err := worker.calculate([]byte(`{"status":"garage"}`)); err != nil {
		t.Fatal(err)
	}
	if _, err := worker.calculate([]byte(`{"status":"live"}`)); err != nil {
		t.Fatalf("garage ACK must not consume the first driving initialization budget: %v", err)
	}
}

func TestRolesAndSession(t *testing.T) {
	s := &Server{pilotToken: strings.Repeat("p", 32), viewerToken: strings.Repeat("v", 32)}
	for _, token := range []string{s.pilotToken, s.viewerToken} {
		r := httptest.NewRequest("POST", "http://localhost/api/session", strings.NewReader(`{"token":"`+token+`"}`))
		r.Header.Set("Origin", "http://localhost")
		w := httptest.NewRecorder()
		s.login(w, r)
		if token == s.pilotToken && w.Code != 401 {
			t.Fatal("pilot token accepted as viewer")
		}
		if token == s.viewerToken {
			if w.Code != 204 {
				t.Fatalf("login: %d", w.Code)
			}
			next := httptest.NewRequest("GET", "http://localhost/ws/view", nil)
			next.AddCookie(w.Result().Cookies()[0])
			if !s.viewerAuth(next) {
				t.Fatal("valid cookie rejected")
			}
			probe := httptest.NewRequest("GET", "http://localhost/api/session", nil)
			probe.AddCookie(w.Result().Cookies()[0])
			checked := httptest.NewRecorder()
			s.login(checked, probe)
			if checked.Code != 204 {
				t.Fatal("session probe rejected valid cookie")
			}
			probe = httptest.NewRequest("GET", "http://localhost/api/session", nil)
			checked = httptest.NewRecorder()
			s.login(checked, probe)
			if checked.Code != 401 {
				t.Fatal("anonymous session probe accepted")
			}
			cookie := w.Result().Cookies()[0]
			cookie.Value += "tampered"
			next = httptest.NewRequest("GET", "http://localhost/ws/view", nil)
			next.AddCookie(cookie)
			if s.viewerAuth(next) {
				t.Fatal("tampered cookie accepted")
			}
		}
	}
}

func TestOrigin(t *testing.T) {
	r := httptest.NewRequest("GET", "http://localhost/ws/view", nil)
	r.Header.Set("Origin", "https://attacker.test")
	if sameOrigin(r) {
		t.Fatal("cross origin accepted")
	}
	r.Header.Set("Origin", "http://localhost")
	if !sameOrigin(r) {
		t.Fatal("same origin rejected")
	}
}

func TestDesktopStatusAuthorizationAndFreshness(t *testing.T) {
	s := &Server{pilotToken: strings.Repeat("p", 32), viewerToken: strings.Repeat("v", 32),
		connected: true, viewers: 1, received: time.Now().Add(-2 * time.Second),
		ingested: time.Now(), computeMs: 12.5, state: json.RawMessage(`{"status":"garage"}`)}
	for _, mode := range []string{"anonymous", "pilot", "viewer-bearer", "viewer-cookie", "cross-origin", "post"} {
		r := httptest.NewRequest("GET", "http://localhost/api/status", nil)
		if mode == "pilot" || mode == "cross-origin" || mode == "post" {
			r.Header.Set("Authorization", "Bearer "+s.pilotToken)
		}
		if mode == "viewer-bearer" {
			r.Header.Set("Authorization", "Bearer "+s.viewerToken)
		}
		if mode == "viewer-cookie" {
			value := strconv.FormatInt(time.Now().Add(time.Hour).Unix(), 10) + ".nonce"
			r.AddCookie(&http.Cookie{Name: "spotter_session", Value: value + "." + s.signature(value)})
		}
		if mode == "cross-origin" {
			r.Header.Set("Origin", "https://attacker.test")
		}
		if mode == "post" {
			r.Method = "POST"
		}
		w := httptest.NewRecorder()
		s.status(w, r)
		want := 401
		if mode == "pilot" || mode == "viewer-cookie" {
			want = 200
		}
		if mode == "post" {
			want = 405
		}
		if w.Code != want {
			t.Fatalf("%s: got %d want %d", mode, w.Code, want)
		}
		if want == 200 {
			var value map[string]any
			if err := json.Unmarshal(w.Body.Bytes(), &value); err != nil {
				t.Fatal(err)
			}
			if value["gameStatus"] != "garage" || value["sourceConnected"] != true || value["viewersConnected"] != float64(1) || value["sourceAgeMs"].(float64) < 2000 {
				t.Fatal(value)
			}
			if strings.Contains(w.Body.String(), s.pilotToken) || strings.Contains(w.Body.String(), s.viewerToken) {
				t.Fatal("status leaks credentials")
			}
			if w.Header().Get("Cache-Control") != "no-store" {
				t.Fatal("presence response may be cached")
			}
		}
	}
}
