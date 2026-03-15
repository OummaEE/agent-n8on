// installer.rs - Auto-installation module for Agent n8On

use std::net::TcpStream;
use std::path::{Component, PathBuf};
use std::process::Command;
use std::time::Duration;
use serde::Serialize;
use sha2::{Sha256, Digest};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

// ============================================================
// RUNTIME CONSTANTS — UPDATE THESE when releasing new runtime
// ============================================================

const RUNTIME_TAG: &str = "runtime-v1.0.0";
const RUNTIME_N8N_VERSION: &str = "2.11.3";
const RUNTIME_NODE_VERSION: &str = "20.11.0";
const RUNTIME_SHA256: &str = "UPDATE_AFTER_FIRST_BUILD";

fn get_runtime_url() -> String {
    format!(
        "https://github.com/OWNER/REPO/releases/download/{}/n8n-runtime-win64.zip",
        RUNTIME_TAG
    )
}

// ============================================================
// RUNTIME MANIFEST STRUCTS
// ============================================================

#[derive(Debug, serde::Deserialize, serde::Serialize)]
struct RuntimeManifest {
    n8n_version: String,
    node_version: String,
    npm_version: String,
    runtime_tag: String,
    built_at: String,
    paths: RuntimePaths,
}

#[derive(Debug, serde::Deserialize, serde::Serialize)]
struct RuntimePaths {
    node_exe: String,
    n8n_bin: String,
}

// ============================================================
// INSTALLER LOGGER  (mirrors main.rs log(), no shared mutex needed
// since file appends are atomic enough for diagnostic logs)
// ============================================================
fn log_install(msg: &str) {
    use std::io::Write;
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let line = format!("T+{}  [installer] {}\n", secs, msg);
    let appdata = std::env::var("APPDATA").unwrap_or_else(|_| ".".to_string());
    let path = format!("{}/Agent n8On/debug.log", appdata);
    if let Some(parent) = std::path::Path::new(&path).parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let _ = f.write_all(line.as_bytes());
    }
    print!("{}", line);
}

// ============================================================
// SYSTEM DETECTION
// ============================================================

#[derive(Clone, Serialize)]
pub struct SystemCapabilities {
    pub ram_gb: u64,
    pub vram_gb: Option<u64>,
    pub gpu_name: Option<String>,
    pub free_disk_gb: u64,
}

pub fn detect_system() -> SystemCapabilities {
    let ram_gb = detect_ram();
    let (gpu_name, vram_gb) = detect_gpu();
    let free_disk_gb = detect_free_disk();
    SystemCapabilities { ram_gb, vram_gb, gpu_name, free_disk_gb }
}

fn detect_ram() -> u64 {
    let output = Command::new("powershell")
        .args(["-NoProfile", "-Command",
            "(Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory"])
        .output();

    if let Ok(out) = output {
        if let Ok(s) = String::from_utf8(out.stdout) {
            if let Ok(bytes) = s.trim().parse::<u64>() {
                return bytes / 1024 / 1024 / 1024;
            }
        }
    }
    8
}

fn detect_gpu() -> (Option<String>, Option<u64>) {
    // 1. NVIDIA: nvidia-smi gives exact VRAM in MiB — most reliable source.
    if let Some(result) = try_nvidia_smi() {
        return result;
    }
    // 2. AMD / other: WMI, but only trust the value under strict conditions
    //    (see wmi_detect_gpu for why).
    wmi_detect_gpu()
}

/// Query nvidia-smi for GPU name and VRAM.
/// Returns None if nvidia-smi is not present or exits non-zero (non-NVIDIA system).
fn try_nvidia_smi() -> Option<(Option<String>, Option<u64>)> {
    let out = Command::new("nvidia-smi")
        .args(["--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        .output()
        .ok()?;

    if !out.status.success() {
        return None;
    }

    let text = String::from_utf8_lossy(&out.stdout);
    let line = text.lines().next()?.trim();
    if line.is_empty() {
        return None;
    }

    // Output format: "NVIDIA GeForce RTX 3060, 12288"
    // Use rfind so GPU names containing a comma (rare but possible) are handled.
    let comma = line.rfind(',')?;
    let name = line[..comma].trim().to_string();
    let vram_mib: u64 = line[comma + 1..].trim().parse().ok()?;
    // nvidia-smi reports in MiB; convert to GiB (integer, round down).
    let vram_gb = vram_mib / 1024;

    Some((
        Some(name),
        if vram_gb > 0 { Some(vram_gb) } else { None },
    ))
}

/// Returns true iff n is a positive power of two.
fn is_power_of_two(n: u64) -> bool {
    n > 0 && (n & (n - 1)) == 0
}

/// Detect GPU name and VRAM via WMI Win32_VideoController.
///
/// WMI AdapterRAM is a 32-bit field. Any card with > 4 GiB VRAM will return
/// a truncated/overflowed value (e.g. 8 GiB → 0, 6 GiB → 2 GiB).
/// We only trust the byte value when:
///   - it is strictly > 4 GiB  (rules out 32-bit overflow artifacts that wrap small)
///   - AND it is a power of two (standard VRAM sizes: 8, 16, 32 GiB)
/// All other cases return None for vram_gb to trigger "choose manually" UI.
fn wmi_detect_gpu() -> (Option<String>, Option<u64>) {
    let out = Command::new("powershell")
        .args([
            "-NoProfile", "-Command",
            "Get-WmiObject Win32_VideoController \
             | Select-Object -First 1 Name,AdapterRAM \
             | ConvertTo-Json -Compress",
        ])
        .output();

    let (name, adapter_ram_bytes) = match out {
        Ok(o) => {
            let text = String::from_utf8_lossy(&o.stdout);
            match serde_json::from_str::<serde_json::Value>(text.trim()) {
                Ok(json) => {
                    let n = json["Name"].as_str()
                        .filter(|s| !s.is_empty())
                        .map(String::from);
                    let r = json["AdapterRAM"].as_u64().unwrap_or(0);
                    (n, r)
                }
                Err(_) => return (None, None),
            }
        }
        Err(_) => return (None, None),
    };

    const FOUR_GIB: u64 = 4 * 1024 * 1024 * 1024;
    let vram_gb = if adapter_ram_bytes > FOUR_GIB && is_power_of_two(adapter_ram_bytes) {
        Some(adapter_ram_bytes / 1024 / 1024 / 1024)
    } else {
        // Value is either zero, an overflow artifact, or a non-power-of-two that
        // we can't distinguish from overflow.  Return None → "choose manually".
        None
    };

    (name, vram_gb)
}

fn detect_free_disk() -> u64 {
    let output = Command::new("powershell")
        .args(["-NoProfile", "-Command",
            "(Get-PSDrive -Name C).Free"])
        .output();

    if let Ok(out) = output {
        if let Ok(s) = String::from_utf8(out.stdout) {
            if let Ok(bytes) = s.trim().parse::<u64>() {
                return bytes / 1024 / 1024 / 1024;
            }
        }
    }
    50
}

// ============================================================
// MODEL SELECTION
// ============================================================

pub struct ModelOption {
    pub name: &'static str,
    pub ollama_name: &'static str,
    pub size_gb: f32,
    pub min_ram_gb: u64,
    pub min_vram_gb: Option<u64>,
    pub description: &'static str,
}

pub const MODELS: &[ModelOption] = &[
    ModelOption {
        name: "Qwen 2.5 Coder 14B",
        ollama_name: "qwen2.5-coder:14b",
        size_gb: 8.5,
        min_ram_gb: 16,
        min_vram_gb: Some(8),
        description: "Лучшее качество, для мощных ПК",
    },
    ModelOption {
        name: "Qwen 2.5 Coder 7B",
        ollama_name: "qwen2.5-coder:7b",
        size_gb: 4.5,
        min_ram_gb: 8,
        min_vram_gb: None,
        description: "Сбалансированный вариант",
    },
    ModelOption {
        name: "Qwen 2.5 Coder 3B",
        ollama_name: "qwen2.5-coder:3b",
        size_gb: 2.0,
        min_ram_gb: 4,
        min_vram_gb: None,
        description: "Для слабых компьютеров",
    },
];

pub fn recommend_model(caps: &SystemCapabilities) -> &'static ModelOption {
    for model in MODELS {
        let ram_ok = caps.ram_gb >= model.min_ram_gb;
        let vram_ok = model.min_vram_gb
            .map(|min| caps.vram_gb.unwrap_or(0) >= min)
            .unwrap_or(true);
        let disk_ok = caps.free_disk_gb as f32 >= model.size_gb + 5.0;

        if ram_ok && vram_ok && disk_ok {
            return model;
        }
    }
    &MODELS[MODELS.len() - 1]
}

// ============================================================
// OLLAMA
// ============================================================

pub fn is_ollama_installed() -> bool {
    let username = std::env::var("USERNAME").unwrap_or_default();
    let paths = [
        format!("C:/Users/{}/AppData/Local/Programs/Ollama/ollama.exe", username),
        "C:/Program Files/Ollama/ollama.exe".to_string(),
    ];

    for path in &paths {
        if std::path::Path::new(path).exists() {
            log_install(&format!("is_ollama_installed: found at {}", path));
            return true;
        }
    }

    let via_path = Command::new("ollama")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);
    log_install(&format!("is_ollama_installed: PATH check={}", via_path));
    via_path
}

pub async fn install_ollama<F>(progress: F) -> Result<(), String>
where
    F: Fn(u32, &str),
{
    use futures::StreamExt;

    let url = "https://ollama.com/download/OllamaSetup.exe";
    let path = std::env::temp_dir().join("OllamaSetup.exe");

    log_install("install_ollama: starting download from ollama.com");
    progress(2, "Скачивание Ollama (~80 MB)...");

    let resp = reqwest::get(url).await.map_err(|e| {
        log_install(&format!("install_ollama: download failed: {}", e));
        e.to_string()
    })?;

    let total_bytes = resp.content_length().unwrap_or(0);
    log_install(&format!("install_ollama: content-length={} bytes", total_bytes));

    let mut downloaded: u64 = 0;
    let mut file_bytes: Vec<u8> = Vec::with_capacity(total_bytes as usize);
    let mut last_reported_pct: u32 = 0;
    let mut stream = resp.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| e.to_string())?;
        downloaded += chunk.len() as u64;
        file_bytes.extend_from_slice(&chunk);

        if total_bytes > 0 {
            let pct = ((downloaded as f64 / total_bytes as f64) * 55.0) as u32; // 0-55 range
            if pct >= last_reported_pct + 5 {
                last_reported_pct = pct;
                let dl_mb = downloaded / 1_048_576;
                let tot_mb = total_bytes / 1_048_576;
                progress(2 + pct, &format!("Скачивание Ollama: {} MB / {} MB...", dl_mb, tot_mb));
            }
        }
    }

    log_install(&format!("install_ollama: downloaded {} bytes, writing to disk", downloaded));
    std::fs::write(&path, &file_bytes).map_err(|e| e.to_string())?;

    log_install("install_ollama: running silent installer");
    progress(60, "Установка Ollama...");

    let status = Command::new(&path)
        .args(["/VERYSILENT", "/NORESTART"])
        .status()
        .map_err(|e| {
            log_install(&format!("install_ollama: installer spawn failed: {}", e));
            e.to_string()
        })?;

    if !status.success() {
        let msg = format!("Ошибка установки Ollama (exit code: {:?})", status.code());
        log_install(&msg);
        return Err(msg);
    }

    log_install("install_ollama: done");
    progress(100, "Ollama установлена");
    Ok(())
}

/// Returns true only when Ollama is fully initialised:
/// TCP port open AND GET /api/tags returns HTTP 200 with valid JSON.
/// A successful TCP connect while Ollama is still booting gives 200 but
/// sometimes an empty/invalid body — that case is rejected here.
pub fn check_ollama_running() -> bool {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(800))
        .build()
        .ok()
        .and_then(|c| c.get("http://127.0.0.1:11434/api/tags").send().ok())
        .filter(|r| r.status().is_success())
        .and_then(|r| r.json::<serde_json::Value>().ok())
        .is_some()
}

/// Start `ollama serve` if not already running, then wait up to 60 seconds
/// for Ollama to become fully ready (HTTP 200 + valid JSON on /api/tags).
///
/// `progress(elapsed_secs)` is called once per second so the caller can
/// update the UI. Typical messages:
///   ≤ 15s  → "Запуск Ollama... (N сек)"
///   ≤ 45s  → "Запуск Ollama... (N сек)"
///    > 45s  → "Запуск занимает больше времени, подождите..."
pub fn start_ollama_service<F>(progress: F) -> Result<(), String>
where
    F: Fn(u32, &str),
{
    if check_ollama_running() {
        log_install("start_ollama_service: already running");
        return Ok(());
    }

    let username = std::env::var("USERNAME").unwrap_or_default();
    let ollama_path = format!(
        "C:/Users/{}/AppData/Local/Programs/Ollama/ollama.exe",
        username
    );
    let cmd = if std::path::Path::new(&ollama_path).exists() {
        log_install(&format!("start_ollama_service: using {}", ollama_path));
        ollama_path
    } else {
        log_install("start_ollama_service: using 'ollama' from PATH");
        "ollama".to_string()
    };

    #[cfg(target_os = "windows")]
    Command::new(&cmd)
        .arg("serve")
        .creation_flags(0x08000000) // CREATE_NO_WINDOW
        .spawn()
        .map_err(|e| {
            log_install(&format!("start_ollama_service: spawn failed: {}", e));
            format!("Не удалось запустить Ollama: {}", e)
        })?;

    #[cfg(not(target_os = "windows"))]
    Command::new(&cmd)
        .arg("serve")
        .spawn()
        .map_err(|e| {
            log_install(&format!("start_ollama_service: spawn failed: {}", e));
            format!("Не удалось запустить Ollama: {}", e)
        })?;

    log_install("start_ollama_service: waiting up to 180s for HTTP /api/tags");
    const MAX_SECS: u32 = 180;
    for elapsed in 1..=MAX_SECS {
        std::thread::sleep(Duration::from_secs(1));

        if check_ollama_running() {
            log_install(&format!("start_ollama_service: ready after {} secs", elapsed));
            return Ok(());
        }

        // Emit progress feedback only at milestone ticks; check every tick.
        match elapsed {
            30 | 60 | 90 | 120 => {
                progress(
                    elapsed * 100 / MAX_SECS,
                    &format!("Запуск Ollama... ({} сек)", elapsed),
                );
            }
            s if s > 120 && (s % 10 == 0) => {
                // After 120s: remind user every 10 seconds so they don't think it froze
                progress(
                    elapsed * 100 / MAX_SECS,
                    "Ollama запускается медленно (первый запуск). Подождите...",
                );
            }
            _ => {}
        }
    }

    let msg = format!("Ollama не запустилась за {} секунд", MAX_SECS);
    log_install(&msg);
    Err(msg)
}

// ============================================================
// MODEL DOWNLOAD
// ============================================================

pub async fn pull_model<F>(model_name: &str, progress: F) -> Result<(), String>
where
    F: Fn(u32, &str),
{
    use futures::StreamExt;

    log_install(&format!("pull_model: starting download of '{}'", model_name));
    progress(0, &format!("Начало скачивания {}...", model_name));

    let client = reqwest::Client::new();
    let response = client
        .post("http://localhost:11434/api/pull")
        .json(&serde_json::json!({"name": model_name, "stream": true}))
        .send()
        .await
        .map_err(|e| {
            log_install(&format!("pull_model: connection to Ollama failed: {}", e));
            format!("Ошибка подключения к Ollama: {}", e)
        })?;

    let mut stream = response.bytes_stream();
    let mut last_percent = 0u32;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| e.to_string())?;
        let text = String::from_utf8_lossy(&chunk);

        for line in text.lines() {
            if line.is_empty() {
                continue;
            }
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(line) {
                if let Some(err) = json["error"].as_str() {
                    return Err(err.to_string());
                }
                if let (Some(completed), Some(total)) =
                    (json["completed"].as_u64(), json["total"].as_u64())
                {
                    if total > 0 {
                        let percent =
                            ((completed as f64 / total as f64) * 100.0) as u32;
                        if percent != last_percent {
                            last_percent = percent;
                            let dl_mb = completed / 1024 / 1024;
                            let tot_mb = total / 1024 / 1024;
                            progress(
                                percent,
                                &format!(
                                    "Скачивание: {} MB / {} MB",
                                    dl_mb, tot_mb
                                ),
                            );
                        }
                    }
                }
            }
        }
    }

    log_install(&format!("pull_model: '{}' download complete", model_name));
    progress(100, "Модель загружена");
    Ok(())
}

// ============================================================
// N8N — PORTABLE RUNTIME
// ============================================================

/// Returns the runtime base directory: %LOCALAPPDATA%\Agent n8On\runtime\
fn get_runtime_dir() -> PathBuf {
    let app_data = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(&app_data).join("Agent n8On").join("runtime")
}

/// Returns (node_exe, n8n_bin) paths inside the local runtime directory.
pub fn get_runtime_paths() -> (PathBuf, PathBuf) {
    let runtime_dir = get_runtime_dir();
    let node_exe = runtime_dir.join("node").join("node.exe");
    let n8n_bin  = runtime_dir.join("n8n").join("node_modules").join("n8n").join("bin").join("n8n");
    (node_exe, n8n_bin)
}

/// Normalizes a path without accessing the filesystem (resolves ".." and "." components).
fn normalize_path(path: &std::path::Path) -> PathBuf {
    let mut result = PathBuf::new();
    for component in path.components() {
        match component {
            Component::ParentDir => { result.pop(); }
            Component::CurDir    => {}
            c                    => result.push(c.as_os_str()),
        }
    }
    result
}

// ── Path traversal protection ─────────────────────────────────────────────────

fn is_safe_archive_path(entry_name: &str) -> bool {
    let path = std::path::Path::new(entry_name);
    for component in path.components() {
        match component {
            Component::ParentDir => return false,
            Component::RootDir   => return false,
            Component::Prefix(_) => return false,
            _ => continue,
        }
    }
    let normalized = entry_name.replace('\\', "/");
    !normalized.contains("..") && !normalized.starts_with('/')
}

fn safe_extract_entry(
    entry: &mut zip::read::ZipFile,
    runtime_dir: &std::path::Path,
) -> Result<(), String> {
    let entry_name = entry.name().to_string();

    // 1. Check entry name — reject unsafe paths with error
    if !is_safe_archive_path(&entry_name) {
        log_install(&format!("ERROR: Unsafe archive entry: {}", entry_name));
        return Err(format!("Unsafe archive entry: {}", entry_name));
    }

    // 2. Build outpath
    let outpath = runtime_dir.join(&entry_name);

    // 3. Check parent stays within runtime_dir — reject with error
    if let Some(parent) = outpath.parent() {
        let parent_normalized  = normalize_path(parent);
        let runtime_normalized = normalize_path(runtime_dir);
        if !parent_normalized.starts_with(&runtime_normalized) {
            log_install(&format!("ERROR: Archive entry escapes runtime_dir: {}", outpath.display()));
            return Err(format!("Archive entry escapes runtime_dir: {}", outpath.display()));
        }
    }

    // 4. Create directory or file
    if entry.is_dir() {
        std::fs::create_dir_all(&outpath)
            .map_err(|e| format!("Cannot create directory {}: {}", outpath.display(), e))?;
    } else {
        if let Some(parent) = outpath.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Cannot create parent directory {}: {}", parent.display(), e))?;
        }
        let mut outfile = std::fs::File::create(&outpath)
            .map_err(|e| format!("Cannot create file {}: {}", outpath.display(), e))?;
        std::io::copy(entry, &mut outfile)
            .map_err(|e| format!("Cannot write file {}: {}", outpath.display(), e))?;
    }

    // 5. Additional canonicalize check for already-created paths
    if outpath.exists() {
        if let (Ok(canonical_out), Ok(canonical_runtime)) =
            (outpath.canonicalize(), runtime_dir.canonicalize())
        {
            if !canonical_out.starts_with(&canonical_runtime) {
                log_install(&format!(
                    "CRITICAL: Canonical path escaped runtime_dir, removing: {}",
                    outpath.display()
                ));
                if outpath.is_dir() {
                    std::fs::remove_dir_all(&outpath).ok();
                } else {
                    std::fs::remove_file(&outpath).ok();
                }
                return Err(format!("Path traversal detected: {}", entry_name));
            }
        }
    }

    Ok(())
}

// ── SHA256 verification ───────────────────────────────────────────────────────

fn verify_file_sha256(file_path: &std::path::Path, expected_hash: &str) -> Result<(), String> {
    log_install(&format!("verify_file_sha256: checking {}", file_path.display()));

    let mut file = std::fs::File::open(file_path)
        .map_err(|e| format!("Cannot open file: {}", e))?;

    let mut hasher = Sha256::new();
    std::io::copy(&mut file, &mut hasher)
        .map_err(|e| format!("Cannot read file: {}", e))?;

    let actual   = format!("{:x}", hasher.finalize()).to_uppercase();
    let expected = expected_hash.to_uppercase();

    if actual != expected {
        return Err(format!(
            "SHA256 mismatch!\nExpected: {}\nActual:   {}",
            expected, actual
        ));
    }

    log_install("verify_file_sha256: OK");
    Ok(())
}

// ── Unique temp zip path ──────────────────────────────────────────────────────

fn get_unique_temp_zip_path() -> Result<PathBuf, String> {
    use std::time::{SystemTime, UNIX_EPOCH};
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let pid = std::process::id();
    let temp_dir = std::env::temp_dir()
        .join("agent-n8on-runtime")
        .join(format!("{}-{}", timestamp, pid));
    std::fs::create_dir_all(&temp_dir)
        .map_err(|e| format!("Cannot create temp runtime directory {}: {}", temp_dir.display(), e))?;
    Ok(temp_dir.join("n8n-runtime-win64.zip"))
}

// ── ZIP extraction helper ─────────────────────────────────────────────────────

fn extract_to_directory(zip_path: &std::path::Path, target_dir: &std::path::Path) -> Result<(), String> {
    let file = std::fs::File::open(zip_path)
        .map_err(|e| format!("Cannot open zip: {}", e))?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| format!("Invalid zip: {}", e))?;
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)
            .map_err(|e| format!("Zip entry error: {}", e))?;
        safe_extract_entry(&mut entry, target_dir)?;
    }
    Ok(())
}

// ── Manifest validation ───────────────────────────────────────────────────────

fn validate_manifest_at_path(
    manifest_path: &std::path::Path,
    runtime_dir: &std::path::Path,
) -> Result<RuntimeManifest, String> {
    // 1. Check manifest exists
    if !manifest_path.exists() {
        log_install("validate_manifest: FAILED - manifest missing");
        return Err("manifest missing".to_string());
    }

    // 2. Read manifest
    let content = std::fs::read_to_string(manifest_path)
        .map_err(|e| {
            let msg = format!("manifest read failed: {}", e);
            log_install(&format!("validate_manifest: FAILED - {}", msg));
            msg
        })?;

    // 3. Parse JSON
    let manifest: RuntimeManifest = serde_json::from_str(&content)
        .map_err(|e| {
            let msg = format!("manifest parse failed: {}", e);
            log_install(&format!("validate_manifest: FAILED - {}", msg));
            msg
        })?;

    // 4. Check versions
    if manifest.runtime_tag != RUNTIME_TAG {
        let msg = format!(
            "version mismatch: expected runtime_tag={}, got={}",
            RUNTIME_TAG, manifest.runtime_tag
        );
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }
    if manifest.n8n_version != RUNTIME_N8N_VERSION {
        let msg = format!(
            "version mismatch: expected n8n={}, got={}",
            RUNTIME_N8N_VERSION, manifest.n8n_version
        );
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }
    if manifest.node_version != RUNTIME_NODE_VERSION {
        let msg = format!(
            "version mismatch: expected node={}, got={}",
            RUNTIME_NODE_VERSION, manifest.node_version
        );
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }

    // 5. Check manifest paths are safe (no path traversal)
    if !is_safe_archive_path(&manifest.paths.node_exe)
        || !is_safe_archive_path(&manifest.paths.n8n_bin)
    {
        let msg = "manifest paths invalid or point outside runtime directory".to_string();
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }

    // 5b. Check resolved paths stay within runtime_dir
    let node_resolved      = runtime_dir.join(&manifest.paths.node_exe);
    let n8n_resolved       = runtime_dir.join(&manifest.paths.n8n_bin);
    let runtime_normalized = normalize_path(runtime_dir);

    if !normalize_path(&node_resolved).starts_with(&runtime_normalized) {
        let msg = format!(
            "manifest paths resolve outside runtime directory: {}",
            manifest.paths.node_exe
        );
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }
    if !normalize_path(&n8n_resolved).starts_with(&runtime_normalized) {
        let msg = format!(
            "manifest paths resolve outside runtime directory: {}",
            manifest.paths.n8n_bin
        );
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }

    // 6. Check binaries exist
    let node_exe = runtime_dir.join(&manifest.paths.node_exe);
    let n8n_bin  = runtime_dir.join(&manifest.paths.n8n_bin);

    if !node_exe.exists() {
        let msg = format!("node.exe missing at {}", node_exe.display());
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }
    if !n8n_bin.exists() {
        let msg = format!("n8n bin missing at {}", n8n_bin.display());
        log_install(&format!("validate_manifest: FAILED - {}", msg));
        return Err(msg);
    }

    log_install(&format!(
        "validate_manifest: OK (tag={}, n8n={}, node={})",
        manifest.runtime_tag, manifest.n8n_version, manifest.node_version
    ));
    Ok(manifest)
}

/// Validate the installed production runtime.
fn validate_existing_runtime() -> Result<RuntimeManifest, String> {
    let runtime_dir   = get_runtime_dir();
    let manifest_path = runtime_dir.join("manifest.json");
    validate_manifest_at_path(&manifest_path, &runtime_dir)
}

/// Returns true when the runtime is downloaded, extracted, and valid.
pub fn is_runtime_installed() -> bool {
    validate_existing_runtime().is_ok()
}

/// Check if n8n is available — checks for runtime, not system npm.
pub fn is_n8n_installed() -> bool {
    is_runtime_installed()
}

/// Kept for compatibility — always false with portable runtime.
pub fn is_node_installed() -> bool {
    false
}

pub fn check_n8n_running() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:5678".parse().unwrap(),
        Duration::from_millis(500),
    )
    .is_ok()
}

// ── Download and atomic install ───────────────────────────────────────────────

/// Download the pre-built runtime zip from GitHub Releases and extract to
/// %LOCALAPPDATA%\Agent n8On\runtime\ using a staging directory for atomicity.
pub async fn download_and_extract_runtime(window: &tauri::Window) -> Result<(), String> {
    use futures::StreamExt;
    use std::io::Write;

    // Guard against releasing with placeholder SHA256
    if RUNTIME_SHA256 == "UPDATE_AFTER_FIRST_BUILD" {
        return Err(
            "RUNTIME_SHA256 not configured. Build runtime first and update the hash.".to_string(),
        );
    }

    let runtime_dir = get_runtime_dir();
    let staging_dir = runtime_dir
        .parent()
        .ok_or("Cannot get parent dir")?
        .join("runtime_staging");
    let backup_dir = runtime_dir
        .parent()
        .ok_or("Cannot get parent dir")?
        .join("runtime_backup");

    // Helper to emit progress events
    let emit = |progress: u32, msg: &str| {
        let _ = window.emit(
            "install-progress",
            serde_json::json!({
                "component": "n8n", "status": "progress",
                "progress": progress, "message": msg
            }),
        );
    };

    // Check existing runtime
    match validate_existing_runtime() {
        Ok(manifest) => {
            log_install(&format!(
                "download_and_extract_runtime: valid runtime exists (tag={}), skipping",
                manifest.runtime_tag
            ));
            return Ok(());
        }
        Err(reason) => {
            log_install(&format!(
                "download_and_extract_runtime: need install ({})",
                reason
            ));
        }
    }

    // Clear leftover staging from a previous attempt
    if staging_dir.exists() {
        std::fs::remove_dir_all(&staging_dir).ok();
    }
    std::fs::create_dir_all(&staging_dir)
        .map_err(|e| format!("Cannot create staging dir: {}", e))?;

    // Unique temp path for the zip
    let zip_path = get_unique_temp_zip_path()?;

    emit(0, "Скачивание n8n runtime...");
    let url = get_runtime_url();
    log_install(&format!("download_and_extract_runtime: downloading from {}", url));

    // ── Download ─────────────────────────────────────────────────────────────
    let response = reqwest::Client::new()
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Ошибка скачивания runtime: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("Ошибка скачивания runtime: HTTP {}", response.status()));
    }

    let total_size = response.content_length().unwrap_or(0);
    log_install(&format!("download_and_extract_runtime: content-length={}", total_size));

    let mut file = std::fs::File::create(&zip_path)
        .map_err(|e| format!("Не удалось создать temp файл: {}", e))?;

    let mut downloaded: u64 = 0;
    let mut stream = response.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Ошибка скачивания: {}", e))?;
        file.write_all(&chunk).map_err(|e| format!("Ошибка записи: {}", e))?;
        downloaded += chunk.len() as u64;
        if total_size > 0 {
            let pct = (downloaded as f64 / total_size as f64 * 48.0) as u32; // 0–48
            emit(
                pct,
                &format!(
                    "Скачивание runtime: {:.0} / {:.0} MB",
                    downloaded as f64 / 1e6,
                    total_size as f64 / 1e6
                ),
            );
        }
    }
    drop(file);
    log_install("download_and_extract_runtime: download complete");

    // ── SHA256 ────────────────────────────────────────────────────────────────
    emit(50, "Verifying integrity...");
    verify_file_sha256(&zip_path, RUNTIME_SHA256)?;

    // ── Extract to STAGING ────────────────────────────────────────────────────
    emit(55, "Extracting to staging...");
    extract_to_directory(&zip_path, &staging_dir)?;

    // Remove temp zip
    if let Some(temp_dir) = zip_path.parent() {
        if let Err(e) = std::fs::remove_dir_all(temp_dir) {
            log_install(&format!("WARNING: Could not remove temp dir: {}", e));
        }
    }

    // ── Validate staging ─────────────────────────────────────────────────────
    emit(90, "Validating...");
    let staging_manifest_path = staging_dir.join("manifest.json");
    validate_manifest_at_path(&staging_manifest_path, &staging_dir)?;

    // ── ATOMIC REPLACE: staging -> production ────────────────────────────────
    emit(95, "Activating runtime...");

    if runtime_dir.exists() {
        if backup_dir.exists() {
            if let Err(e) = std::fs::remove_dir_all(&backup_dir) {
                log_install(&format!(
                    "ERROR: Cannot remove old backup dir {}: {}",
                    backup_dir.display(),
                    e
                ));
                std::fs::remove_dir_all(&staging_dir).ok();
                return Err(format!(
                    "Cannot remove old backup dir {}: {}",
                    backup_dir.display(),
                    e
                ));
            }
        }
        match std::fs::rename(&runtime_dir, &backup_dir) {
            Ok(_) => {
                log_install("Backed up existing runtime");
            }
            Err(backup_err) => {
                log_install(&format!(
                    "WARNING: Could not backup existing runtime: {}",
                    backup_err
                ));
                if let Err(delete_err) = std::fs::remove_dir_all(&runtime_dir) {
                    log_install(&format!(
                        "ERROR: Cannot backup or delete existing runtime: {}",
                        delete_err
                    ));
                    std::fs::remove_dir_all(&staging_dir).ok();
                    return Err(format!(
                        "Cannot replace existing runtime: backup failed ({}), delete failed ({})",
                        backup_err, delete_err
                    ));
                }
                log_install("Deleted existing runtime (backup failed)");
            }
        }
    }

    // Rename staging to production
    if let Err(e) = std::fs::rename(&staging_dir, &runtime_dir) {
        log_install(&format!("ERROR: Failed to activate staging: {}", e));
        if backup_dir.exists() {
            match std::fs::rename(&backup_dir, &runtime_dir) {
                Ok(_)              => log_install("Restored previous runtime from backup"),
                Err(restore_err)   => log_install(&format!("CRITICAL: Failed to restore backup: {}", restore_err)),
            }
        }
        std::fs::remove_dir_all(&staging_dir).ok();
        return Err(format!("Failed to activate runtime: {}", e));
    }

    // Success — remove backup
    if backup_dir.exists() {
        if let Err(e) = std::fs::remove_dir_all(&backup_dir) {
            log_install(&format!("WARNING: Could not remove backup: {}", e));
        }
    }

    emit(100, "Runtime ready");
    log_install("download_and_extract_runtime: complete");
    Ok(())
}

/// Start n8n using paths read from the runtime manifest.
/// Validates that resolved paths stay within the runtime directory before spawning.
pub fn start_n8n_service() -> Result<(), String> {
    let manifest    = validate_existing_runtime()?;
    let runtime_dir = get_runtime_dir();

    let node_exe = runtime_dir.join(&manifest.paths.node_exe);
    let n8n_bin  = runtime_dir.join(&manifest.paths.n8n_bin);

    // Check resolved paths stay within runtime_dir
    let runtime_normalized = normalize_path(&runtime_dir);
    let node_normalized    = normalize_path(&node_exe);
    let n8n_normalized     = normalize_path(&n8n_bin);

    if !node_normalized.starts_with(&runtime_normalized) {
        return Err(format!(
            "manifest paths resolve outside runtime directory: {}",
            node_exe.display()
        ));
    }
    if !n8n_normalized.starts_with(&runtime_normalized) {
        return Err(format!(
            "manifest paths resolve outside runtime directory: {}",
            n8n_bin.display()
        ));
    }

    // Extra existence check after path resolution
    if !node_exe.exists() {
        return Err(format!(
            "node.exe not found at {} (after path resolution)",
            node_exe.display()
        ));
    }
    if !n8n_bin.exists() {
        return Err(format!(
            "n8n bin not found at {} (after path resolution)",
            n8n_bin.display()
        ));
    }

    log_install(&format!("start_n8n_service: {} {}", node_exe.display(), n8n_bin.display()));

    if check_n8n_running() {
        log_install("start_n8n_service: already running");
        return Ok(());
    }

    std::process::Command::new(&node_exe)
        .arg(&n8n_bin)
        .env("N8N_PORT", "5678")
        .spawn()
        .map_err(|e| format!("Failed to start n8n: {}", e))?;

    log_install("start_n8n_service: waiting up to 120s for n8n on port 5678");
    for elapsed in 1..=120u32 {
        if check_n8n_running() {
            log_install(&format!("start_n8n_service: ready after {} secs", elapsed));
            return Ok(());
        }
        std::thread::sleep(Duration::from_secs(1));
        if elapsed % 30 == 0 {
            log_install(&format!("start_n8n_service: still waiting... {}s", elapsed));
        }
    }
    log_install("start_n8n_service: timed out (non-fatal)");
    Ok(())
}


// ============================================================
// SERVICE AUTO-START
// ============================================================

pub fn ensure_services_running() {
    if !check_ollama_running() {
        println!("Starting Ollama...");
        if let Err(e) = start_ollama_service(|_, msg| println!("Ollama: {}", msg)) {
            eprintln!("Failed to start Ollama: {}", e);
        }
    }

    if is_n8n_installed() && !check_n8n_running() {
        println!("Starting n8n...");
        if let Err(e) = start_n8n_service() {
            eprintln!("Failed to start n8n: {}", e);
        }
    }
}

// ============================================================
// SETUP STATE
// ============================================================

fn get_config_dir() -> std::path::PathBuf {
    let base = std::env::var("APPDATA")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("."));
    base.join("Agent n8On")
}

pub fn is_setup_complete() -> bool {
    get_config_dir().join(".setup_complete").exists()
}

pub fn mark_setup_complete() {
    let dir = get_config_dir();
    std::fs::create_dir_all(&dir).ok();
    std::fs::write(dir.join(".setup_complete"), "1").ok();
}
