#!/usr/bin/env python3
"""
Simple ManaPool Pricer - Single File Version

Prices cards using only ManaPool pricing sources (NM and LP+ prices).
No MTGJSON or other external dependencies.

Configuration is set directly in this file - just edit the CONFIGURATION section below.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any

import requests

# ============================================================================
# CONFIGURATION - Edit these values directly
# ============================================================================

# === API CREDENTIALS (Required) ===
API_BASE_URL = "https://manapool.com/api/v1"
API_EMAIL = ""
API_TOKEN = ""

# === PRICING SETTINGS (Optional) ===
DRY_RUN = True

# Pricing strategy options:
#   "nm_with_floor" - Use NM price, never go below LP+ (safest, recommended)
#   "lp_plus"       - Use LP+ price only (conservative pricing)
#   "average"       - Average NM and LP+ prices (balanced)
#   "nm_only"       - Use only NM price (aggressive)
#   "general_low"   - Use price_cents (general/market price - most competitive)
PRICING_STRATEGY = "lp_plus"

LP_FLOOR_PERCENT = 100.0      # LP+ floor percentage (100 = strict floor)
MIN_PRICE = 0.01              # Minimum price in dollars
MAX_REDUCTION_PERCENT = 5.0   # Maximum price drop per run (%)

# ============================================================================
# END CONFIGURATION
# ============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class SimpleManaPoolPricer:
    """Simple pricer using only ManaPool API pricing sources."""

    def __init__(self):
        """Initialize the pricer with environment configuration."""
        self._load_config()
        self._setup_session()

    def _load_config(self):
        """Load configuration from script constants."""
        # Load settings from constants defined at top of file
        self.base_url = API_BASE_URL.rstrip('/')
        self.email = API_EMAIL
        self.access_token = API_TOKEN

        if not all([self.base_url, self.email, self.access_token]):
            logger.error("")
            logger.error("=" * 80)
            logger.error("CONFIGURATION ERROR - Missing API Credentials")
            logger.error("=" * 80)
            logger.error("")
            logger.error("Please edit this script and set your credentials:")
            logger.error("")
            logger.error("  1. Open this file in a text editor")
            logger.error("  2. Find the CONFIGURATION section at the top (around line 25)")
            logger.error("  3. Set your credentials:")
            logger.error("")
            logger.error("     API_EMAIL = \"your-email@example.com\"")
            logger.error("     API_TOKEN = \"your-access-token-here\"")
            logger.error("")
            logger.error("=" * 80)
            sys.exit(1)

        # Load optional settings from constants
        self.dry_run = DRY_RUN
        self.pricing_strategy = PRICING_STRATEGY
        self.lp_floor_percent = LP_FLOOR_PERCENT
        self.min_price = MIN_PRICE
        self.max_reduction_percent = MAX_REDUCTION_PERCENT

        logger.info("=" * 80)
        logger.info("Simple ManaPool Pricer - Configuration")
        logger.info("=" * 80)
        logger.info(f"API Base URL: {self.base_url}")
        logger.info(f"Email: {self.email}")
        logger.info(f"Dry Run: {self.dry_run}")
        logger.info(f"Pricing Strategy: {self.pricing_strategy}")
        logger.info(f"LP+ Floor: {self.lp_floor_percent}%")
        logger.info(f"Min Price: ${self.min_price}")
        logger.info(f"Max Reduction: {self.max_reduction_percent}%")
        logger.info("=" * 80)
        logger.info("")

    def _setup_session(self):
        """Setup HTTP session with authentication."""
        self.session = requests.Session()
        self.session.headers.update({
            "X-ManaPool-Email": self.email,
            "X-ManaPool-Access-Token": self.access_token,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_inventory(self) -> list[dict[str, Any]]:
        """Fetch all inventory from ManaPool API."""
        logger.info("[1/4] Fetching inventory from ManaPool...")

        all_items = []
        offset = 0
        limit = 10000

        while True:
            url = f"{self.base_url}/seller/inventory"
            params = {"limit": limit, "offset": offset}

            try:
                response = self.session.get(url, params=params, timeout=60)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch inventory: {e}")
                sys.exit(1)

            inventory = data.get("inventory", [])
            all_items.extend(inventory)

            pagination = data.get("pagination", {})
            total = pagination.get("total", 0)
            returned = pagination.get("returned", 0)

            logger.info(f"  Fetched {len(all_items):,}/{total:,} items")

            if len(all_items) >= total or returned < limit:
                break

            offset += limit

        logger.info(f"  Total inventory items: {len(all_items):,}")
        logger.info("")
        return all_items

    def fetch_prices(self) -> dict[str, dict[str, Any]]:
        """Fetch pricing data from ManaPool API."""
        logger.info("[2/4] Fetching price data from ManaPool...")

        url = f"{self.base_url}/prices/singles"

        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch prices: {e}")
            sys.exit(1)

        cards = data.get("data", [])
        logger.info(f"  Received {len(cards):,} price records")

        # Index by both scryfall_id AND product_id for flexible lookup
        price_index = {}
        for card in cards:
            # Index by scryfall_id
            scryfall_id = card.get("scryfall_id")
            if scryfall_id:
                price_index[scryfall_id] = card

            # Also index by product_id (ManaPool ID) if available
            product_id = card.get("id") or card.get("product_id")
            if product_id:
                price_index[product_id] = card

        logger.info(f"  Indexed {len(price_index):,} unique entries (by scryfall_id and product_id)")
        logger.info("")
        return price_index

    def calculate_new_price(
        self,
        current_price: float,
        nm_price: float | None,
        lp_plus_price: float | None,
        general_price: float | None = None,
    ) -> tuple[float | None, str]:
        """
        Calculate new price based on strategy.

        Returns:
            (new_price, reason) tuple
        """
        if self.pricing_strategy == "nm_only":
            if nm_price is None:
                return None, "No NM price available"
            new_price = nm_price
            reason = f"NM price: ${nm_price:.2f}"

        elif self.pricing_strategy == "lp_plus":
            if lp_plus_price is None:
                return None, "No LP+ price available"
            new_price = lp_plus_price
            reason = f"LP+ price: ${lp_plus_price:.2f}"

        elif self.pricing_strategy == "average":
            prices = [p for p in [nm_price, lp_plus_price] if p is not None]
            if not prices:
                return None, "No pricing data available"
            new_price = sum(prices) / len(prices)
            reason = f"Average of {len(prices)} sources: ${new_price:.2f}"

        elif self.pricing_strategy == "general_low":
            # Use general/market price (price_cents)
            if general_price is None:
                return None, "No general price available"
            new_price = general_price
            reason = f"General/market price: ${general_price:.2f}"

        else:  # nm_with_floor (default)
            if nm_price is None:
                return None, "No NM price available"

            new_price = nm_price
            reason = f"NM: ${nm_price:.2f}"

            # Apply LP+ floor if available
            if lp_plus_price is not None:
                lp_floor = lp_plus_price * (self.lp_floor_percent / 100.0)
                if new_price < lp_floor:
                    new_price = lp_floor
                    reason += f" (LP+ floor: ${lp_floor:.2f})"

        # Apply minimum price
        if new_price < self.min_price:
            new_price = self.min_price
            reason += f" (min: ${self.min_price})"

        # Apply maximum reduction cap
        if current_price > 0:
            max_reduction = current_price * (self.max_reduction_percent / 100.0)
            min_allowed = current_price - max_reduction
            if new_price < min_allowed:
                new_price = min_allowed
                reason += f" (capped at {self.max_reduction_percent}% reduction)"

        return new_price, reason

    def process_inventory(
        self,
        inventory: list[dict[str, Any]],
        price_data: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process inventory and calculate new prices."""
        logger.info("[3/4] Processing inventory and calculating new prices...")

        # Debug: Show sample inventory item structure
        if inventory:
            logger.info("")
            logger.info("Debug - Sample inventory item fields:")
            sample = inventory[0]
            logger.info(f"  Keys: {list(sample.keys())}")
            logger.info(f"  Sample: {dict(list(sample.items())[:5])}")
            logger.info("")

        # Debug: Show sample price data structure
        if price_data:
            logger.info("Debug - Sample price data:")
            sample_key = list(price_data.keys())[0]
            logger.info(f"  Sample key: {sample_key}")
            logger.info(f"  Sample value keys: {list(price_data[sample_key].keys())[:10]}")
            logger.info("")

        updates = []
        stats = {
            "total": 0,
            "no_data": 0,
            "no_change": 0,
            "increased": 0,
            "decreased": 0,
            "errors": 0,
        }

        for item in inventory:
            stats["total"] += 1

            try:
                # Handle nested structure: product -> single -> scryfall_id
                product = item.get("product", {})
                single = product.get("single", {})

                # Skip if not a single (e.g., sealed product without single data)
                if not single:
                    stats["no_data"] += 1
                    continue

                scryfall_id = single.get("scryfall_id")
                product_id = product.get("id")  # ManaPool product ID

                # Try to get pricing data - first by scryfall_id, then by product_id
                card_data = None
                if scryfall_id:
                    card_data = price_data.get(scryfall_id)
                if not card_data and product_id:
                    card_data = price_data.get(product_id)

                if not card_data:
                    stats["no_data"] += 1
                    continue

                # Get fields from the nested structure
                finish = single.get("finish_id", "NF")
                condition = single.get("condition_id", "NM")
                language = single.get("language_id", "en")
                name = single.get("name", "Unknown")
                set_code = single.get("set", "???")

                # Price is at the top level
                current_price = item.get("price_cents", 0) / 100.0

                # Use scryfall_id if available, otherwise use product_id for updates
                lookup_id = scryfall_id or product_id
                if not lookup_id:
                    stats["no_data"] += 1
                    continue

                # Extract NM, LP+, and general prices based on finish
                nm_price = self._get_nm_price(card_data, finish)
                lp_plus_price = self._get_lp_plus_price(card_data, finish)
                general_price = self._get_general_price(card_data, finish)

                # Calculate new price
                new_price, reason = self.calculate_new_price(
                    current_price,
                    nm_price,
                    lp_plus_price,
                    general_price
                )

                if new_price is None:
                    stats["no_data"] += 1
                    continue

                # Round to 2 decimal places
                new_price = round(new_price, 2)

                # Check if price changed
                if abs(new_price - current_price) < 0.01:
                    stats["no_change"] += 1
                    continue

                # Track increase/decrease
                if new_price > current_price:
                    stats["increased"] += 1
                elif new_price < current_price:
                    stats["decreased"] += 1

                # Create update record
                # Note: API requires scryfall_id for updates
                updates.append({
                    "scryfall_id": lookup_id,  # Use whatever ID we found
                    "finish_id": finish,
                    "condition_id": condition,
                    "language_id": language,
                    "price_cents": int(new_price * 100),
                    "quantity": item.get("quantity", 0),
                    # Metadata for reporting
                    "_name": name,
                    "_set": set_code,
                    "_current_price": current_price,
                    "_new_price": new_price,
                    "_reason": reason,
                    "_matched_by": "scryfall_id" if scryfall_id and price_data.get(scryfall_id) else "product_id",
                })

            except Exception as e:
                stats["errors"] += 1
                logger.debug(f"Error processing {item.get('name', 'unknown')}: {e}")

        logger.info("")
        logger.info("  Processing Summary:")
        logger.info(f"    Total cards: {stats['total']:,}")
        logger.info(f"    No price data: {stats['no_data']:,}")
        logger.info(f"    No change: {stats['no_change']:,}")
        logger.info(f"    Increases: {stats['increased']:,}")
        logger.info(f"    Decreases: {stats['decreased']:,}")
        logger.info(f"    Errors: {stats['errors']:,}")
        logger.info(f"    Total updates: {len(updates):,}")
        logger.info("")

        return updates

    def _get_nm_price(self, card_data: dict, finish: str) -> float | None:
        """Extract NM price for given finish."""
        field_map = {
            "NF": "price_cents_nm",
            "FO": "price_cents_nm_foil",
            "EF": "price_cents_nm_etched",
        }
        field = field_map.get(finish)
        if not field:
            return None

        price_cents = card_data.get(field)
        if price_cents is None:
            return None

        return float(price_cents) / 100.0

    def _get_lp_plus_price(self, card_data: dict, finish: str) -> float | None:
        """Extract LP+ price for given finish."""
        field_map = {
            "NF": "price_cents_lp_plus",
            "FO": "price_cents_lp_plus_foil",
            "EF": "price_cents_lp_plus_etched",
        }
        field = field_map.get(finish)
        if not field:
            return None

        price_cents = card_data.get(field)
        if price_cents is None:
            return None

        return float(price_cents) / 100.0

    def _get_general_price(self, card_data: dict, finish: str) -> float | None:
        """Extract general/market price (price_cents) for given finish."""
        # price_cents is only available for nonfoil, not for foil or etched variants
        if finish == "NF":
            field = "price_cents"
        elif finish == "FO":
            field = "price_cents_foil"
        elif finish == "EF":
            field = "price_cents_etched"
        else:
            return None

        price_cents = card_data.get(field)
        if price_cents is None:
            return None

        return float(price_cents) / 100.0

    def apply_updates(self, updates: list[dict[str, Any]]) -> bool:
        """Apply price updates to ManaPool API (with confirmation)."""
        if not updates:
            logger.info("[4/4] No updates to apply")
            return True

        logger.info(f"[4/4] Reviewing {len(updates):,} price updates...")
        logger.info("")

        # ALWAYS show preview of changes
        logger.info("=" * 80)
        logger.info("PRICE CHANGE PREVIEW")
        logger.info("=" * 80)
        logger.info("")

        # Show biggest increases and decreases
        self._print_extremes(updates)
        logger.info("")

        # Show sample of all changes
        self._print_sample_updates(updates)
        logger.info("")

        # Calculate summary statistics
        increases = sum(1 for u in updates if u["_new_price"] > u["_current_price"])
        decreases = sum(1 for u in updates if u["_new_price"] < u["_current_price"])
        total_current = sum(u["_current_price"] for u in updates)
        total_new = sum(u["_new_price"] for u in updates)
        total_change = total_new - total_current

        logger.info("Summary:")
        logger.info(f"  Total updates: {len(updates):,}")
        logger.info(f"  Price increases: {increases:,}")
        logger.info(f"  Price decreases: {decreases:,}")
        logger.info(f"  Total value change: ${total_change:+,.2f}")
        logger.info("")

        # Check if this is dry run mode
        if self.dry_run:
            logger.info("=" * 80)
            logger.info("DRY RUN MODE - No changes will be applied")
            logger.info("To apply changes, set DRY_RUN = False in this script")
            logger.info("=" * 80)
            return True

        # Ask for confirmation before applying
        logger.info("=" * 80)
        logger.info("READY TO APPLY CHANGES")
        logger.info("=" * 80)
        logger.info("")
        logger.info(f"This will update {len(updates):,} prices in your ManaPool inventory.")
        logger.info("")

        try:
            response = input("Type 'yes' to confirm and apply these changes: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            logger.info("\nCancelled by user")
            return False

        if response != "yes":
            logger.info("")
            logger.info("Update cancelled - no changes were made")
            return False

        logger.info("")
        logger.info("Applying updates to ManaPool...")
        logger.info("")

        # Remove metadata fields before sending to API
        clean_updates = []
        for update in updates:
            clean_updates.append({
                "scryfall_id": update["scryfall_id"],
                "finish_id": update["finish_id"],
                "condition_id": update["condition_id"],
                "language_id": update["language_id"],
                "price_cents": update["price_cents"],
                "quantity": update["quantity"],
            })

        # Apply updates in batches
        batch_size = 1500
        total = len(clean_updates)
        num_batches = (total + batch_size - 1) // batch_size

        url = f"{self.base_url}/seller/inventory/scryfall_id"

        for i in range(0, total, batch_size):
            batch_num = i // batch_size + 1
            batch = clean_updates[i:i + batch_size]

            logger.info(f"  Batch {batch_num}/{num_batches}: {len(batch):,} updates...")

            try:
                response = self.session.post(url, json=batch, timeout=120)
                response.raise_for_status()
                logger.info(f"  Batch {batch_num}/{num_batches}: Success!")
            except requests.exceptions.RequestException as e:
                logger.error(f"  Batch {batch_num}/{num_batches}: Failed - {e}")
                return False

        logger.info("")
        logger.info(f"✓ Successfully updated {total:,} prices!")
        return True

    def _print_extremes(self, updates: list[dict[str, Any]], limit: int = 10):
        """Print biggest increases and decreases."""
        # Sort by absolute change
        sorted_by_increase = sorted(
            updates,
            key=lambda u: u["_new_price"] - u["_current_price"],
            reverse=True
        )
        sorted_by_decrease = sorted(
            updates,
            key=lambda u: u["_new_price"] - u["_current_price"]
        )

        logger.info(f"Top {limit} INCREASES:")
        logger.info(f"{'Card':<40} {'Set':<6} {'Current':>10} {'New':>10} {'Change':>12}")
        logger.info("-" * 80)
        for update in sorted_by_increase[:limit]:
            name = update["_name"][:38]
            set_code = update["_set"]
            current = update["_current_price"]
            new = update["_new_price"]
            change = new - current
            change_pct = (change / current * 100) if current > 0 else 0

            logger.info(
                f"{name:<40} {set_code:<6} ${current:>9.2f} ${new:>9.2f} "
                f"+${change:>8.2f} ({change_pct:+.1f}%)"
            )

        logger.info("")
        logger.info(f"Top {limit} DECREASES:")
        logger.info(f"{'Card':<40} {'Set':<6} {'Current':>10} {'New':>10} {'Change':>12}")
        logger.info("-" * 80)
        for update in sorted_by_decrease[:limit]:
            name = update["_name"][:38]
            set_code = update["_set"]
            current = update["_current_price"]
            new = update["_new_price"]
            change = new - current
            change_pct = (change / current * 100) if current > 0 else 0

            logger.info(
                f"{name:<40} {set_code:<6} ${current:>9.2f} ${new:>9.2f} "
                f"-${abs(change):>8.2f} ({change_pct:.1f}%)"
            )

    def _print_sample_updates(self, updates: list[dict[str, Any]], limit: int = 20):
        """Print sample of updates for dry-run mode."""
        logger.info("Sample price changes (first %d):", min(limit, len(updates)))
        logger.info("")
        logger.info(f"{'Card':<40} {'Set':<6} {'Current':>10} {'New':>10} {'Change':>10}")
        logger.info("-" * 80)

        for update in updates[:limit]:
            name = update["_name"][:38]
            set_code = update["_set"]
            current = update["_current_price"]
            new = update["_new_price"]
            change = new - current
            change_pct = (change / current * 100) if current > 0 else 0

            logger.info(
                f"{name:<40} {set_code:<6} ${current:>9.2f} ${new:>9.2f} "
                f"{change:+9.2f} ({change_pct:+.1f}%)"
            )

        if len(updates) > limit:
            logger.info(f"... and {len(updates) - limit:,} more")

        logger.info("")

    def save_report(self, updates: list[dict[str, Any]]):
        """Save detailed report to JSON file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"price_updates_{timestamp}.json"

        report = {
            "timestamp": datetime.now().isoformat(),
            "dry_run": self.dry_run,
            "strategy": self.pricing_strategy,
            "total_updates": len(updates),
            "updates": updates,
        }

        with open(filename, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Detailed report saved to: {filename}")

    def run(self):
        """Run the pricing workflow."""
        try:
            # Fetch data
            inventory = self.fetch_inventory()
            price_data = self.fetch_prices()

            # Process and calculate new prices
            updates = self.process_inventory(inventory, price_data)

            # Apply updates
            success = self.apply_updates(updates)

            # Save report
            if updates:
                self.save_report(updates)

            logger.info("")
            logger.info("=" * 80)
            if success:
                logger.info("Pricing completed successfully!")
            else:
                logger.info("Pricing completed with errors")
            logger.info("=" * 80)

            return 0 if success else 1

        except KeyboardInterrupt:
            logger.info("\nInterrupted by user")
            return 130
        except Exception as e:
            logger.error(f"\nUnexpected error: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            if hasattr(self, 'session'):
                self.session.close()


def main():
    """Main entry point."""
    pricer = SimpleManaPoolPricer()
    sys.exit(pricer.run())


if __name__ == "__main__":
    main()
