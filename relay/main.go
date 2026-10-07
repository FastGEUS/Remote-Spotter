// TinyPedal Remote Spotter extension. GPL-3.0-or-later.
package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

//go:embed web/*
var assets embed.FS

const maxFrame = 1024 * 1024

type Worker struct {
	cmd     *exec.Cmd
	input   io.WriteCloser
	output  *bufio.Scanner
	timeout time.Duration
}

func newWorker(root, python string) (*Worker, error) {
	cmd := exec.Command(python, "-u", "-m", "remote.compute")
	cmd.Dir = root
	cmd.Stderr = os.Stderr
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	if err = cmd.Start(); err != nil {
		return nil, err
	}
	return &Worker{cmd: cmd, input: stdin, output: scanner, timeout: 15 * time.Second}, nil
}

func (w *Worker) close() {
	_ = w.input.Close()
	done := make(chan struct{})
	go func() { _ = w.cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		_ = w.cmd.Process.Kill()
		<-done
	}
}

func (w *Worker) calculate(raw []byte) ([]byte, error) {
	return w.calculateContext(context.Background(), raw)
}

var errComputeTimeout = errors.New("compute timeout")

func (w *Worker) calculateContext(ctx context.Context, raw []byte) ([]byte, error) {
	type result struct {
		data []byte
		err  error
	}
	done := make(chan result, 1)
	go func() {
		if _, err := w.input.Write(append(raw, '\n')); err != nil {
			done <- result{err: err}
			return
		}
		if !w.output.Scan() {
			done <- result{err: errors.New("compute worker ended")}
			return
		}
		data := append([]byte(nil), w.output.Bytes()...)
		if !json.Valid(data) {
			done <- result{err: errors.New("invalid compute response")}
			return
		}
		var response struct {
			Type  string `json:"type"`
			Error string `json:"error"`
		}
		if err := json.Unmarshal(data, &response); err != nil {
			done <- result{err: err}
			return
		}
		if response.Type != "presentation" {
			reason := strings.NewReplacer("\n", " ", "\r", " ").Replace(response.Error)
			if len(reason) > 256 {
				reason = reason[:256]
			}
			done <- result{err: fmt.Errorf("ingest rejected: %s", reason)}
			return
		}
		done <- result{data: data}
	}()
	timer := time.NewTimer(w.timeout)
	defer timer.Stop()
	select {
	case r := <-done:
		return r.data, r.err
	case <-timer.C:
		_ = w.cmd.Process.Kill() // unblock pipe writer/scanner before recreation
		<-done
		return nil, errComputeTimeout
	case <-ctx.Done():
		_ = w.cmd.Process.Kill()
		<-done
		return nil, ctx.Err()
	}
}

type capturedFrame struct {
	raw      []byte
	received time.Time
}

// A slow calculation may keep one current frame and one newest pending frame.
// Replacing the pending frame bounds both memory and accumulated display lag.
func offerLatest(queue chan capturedFrame, frame capturedFrame) {
	select {
	case queue <- frame:
		return
	default:
	}
	select {
	case <-queue:
	default:
	}
	queue <- frame // One producer; the consumer can only free capacity.
}

func (s *Server) calculateFrames(ctx context.Context, queue <-chan capturedFrame, worker *Worker) error {
	defer func() {
		if worker != nil {
			worker.close()
		}
	}()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case frame := <-queue:
			started := time.Now()
			result, err := worker.calculateContext(ctx, frame.raw)
			if errors.Is(err, errComputeTimeout) {
				log.Print("compute timeout: restarting calculation worker; pilot transport remains connected")
				worker.close()
				worker = nil
				worker, err = newWorker(s.root, s.python)
				if err != nil {
					return err
				}
				continue
			}
			if err != nil {
				return err
			}
			s.mu.Lock()
			s.state = result
			s.received = frame.received
			s.computeMs = float64(time.Since(started).Microseconds()) / 1000
			s.mu.Unlock()
		}
	}
}

type Server struct {
	pilotToken, viewerToken, root, python string
	mu                                    sync.Mutex
	state                                 json.RawMessage
	received                              time.Time
	ingested                              time.Time
	connected                             bool
	viewers                               int
	computeMs                             float64
}

func equal(a, b string) bool { return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1 }

func sameOrigin(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		return false
	}
	u, err := url.Parse(origin)
	return err == nil && (u.Scheme == "http" || u.Scheme == "https") && u.Host == r.Host
}

func (s *Server) signature(value string) string {
	h := hmac.New(sha256.New, []byte(s.viewerToken))
	_, _ = h.Write([]byte(value))
	return base64.RawURLEncoding.EncodeToString(h.Sum(nil))
}

func (s *Server) viewerAuth(r *http.Request) bool {
	cookie, err := r.Cookie("spotter_session")
	if err != nil {
		return false
	}
	bits := strings.Split(cookie.Value, ".")
	if len(bits) != 3 {
		return false
	}
	exp, err := strconv.ParseInt(bits[0], 10, 64)
	return err == nil && exp > time.Now().Unix() && equal(bits[2], s.signature(bits[0]+"."+bits[1]))
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodGet {
		w.Header().Set("Cache-Control", "no-store")
		if !s.viewerAuth(r) || r.Header.Get("Origin") != "" && !sameOrigin(r) {
			http.Error(w, "unauthorized", 401)
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost || !sameOrigin(r) {
		http.Error(w, "forbidden", 403)
		return
	}
	var body struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&body); err != nil || !equal(body.Token, s.viewerToken) {
		http.Error(w, "invalid token", 401)
		return
	}
	var nonce [24]byte
	if _, err := rand.Read(nonce[:]); err != nil {
		http.Error(w, "unavailable", 503)
		return
	}
	value := strconv.FormatInt(time.Now().Add(12*time.Hour).Unix(), 10) + "." + base64.RawURLEncoding.EncodeToString(nonce[:])
	secure := r.TLS != nil || r.Header.Get("X-Forwarded-Proto") == "https"
	http.SetCookie(w, &http.Cookie{Name: "spotter_session", Value: value + "." + s.signature(value),
		Path: "/", HttpOnly: true, Secure: secure, SameSite: http.SameSiteStrictMode, MaxAge: 43200})
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) pilot(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet || !equal(r.Header.Get("Authorization"), "Bearer "+s.pilotToken) {
		http.Error(w, "unauthorized", 401)
		return
	}
	// Non-browser agent has no Origin. Browser requests must be same-origin.
	if r.Header.Get("Origin") != "" && !sameOrigin(r) {
		http.Error(w, "forbidden", 403)
		return
	}
	s.mu.Lock()
	if s.connected {
		s.mu.Unlock()
		http.Error(w, "pilot already connected", 409)
		return
	}
	s.connected = true
	s.mu.Unlock()
	defer func() { s.mu.Lock(); s.connected = false; s.mu.Unlock() }()
	upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return r.Header.Get("Origin") == "" || sameOrigin(r) }}
	ackEnabled := r.Header.Get("X-Spotter-Ack") == "1"
	responseHeaders := http.Header{}
	if ackEnabled {
		responseHeaders.Set("X-Spotter-Ack", "1")
	}
	conn, err := upgrader.Upgrade(w, r, responseHeaders)
	if err != nil {
		return
	}
	defer conn.Close()
	worker, err := newWorker(s.root, s.python)
	if err != nil {
		log.Print("compute worker startup failed")
		return
	}
	ctx, cancel := context.WithCancel(r.Context())
	queue := make(chan capturedFrame, 1)
	computeDone := make(chan struct{})
	go func() {
		defer close(computeDone)
		if err := s.calculateFrames(ctx, queue, worker); err != nil && ctx.Err() == nil {
			log.Printf("compute source closed: %s", err)
			_ = conn.Close()
		}
	}()
	defer func() { cancel(); <-computeDone }()
	log.Print("pilot connected; server compute started")
	defer log.Print("pilot disconnected")
	conn.SetReadLimit(maxFrame)
	_ = conn.SetReadDeadline(time.Now().Add(15 * time.Second))
	// Only telemetry refreshes this deadline. A hung collector can still pong.
	stop := make(chan struct{})
	defer close(stop)
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-stop:
				return
			case <-ticker.C:
				if err := conn.WriteControl(websocket.PingMessage, nil, time.Now().Add(time.Second)); err != nil {
					_ = conn.Close()
					return
				}
			}
		}
	}()
	windowStart := time.Now()
	windowFrames := 0
	for {
		typ, raw, err := conn.ReadMessage()
		if err != nil {
			return
		}
		_ = conn.SetReadDeadline(time.Now().Add(15 * time.Second))
		if typ != websocket.TextMessage || !json.Valid(raw) {
			return
		}
		now := time.Now()
		// Permit normal network bursts; cap sustained rate and burst size.
		if now.Sub(windowStart) >= time.Second {
			windowStart = now
			windowFrames = 0
		}
		windowFrames++
		if windowFrames > 60 {
			return
		}
		var compact bytes.Buffer
		if err := json.Compact(&compact, raw); err != nil {
			return
		}
		offerLatest(queue, capturedFrame{raw: append([]byte(nil), compact.Bytes()...), received: now})
		s.mu.Lock()
		s.ingested = now
		s.mu.Unlock()
		// ACK means received for calculation. It must never depend on the CPU
		// time of optional modules, or the existing collector reconnects at 5 s.
		if ackEnabled {
			var frame struct {
				Seq int64 `json:"seq"`
			}
			if err := json.Unmarshal(compact.Bytes(), &frame); err != nil {
				return
			}
			_ = conn.SetWriteDeadline(time.Now().Add(2 * time.Second))
			if err := conn.WriteJSON(struct {
				Type string `json:"type"`
				Seq  int64  `json:"seq"`
			}{"ack", frame.Seq}); err != nil {
				return
			}
		}
	}
}

func (s *Server) envelope() []byte {
	s.mu.Lock()
	defer s.mu.Unlock()
	age := int64(-1)
	ingestAge := int64(-1)
	if !s.received.IsZero() {
		age = time.Since(s.received).Milliseconds()
	}
	if !s.ingested.IsZero() {
		ingestAge = time.Since(s.ingested).Milliseconds()
	}
	data, _ := json.Marshal(struct {
		Type            string          `json:"type"`
		ServerTime      int64           `json:"serverTime"`
		SourceAgeMs     int64           `json:"sourceAgeMs"`
		IngestAgeMs     int64           `json:"ingestAgeMs"`
		SourceConnected bool            `json:"sourceConnected"`
		ComputeMs       float64         `json:"computeMs"`
		State           json.RawMessage `json:"state"`
	}{"update", time.Now().UnixMilli(), age, ingestAge, s.connected, s.computeMs, s.state})
	return data
}

// Desktop status is additive: capture/ACK/compute transport stays unchanged.
// Only an authenticated pilot or viewer may inspect presence and freshness.
func (s *Server) status(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	pilot := equal(r.Header.Get("Authorization"), "Bearer "+s.pilotToken)
	if (!pilot && !s.viewerAuth(r)) || (r.Header.Get("Origin") != "" && !sameOrigin(r)) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	sourceAge, ingestAge := int64(-1), int64(-1)
	if !s.received.IsZero() {
		sourceAge = time.Since(s.received).Milliseconds()
	}
	if !s.ingested.IsZero() {
		ingestAge = time.Since(s.ingested).Milliseconds()
	}
	var state struct {
		Status string `json:"status"`
		Mode   string `json:"mode"`
	}
	_ = json.Unmarshal(s.state, &state)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(struct {
		Version          string   `json:"version"`
		SupportedGames   []string `json:"supportedGames"`
		SourceConnected  bool     `json:"sourceConnected"`
		ViewersConnected int      `json:"viewersConnected"`
		GameStatus       string   `json:"gameStatus"`
		GameMode         string   `json:"gameMode"`
		SourceAgeMs      int64    `json:"sourceAgeMs"`
		IngestAgeMs      int64    `json:"ingestAgeMs"`
		ComputeMs        float64  `json:"computeMs"`
	}{"0.4.7", []string{"lmu", "iracing"}, s.connected, s.viewers, state.Status, state.Mode, sourceAge, ingestAge, s.computeMs})
}

func (s *Server) view(w http.ResponseWriter, r *http.Request) {
	if !s.viewerAuth(r) || !sameOrigin(r) {
		http.Error(w, "unauthorized", 401)
		return
	}
	s.mu.Lock()
	if s.viewers >= 3 {
		s.mu.Unlock()
		http.Error(w, "viewer limit", 429)
		return
	}
	s.viewers++
	s.mu.Unlock()
	defer func() { s.mu.Lock(); s.viewers--; s.mu.Unlock() }()
	upgrader := websocket.Upgrader{CheckOrigin: sameOrigin}
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer conn.Close()
	conn.SetReadLimit(1024)
	_ = conn.SetReadDeadline(time.Now().Add(15 * time.Second))
	conn.SetPongHandler(func(string) error { return conn.SetReadDeadline(time.Now().Add(15 * time.Second)) })
	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()
	go func() {
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				cancel()
				return
			}
		}
	}()
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()
	lastPing := time.Now()
	for {
		if time.Since(lastPing) >= 5*time.Second {
			if err := conn.WriteControl(websocket.PingMessage, nil, time.Now().Add(time.Second)); err != nil {
				return
			}
			lastPing = time.Now()
		}
		_ = conn.SetWriteDeadline(time.Now().Add(2 * time.Second))
		if err := conn.WriteMessage(websocket.TextMessage, s.envelope()); err != nil {
			return
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func main() {
	root := os.Getenv("SPOTTER_ROOT")
	if root == "" {
		var err error
		root, err = filepath.Abs("..")
		if err != nil {
			log.Fatal(err)
		}
	}
	python := os.Getenv("SPOTTER_PYTHON")
	if python == "" {
		python = "python3"
	}
	s := &Server{pilotToken: os.Getenv("SPOTTER_PILOT_TOKEN"), viewerToken: os.Getenv("SPOTTER_VIEW_TOKEN"), root: root, python: python}
	if len(s.pilotToken) < 32 || len(s.viewerToken) < 32 || equal(s.pilotToken, s.viewerToken) {
		log.Fatal("Set distinct SPOTTER_PILOT_TOKEN and SPOTTER_VIEW_TOKEN (at least 32 characters)")
	}
	if _, err := os.Stat(filepath.Join(root, "remote", "compute.py")); err != nil {
		log.Fatal("SPOTTER_ROOT must point to the project checkout")
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/session", s.login)
	mux.HandleFunc("/api/status", s.status)
	mux.HandleFunc("/ws/pilot", s.pilot)
	mux.HandleFunc("/ws/view", s.view)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok","scope":"relay-only"}`))
	})
	web, _ := fs.Sub(assets, "web")
	mux.Handle("/", http.FileServer(http.FS(web)))
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
		mux.ServeHTTP(w, r)
	})
	addr := os.Getenv("SPOTTER_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8080"
	}
	srv := &http.Server{Addr: addr, Handler: handler, ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 8192}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shut, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = srv.Shutdown(shut)
	}()
	fmt.Printf("Spotter listening on %s (single-room prototype)\n", addr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
