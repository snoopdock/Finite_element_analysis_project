#!/usr/bin/env python3
"""Centralized logging configuration for the pipeline."""

import logging
import sys

def setup_logger(name: str = "fea_pipeline", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger that writes to stderr."""
    logger = logging.getLogger(name)
    
    # Prevent adding multiple handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    logger.setLevel(level)
    return logger

# Global logger instance
logger = setup_logger()
