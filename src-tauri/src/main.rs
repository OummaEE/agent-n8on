#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

mod installer;

use std::io::Write;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use serde::Serialize;
use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem, Window, WindowEvent,
};

// ============================================================
// PRE-UNINSTALL CLEANUP SCRIPT
// Written to %APPDATA%\Agent n8On\cleanup.ps1 during installation.
// Called by NSIS un.onInit before any files are deleted.
// ============================================================
const CLEANUP_SCRIPT: &str = r#"
$ErrorActionPreference = "SilentlyContinue"

# 1. СНАЧАЛА читаем config, пока он ещё существует
$configPath = "$env:APPDATA\Agent n8On\config.json"
$removeOllama = $false
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        if ($config.installed_by_agent.ollama -eq $true) {
            $removeOllama = $true
        }
    } catch {
        Write-Host "Could not read config.json"
    }
}

# 2. ПОТОМ удаляем Ollama если нужно
if ($removeOllama) {
    Write-Host "Removing Ollama..."
    Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama"
    if (Test-Path $ollamaPath) {
        Remove-Item -Path $ollamaPath -Recurse -Force
    }
    Write-Host "Ollama removed"
}

# 3. Удаляем runtime
$runtimePath = "$env:LOCALAPPDATA\Agent n8On\runtime"
if (Test-Path $runtimePath) {
    Write-Host "Removing runtime..."
    Remove-Item -Path $runtimePath -Recurse -Force
    Write-Host "Runtime removed"
}

# 4. В КОНЦЕ удаляем app data (включая config.json)
$appDataPath = "$env:APPDATA\Agent n8On"
if (Test-Path $appDataPath) {
    Write-Host "Removing app data..."
    Remove-Item -Path $appDataPath -Recurse -Force
    Write-Host "App data removed"
}

$localAppDataPath = "$env:LOCALAPPDATA\Agent n8On"
if (Test-Path $localAppDataPath) {
    Remove-Item -Path $localAppDataPath -Recurse -Force
}

Write-Host "Cleanup complete"
"#;

// ============================================================
// UNINSTALL WRAPPER SCRIPT
// Written to %APPDATA%\Agent n8On\uninstall_wrapper.ps1 during installation.
// The registry UninstallString is replaced with a call to this script so that
// "Programs & Features" → Uninstall runs cleanup first, then the real NSIS uninstaller.
// ============================================================
const UNINSTALL_WRAPPER_SCRIPT: &str = r#"
# Agent n8On uninstall wrapper
# Called by Windows when user clicks Uninstall in Programs & Features.
# 1) Runs cleanup.ps1  (dialog: remove Ollama / models / Node.js / n8n?)
# 2) Restores the real NSIS UninstallString and runs the NSIS uninstaller.

# Step 1: user-facing cleanup dialog
$cleanup = "$env:APPDATA\Agent n8On\cleanup.ps1"
if (Test-Path $cleanup) {
    & powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$cleanup"
}

# Step 2: find our registry key, restore original UninstallString, run real uninstaller
$regRoot = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$appKey = Get-ChildItem $regRoot -EA 0 |
    Get-ItemProperty -EA 0 |
    Where-Object { $_.DisplayName -eq 'Agent n8On' } |
    Select-Object -First 1

if ($appKey -and $appKey._RealUninstallString) {
    $realCmd = $appKey._RealUninstallString
    # Restore so re-runs of uninstaller work cleanly
    Set-ItemProperty -Path $appKey.PSPath -Name UninstallString -Value $realCmd -EA 0
    # Run real NSIS uninstaller silently
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$realCmd`" /S" -Wait -EA 0
} else {
    # Fallback: look for NSIS uninstall.exe in typical locations
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Agent n8On\uninstall.exe",
        "$env:PROGRAMFILES\Agent n8On\uninstall.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) {
            Start-Process $p -ArgumentList "/S" -Wait
            break
        }
    }
}
"#;

// ============================================================
// FILE LOGGER  (%APPDATA%\Agent n8On\debug.log)
// ============================================================

static LOG_LOCK: Mutex<()> = Mutex::new(());

fn log_path() -> String {
    let appdata = std::env::var("APPDATA").unwrap_or_else(|_| ".".to_string());
    format!("{}/Agent n8On/debug.log", appdata)
}

/// Append a timestamped line to the debug log.
/// Timestamp = seconds since Unix epoch (no chrono dep needed).
fn log(msg: &str) {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    // Format: "T+<epoch>  <msg>\n"
    let line = format!("T+{}  {}\n", secs, msg);

    let _lock = LOG_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let path = log_path();
    // Ensure directory exists (silently ignore errors)
    if let Some(parent) = std::path::Path::new(&path).parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let _ = f.write_all(line.as_bytes());
    }
    // Mirror to console so dev builds still show output
    print!("{}", line);
}

// ============================================================
// BACKEND PROCESS MANAGEMENT
// ============================================================

struct BackendState {
    process: Mutex<Option<Child>>,
}

/// Find the directory whose `backend/n8on.py` exists.
/// Returns that directory so callers can use `<result>/backend/`.
///
/// Tauri bundles `../backend/**/*` (relative to src-tauri/) which NSIS
/// installs under `$INSTDIR\_up_\backend\`.  We must therefore probe
/// both `<exe_parent>/backend/` AND `<exe_parent>/_up_/backend/`.
/// For dev builds the exe lives three levels deep inside the project
/// tree, so we also try walking up to the project root.
fn resolve_resource_dir(app_handle: &tauri::AppHandle) -> String {
    log(&format!("resolve_resource_dir: exe={:?}", std::env::current_exe()));

    let exe_parent: Option<std::path::PathBuf> = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()));

    // Build candidate list in priority order
    let mut candidates: Vec<std::path::PathBuf> = Vec::new();
    if let Some(ref ep) = exe_parent {
        // NSIS install: resources with "../" prefix land under "_up_/"
        candidates.push(ep.join("_up_"));
        // Direct sibling (unlikely but harmless to check)
        candidates.push(ep.clone());
        // Dev builds: exe is at src-tauri/target/{debug|release}/
        // so three levels up reaches the project root where backend/ lives
        candidates.push(ep.join("..").join("..").join(".."));
    }
    // Tauri resource_dir() as a final backstop
    if let Some(rd) = app_handle.path_resolver().resource_dir() {
        candidates.push(rd.join("_up_"));
        candidates.push(rd.clone());
    }

    for candidate in &candidates {
        let probe = candidate.join("backend").join("n8on.py");
        log(&format!("resolve_resource_dir: probing {}", probe.display()));
        if probe.exists() {
            // Canonicalize to collapse any ".." segments, then strip \\?\ prefix on Windows
            let resolved = candidate
                .canonicalize()
                .unwrap_or_else(|_| candidate.clone())
                .to_string_lossy()
                .to_string();
            #[cfg(target_os = "windows")]
            let resolved = resolved
                .strip_prefix(r"\\?\")
                .unwrap_or(&resolved)
                .to_string();
            log(&format!("resolve_resource_dir: FOUND → {}", resolved));
            return resolved;
        }
    }

    // Nothing found — log every candidate so the user can send us the log
    log("resolve_resource_dir: ERROR — backend/n8on.py not found in any candidate:");
    for c in &candidates {
        log(&format!("  tried: {}", c.display()));
    }
    // Return exe parent as a last resort so start_backend() can log a clear error
    exe_parent
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|| ".".to_string())
}

fn start_backend(resource_dir: &str) -> Option<Child> {
    let base = std::path::Path::new(resource_dir);
    let backend_dir = base.join("backend");
    let backend_script = backend_dir.join("n8on.py");
    let python_embed = backend_dir.join("python-embed").join("python.exe");

    log(&format!("start_backend: resource_dir={}", resource_dir));
    log(&format!("start_backend: backend_script={} exists={}", backend_script.display(),
        backend_script.exists()));

    if !backend_script.exists() {
        log(&format!("start_backend: ERROR — script not found at {}", backend_script.display()));
        return None;
    }

    // Prefer embedded Python runtime; fall back to system Python
    let python_exe: std::path::PathBuf = if python_embed.exists() {
        log(&format!("start_backend: using embedded Python → {}", python_embed.display()));
        python_embed.clone()
    } else {
        log(&format!("start_backend: embedded Python NOT found at {}, falling back to system 'python'", python_embed.display()));
        std::path::PathBuf::from("python")
    };

    log(&format!("start_backend: spawning: {} {} --no-browser", python_exe.display(), backend_script.display()));

    match Command::new(&python_exe)
        .arg(&backend_script)
        .arg("--no-browser")
        .current_dir(&backend_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(mut child) => {
            let pid = child.id();
            log(&format!("start_backend: spawned PID={}", pid));

            // Watchdog thread: drains stderr and logs it when backend exits.
            // Blocks until the process closes its stderr handle (i.e., process exits).
            if let Some(stderr) = child.stderr.take() {
                thread::spawn(move || {
                    use std::io::Read;
                    let mut output = String::new();
                    let _ = std::io::BufReader::new(stderr).read_to_string(&mut output);
                    if output.is_empty() {
                        log(&format!("backend PID={} exited (no stderr output)", pid));
                    } else {
                        log(&format!("backend PID={} exited with stderr:\n{}", pid, output.trim()));
                    }
                });
            }

            Some(child)
        }
        Err(e) => {
            log(&format!("start_backend: FAILED to spawn (python={}) — {}", python_exe.display(), e));
            None
        }
    }
}

fn stop_backend(state: &BackendState) {
    if let Ok(mut guard) = state.process.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn is_backend_running() -> bool {
    use std::net::TcpStream;
    TcpStream::connect("127.0.0.1:5000").is_ok()
}

fn wait_for_backend(max_seconds: u32) -> bool {
    for _ in 0..max_seconds {
        if is_backend_running() {
            return true;
        }
        thread::sleep(Duration::from_secs(1));
    }
    false
}

// ============================================================
// SYSTEM TRAY
// ============================================================

fn create_system_tray() -> SystemTray {
    let show = CustomMenuItem::new("show".to_string(), "Открыть Agent n8On");
    let restart_item = CustomMenuItem::new("restart".to_string(), "Перезапустить");
    let quit = CustomMenuItem::new("quit".to_string(), "Выход");
    let tray_menu = SystemTrayMenu::new()
        .add_item(show)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(restart_item)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit);
    SystemTray::new().with_menu(tray_menu)
}

// ============================================================
// BASIC COMMANDS
// ============================================================

#[tauri::command]
fn check_backend_status() -> bool {
    is_backend_running()
}

#[tauri::command]
fn restart_backend(state: tauri::State<BackendState>, app_handle: tauri::AppHandle) -> bool {
    stop_backend(&state);
    thread::sleep(Duration::from_secs(1));
    let resource_dir = resolve_resource_dir(&app_handle);
    if let Some(child) = start_backend(&resource_dir) {
        *state.process.lock().unwrap() = Some(child);
        wait_for_backend(10)
    } else {
        false
    }
}

// ============================================================
// INSTALLER COMMANDS
// ============================================================

#[derive(Serialize)]
struct ModelInfo {
    name: String,
    display_name: String,
    description: String,
    size_gb: f32,
    recommended: bool,
    disabled: bool,
    disabled_reason: String,
}

fn model_disabled_reason(
    model: &installer::ModelOption,
    caps: &installer::SystemCapabilities,
) -> (bool, String) {
    // GPU is considered available only if VRAM ≥ 4 GB is detected
    let has_gpu = caps.vram_gb.map(|v| v >= 4).unwrap_or(false);

    // Models that list min_vram_gb require a real GPU
    if model.min_vram_gb.is_some() {
        if !has_gpu {
            return (
                true,
                "Нет GPU (нужна видеокарта с ≥4 GB VRAM). На CPU работает очень медленно.".to_string(),
            );
        }
    }

    // RAM check applies to all models
    if caps.ram_gb < model.min_ram_gb {
        return (
            true,
            format!(
                "Недостаточно RAM: нужно ≥{} GB, у вас {} GB.",
                model.min_ram_gb, caps.ram_gb
            ),
        );
    }

    // 14B without GPU but with enough RAM: warn even if RAM is formally ok
    if model.min_vram_gb.is_some() && !has_gpu && caps.ram_gb >= model.min_ram_gb {
        return (
            true,
            "Нет GPU. Модель 14B без видеокарты работает неприемлемо медленно.".to_string(),
        );
    }

    (false, String::new())
}

#[derive(Serialize)]
struct SystemInfo {
    ram_gb: u64,
    vram_gb: Option<u64>,
    gpu_name: Option<String>,
    free_disk_gb: u64,
    recommendation: String,
    models: Vec<ModelInfo>,
}

#[tauri::command]
async fn check_system() -> Result<SystemInfo, String> {
    log("check_system: called");
    let caps = installer::detect_system();
    let recommended = installer::recommend_model(&caps);

    let models = installer::MODELS
        .iter()
        .map(|m| {
            let (disabled, disabled_reason) = model_disabled_reason(m, &caps);
            ModelInfo {
                name: m.ollama_name.to_string(),
                display_name: m.name.to_string(),
                description: m.description.to_string(),
                size_gb: m.size_gb,
                recommended: m.ollama_name == recommended.ollama_name && !disabled,
                disabled,
                disabled_reason,
            }
        })
        .collect();

    let recommendation = match (caps.vram_gb, caps.gpu_name.as_deref(), caps.ram_gb) {
        // Known VRAM ≥ 8 GB — recommend the best model
        (Some(v), _, _) if v >= 8 => {
            "Ваш компьютер мощный! Рекомендуем продвинутую модель.".to_string()
        }
        // GPU detected but VRAM couldn't be determined (e.g. Hyper-V / virtual GPU)
        (None, Some(gpu), r) if r >= 16 => {
            format!(
                "Видеокарта: {} (VRAM не определён). Для CPU рекомендуем 7B модель.",
                gpu
            )
        }
        (None, Some(gpu), _) => {
            format!(
                "Видеокарта: {} (VRAM не определён). Рекомендуем лёгкую 3B модель.",
                gpu
            )
        }
        // No GPU / low VRAM, but plenty of RAM — balanced recommendation
        (_, _, r) if r >= 16 => {
            "Нет GPU. Рекомендуем 7B модель — работает на CPU при ≥16 GB RAM.".to_string()
        }
        _ => "Рекомендуем лёгкую 3B модель для стабильной работы без GPU.".to_string(),
    };

    log(&format!("check_system: ram={}GB vram={:?}GB gpu={:?} disk={}GB",
        caps.ram_gb, caps.vram_gb, caps.gpu_name, caps.free_disk_gb));
    Ok(SystemInfo {
        ram_gb: caps.ram_gb,
        vram_gb: caps.vram_gb,
        gpu_name: caps.gpu_name,
        free_disk_gb: caps.free_disk_gb,
        recommendation,
        models,
    })
}

fn emit_progress(window: &Window, component: &str, status: &str, progress: u32, message: &str) {
    let _ = window.emit(
        "install-progress",
        serde_json::json!({
            "component": component,
            "status": status,
            "progress": progress,
            "message": message,
        }),
    );
}

#[tauri::command]
async fn run_installation(
    model: String,
    n8n_option: String,
    window: Window,
) -> Result<(), String> {
    log(&format!("run_installation: model='{}' n8n_option='{}'", model, n8n_option));
    // Agent n8On already installed (we are running it)
    emit_progress(&window, "agent", "done", 10, "Agent n8On установлен");

    // Track what was already present BEFORE we install anything.
    // This flag goes into config.json so the uninstaller knows what to remove.
    let ollama_was_missing = !installer::is_ollama_installed();

    // Ollama installation check
    emit_progress(&window, "ollama", "progress", 12, "Проверка Ollama...");
    if ollama_was_missing {
        let w = window.clone();
        installer::install_ollama(move |p, msg| {
            emit_progress(&w, "ollama", "progress", 12 + p / 6, msg);
        })
        .await?;
    }

    // Start Ollama service and WAIT for it to be fully ready.
    // start_ollama_service() polls HTTP /api/tags for up to 180s — blocking,
    // so it runs on the blocking thread pool and we .await the handle.
    emit_progress(&window, "ollama", "progress", 30, "Запуск Ollama...");
    let w_ollama = window.clone();
    let ollama_handle = tokio::task::spawn_blocking(move || {
        installer::start_ollama_service(|_pct, msg| {
            // Mirror live timer updates to the UI (15s / 30s / 45s+ milestones)
            emit_progress(&w_ollama, "ollama", "progress", 35, msg);
        })
    });
    match ollama_handle.await {
        Ok(Ok(_)) => {
            emit_progress(&window, "ollama", "done", 42, "Ollama готова");
        }
        Ok(Err(e)) => {
            // Fatal: Ollama did not start within 60s. Do not proceed to pull_model.
            return Err(format!("Ollama не запустилась: {}", e));
        }
        Err(e) => {
            return Err(format!("Внутренняя ошибка запуска Ollama: {}", e));
        }
    }

    // Model download via Ollama API
    emit_progress(
        &window,
        "model",
        "progress",
        45,
        &format!("Скачивание {}...", model),
    );
    let w2 = window.clone();
    let m = model.clone();
    installer::pull_model(&m, move |p, msg| {
        emit_progress(&w2, "model", "progress", 45 + p / 3, msg);
    })
    .await?;
    emit_progress(&window, "model", "done", 82, "Модель установлена");

    // Persist selected model + installed_by_agent flags so:
    //   (a) Python backend reads the correct model on startup
    //   (b) Uninstaller cleanup.ps1 knows what to remove
    {
        let appdata = std::env::var("APPDATA").unwrap_or_else(|_| ".".to_string());
        let config_path = format!("{}/Agent n8On/config.json", appdata);
        let config = serde_json::json!({
            "model": model,
            "installed_by_agent": {
                "ollama": ollama_was_missing,
            },
        });
        let _ = std::fs::write(&config_path, config.to_string());
        log(&format!("run_installation: saved model='{}' installed_by_agent.ollama={} to config.json",
            model, ollama_was_missing));

        // Write pre-uninstall cleanup script
        let cleanup_path = format!("{}/Agent n8On/cleanup.ps1", appdata);
        if std::fs::write(&cleanup_path, CLEANUP_SCRIPT).is_ok() {
            log("run_installation: cleanup.ps1 written to APPDATA");
        }

        // Write uninstall wrapper (intercepts Programs & Features → Uninstall)
        let wrapper_path = format!("{}/Agent n8On/uninstall_wrapper.ps1", appdata);
        if std::fs::write(&wrapper_path, UNINSTALL_WRAPPER_SCRIPT).is_ok() {
            log("run_installation: uninstall_wrapper.ps1 written to APPDATA");
        }
    }

    // n8n installation — download pre-built portable runtime (Node.js + n8n)
    if n8n_option == "local" {
        installer::download_and_extract_runtime(&window).await?;

        let w4 = window.clone();
        tokio::task::spawn_blocking(move || {
            let _ = installer::start_n8n_service();
            emit_progress(&w4, "n8n", "done", 100, "n8n запущен");
        });
    }

    emit_progress(&window, "complete", "done", 100, "Установка завершена!");
    Ok(())
}

#[tauri::command]
async fn complete_setup(launch_app: bool, app_handle: tauri::AppHandle) -> Result<(), String> {
    installer::mark_setup_complete();

    // Wrap the NSIS UninstallString so "Programs & Features" runs our cleanup first.
    // Uses $env:APPDATA inside PS to avoid all Rust/PS path-escaping issues.
    log("complete_setup: patching registry UninstallString");
    {
        // Use a PS script that resolves its own paths via $env:APPDATA — no Rust escaping needed.
        let ps_cmd = r#"
$log = "$env:APPDATA\Agent n8On\uninstall.log"
Add-Content $log "registry-wrap: started at $(Get-Date)"

$wrapper = "$env:APPDATA\Agent n8On\uninstall_wrapper.ps1"
$regRoot  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'

# Also check HKLM in case installer ran with elevation
$appKey = $null
foreach ($hive in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
                     'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                     'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
    $appKey = Get-ChildItem $hive -EA 0 |
        Get-ItemProperty -EA 0 |
        Where-Object { $_.DisplayName -eq 'Agent n8On' } |
        Select-Object -First 1
    if ($appKey) { Add-Content $log "registry-wrap: found key in $hive: $($appKey.PSChildName)"; break }
}

if (-not $appKey) {
    Add-Content $log "registry-wrap: ERROR — key not found. All Agent-related keys:"
    foreach ($hive in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
                         'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')) {
        Get-ChildItem $hive -EA 0 | Get-ItemProperty -EA 0 |
            Where-Object { $_.DisplayName -like '*Agent*' -or $_.DisplayName -like '*n8*' } |
            ForEach-Object { Add-Content $log "  DisplayName=$($_.DisplayName) Key=$($_.PSChildName)" }
    }
} elseif ($appKey.UninstallString -like '*uninstall_wrapper*') {
    Add-Content $log "registry-wrap: already patched, skipping"
} else {
    $real = $appKey.UninstallString
    Add-Content $log "registry-wrap: original UninstallString=$real"
    New-ItemProperty -Path $appKey.PSPath -Name _RealUninstallString -Value $real -Force -EA 0 | Out-Null
    $newValue = "powershell.exe -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`""
    Set-ItemProperty -Path $appKey.PSPath -Name UninstallString -Value $newValue -EA 0
    Add-Content $log "registry-wrap: patched to $newValue"
}
"#;
        let result = Command::new("powershell.exe")
            .args(["-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd])
            .output();
        match result {
            Ok(o) => {
                let stdout = String::from_utf8_lossy(&o.stdout);
                let stderr = String::from_utf8_lossy(&o.stderr);
                log(&format!("complete_setup: registry wrap exit={}", o.status.success()));
                if !stderr.trim().is_empty() {
                    log(&format!("complete_setup: registry wrap stderr: {}", stderr.trim()));
                }
                if !stdout.trim().is_empty() {
                    log(&format!("complete_setup: registry wrap stdout: {}", stdout.trim()));
                }
            }
            Err(e) => log(&format!("complete_setup: registry wrap spawn failed: {}", e)),
        }
    }

    if let Some(w) = app_handle.get_window("installer") {
        let _ = w.close();
    }

    if launch_app {
        let resource_dir = resolve_resource_dir(&app_handle);

        // Start services in background
        thread::spawn(|| {
            installer::ensure_services_running();
        });

        // Start backend
        if let Some(state) = app_handle.try_state::<BackendState>() {
            if let Some(child) = start_backend(&resource_dir) {
                *state.process.lock().unwrap() = Some(child);
            }
        }

        // Show main window after backend warms up
        let handle = app_handle.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_secs(2));
            if let Some(main_window) = handle.get_window("main") {
                let _ = main_window.show();
                let _ = main_window.set_focus();
                // Signal readiness via event (frontend listens and reloads)
                if wait_for_backend(15) {
                    let _ = main_window.emit("backend-ready", true);
                } else {
                    let _ = main_window.emit("backend-ready", false);
                }
            }
        });
    } else {
        std::process::exit(0);
    }

    Ok(())
}

#[tauri::command]
async fn close_installer(app_handle: tauri::AppHandle) {
    if let Some(w) = app_handle.get_window("installer") {
        let _ = w.close();
    }
    std::process::exit(0);
}

#[tauri::command]
async fn launch_app(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(main_window) = app_handle.get_window("main") {
        let _ = main_window.show();
        let _ = main_window.set_focus();
    }
    Ok(())
}

// ============================================================
// MAIN
// ============================================================

fn main() {
    let system_tray = create_system_tray();

    tauri::Builder::default()
        .system_tray(system_tray)
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::LeftClick { .. } => {
                if let Some(window) = app.get_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
                "show" => {
                    if let Some(window) = app.get_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                "restart" | "quit" => {
                    if let Some(state) = app.try_state::<BackendState>() {
                        stop_backend(&state);
                    }
                    std::process::exit(0);
                }
                _ => {}
            },
            _ => {}
        })
        .manage(BackendState {
            process: Mutex::new(None),
        })
        .setup(|app| {
            log(&format!("=== Agent n8On starting (PID={}) ===", std::process::id()));
            log(&format!("setup: is_setup_complete={}", installer::is_setup_complete()));
            if installer::is_setup_complete() {
                // Normal launch: start services and backend
                // Use the same multi-candidate resolver as the Tauri commands.
                // We don't have an AppHandle here, only App, so we replicate
                // the exe-parent probe (covers both NSIS install and dev builds).
                let resource_dir = {
                    let exe_parent = std::env::current_exe().ok()
                        .and_then(|p| p.parent().map(|d| d.to_path_buf()));

                    let candidates: Vec<std::path::PathBuf> = exe_parent
                        .iter()
                        .flat_map(|ep| vec![
                            ep.join("_up_"),
                            ep.clone(),
                            ep.join("..").join("..").join(".."),
                        ])
                        .chain(app.path_resolver().resource_dir().into_iter().flat_map(|rd| {
                            vec![rd.join("_up_"), rd]
                        }))
                        .collect();

                    candidates.into_iter()
                        .find(|c| c.join("backend").join("n8on.py").exists())
                        .map(|c| c.canonicalize().unwrap_or(c).to_string_lossy().to_string())
                        .unwrap_or_else(|| ".".to_string())
                };

                println!("Setup complete. Resource dir: {}", resource_dir);

                thread::spawn(|| {
                    installer::ensure_services_running();
                });

                let state = app.state::<BackendState>();
                if let Some(child) = start_backend(&resource_dir) {
                    *state.process.lock().unwrap() = Some(child);
                }

                if let Some(window) = app.get_window("main") {
                    let _ = window.show();
                    let w = window.clone();
                    thread::spawn(move || {
                        let ready = wait_for_backend(20);
                        log(&format!("setup: backend-ready={}", ready));
                        let _ = w.emit("backend-ready", ready);
                    });
                }
            } else {
                // First run: show installer window (configured in tauri.conf.json)
                println!("First run. Opening installer...");
                if let Some(installer_window) = app.get_window("installer") {
                    let _ = installer_window.show();
                    let _ = installer_window.set_focus();
                }
            }
            Ok(())
        })
        .on_window_event(|event| {
            if let WindowEvent::CloseRequested { api, .. } = event.event() {
                if event.window().label() == "main" {
                    event.window().hide().unwrap();
                    api.prevent_close();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            check_backend_status,
            restart_backend,
            check_system,
            run_installation,
            complete_setup,
            close_installer,
            launch_app,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
