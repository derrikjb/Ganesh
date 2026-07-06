//! Ganesh Tauri shell library.
//!
//! Contains the testable sidecar lifecycle logic used by the Tauri binary:
//!   * spawning the Python sidecar process,
//!   * reading the `PORT: <port>` line from its stdout,
//!   * graceful shutdown via SIGTERM with a timeout fallback to SIGKILL.
//!
//! The app binary (`main.rs`) wires these primitives into the Tauri runtime,
//! but the core logic lives here so it can be unit-tested with mock sidecar
//! scripts without booting a full Tauri window.

pub mod commands;

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

// ---------------------------------------------------------------------------
// System tray + global hotkey configuration
// ---------------------------------------------------------------------------

/// Menu item ID for the "Show" tray menu entry.
pub const TRAY_SHOW_ID: &str = "tray_show";
/// Menu item ID for the "Hide" tray menu entry.
pub const TRAY_HIDE_ID: &str = "tray_hide";
/// Menu item ID for the "Quit" tray menu entry.
pub const TRAY_QUIT_ID: &str = "tray_quit";

/// Accelerator string for the global toggle-window hotkey.
///
/// `Control+Shift+G` is used on both Windows and Linux (the only supported
/// platforms). macOS is out of scope; if it ever lands, swap to `Super+Shift+G`.
pub const HOTKEY_TOGGLE: &str = "Control+Shift+G";

/// The ordered `(id, label)` pairs that make up the tray context menu.
///
/// Kept as pure data so the menu structure can be unit-tested without
/// constructing a live Tauri `AppHandle` (which needs a windowing system).
/// `main.rs` turns this spec into real `MenuItem`s at setup time.
pub fn tray_menu_spec() -> &'static [(&'static str, &'static str)] {
    &[
        (TRAY_SHOW_ID, "Show"),
        (TRAY_HIDE_ID, "Hide"),
        (TRAY_QUIT_ID, "Quit"),
    ]
}

/// Decide whether a close request should be intercepted (minimize to tray)
/// or allowed to proceed (real quit).
///
/// Returns `true` when the window should be hidden instead of closed — i.e.
/// always, for the minimize-to-tray behaviour. Exposed as a function so the
/// policy is testable without a window.
pub fn should_minimize_to_tray() -> bool {
    true
}

/// Prefix emitted by the sidecar on stdout once it has bound a port.
pub const PORT_PREFIX: &str = "PORT: ";

/// Default grace period before force-killing the sidecar on shutdown.
pub const DEFAULT_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);

/// A handle to a running sidecar: the child process plus the discovered port.
pub struct SidecarHandle {
    pub child: Child,
    pub port: u16,
}

/// Mutable app state holding the sidecar child + port, guarded by a mutex.
/// Stored in Tauri via `Builder::manage`.
pub struct SidecarState {
    pub child: Mutex<Option<Child>>,
    pub port: Mutex<Option<u16>>,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            port: Mutex::new(None),
        }
    }

    pub fn set(&self, handle: SidecarHandle) {
        *self.port.lock().unwrap() = Some(handle.port);
        *self.child.lock().unwrap() = Some(handle.child);
    }

    pub fn port(&self) -> Option<u16> {
        *self.port.lock().unwrap()
    }

    /// Take ownership of the child (for shutdown). Returns `None` if already
    /// taken or never set.
    pub fn take_child(&self) -> Option<Child> {
        self.child.lock().unwrap().take()
    }
}

impl Default for SidecarState {
    fn default() -> Self {
        Self::new()
    }
}

/// Parse a single stdout line for the `PORT: <port>` marker.
///
/// Returns `Some(port)` when the line begins with [`PORT_PREFIX`] followed by a
/// parseable `u16`. Trims surrounding whitespace so trailing `\r` (Windows
/// sidecars) does not break parsing.
pub fn parse_port_line(line: &str) -> Option<u16> {
    let rest = line.strip_prefix(PORT_PREFIX)?;
    rest.trim().parse::<u16>().ok()
}

/// Read lines from any `BufRead` until a `PORT: <port>` line is found.
///
/// Returns the port or `None` if the stream ends without a port line.
pub fn read_port_from_reader<R: BufRead>(reader: R) -> Option<u16> {
    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => return None,
        };
        if let Some(port) = parse_port_line(&line) {
            return Some(port);
        }
    }
    None
}

/// Spawn a sidecar binary and read its port from stdout.
///
/// `binary` is the path to the executable; `args` are forwarded verbatim.
/// The child's stdout is piped and scanned line-by-line for the `PORT:` marker.
/// stderr is inherited so sidecar diagnostics surface in the Tauri console.
pub fn spawn_sidecar(binary: &str, args: &[&str]) -> std::io::Result<SidecarHandle> {
    let mut child = Command::new(binary)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::Other, "no stdout pipe"))?;

    let reader = BufReader::new(stdout);
    let port = read_port_from_reader(reader).ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::UnexpectedEof,
            "sidecar exited without printing PORT line",
        )
    })?;

    Ok(SidecarHandle { child, port })
}

/// Send SIGTERM (Unix) or terminate (Windows) to the child, then wait up to
/// `timeout` for it to exit. If it does not exit in time, force-kill it.
///
/// Returns `Ok(())` once the child has been reaped (gracefully or not).
pub fn shutdown_sidecar(child: &mut Child, timeout: Duration) -> std::io::Result<()> {
    send_term(child)?;

    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        match child.try_wait()? {
            Some(_) => return Ok(()),
            None => std::thread::sleep(Duration::from_millis(50)),
        }
    }

    let _ = child.kill();
    child.wait()?;
    Ok(())
}

/// Send a graceful termination signal to the child.
///
/// On Unix this is `SIGTERM`; on Windows there is no equivalent so we fall
/// back to `TerminateProcess` (a hard kill) — Windows sidecars should install
/// a `CTRL_BREAK`/`CTRL_CLOSE` handler for graceful shutdown in future.
#[cfg(unix)]
fn send_term(child: &Child) -> std::io::Result<()> {
    let pid = child.id() as i32;
    // SAFETY: libc::kill is a thread-safe syscall; pid > 0 targets a single
    // process we own.
    unsafe {
        if libc::kill(pid, libc::SIGTERM) != 0 {
            return Err(std::io::Error::last_os_error());
        }
    }
    Ok(())
}

#[cfg(windows)]
fn send_term(child: &Child) -> std::io::Result<()> {
    child.kill()
}

// ---------------------------------------------------------------------------
// Auto-update
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum UpdateChannel {
    Stable,
    Beta,
}

impl UpdateChannel {
    pub fn as_str(self) -> &'static str {
        match self {
            UpdateChannel::Stable => "stable",
            UpdateChannel::Beta => "beta",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct UpdateConfig {
    pub channel: UpdateChannel,
    pub auto_check: bool,
}

impl Default for UpdateConfig {
    fn default() -> Self {
        Self {
            channel: UpdateChannel::Stable,
            auto_check: true,
        }
    }
}

pub fn parse_update_channel(s: &str) -> Option<UpdateChannel> {
    match s.trim().to_ascii_lowercase().as_str() {
        "stable" => Some(UpdateChannel::Stable),
        "beta" => Some(UpdateChannel::Beta),
        _ => None,
    }
}

pub fn select_endpoint<'a>(
    endpoints: &'a [(&'static str, &'a str)],
    channel: UpdateChannel,
) -> Option<&'a str> {
    endpoints
        .iter()
        .find(|(c, _)| {
            parse_update_channel(c).map(|ch| ch == channel).unwrap_or(false)
        })
        .map(|(_, url)| *url)
}

pub fn should_auto_check(config: &UpdateConfig) -> bool {
    config.auto_check
}

pub fn compare_versions(current: &str, available: &str) -> std::cmp::Ordering {
    let parse = |s: &str| -> Vec<u64> {
        s.trim()
            .trim_start_matches('v')
            .split(|c: char| !c.is_ascii_digit())
            .filter(|p| !p.is_empty())
            .filter_map(|p| p.parse::<u64>().ok())
            .collect()
    };
    let cur = parse(current);
    let avl = parse(available);
    let len = cur.len().max(avl.len());
    for i in 0..len {
        let c = cur.get(i).copied().unwrap_or(0);
        let a = avl.get(i).copied().unwrap_or(0);
        match c.cmp(&a) {
            std::cmp::Ordering::Equal => continue,
            ord => return ord,
        }
    }
    std::cmp::Ordering::Equal
}

pub fn is_update_available(current: &str, available: &str) -> bool {
    compare_versions(current, available) == std::cmp::Ordering::Less
}

pub fn build_endpoint_url(template: &str, channel: UpdateChannel, current_version: &str, target: &str) -> String {
    template
        .replace("{{channel}}", channel.as_str())
        .replace("{{current_version}}", current_version)
        .replace("{{target}}", target)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn mock_sidecar_script(body: &str) -> String {
        // `& wait` makes the long-running command interruptible by the TERM
        // trap — a foreground `sleep` would block signal delivery until done.
        format!("trap 'exit 0' TERM; {body} & wait")
    }

    #[test]
    fn test_parse_port_line_valid() {
        assert_eq!(parse_port_line("PORT: 12345"), Some(12345));
        assert_eq!(parse_port_line("PORT: 0"), Some(0));
        assert_eq!(parse_port_line("PORT: 65535"), Some(65535));
    }

    #[test]
    fn test_parse_port_line_trims_whitespace() {
        assert_eq!(parse_port_line("PORT: 8080\r\n"), Some(8080));
        assert_eq!(parse_port_line("PORT:   9999  "), Some(9999));
    }

    #[test]
    fn test_parse_port_line_rejects_invalid() {
        assert_eq!(parse_port_line("not a port line"), None);
        assert_eq!(parse_port_line("PORT: abc"), None);
        assert_eq!(parse_port_line("PORT: 999999"), None);
        assert_eq!(parse_port_line(" PORT: 1234"), None);
    }

    #[test]
    fn test_read_port_from_reader_finds_port() {
        let input = "Starting up...\nSome log\nPORT: 4242\nMore output\n";
        let reader = Cursor::new(input);
        assert_eq!(read_port_from_reader(reader), Some(4242));
    }

    #[test]
    fn test_read_port_from_reader_no_port() {
        let input = "no port here\njust logs\n";
        let reader = Cursor::new(input);
        assert_eq!(read_port_from_reader(reader), None);
    }

    #[test]
    fn test_sidecar_spawn_reads_port() {
        let script = mock_sidecar_script("echo 'PORT: 31337'; sleep 30");
        let mut child = Command::new("sh")
            .arg("-c")
            .arg(&script)
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("failed to spawn mock sidecar");

        let stdout = child.stdout.take().expect("stdout pipe");
        let port = read_port_from_reader(BufReader::new(stdout));
        assert_eq!(port, Some(31337));

        let _ = child.kill();
        let _ = child.wait();
    }

    #[test]
    fn test_sidecar_spawn_full_flow() {
        let script = mock_sidecar_script("echo 'PORT: 22000'; sleep 30");
        let handle = spawn_sidecar("sh", &["-c", &script]).expect("spawn failed");
        assert_eq!(handle.port, 22000);

        let mut child = handle.child;
        match child.try_wait() {
            Ok(None) => {}
            Ok(Some(status)) => panic!("sidecar exited early: {status}"),
            Err(e) => panic!("try_wait failed: {e}"),
        }

        let _ = child.kill();
        let _ = child.wait();
    }

    #[test]
    fn test_shutdown_graceful_exit() {
        let script = mock_sidecar_script("echo 'PORT: 1'; sleep 30");
        let handle = spawn_sidecar("sh", &["-c", &script]).expect("spawn failed");
        let mut child = handle.child;

        let start = Instant::now();
        shutdown_sidecar(&mut child, Duration::from_secs(3)).expect("shutdown failed");
        let elapsed = start.elapsed();

        assert!(elapsed < Duration::from_secs(3), "shutdown took too long: {elapsed:?}");

        match child.try_wait() {
            Ok(Some(_)) => {}
            Ok(None) => panic!("child still running after shutdown"),
            Err(e) => panic!("try_wait failed: {e}"),
        }
    }

    #[test]
    fn test_shutdown_force_kills_unresponsive() {
        let python = std::env::var("PYTHON3").unwrap_or_else(|_| "python3".to_string());
        let py_ok = Command::new(&python)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !py_ok {
            eprintln!("skipping test_shutdown_force_kills_unresponsive: python3 unavailable");
            return;
        }

        let script = "import signal, time; signal.signal(signal.SIGTERM, lambda *a: None); print('PORT: 1', flush=True); time.sleep(30)";
        let handle = spawn_sidecar(&python, &["-c", script]).expect("spawn failed");
        let mut child = handle.child;

        let start = Instant::now();
        shutdown_sidecar(&mut child, Duration::from_millis(500)).expect("shutdown failed");
        let elapsed = start.elapsed();

        assert!(elapsed < Duration::from_secs(3), "force-kill took too long: {elapsed:?}");
        match child.try_wait() {
            Ok(Some(_)) => {}
            Ok(None) => panic!("child still running after force-kill"),
            Err(e) => panic!("try_wait failed: {e}"),
        }
    }

    #[test]
    fn test_sidecar_state_set_and_get() {
        let state = SidecarState::new();
        assert_eq!(state.port(), None);

        *state.port.lock().unwrap() = Some(42);
        assert_eq!(state.port(), Some(42));
        assert!(state.take_child().is_none());
    }

    #[test]
    fn test_tray_menu_items() {
        let spec = tray_menu_spec();
        assert_eq!(spec.len(), 3, "tray menu must have exactly 3 items");

        let (show_id, show_label) = spec[0];
        assert_eq!(show_id, TRAY_SHOW_ID);
        assert_eq!(show_label, "Show");

        let (hide_id, hide_label) = spec[1];
        assert_eq!(hide_id, TRAY_HIDE_ID);
        assert_eq!(hide_label, "Hide");

        let (quit_id, quit_label) = spec[2];
        assert_eq!(quit_id, TRAY_QUIT_ID);
        assert_eq!(quit_label, "Quit");

        let ids: Vec<&str> = spec.iter().map(|(id, _)| *id).collect();
        let unique: std::collections::HashSet<&str> = ids.iter().copied().collect();
        assert_eq!(ids.len(), unique.len(), "tray menu item IDs must be unique");
    }

    #[test]
    fn test_hotkey_registration() {
        let wrapper =
            tauri_plugin_global_shortcut::ShortcutWrapper::try_from(HOTKEY_TOGGLE);
        assert!(
            wrapper.is_ok(),
            "HOTKEY_TOGGLE ({HOTKEY_TOGGLE}) must parse into a valid Shortcut"
        );
    }

    #[test]
    fn test_minimize_to_tray_policy() {
        assert!(
            should_minimize_to_tray(),
            "close button must minimize to tray, not quit"
        );
    }

    #[test]
    fn test_parse_update_channel_valid() {
        assert_eq!(parse_update_channel("stable"), Some(UpdateChannel::Stable));
        assert_eq!(parse_update_channel("beta"), Some(UpdateChannel::Beta));
        assert_eq!(parse_update_channel("  Stable "), Some(UpdateChannel::Stable));
        assert_eq!(parse_update_channel("BETA"), Some(UpdateChannel::Beta));
    }

    #[test]
    fn test_parse_update_channel_invalid() {
        assert_eq!(parse_update_channel("nightly"), None);
        assert_eq!(parse_update_channel(""), None);
        assert_eq!(parse_update_channel("alpha"), None);
    }

    #[test]
    fn test_update_channel_as_str() {
        assert_eq!(UpdateChannel::Stable.as_str(), "stable");
        assert_eq!(UpdateChannel::Beta.as_str(), "beta");
    }

    #[test]
    fn test_update_config_default() {
        let cfg = UpdateConfig::default();
        assert_eq!(cfg.channel, UpdateChannel::Stable);
        assert!(cfg.auto_check);
    }

    #[test]
    fn test_should_auto_check() {
        assert!(should_auto_check(&UpdateConfig { channel: UpdateChannel::Stable, auto_check: true }));
        assert!(!should_auto_check(&UpdateConfig { channel: UpdateChannel::Beta, auto_check: false }));
    }

    #[test]
    fn test_select_endpoint_matches_channel() {
        let endpoints: &[(&'static str, &str)] = &[
            ("stable", "https://releases.ganesh.ai/stable"),
            ("beta", "https://releases.ganesh.ai/beta"),
        ];
        assert_eq!(select_endpoint(endpoints, UpdateChannel::Stable), Some("https://releases.ganesh.ai/stable"));
        assert_eq!(select_endpoint(endpoints, UpdateChannel::Beta), Some("https://releases.ganesh.ai/beta"));
    }

    #[test]
    fn test_select_endpoint_no_match() {
        let endpoints: &[(&'static str, &str)] = &[("stable", "https://releases.ganesh.ai/stable")];
        assert_eq!(select_endpoint(endpoints, UpdateChannel::Beta), None);
    }

    #[test]
    fn test_select_endpoint_empty() {
        let endpoints: &[(&'static str, &str)] = &[];
        assert_eq!(select_endpoint(endpoints, UpdateChannel::Stable), None);
    }

    #[test]
    fn test_compare_versions_equal() {
        assert_eq!(compare_versions("0.1.0", "0.1.0"), std::cmp::Ordering::Equal);
        assert_eq!(compare_versions("1.0.0", "1.0.0"), std::cmp::Ordering::Equal);
    }

    #[test]
    fn test_compare_versions_less() {
        assert_eq!(compare_versions("0.1.0", "0.2.0"), std::cmp::Ordering::Less);
        assert_eq!(compare_versions("1.0.0", "1.0.1"), std::cmp::Ordering::Less);
        assert_eq!(compare_versions("0.9.9", "1.0.0"), std::cmp::Ordering::Less);
    }

    #[test]
    fn test_compare_versions_greater() {
        assert_eq!(compare_versions("0.2.0", "0.1.0"), std::cmp::Ordering::Greater);
        assert_eq!(compare_versions("2.0.0", "1.9.9"), std::cmp::Ordering::Greater);
    }

    #[test]
    fn test_compare_versions_strips_v_prefix() {
        assert_eq!(compare_versions("v0.1.0", "0.1.0"), std::cmp::Ordering::Equal);
        assert_eq!(compare_versions("v1.0.0", "v0.9.0"), std::cmp::Ordering::Greater);
    }

    #[test]
    fn test_compare_versions_different_length() {
        assert_eq!(compare_versions("1.0", "1.0.0"), std::cmp::Ordering::Equal);
        assert_eq!(compare_versions("1.0.0", "1.0.1"), std::cmp::Ordering::Less);
    }

    #[test]
    fn test_is_update_available() {
        assert!(is_update_available("0.1.0", "0.2.0"));
        assert!(!is_update_available("0.2.0", "0.1.0"));
        assert!(!is_update_available("0.1.0", "0.1.0"));
    }

    #[test]
    fn test_build_endpoint_url_substitutes_placeholders() {
        let url = build_endpoint_url(
            "https://releases.ganesh.ai/{{target}}/{{current_version}}/{{channel}}",
            UpdateChannel::Beta,
            "0.1.0",
            "linux-x86_64",
        );
        assert_eq!(url, "https://releases.ganesh.ai/linux-x86_64/0.1.0/beta");
    }

    #[test]
    fn test_build_endpoint_url_no_placeholders() {
        let url = build_endpoint_url(
            "https://releases.ganesh.ai/static.json",
            UpdateChannel::Stable,
            "0.1.0",
            "linux",
        );
        assert_eq!(url, "https://releases.ganesh.ai/static.json");
    }

    #[test]
    fn test_update_config_serde_roundtrip() {
        let cfg = UpdateConfig { channel: UpdateChannel::Beta, auto_check: false };
        let json = serde_json::to_string(&cfg).expect("serialize");
        let back: UpdateConfig = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(cfg, back);
        assert!(json.contains("\"beta\""));
    }
}
