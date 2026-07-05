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

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

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
}
