package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"
)

const (
	tokenURL = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
	statusURL = "https://qrcodeapi.115.com/get/status/"
	qrURL = "https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid=%s"
)

var validApps = map[string]bool{
	"web": true, "android": true, "ios": true, "linux": true, "mac": true,
	"windows": true, "tv": true, "alipaymini": true, "wechatmini": true, "qandroid": true,
}

type apiResponse struct {
	State any             `json:"state"`
	Error string          `json:"error"`
	Msg   string          `json:"msg"`
	Data  json.RawMessage `json:"data"`
}

type tokenData struct {
	UID  string `json:"uid"`
	Time int64  `json:"time"`
	Sign string `json:"sign"`
}

type statusData struct {
	Status int `json:"status"`
}

type loginData struct {
	Cookie map[string]string `json:"cookie"`
}

func main() {
	app := flag.String("app", "tv", "115 app type: web/android/ios/linux/mac/windows/tv/alipaymini/wechatmini/qandroid")
	cookiePath := flag.String("cookie-path", "~/.115-cookies", "path to save cookies")
	qrPath := flag.String("qr-path", "", "path to save the QR code image")
	noSave := flag.Bool("no-save", false, "print cookies without saving")
	printCookie := flag.Bool("print-cookie", false, "print cookies after successful login")
	noOpen := flag.Bool("no-open", false, "do not open QR code image")
	poll := flag.Duration("poll", 2*time.Second, "QR status polling interval")
	flag.Parse()

	if !validApps[*app] {
		fatalf("unsupported app %q", *app)
	}

	client := &http.Client{Timeout: 15 * time.Second}
	token, err := getToken(client)
	if err != nil {
		fatalf("get QR token failed: %v", err)
	}

	qr := fmt.Sprintf(qrURL, url.QueryEscape(token.UID))
	qrFile, err := saveQRImage(client, qr, *qrPath, token.UID)
	if err != nil {
		fatalf("save QR code failed: %v", err)
	}
	fmt.Println("Open this URL and scan with the 115 app:")
	printQRInstructions(qrFile, qr)
	fmt.Printf("If the agent cannot render the image, open this file and scan it manually: %s\n", qrFile)
	if !*noOpen {
		if err := openBrowser(qrFile); err != nil {
			fmt.Fprintf(os.Stderr, "warning: failed to open QR image: %v\n", err)
		}
	}

	if err := waitForLogin(client, token, *poll); err != nil {
		fatalf("QR login failed: %v", err)
	}

	cookies, err := getLoginCookies(client, token.UID, *app)
	if err != nil {
		fatalf("get login cookies failed: %v", err)
	}
	cookieText := formatCookies(cookies)

	if !*noSave {
		path, err := expandPath(*cookiePath)
		if err != nil {
			fatalf("resolve cookie path failed: %v", err)
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			fatalf("create cookie directory failed: %v", err)
		}
		if err := os.WriteFile(path, []byte(cookieText), 0o600); err != nil {
			fatalf("save cookies failed: %v", err)
		}
		fmt.Printf("Cookies saved to: %s\n", path)
	}

	if *printCookie || *noSave {
		fmt.Println(cookieText)
	}
}

func getToken(client *http.Client) (tokenData, error) {
	var token tokenData
	resp, err := getJSON(client, tokenURL, nil)
	if err != nil {
		return token, err
	}
	if err := decodeData(resp, &token); err != nil {
		return token, err
	}
	if token.UID == "" || token.Sign == "" || token.Time == 0 {
		return token, fmt.Errorf("unexpected token response: %s", string(resp.Data))
	}
	return token, nil
}

func saveQRImage(client *http.Client, qr, requestedPath, uid string) (string, error) {
	if requestedPath == "" {
		requestedPath = filepath.Join(os.TempDir(), "115-login-qrcode-"+uid+".png")
	}
	path, err := expandPath(requestedPath)
	if err != nil {
		return "", err
	}
	req, err := http.NewRequest(http.MethodGet, qr, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "115-cookie-helper/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(data))
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return "", err
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		return "", err
	}
	return path, nil
}

func waitForLogin(client *http.Client, token tokenData, poll time.Duration) error {
	query := url.Values{}
	query.Set("uid", token.UID)
	query.Set("time", fmt.Sprint(token.Time))
	query.Set("sign", token.Sign)

	for {
		time.Sleep(poll)
		resp, err := getJSON(client, statusURL+"?"+query.Encode(), nil)
		if err != nil {
			fmt.Printf("[status=?] status API did not respond, still waiting for scan confirmation... (%v)\n", err)
			continue
		}
		var status statusData
		if err := decodeData(resp, &status); err != nil {
			return err
		}
		switch status.Status {
		case 0:
			fmt.Println("[status=0] waiting for scan...")
		case 1:
			fmt.Println("[status=1] scanned, confirm on your phone...")
		case 2:
			fmt.Println("[status=2] signed in.")
			return nil
		case -1:
			return errors.New("QR code expired")
		case -2:
			return errors.New("login canceled")
		default:
			return fmt.Errorf("unexpected QR status: %d", status.Status)
		}
	}
}

func printQRInstructions(qrFile, qr string) {
	fileURI := pathToFileURI(qrFile)
	markdown := fmt.Sprintf("![115 登录二维码](%s)", filepath.ToSlash(qrFile))
	payload := map[string]string{
		"type":        "115-login-qr",
		"image_path":  qrFile,
		"image_uri":   fileURI,
		"remote_url":  qr,
		"markdown":    markdown,
		"instruction": "请用 115 App 扫码，并在手机上确认登录。",
	}
	data, err := json.Marshal(payload)
	if err != nil {
		data = []byte("{}")
	}
	fmt.Printf("QR_IMAGE_PATH: %s\n", qrFile)
	fmt.Printf("QR_FILE_URI: %s\n", fileURI)
	fmt.Printf("QR_REMOTE_URL: %s\n", qr)
	fmt.Printf("QR_MARKDOWN: %s\n", markdown)
	fmt.Printf("LOGIN_QR_JSON: %s\n", data)
}

func pathToFileURI(path string) string {
	slashPath := filepath.ToSlash(path)
	if runtime.GOOS == "windows" && len(slashPath) >= 2 && slashPath[1] == ':' {
		slashPath = "/" + slashPath
	}
	if !strings.HasPrefix(slashPath, "/") {
		slashPath = "/" + slashPath
	}
	return (&url.URL{Scheme: "file", Path: slashPath}).String()
}

func getLoginCookies(client *http.Client, uid, app string) (map[string]string, error) {
	form := url.Values{}
	form.Set("app", app)
	form.Set("account", uid)
	api := fmt.Sprintf("https://passportapi.115.com/app/1.0/%s/1.0/login/qrcode/", app)
	resp, err := getJSON(client, api, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, err
	}
	var login loginData
	if err := decodeData(resp, &login); err != nil {
		return nil, err
	}
	if len(login.Cookie) == 0 {
		return nil, fmt.Errorf("response has no data.cookie: %s", string(resp.Data))
	}
	return login.Cookie, nil
}

func getJSON(client *http.Client, endpoint string, body io.Reader) (apiResponse, error) {
	method := http.MethodGet
	var contentType string
	if body != nil {
		method = http.MethodPost
		contentType = "application/x-www-form-urlencoded"
	}
	req, err := http.NewRequest(method, endpoint, body)
	if err != nil {
		return apiResponse{}, err
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	req.Header.Set("User-Agent", "115-cookie-helper/1.0")

	httpResp, err := client.Do(req)
	if err != nil {
		return apiResponse{}, err
	}
	defer httpResp.Body.Close()

	data, err := io.ReadAll(httpResp.Body)
	if err != nil {
		return apiResponse{}, err
	}
	if httpResp.StatusCode < 200 || httpResp.StatusCode >= 300 {
		return apiResponse{}, fmt.Errorf("HTTP %d: %s", httpResp.StatusCode, string(data))
	}

	var resp apiResponse
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := decoder.Decode(&resp); err != nil {
		return apiResponse{}, err
	}
	if isFalse(resp.State) {
		msg := resp.Error
		if msg == "" {
			msg = resp.Msg
		}
		if msg == "" {
			msg = string(data)
		}
		return apiResponse{}, errors.New(msg)
	}
	return resp, nil
}

func decodeData(resp apiResponse, out any) error {
	if len(resp.Data) == 0 || string(resp.Data) == "null" {
		return errors.New("missing data field")
	}
	return json.Unmarshal(resp.Data, out)
}

func isFalse(value any) bool {
	switch v := value.(type) {
	case bool:
		return !v
	case json.Number:
		i, err := v.Int64()
		return err == nil && i == 0
	case float64:
		return v == 0
	case string:
		return v == "false" || v == "0"
	default:
		return false
	}
}

func formatCookies(cookies map[string]string) string {
	preferred := []string{"UID", "CID", "SEID", "KID"}
	used := make(map[string]bool, len(cookies))
	parts := make([]string, 0, len(cookies))
	for _, key := range preferred {
		if value, ok := cookies[key]; ok {
			parts = append(parts, key+"="+value)
			used[key] = true
		}
	}
	var rest []string
	for key := range cookies {
		if !used[key] {
			rest = append(rest, key)
		}
	}
	sort.Strings(rest)
	for _, key := range rest {
		parts = append(parts, key+"="+cookies[key])
	}
	return strings.Join(parts, "; ")
}

func expandPath(path string) (string, error) {
	if path == "" {
		return "", errors.New("empty path")
	}
	if path == "~" || strings.HasPrefix(path, "~/") || strings.HasPrefix(path, `~\`) {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		if path == "~" {
			return home, nil
		}
		return filepath.Join(home, path[2:]), nil
	}
	return filepath.Abs(path)
}

func openBrowser(target string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", target)
	case "darwin":
		cmd = exec.Command("open", target)
	default:
		cmd = exec.Command("xdg-open", target)
	}
	return cmd.Start()
}

func fatalf(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "Error: "+format+"\n", args...)
	os.Exit(1)
}
