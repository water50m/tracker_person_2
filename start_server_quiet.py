#!/usr/bin/env python3
"""Start uvicorn server with minimal logging"""

import uvicorn
import logging

# Reduce logging verbosity
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="warning",
        access_log=False,  # Disable access log
    )
