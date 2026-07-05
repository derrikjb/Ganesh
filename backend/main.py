import sys
import argparse

def check_imports():
    deps = ["fastapi", "uvicorn", "litellm", "pydantic", "keyring"]
    failed = []
    
    print("Checking native dependencies...")
    for dep in deps:
        try:
            __import__(dep)
            print(f"  [OK] {dep}")
        except ImportError as e:
            print(f"  [FAIL] {dep}: {e}")
            failed.append(dep)
            
    if failed:
        print(f"\nImport check failed for: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("\nAll native dependencies imported successfully.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Ganesh Backend Server")
    parser.add_argument("--check-imports", action="store_true", help="Check if native dependencies are importable and exit")
    
    args, unknown = parser.parse_known_args()
    
    if args.check_imports:
        check_imports()
        
    print("Ganesh Backend starting...")

if __name__ == "__main__":
    main()
