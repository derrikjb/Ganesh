// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use ganesh_lib::{
    self as lib, shutdown_sidecar, spawn_sidecar, SidecarState, DEFAULT_SHUTDOWN_TIMEOUT,
    HOTKEY_TOGGLE, PTT_HOTKEY_DEFAULT, TRAY_HIDE_ID, TRAY_QUIT_ID, TRAY_SHOW_ID,
};
use ganesh_lib::commands::update::UpdateState;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{
    image::Image, menu::{Menu, MenuItem}, tray::{MouseButton, TrayIconEvent}, Emitter, Manager, RunEvent, WindowEvent,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

fn resolve_sidecar() -> (String, Vec<String>) {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(PathBuf::from));
    if let Some(dir) = exe_dir {
        let candidate = dir.join("ganesh-backend");
        // In dev, build.rs creates an empty placeholder and Tauri copies it
        // next to the exe. An empty file isn't a real sidecar — skip it so
        // we fall through to the python main.py fallback below.
        if candidate.exists() && candidate.metadata().map(|m| m.len() > 0).unwrap_or(false) {
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

struct PttState {
    hotkey: Mutex<String>,
}

#[tauri::command]
fn set_ptt_hotkey(
    app: tauri::AppHandle,
    state: tauri::State<'_, PttState>,
    hotkey: String,
) -> Result<String, String> {
    let old = state.hotkey.lock().unwrap().clone();
    if old == hotkey {
        return Ok(hotkey);
    }

    let global = app.global_shortcut();
    if let Err(e) = global.unregister(old.as_str()) {
        eprintln!("failed to unregister old PTT hotkey '{old}': {e}");
    }

    let app_handle = app.clone();
    global
        .on_shortcut(hotkey.as_str(), move |app, _shortcut, event| {
            if event.state() == ShortcutState::Pressed {
                let _ = app.emit("ganesh:ptt-press", ());
            } else {
                let _ = app.emit("ganesh:ptt-release", ());
            }
        })
        .map_err(|e| format!("failed to register PTT hotkey '{hotkey}': {e}"))?;

    *state.hotkey.lock().unwrap() = hotkey.clone();
    let _ = app_handle.emit("ganesh:ptt-hotkey-changed", hotkey.clone());
    Ok(hotkey)
}

#[tauri::command]
fn get_ptt_hotkey(state: tauri::State<'_, PttState>) -> String {
    state.hotkey.lock().unwrap().clone()
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
    }
}

fn build_tray_menu(app: &tauri::AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let show = MenuItem::with_id(app, TRAY_SHOW_ID, "Show", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, TRAY_HIDE_ID, "Hide", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, TRAY_QUIT_ID, "Quit", true, None::<&str>)?;
    Menu::with_items(app, &[&show, &hide, &quit])
}

fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let menu = build_tray_menu(app)?;
    let icon = app.default_window_icon()
        .cloned()
        .unwrap_or_else(|| Image::from_path("icons/32x32.png").unwrap());
    tauri::tray::TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .tooltip("Ganesh")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            TRAY_SHOW_ID => show_main_window(app),
            TRAY_HIDE_ID => hide_main_window(app),
            TRAY_QUIT_ID => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, .. } = event {
                toggle_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn build_app() -> tauri::Builder<tauri::Wry> {
    let state = SidecarState::new();
    let update_state = UpdateState::new();
    let ptt_state = PttState { hotkey: Mutex::new(PTT_HOTKEY_DEFAULT.to_string()) };

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(state)
        .manage(update_state)
        .manage(ptt_state)
        .invoke_handler(tauri::generate_handler![
            get_sidecar_port,
            get_ptt_hotkey,
            set_ptt_hotkey,
            ganesh_lib::commands::update::check_update,
            ganesh_lib::commands::update::download_update,
            ganesh_lib::commands::update::install_update,
            ganesh_lib::commands::update::cancel_update,
            ganesh_lib::commands::update::get_update_config,
            ganesh_lib::commands::update::set_update_config,
        ])
        .setup(|app| {
            let state = app.state::<SidecarState>();
            if let Err(e) = spawn_and_store_sidecar(&state) {
                eprintln!("sidecar spawn failed: {e}");
            }

            build_tray(app.handle())?;

            let global = app.global_shortcut();
            global.on_shortcut(HOTKEY_TOGGLE, move |app, _shortcut, _event| {
                toggle_main_window(app);
            })?;

            let ptt_state = app.state::<PttState>();
            let ptt_hotkey = ptt_state.hotkey.lock().unwrap().clone();
            global.on_shortcut(ptt_hotkey.as_str(), move |app, _shortcut, event| {
                if event.state() == ShortcutState::Pressed {
                    let _ = app.emit("ganesh:ptt-press", ());
                } else {
                    let _ = app.emit("ganesh:ptt-release", ());
                }
            })?;

            let update_state = app.state::<UpdateState>();
            let config = update_state.config.lock().unwrap().clone();
            if lib::should_auto_check(&config) && !cfg!(debug_assertions) {
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    use tauri_plugin_updater::UpdaterExt;
                    let updater = match handle.updater() {
                        Ok(u) => u,
                        Err(_) => return,
                    };
                    match updater.check().await {
                        Ok(Some(u)) => {
                            let current = handle.package_info().version.to_string();
                            if lib::is_update_available(&current, &u.version) {
                                let _ = handle.emit("update://available", u.version.clone());
                            }
                        }
                        _ => {}
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if lib::should_minimize_to_tray() {
                    api.prevent_close();
                    let _ = window.hide();
                } else {
                    let state = window.app_handle().state::<SidecarState>();
                    if let Some(mut child) = state.take_child() {
                        let _ = shutdown_sidecar(&mut child, DEFAULT_SHUTDOWN_TIMEOUT);
                    }
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
