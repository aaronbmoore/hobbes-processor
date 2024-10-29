import os
import shutil
import subprocess
from pathlib import Path
from typing import List

def clean_dist():
    """Clean dist directory"""
    dist_dir = Path("dist")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir()

def copy_shared(function_dir: Path):
    """Copy shared code to function directory"""
    shared_dir = Path("src/shared")
    dest_dir = function_dir / "shared"
    shutil.copytree(shared_dir, dest_dir)

def copy_function(function_name: str, function_dir: Path):
    """Copy function code to build directory"""
    src_dir = Path(f"src/{function_name}")
    for item in src_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, function_dir)

def create_zip(function_dir: Path, output_path: Path):
    """Create ZIP file for Lambda deployment"""
    shutil.make_archive(str(output_path.with_suffix("")), "zip", function_dir)

def build_function(function_name: str):
    """Build Lambda function package"""
    print(f"Building {function_name}...")
    dist_dir = Path("dist")
    function_dir = dist_dir / function_name
    function_dir.mkdir()

    # Copy code
    copy_shared(function_dir)
    copy_function(function_name, function_dir)

    # Create ZIP
    create_zip(function_dir, dist_dir / f"{function_name}.zip")
    print(f"Created {function_name}.zip")

def main():
    """Main build script"""
    clean_dist()
    
    functions = ["webhook_handler", "file_processor"]
    for function in functions:
        build_function(function)

if __name__ == "__main__":
    main()