use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, ResourceId, State};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::{is_update_available, UpdateChannel, UpdateConfig};

pub struct UpdateState {
    pub config: Mutex<UpdateConfig>,
    pub cancel_flag: Arc<AtomicBool>,
    pub pending_update: Mutex<Option<ResourceId>>,
    pub downloaded_bytes: Mutex<Option<Vec<u8>>>,
}

impl UpdateState {
    pub fn new() -> Self {
        Self {
            config: Mutex::new(UpdateConfig::default()),
            cancel_flag: Arc::new(AtomicBool::new(false)),
            pending_update: Mutex::new(None),
            downloaded_bytes: Mutex::new(None),
        }
    }
}

impl Default for UpdateState {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Serialize)]
pub struct UpdateInfo {
    pub available: bool,
    pub version: Option<String>,
    pub current_version: String,
    pub body: Option<String>,
    pub date: Option<String>,
    pub download_url: Option<String>,
}

#[derive(Debug, Serialize, Clone)]
pub struct DownloadProgress {
    pub downloaded: usize,
    pub total: Option<u64>,
}

fn resolve_channel(config: &UpdateConfig) -> UpdateChannel {
    config.channel.clone()
}

#[tauri::command]
pub async fn check_update(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<UpdateInfo, String> {
    let config = state.config.lock().unwrap().clone();
    let _channel = resolve_channel(&config);

    let updater = app.updater().map_err(|e| format!("updater init failed: {e}"))?;
    let update = updater
        .check()
        .await
        .map_err(|e| format!("update check failed: {e}"))?;

    let current_version = app.package_info().version.to_string();

    match update {
        Some(update) => {
            let available = is_update_available(&current_version, &update.version);
            if !available {
                *state.pending_update.lock().unwrap() = None;
                return Ok(UpdateInfo {
                    available: false,
                    version: None,
                    current_version,
                    body: None,
                    date: None,
                    download_url: None,
                });
            }

            let info = UpdateInfo {
                available: true,
                version: Some(update.version.clone()),
                current_version,
                body: update.body.clone(),
                date: update.date.map(|d| d.to_string()),
                download_url: Some(update.download_url.to_string()),
            };

            let rid = app.resources_table().add(update);
            *state.pending_update.lock().unwrap() = Some(rid);

            Ok(info)
        }
        None => {
            *state.pending_update.lock().unwrap() = None;
            Ok(UpdateInfo {
                available: false,
                version: None,
                current_version,
                body: None,
                date: None,
                download_url: None,
            })
        }
    }
}

#[tauri::command]
pub async fn download_update(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<bool, String> {
    state.cancel_flag.store(false, Ordering::SeqCst);
    let cancel = state.cancel_flag.clone();

    let rid_opt = *state.pending_update.lock().unwrap();
    let rid = rid_opt.ok_or_else(|| "no pending update to download".to_string())?;

    let update_arc = app
        .resources_table()
        .get::<Update>(rid)
        .map_err(|e| format!("failed to retrieve pending update: {e}"))?;

    let app_handle = app.clone();
    let bytes = update_arc
        .download(
            move |downloaded, total| {
                if cancel.load(Ordering::SeqCst) {
                    return;
                }
                let _ = app_handle.emit(
                    "update://progress",
                    DownloadProgress { downloaded, total },
                );
            },
            || {},
        )
        .await
        .map_err(|e| format!("download failed: {e}"))?;

    if state.cancel_flag.load(Ordering::SeqCst) {
        return Ok(false);
    }

    *state.downloaded_bytes.lock().unwrap() = Some(bytes.clone());
    let _ = app.emit("update://download-complete", bytes.len());
    Ok(true)
}

#[tauri::command]
pub async fn install_update(
    app: AppHandle,
    state: State<'_, UpdateState>,
) -> Result<bool, String> {
    let rid_opt = *state.pending_update.lock().unwrap();
    let rid = rid_opt.ok_or_else(|| "no pending update to install".to_string())?;

    let bytes = state
        .downloaded_bytes
        .lock()
        .unwrap()
        .take()
        .ok_or_else(|| "no downloaded bytes — call download_update first".to_string())?;

    let update_arc = app
        .resources_table()
        .get::<Update>(rid)
        .map_err(|e| format!("failed to retrieve pending update: {e}"))?;

    update_arc
        .install(&bytes)
        .map_err(|e| format!("install failed: {e}"))?;

    *state.pending_update.lock().unwrap() = None;
    Ok(true)
}

#[tauri::command]
pub fn cancel_update(state: State<'_, UpdateState>) -> bool {
    state.cancel_flag.store(true, Ordering::SeqCst);
    true
}

#[tauri::command]
pub fn get_update_config(state: State<'_, UpdateState>) -> UpdateConfig {
    state.config.lock().unwrap().clone()
}

#[tauri::command]
pub fn set_update_config(
    state: State<'_, UpdateState>,
    config: UpdateConfig,
) -> UpdateConfig {
    let mut current = state.config.lock().unwrap();
    *current = config.clone();
    config
}
