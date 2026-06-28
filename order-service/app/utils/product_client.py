import os
import httpx
from typing import Optional

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")


class ProductServiceError(Exception):
    """Raised when product-service is unreachable or returns an error."""
    pass


async def get_variant(product_id: str, variant_id: str) -> Optional[dict]:
    """
    Fetches a product from product-service and returns the matching
    variant, or None if the product/variant doesn't exist or is unavailable.
    Raises ProductServiceError on network failure — checkout must fail
    loudly rather than proceeding with stale prices.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{PRODUCT_SERVICE_URL}/products/{product_id}"
            )
    except httpx.RequestError as e:
        raise ProductServiceError(
            f"Could not reach product-service: {e}"
        ) from e

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ProductServiceError(
            f"product-service returned unexpected status {response.status_code}"
        )

    product = response.json()
    if not product.get("is_available"):
        return None

    for variant in product.get("variants", []):
        if str(variant["id"]) == str(variant_id):
            return {
                "product_name": product["name"],
                "size": variant["size"],
                "unit_price": variant["price"],
                "is_available": variant["is_available"],
            }

    return None
