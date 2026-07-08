fn main() {
    // tauri-build validates `bundle.externalBin` entries by checking that a
    // target-triple-suffixed sibling exists — e.g. for
    // `../backend/dist/ganesh-backend` it looks for
    // `../backend/dist/ganesh-backend-x86_64-unknown-linux-gnu`.
    //
    // In dev (`cargo check` / `cargo run`) the PyInstaller sidecar hasn't
    // been built yet — and isn't needed, because `resolve_sidecar` in
    // main.rs falls back to `python3 backend/main.py`. To keep the README's
    // dev workflow (`cargo check`) runnable without a multi-minute
    // PyInstaller build, create an empty placeholder at the expected path
    // when the real binary is absent.
    //
    // Bundle builds replace the placeholder with the real artifact (see
    // scripts/build-*.sh / build-*.ps1, which symlink/copy the suffixed
    // name onto the PyInstaller output).
    if let Ok(target) = std::env::var("TARGET") {
        let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into());
        let placeholder = std::path::Path::new(&manifest_dir)
            .join("..")
            .join("backend")
            .join("dist")
            .join(format!("ganesh-backend-{target}"));
        if !placeholder.exists() {
            if let Some(parent) = placeholder.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            match std::fs::write(&placeholder, b"") {
                Ok(()) => println!(
                    "cargo:warning=created empty sidecar placeholder at {} \
                     (dev only; real binary built by PyInstaller at bundle time)",
                    placeholder.display()
                ),
                Err(e) => println!(
                    "cargo:warning=could not create sidecar placeholder at {}: {}",
                    placeholder.display(),
                    e
                ),
            }
        }
    }

    tauri_build::build()
}
