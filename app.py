import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st
import streamlit.components.v1 as components

# 讓 streamlit 能夠正確引入所有子目錄
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 載入環境變數
load_dotenv(override=True)

st.set_page_config(page_title="台股開盤預測儀表板", layout="wide")

# --- CSS 調整：隱藏 Streamlit 預設的多餘邊距，讓嵌入的 HTML 能最大化呈現 ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 0rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        iframe {
            border-radius: 12px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            height: 3800px !important;
            min-height: 3800px !important;
        }
    </style>
""", unsafe_allow_html=True)

# 透過隱藏的 iframe 元件為父視窗 window.parent 註冊跨域 PDF 下載事件監聽器
components.html("""
<script>
    if (!window.parent.__message_listener_added) {
        window.parent.__message_listener_added = true;
        console.log('[Parent] Registering download_pdf message listener...');
        window.parent.addEventListener('message', function(event) {
            if (event.data && event.data.type === 'download_pdf') {
                console.log('[Parent] Received download_pdf base64 message, trigger download...');
                try {
                    var base64 = event.data.base64;
                    var filename = event.data.filename;
                    
                    var byteCharacters = atob(base64);
                    var byteNumbers = new Array(byteCharacters.length);
                    for (var i = 0; i < byteCharacters.length; i++) {
                        byteNumbers[i] = byteCharacters.charCodeAt(i);
                    }
                    var byteArray = new Uint8Array(byteNumbers);
                    var blob = new Blob([byteArray], {type: 'application/pdf'});
                    
                    var link = window.parent.document.createElement('a');
                    link.href = window.parent.URL.createObjectURL(blob);
                    link.download = filename;
                    window.parent.document.body.appendChild(link);
                    link.click();
                    window.parent.document.body.removeChild(link);
                    console.log('[Parent] PDF downloaded successfully');
                } catch (err) {
                    console.error('[Parent] Failed to download PDF:', err);
                }
            }
        });
    }
</script>
""", height=0)

# --- Sidebar: API 設定與控制面板 ---
is_windows = sys.platform == "win32"

if not is_windows:
    st.sidebar.info("☁️ **雲端展示模式**\n\n資料抓取與模型預測功能需透過元大 API (限 Windows 平台執行)，因此此雲端頁面僅提供**預測結果展示**。\n\n若要產生最新預測，請於您的本機電腦執行更新。")
    account = password = pfx_path = pfx_pass = ""
    save_btn = False
else:
    st.sidebar.header("🔐 元大 API 設定")
    st.sidebar.markdown("請輸入您的元大 API 憑證與帳號密碼。")

    default_account = os.getenv("YUANTA_ACCOUNT", "")
    default_password = os.getenv("YUANTA_PASSWORD", "")
    default_pfx = os.getenv("YUANTA_PFX_PATH", "")
    default_pfx_pass = os.getenv("YUANTA_PFX_PASSWORD", "")

    account = st.sidebar.text_input(
        "登入帳號 (Account)", 
        value=default_account, 
        help="請輸入元大 API 規定的帳號格式。\n- 證券帳號：S + 4碼分公司 + 7碼帳號 (如 S98875005091)\n- 期貨帳號：F + 10碼分公司 + 7碼帳號 (如 FF021000P001234567)\n※請注意：API 登入不支援直接輸入身分證字號。"
    )
    password = st.sidebar.text_input("密碼 (Password)", value=default_password, type="password")

    st.sidebar.markdown("---")
    st.sidebar.subheader("憑證設定 (PFX)")
    pfx_path = st.sidebar.text_input("憑證檔案路徑", value=default_pfx)
    pfx_pass = st.sidebar.text_input("憑證密碼", value=default_pfx_pass, type="password")

    save_btn = st.sidebar.button("💾 儲存設定並測試連線", use_container_width=True)

# --- Sidebar: 台股開盤預測儀表板 系統控制面板 ---
st.sidebar.markdown("---")
st.sidebar.header("📊 台股開盤預測儀表板")
st.sidebar.subheader("⚙️ 系統控制面板")

# 檢查背景子進程狀態 (絕對路徑)
status_file = os.path.join(ROOT, "outputs", "predict_status.json")
status_data = None
if os.path.exists(status_file):
    try:
        with open(status_file, "r", encoding="utf-8") as sf:
            status_data = json.load(sf)
    except Exception:
        pass

# 檢查進程是否實際還在運行
is_running = False
if status_data and status_data.get("status") == "running":
    pid = status_data.get("pid", -1)
    if pid > 0:
        try:
            try:
                import psutil
                is_running = psutil.pid_exists(pid)
            except Exception:
                if os.name == "nt":
                    import ctypes
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    if handle:
                        kernel32.CloseHandle(handle)
                        is_running = True
                    else:
                        err_code = kernel32.GetLastError()
                        is_running = (err_code == 5)
                else:
                    os.kill(pid, 0)
                    is_running = True
        except Exception:
            is_running = False

if "last_processed_time" not in st.session_state:
    st.session_state.last_processed_time = None

# --- 自動背景過期檢查與刷新 ---
html_file_path = os.path.join(ROOT, "outputs", "dashboard.html")
auto_update_interval = 300  # 5分鐘

should_auto_trigger = False
if os.path.exists(html_file_path):
    last_mod = os.path.getmtime(html_file_path)
    elapsed = time.time() - last_mod
    if elapsed > auto_update_interval:
        should_auto_trigger = True
else:
    should_auto_trigger = True

if is_windows and should_auto_trigger and not is_running:
    env = os.environ.copy()
    env["YUANTA_ACCOUNT"] = account
    env["YUANTA_PASSWORD"] = password
    env["YUANTA_PFX_PATH"] = pfx_path
    env["YUANTA_PFX_PASSWORD"] = pfx_pass
    
    import subprocess
    try:
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NO_WINDOW
        
        python_exe = sys.executable
        subprocess.Popen(
            [python_exe, "pipeline/run.py"],
            env=env,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags
        )
        is_running = True
        st.toast("🔄 儀表板數據已過期，已自動在背景啟動預測流程！", icon="⏳")
    except Exception as e:
        pass

# 1. 抓取最新夜盤報價按鈕
if is_windows and st.sidebar.button("🔄 抓取最新 TXFPM1 報價", use_container_width=True):
    with st.sidebar.spinner("連線至元大 API 中..."):
        import subprocess
        env = os.environ.copy()
        env["YUANTA_ACCOUNT"] = account
        env["YUANTA_PASSWORD"] = password
        env["YUANTA_PFX_PATH"] = pfx_path
        env["YUANTA_PFX_PASSWORD"] = pfx_pass
        
        try:
            result = subprocess.run(
                [sys.executable, "utils/fetch_txf.py"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout.strip())
                    if "error" in data:
                        st.sidebar.error(data["error"])
                    else:
                        st.sidebar.success("抓取成功！")
                        st.sidebar.json(data["data"])
                except Exception:
                    st.sidebar.error("無法解析輸出資料")
                    st.sidebar.code(result.stdout)
            else:
                st.sidebar.error("抓取失敗")
                st.sidebar.code(result.stderr or result.stdout)
        except Exception as e:
            st.sidebar.error(f"執行錯誤: {e}")

# 2. 執行預測與重新整理按鈕
if is_windows and is_running:
    if st.sidebar.button("🔄 重新整理檢測狀態", use_container_width=True):
        st.rerun()
elif is_windows:
    if st.sidebar.button("🚀 執行完整預測流程", use_container_width=True):
        env = os.environ.copy()
        env["YUANTA_ACCOUNT"] = account
        env["YUANTA_PASSWORD"] = password
        env["YUANTA_PFX_PATH"] = pfx_path
        env["YUANTA_PFX_PASSWORD"] = pfx_pass
        
        import subprocess
        try:
            creation_flags = 0
            if os.name == "nt":
                creation_flags = subprocess.CREATE_NO_WINDOW
            
            python_exe = sys.executable
            subprocess.Popen(
                [python_exe, "pipeline/run.py"],
                env=env,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            st.toast("🚀 預報 Pipeline 已於背景成功啟動！")
            import time
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"無法啟動預測子進程: {e}")

# 狀態提示與結果處理
if is_windows and is_running:
    st.sidebar.info("⏳ 預測流程執行中，請稍候... (此過程為非同步背景執行，網頁不會卡死)")
elif is_windows and status_data:
        status_val = status_data.get("status")
        task_time = status_data.get("end_time") or status_data.get("error") or "error_fallback"
        
        if task_time != st.session_state.last_processed_time:
            st.session_state.last_processed_time = task_time
            if status_val == "success":
                st.sidebar.success("🎉 預測流程執行完成！")
                try:
                    os.remove(status_file)
                except Exception:
                    try:
                        with open(status_file, "w", encoding="utf-8") as sf:
                            json.dump({"status": "idle"}, sf)
                    except Exception:
                        pass
            elif status_val == "failed":
                st.sidebar.error(f"❌ 預測流程執行失敗！錯誤資訊：{status_data.get('error')}")
                try:
                    os.remove(status_file)
                except Exception:
                    try:
                        with open(status_file, "w", encoding="utf-8") as sf:
                            json.dump({"status": "idle"}, sf)
                    except Exception:
                        pass

# --- 📊 預測儀表板 (直接滿版嵌入產出的 HTML) ---
html_path = os.path.join(ROOT, "outputs", "dashboard.html")

if os.path.exists(html_path):
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # 透過在 HTML 末端附加時間戳記註解來破除 Streamlit 內置快取，強迫重新渲染
        html_content += f"\n<!-- cache_breaker: {datetime.now().timestamp()} -->"
        components.html(html_content, height=3800, scrolling=True)
    except Exception as e:
        st.error(f"無法渲染儀表板 HTML: {e}")
else:
    st.info("尚未產生預測儀表板 HTML，請先執行預測流程。")

# --- 隱藏自動重新整理按鈕與 JS 定時點擊器 ---
st.button("AUTO_RERUN", key="auto_rerun_trigger_btn")

components.html("""
<script>
    // 輪詢隱藏 AUTO_RERUN 按鈕的 Streamlit 容器，避免畫面閃爍
    var hideInterval = setInterval(function() {
        try {
            var buttons = window.parent.document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].textContent.trim() === 'AUTO_RERUN') {
                    var container = buttons[i].closest('div[data-testid="stButton"]');
                    if (container) {
                        container.style.display = 'none';
                        clearInterval(hideInterval);
                        console.log('[AutoRefresh] Hidden auto_rerun button container.');
                        break;
                    }
                }
            }
        } catch (e) {}
    }, 50);

    // 30秒後自動點擊該按鈕以觸發 Rerun
    setTimeout(function() {
        try {
            var buttons = window.parent.document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].textContent.trim() === 'AUTO_RERUN') {
                    buttons[i].click();
                    console.log('[AutoRefresh] Silent rerun triggered.');
                    break;
                }
            }
        } catch (e) {
            console.error('[AutoRefresh] Failed to click rerun button:', e);
        }
    }, 30000);
</script>
""", height=0)

if save_btn:
    st.toast("設定已儲存！", icon="✅")

