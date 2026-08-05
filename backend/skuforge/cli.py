"""Terminal runner: python -m skuforge.cli MPN BRAND [DESCRIPTION]"""
import json
import sys

from . import config
from .models import SKUInput
from .orchestrator import run_sku


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: python -m skuforge.cli MPN BRAND [DESCRIPTION]")
        sys.exit(1)
    sku = SKUInput(
        mpn=sys.argv[1],
        brand=sys.argv[2],
        description=sys.argv[3] if len(sys.argv) > 3 else "",
    )
    mode = "MOCK" if config.MOCK_MODE else "LIVE"
    print(f"[{mode}] SKUForge pipeline: {sku.brand} {sku.mpn}\n")

    record = run_sku(sku, emit=lambda e: print(f"  [{e.agent:<10}] {e.step}"))

    print("\n=== RECORD ===")
    print(json.dumps(record.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()
