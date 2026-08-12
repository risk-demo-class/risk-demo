"""Deprecated compatibility entry point for Step 6 manufacturing training.

The former ecommerce-like random feature generator was removed because it did not
come from the six manufacturing business tables or the accepted 25-feature code.
Use the snapshot dataset produced by gen_train_dataset.py instead.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.train_xgb_model import main


if __name__ == "__main__":
    main()
