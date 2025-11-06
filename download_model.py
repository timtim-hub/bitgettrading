#!/usr/bin/env python3
"""Download pre-trained model weights."""

import argparse
from pathlib import Path

import requests
from tqdm import tqdm

from src.bitget_trading.logger import setup_logging

logger = setup_logging()


def download_file(url: str, destination: Path) -> None:
    """
    Download file with progress bar.
    
    Args:
        url: URL to download from
        destination: Where to save the file
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    destination.parent.mkdir(parents=True, exist_ok=True)
    
    with open(destination, 'wb') as f, tqdm(
        total=total_size,
        unit='B',
        unit_scale=True,
        desc=destination.name
    ) as pbar:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            pbar.update(len(chunk))
    
    logger.info("model_downloaded", path=str(destination), size_mb=total_size / 1024 / 1024)


def main() -> None:
    """Download pre-trained model."""
    parser = argparse.ArgumentParser(description="Download pre-trained model")
    parser.add_argument(
        "--url",
        type=str,
        default="https://huggingface.co/timtim-hub/bitget-sol-model/resolve/main/sol_model_2025.pth",
        help="URL to download model from"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/sol_model_2025.pth",
        help="Output path for model"
    )
    
    args = parser.parse_args()
    
    output_path = Path(args.output)
    
    if output_path.exists():
        logger.warning("model_already_exists", path=str(output_path))
        response = input("Overwrite? (y/n): ")
        if response.lower() != 'y':
            logger.info("download_cancelled")
            return
    
    try:
        logger.info("downloading_model", url=args.url)
        download_file(args.url, output_path)
        logger.info("download_completed")
    except requests.exceptions.RequestException as e:
        logger.error("download_failed", error=str(e))
        logger.info("You can train your own model by running: poetry run python train_model.py")


if __name__ == "__main__":
    main()

