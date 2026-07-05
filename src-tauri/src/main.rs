// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use ganesh_lib::{shutdown_sidecar, spawn_sidecar, SidecarState, DEFAULT_SHUTDOWN_TIMEOUT};
use std::path::PathBuf;
use tauri::{Manager, RunEvent, WindowEvent};

/// Resolve the sidecar binary path.
///
/// In a bundled Tauri app the sidecar lives next to the main executable and
/// is named `ganesh-backend` (with a platform-specific suffix on Windows). In
/// dev (or when the bundled binary is absent) we fall back to invoking the
/// Python source directly so the shell is runnable without a PyInstaller
/// build.
fn resolve_sidecar() -> (String, Vec<String>) {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(PathBuf::from));
    if let Some(dir) = exe_dir {
        let candidate = dir.join("ganesh-backend");
        if candidate.exists() {
            return (candidate.to_string_lossy().into_owned(), Vec::new());
        }
    }

    let backend_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("backend");
    let venv_python = backend_root.join("venv").join("bin").join("python");
    let python = if venv_python.exists() {
        venv_python.to_string_lossy().into_owned()
    } else {
        "python3".to_string()
    };
    let main_py = backend_root.join("main.py").to_string_lossy().into_owned();
    (python, vec![main_py])
}

fn spawn_and_store_sidecar(state: &SidecarState) -> Result<(), String> {
    let (binary, args) = resolve_sidecar();
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    let handle = spawn_sidecar(&binary, &arg_refs)
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;
    state.set(handle);
    Ok(())
}

#[tauri::command]
fn get_sidecar_port(state: tauri::State<'_, SidecarState>) -> Option<u16> {
    state.port()
}

fn build_app() -> tauri::Builder<tauri::Wry> {
    let state = SidecarState::new();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
                let _ = window.unminimize();
            }
        }))
        .manage(state)
        .invoke_handler(tauri::generate_handler![get_sidecar_port])
        .setup(|app| {
            let state = app.state::<SidecarState>();
            if let Err(e) = spawn_and_store_sidecar(&state) {
                eprintln!("sidecar spawn failed: {e}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                let state = window.app_handle().state::<SidecarState>();
                if let Some(mut child) = state.take_child() {
                    let _ = shutdown_sidecar(&mut child, DEFAULT_SHUTDOWN_TIMEOUT);
                }
            }
        })
}

pub fn run() {
    let app = build_app()
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            let state = app_handle.state::<SidecarState>();
            if let Some(mut child) = state.take_child() {
                let _ = shutdown_sidecar(&mut child, DEFAULT_SHUTDOWN_TIMEOUT);
            }
        }
    });
}

fn main() {
    run();
}
