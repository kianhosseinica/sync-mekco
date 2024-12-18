import requests
from django.http import JsonResponse
import logging
import time
from django.shortcuts import render
from .forms import SystemSkuForm
import logging
import sys
# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants for API URLs and organization ID
ZOHO_AUTH_BASE_URL = "https://accounts.zoho.com/oauth/v2"
ZOHO_API_BASE_URL = "https://www.zohoapis.com/books/v3"
CLIENT_ID = "1000.4EBWLV02KO1UA1L0YRUSYWVNYZYUQF"  # Replace with your client ID
CLIENT_SECRET = "dd42af92df0b3974f285a6e3b41d83a6891f80fe1b"  # Replace with your client secret
REFRESH_TOKEN = "1000.7d421efc934f671f5d004dcc93c69cfe.cc9d8fb5b418c658fd0af28eb71f9530"  # Replace with your refresh token

ORGANIZATION_ID = "762023225"
ZOHO_RATE_LIMIT = 100  # requests per minute
zoho_access_token = None
request_count = 0
purchase_account_id = None  # To be set globally after fetching
rate_limit_count = 0

# Function to refresh Lightspeed access token
def refresh_access_token():
    url = "https://cloud.lightspeedapp.com/oauth/access_token.php"
    payload = {
        "client_id": "6e9be2c0819d3e6e77213368de1a4b5308d94bae4a1698af014bbbbce71f4ccd",
        "client_secret": "07a118c07adedd5427bfd4c793410c5dc11472f79d6ad4854f04d00eadff48fa",
        "refresh_token": "84149496a4213a36bd3e7a5131cdaf1521167093",
        "grant_type": "refresh_token"
    }

    response = requests.post(url, data=payload)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        logger.error(f"Failed to refresh Lightspeed access token: {response.text}")
        return None

# Function to fetch all items from Lightspeed
def get_all_items():
    access_token = refresh_access_token()
    if not access_token:
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.lightspeedapp.com/API/V3/Account/292471/Item.json"
    items = []

    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            items.extend([{
                "defaultCost": item.get("defaultCost"),
                "description": item.get("description"),
                "manufacturerSku": item.get("manufacturerSku"),
                "price": next((price.get("amount") for price in item.get("Prices", {}).get("ItemPrice", []) if price.get("useType") == "Default"), None)
            } for item in data.get('Item', [])])
            url = data['@attributes'].get('next')
        else:
            logger.error(f"Failed to fetch items from Lightspeed: {response.text}")
            return []

    return items

# Function to fetch item details from Lightspeed by manufacturerSku
def get_lightspeed_item_details(sku):
    access_token = refresh_access_token()
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.lightspeedapp.com/API/V3/Account/292471/Item.json?manufacturerSku={sku}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        item = None
        if 'Item' in data:
            if isinstance(data['Item'], list) and len(data['Item']) > 0:
                item = data['Item'][0]
            elif isinstance(data['Item'], dict):
                item = data['Item']
        if item:
            return {
                "defaultCost": item.get("defaultCost"),
                "description": item.get("description"),
                "manufacturerSku": item.get("manufacturerSku"),
                "price": next((price.get("amount") for price in item.get("Prices", {}).get("ItemPrice", []) if price.get("useType") == "Default"), None)
            }
    logger.error(f"Failed to fetch item from Lightspeed for SKU {sku}: {response.text}")
    return None

# Function to refresh Zoho access token
# def refresh_zoho_access_token():
#     url = "https://accounts.zoho.com/oauth/v2/token"
#     payload = {
#         "refresh_token": "1000.7d421efc934f671f5d004dcc93c69cfe.cc9d8fb5b418c658fd0af28eb71f9530",
#         "client_id": "1000.4EBWLV02KO1UA1L0YRUSYWVNYZYUQF",
#         "client_secret": "dd42af92df0b3974f285a6e3b41d83a6891f80fe1b",
#         "grant_type": "refresh_token",
#         "redirect_uri": "http://localhost:8000/callback/"
#     }
#
#     response = requests.post(url, data=payload)
#     if response.status_code == 200:
#         global zoho_access_token
#         zoho_access_token = response.json().get('access_token')
#         logger.info(f"Successfully refreshed Zoho access token: {zoho_access_token}")
#         return zoho_access_token
#     else:
#         logger.error(f"Failed to refresh Zoho access token: {response.text}")
#         return None

zoho_access_token_expiry = 0

def refresh_zoho_access_token():
    global zoho_access_token, zoho_access_token_expiry
    url = f"{ZOHO_AUTH_BASE_URL}/token"
    payload = {
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            data = response.json()
            zoho_access_token = data.get("access_token")
            # Tokens expire in 1 hour by default, set expiry
            zoho_access_token_expiry = time.time() + 3600
            logger.info("Successfully refreshed Zoho access token.")
            return zoho_access_token
        else:
            logger.error(f"Failed to refresh Zoho access token: {response.text}")
            return None
    except requests.RequestException as e:
        logger.error(f"Error refreshing Zoho access token: {e}")
        return None



# Function to get Zoho headers with a valid access token
def get_zoho_headers():
    """Return headers for Zoho API calls."""
    global zoho_access_token
    if not zoho_access_token:
        zoho_access_token = refresh_zoho_access_token()
    if not zoho_access_token:
        raise ValueError("Failed to obtain Zoho access token.")
    return {
        "Authorization": f"Zoho-oauthtoken {zoho_access_token}",
        "Content-Type": "application/json",
    }


# Function to manage API rate limits
rate_limit_start_time = time.time()

def handle_rate_limit():
    global rate_limit_count, rate_limit_start_time
    if rate_limit_count >= ZOHO_RATE_LIMIT:
        elapsed_time = time.time() - rate_limit_start_time
        if elapsed_time < 60:
            logger.info(f"Rate limit reached. Sleeping for {60 - elapsed_time} seconds...")
            time.sleep(60 - elapsed_time)
        rate_limit_count = 0
        rate_limit_start_time = time.time()
    rate_limit_count += 1


# Function to make a request with automatic token refresh
def make_zoho_request(method, endpoint, data=None):
    max_retries = 3
    for attempt in range(max_retries):
        handle_rate_limit()
        headers = get_zoho_headers()
        url = f"{ZOHO_API_BASE_URL}/{endpoint}"
        try:
            response = requests.request(method, url, headers=headers, json=data)
            if response.status_code == 401:  # Unauthorized
                logger.warning("Access token expired. Refreshing...")
                refresh_zoho_access_token()
                headers = get_zoho_headers()  # Retry with refreshed token
                response = requests.request(method, url, headers=headers, json=data)
            if response.status_code in [200, 201]:
                return response
            elif response.status_code in [429, 503]:  # Rate limit or service unavailable
                logger.warning(f"Temporary issue: {response.status_code}. Retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.error(f"Zoho API request failed: {response.status_code} - {response.text}")
                return response  # Return even if not successful for better logging
        except requests.RequestException as e:
            logger.error(f"Error making Zoho API request: {e}")
        logger.info(f"Retrying API request ({attempt + 1}/{max_retries})...")
    return None  # Exhausted all retries





def revoke_zoho_refresh_token():
    """Revoke the refresh token."""
    url = f"{ZOHO_AUTH_BASE_URL}/token/revoke"
    payload = {"token": REFRESH_TOKEN}
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            logger.info("Successfully revoked Zoho refresh token.")
        else:
            logger.error(f"Failed to revoke Zoho refresh token: {response.text}")
    except requests.RequestException as e:
        logger.error(f"Error revoking Zoho refresh token: {e}")
# Function to fetch all items from Zoho
def get_all_zoho_items():
    url = f"items?organization_id={ORGANIZATION_ID}&filter_by=Status.Active"
    items = []

    while url:
        response = make_zoho_request("GET", url)
        if response and response.status_code == 200:
            data = response.json()
            items.extend([{
                "item_id": item.get("item_id"),
                "name": item.get("name"),
                "rate": item.get("rate"),
                "purchase_rate": item.get("purchase_rate"),
                "sku": item.get("sku"),
            } for item in data['items']])
            page_context = data.get("page_context", {})
            if page_context.get("has_more_page"):
                url = f"items?organization_id={ORGANIZATION_ID}&filter_by=Status.Active&page={page_context['page'] + 1}&per_page={page_context['per_page']}"
            else:
                url = None
        else:
            logger.error(f"Failed to fetch items from Zoho: {response.text if response else 'No response'}")
            return []

    return items


# Function to check if an item exists in Zoho
def check_item_exists_in_zoho(sku, zoho_items):
    return next((item for item in zoho_items if item['sku'] == sku), None)

# Function to normalize values for comparison
def normalize_value(value):
    if value is None or value == "":
        return ''
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, float):
        return round(value, 2)
    return value

def compare_floats(value1, value2, tolerance=0.01):
    try:
        float1 = float(value1)
        float2 = float(value2)
        return abs(float1 - float2) <= tolerance
    except (TypeError, ValueError) as e:
        logger.error(f"Error comparing floats: {e}. Values: {value1}, {value2}")
        return False

# Function to update items in Zoho
import time
import logging

logger = logging.getLogger(__name__)


def update_item_in_zoho(item_id, fields):
    """
    Updates an item in Zoho with the provided fields.
    Retries the operation up to max_retries times in case of failure.

    :param item_id: ID of the item in Zoho to be updated.
    :param fields: Dictionary of fields to update in the item.
    :return: True if the update was successful, False otherwise.
    """
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to update item {item_id}, Attempt: {attempt + 1}")
            response = make_zoho_request(
                "PUT",
                f"items/{item_id}?organization_id={ORGANIZATION_ID}",  # Endpoint only
                fields  # Data payload
            )

            if response is None:
                logger.error(f"No response received for item {item_id} update.")
                raise Exception("No response from Zoho API.")

            if response.status_code == 200:
                logger.info(f"Successfully updated item {item_id}: {fields}")
                return True

            # Handle specific errors (e.g., duplicate item)
            if response.status_code == 400:
                error_data = response.json()
                if error_data.get("code") == 1001:  # Duplicate item error
                    logger.warning(f"Item '{fields.get('name')}' already exists in Zoho. Skipping update for {item_id}.")
                    return False  # Skipping as it already exists
                logger.error(f"Error updating item {item_id}: {error_data}")
            else:
                logger.error(
                    f"Unexpected error updating item {item_id} - Status: {response.status_code}, Response: {response.text}"
                )

        except Exception as e:
            logger.error(f"Exception while updating item {item_id}: {e}")

        # Retry logic
        if attempt < max_retries - 1:
            logger.info(f"Retrying update for item {item_id} in {retry_delay} seconds...")
            time.sleep(retry_delay)

    logger.error(f"Exhausted all retries for updating item {item_id}.")
    return False



# Function to fetch the purchase account ID from Zoho
def get_purchase_account_id():
    global purchase_account_id
    if purchase_account_id is None:
        url = f"{ZOHO_API_BASE_URL}/chartofaccounts?organization_id={ORGANIZATION_ID}"
        headers = get_zoho_headers()
        response = make_zoho_request("GET", url, headers)

        if response.status_code == 200:
            accounts = response.json().get("chartofaccounts", [])
            for account in accounts:
                if account['account_type'] == 'Cost of Goods Sold':  # Example filter
                    purchase_account_id = account['account_id']
                    break
            if not purchase_account_id:
                logger.error("Failed to find 'Cost of Goods Sold' account.")
        else:
            logger.error(f"Failed to retrieve purchase account ID from Zoho: {response.text}")
    return purchase_account_id

# Updated compare_items view
import logging
from django.http import JsonResponse

logger = logging.getLogger(__name__)

def compare_items(request):
    lightspeed_items = get_all_items()
    zoho_items = get_all_zoho_items()

    if not lightspeed_items or not zoho_items:
        logger.error("Failed to fetch items from one or both APIs.")
        return JsonResponse({"error": "Failed to fetch items from one or both APIs"}, status=400)

    lightspeed_dict = {item['manufacturerSku']: item for item in lightspeed_items}
    zoho_dict = {item['sku']: item for item in zoho_items}

    items_to_update = []
    items_to_create = []
    successful_updates = []
    failed_updates = []

    for sku, ls_item in lightspeed_dict.items():
        zoho_item = zoho_dict.get(sku)

        if zoho_item:
            fields_to_update = {}

            # Convert to appropriate types and compare purchase_rate and defaultCost
            ls_cost = float(ls_item.get('defaultCost') or 0.0)
            zoho_cost = float(zoho_item.get('purchase_rate') or 0.0)

            if abs(ls_cost - zoho_cost) > 0.01:
                fields_to_update["purchase_rate"] = ls_cost
                fields_to_update["purchase_account_id"] = "2866866000000034003"

            # Compare description with name
            if normalize_value(ls_item.get('description')) != normalize_value(zoho_item.get('name')):
                fields_to_update["name"] = ls_item.get('description')

            # Compare price with rate
            ls_price = float(ls_item.get('price') or 0.0)
            zoho_rate = float(zoho_item.get('rate') or 0.0)

            if abs(ls_price - zoho_rate) > 0.01:
                fields_to_update["rate"] = ls_price

            if fields_to_update:
                items_to_update.append({
                    "item_id": zoho_item["item_id"],
                    "fields": fields_to_update
                })
        else:
            # Log for item creation preparation
            logger.info(f"Preparing to create item with SKU: {sku}")
            name = ls_item.get("description")
            initial_stock_rate = ls_item.get("defaultCost", 1.0)  # Default to 1 if no cost is specified

            # Ensure initial_stock_rate is a float
            try:
                initial_stock_rate = float(initial_stock_rate)
            except ValueError:
                logger.error(f"Invalid initial_stock_rate for SKU {sku}: {initial_stock_rate}. Skipping item creation.")
                continue  # Skip this item if initial_stock_rate is invalid

            # Check required fields before adding item to create list
            if name and initial_stock_rate > 0:
                item_to_create = {
                    "name": name,
                    "rate": float(ls_item.get("price") or 0.0),
                    "description": name,
                    "sku": sku,
                    "product_type": "goods",
                    "purchase_rate": initial_stock_rate,
                    "purchase_account_id": "2866866000000034003",
                    "inventory_account_id": "2866866000000034001",
                    "item_type": "inventory",
                    "initial_stock": 1,
                    "initial_stock_rate": initial_stock_rate,
                }
                items_to_create.append(item_to_create)
            else:
                logger.warning(
                    f"Skipping item creation for SKU {sku}: Missing 'name' or invalid 'initial_stock_rate' ({initial_stock_rate})"
                )

    logger.info(f"Total items to update: {len(items_to_update)}")
    logger.info(f"Total items to create: {len(items_to_create)}")

    # Process updates
    for idx, item in enumerate(items_to_update):
        success = update_item_in_zoho(item["item_id"], item["fields"])  # Removed headers
        if success:
            successful_updates.append(item)
        else:
            failed_updates.append(item)
            logger.error(f"Failed to update item in Zoho: {item['item_id']}")

        if (idx + 1) % 1000 == 0:
            logger.info(
                f"Processed {idx + 1} items. Successful updates: {len(successful_updates)}, Remaining: {len(items_to_update) - (idx + 1)}"
            )

    logger.info(
        f"Total items to update: {len(items_to_update)}, Successful updates: {len(successful_updates)}, Failed updates: {len(failed_updates)}"
    )

    # Process creations
    for idx, item in enumerate(items_to_create):
        response = make_zoho_request("POST", f"items?organization_id={ORGANIZATION_ID}", item)

        if response is None:
            logger.error(f"No response received for item creation with SKU {item['sku']}.")
            failed_updates.append(item)
            continue

        if response.status_code == 201:
            logger.info(f"Successfully created item in Zoho: {item['sku']}")
            successful_updates.append(item)
        elif response.status_code == 400:
            error_data = response.json()
            error_code = error_data.get("code")

            if error_code == 1001:
                logger.warning(
                    f"Duplicate item '{item['name']}' (SKU: {item['sku']}) already exists. Skipping creation."
                )
            elif error_code == 2051:
                logger.error(
                    f"Failed to create item '{item['name']}' (SKU: {item['sku']}): {error_data.get('message')}"
                )
            else:
                logger.error(f"Failed to create item in Zoho: {item['sku']} - {error_data}")
            failed_updates.append(item)
        else:
            logger.error(
                f"Failed to create item in Zoho: {item['sku']} - Status Code: {response.status_code}, Response: {response.text}"
            )
            failed_updates.append(item)

    return JsonResponse({
        "message": "Items processed.",
        "successful_updates": len(successful_updates),
        "failed_updates": len(failed_updates)
    })




# New view to handle user input for systemSku and update/create in Zoho
def update_or_create_specific_items(request):
    if request.method == "POST":
        form = SystemSkuForm(request.POST)
        if form.is_valid():
            skus = form.cleaned_data['systemSku'].split(',')
            skus = [sku.strip() for sku in skus]

            items_to_update = []
            items_to_create = []

            for sku in skus:
                # Get item details from Lightspeed using the SKU
                ls_item = get_lightspeed_item_details_by_sku(sku)
                if not ls_item:
                    logger.warning(f"No item found in Lightspeed for SKU {sku}, skipping.")
                    continue

                # Try to retrieve the item from Zoho using the SKU
                zoho_item = get_zoho_item_by_sku(sku)

                if zoho_item:
                    # Prepare the fields to update
                    fields_to_update = {}
                    ls_cost = float(ls_item.get('defaultCost', 0.0))
                    zoho_cost = float(zoho_item.get('purchase_rate', 0.0))

                    if ls_cost != zoho_cost:
                        fields_to_update["purchase_rate"] = ls_cost
                        fields_to_update["purchase_account_id"] = "2866866000000034003"
                        logger.info(f"Updating purchase_rate for SKU {sku}: {zoho_cost} -> {ls_cost}")

                    if normalize_value(ls_item.get('description')) != normalize_value(zoho_item.get('name')):
                        fields_to_update["name"] = ls_item['description']

                    ls_price = float(ls_item.get('price', 0.0))
                    zoho_rate = float(zoho_item.get('rate', 0.0))

                    if ls_price != zoho_rate:
                        fields_to_update["rate"] = ls_price

                    if fields_to_update:
                        items_to_update.append({
                            "item_id": zoho_item["item_id"],
                            "fields": fields_to_update
                        })
                else:
                    # Prepare item creation payload
                    item_to_create = {
                        "name": ls_item["description"],
                        "rate": ls_item["price"],
                        "description": ls_item["description"],
                        "sku": ls_item["manufacturerSku"],
                        "product_type": "goods",
                        "purchase_rate": ls_item.get("defaultCost", 0.0),
                        "purchase_account_id": "2866866000000034003",
                        "inventory_account_id": "2866866000000034001",
                        "item_type": "inventory",
                        "initial_stock": 1,
                        "initial_stock_rate": ls_item.get("defaultCost", 0.0),
                    }

                    items_to_create.append(item_to_create)

            # Create new items in Zoho
            for item in items_to_create:
                response = make_zoho_request("POST", f"items?organization_id={ORGANIZATION_ID}", item)
                if response and response.status_code == 201:
                    logger.info(f"Successfully created item in Zoho: {item['sku']}")
                elif response and response.status_code == 400:
                    error_data = response.json()
                    if error_data.get("code") == 1001:
                        logger.warning(f"Item with SKU {item['sku']} already exists in Zoho, skipping creation.")
                    else:
                        logger.error(f"Failed to create item in Zoho: {item['sku']} - {error_data}")
                else:
                    logger.error(f"Failed to create item in Zoho: {item['sku']} - {response.text if response else 'No response'}")

            # Update existing items in Zoho
            for item in items_to_update:
                update_item_in_zoho(item["item_id"], item["fields"])

            return JsonResponse({"message": "Specified items processed. Check logs for details."})

    else:
        form = SystemSkuForm()

    return render(request, 'api/update_create_items.html', {'form': form})




def get_lightspeed_item_details_by_sku(sku):
    access_token = refresh_access_token()
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.lightspeedapp.com/API/V3/Account/292471/Item.json?manufacturerSku={sku}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        if 'Item' in data:
            item = data['Item']
            if isinstance(item, list):
                item = item[0]
            return {
                "itemID": item.get("itemID"),
                "defaultCost": item.get("defaultCost"),
                "description": item.get("description"),
                "manufacturerSku": item.get("manufacturerSku"),
                "price": next((price.get("amount") for price in item.get("Prices", {}).get("ItemPrice", []) if price.get("useType") == "Default"), None)
            }
    logger.error(f"Failed to fetch item from Lightspeed for SKU {sku}: {response.text}")
    return None


def get_zoho_item_by_sku(sku):
    """
    Fetch an item from Zoho using its SKU.
    Handles cases where the item is not found or if the request fails.
    """
    url = f"items?organization_id={ORGANIZATION_ID}&search_text={sku}"  # Use `search_text` to find by SKU
    try:
        response = make_zoho_request("GET", url)
        if response and response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if items:
                return items[0]  # Return the first matching item
            else:
                logger.info(f"Item with SKU {sku} not found in Zoho.")
                return None
        elif response:
            logger.error(f"Failed to fetch item from Zoho for SKU {sku}. Status Code: {response.status_code}, Response: {response.text}")
        else:
            logger.error(f"Failed to fetch item from Zoho for SKU {sku}. No response received.")
    except Exception as e:
        logger.error(f"Exception occurred while fetching item from Zoho for SKU {sku}: {e}")
    return None


def fetch_all_items_with_quantities(request):
    """
    Fetch all items with their quantities and sell prices from Lightspeed, excluding unsupported relations.
    """
    access_token = refresh_access_token()
    if not access_token:
        logger.error("Unable to refresh Lightspeed access token.")
        return JsonResponse({"error": "Failed to refresh Lightspeed access token."}, status=500)

    # Define initial API URL and parameters
    url = 'https://api.lightspeedapp.com/API/V3/Account/292471/Item.json'
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "load_relations": '["ItemShops"]',  # Include supported relations only
        "limit": 100  # Fetch up to 100 items per request
    }

    items = []  # To store all fetched items
    try:
        while url:
            # Fetch data from Lightspeed API
            response = requests.get(url, headers=headers, params=params)
            logger.info(f"Lightspeed API Response Status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Failed to fetch items. Status: {response.status_code}, Response: {response.text}")
                break

            # Parse the response JSON
            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"Error parsing Lightspeed response JSON: {e}")
                break

            current_items = data.get('Item', [])
            if not isinstance(current_items, list):
                # Handle case where a single item is returned
                current_items = [current_items] if isinstance(current_items, dict) else []

            # Process each item
            for item in current_items:
                if not isinstance(item, dict):
                    logger.warning(f"Skipping invalid item format: {item}")
                    continue

                # Prepare item details
                item_info = {
                    "itemID": item.get("itemID"),
                    "description": item.get("description"),
                    "defaultCost": item.get("defaultCost"),
                    "manufacturerSku": item.get("manufacturerSku"),
                    "sellPrice": None,  # Placeholder for sell price
                    "quantities": []
                }

                # Extract sell price directly from the item
                prices = item.get("Prices", {}).get("ItemPrice", [])
                if isinstance(prices, list):
                    item_info["sellPrice"] = next(
                        (price.get("amount") for price in prices if price.get("useType") == "Default"),
                        None
                    )

                # Extract quantities from ItemShops
                item_shops = item.get("ItemShops", {}).get("ItemShop", [])
                if isinstance(item_shops, dict):  # Convert single shop data to a list
                    item_shops = [item_shops]

                for shop in item_shops:
                    qoh = int(shop.get("qoh", 0))  # Get quantity on hand
                    item_info["quantities"].append({
                        "shopID": shop.get("shopID"),
                        "quantity_on_hand": qoh
                    })

                # Append item to the list
                items.append(item_info)

            # Update URL for the next page
            url = data.get('@attributes', {}).get('next')

        return JsonResponse({"items": items}, safe=False)

    except requests.RequestException as e:
        logger.error(f"Error while making request to Lightspeed API: {e}")
        return JsonResponse({"error": "An error occurred while fetching items."}, status=500)

    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        return JsonResponse({"error": "An unexpected error occurred."}, status=500)




from django.http import JsonResponse
import json

from django.http import JsonResponse
import json

def update_all_items_in_zoho(request):
    """
    Fetch all items from Lightspeed and update corresponding items in Zoho when accessed via GET request.
    Handles negative quantities appropriately.
    """
    try:
        # Fetch all items from Lightspeed
        lightspeed_response = fetch_all_items_with_quantities(request)
        lightspeed_data = json.loads(lightspeed_response.content)
    except Exception as e:
        logger.error(f"Failed to fetch items from Lightspeed: {e}")
        return JsonResponse({"error": "Failed to fetch items from Lightspeed."}, status=500)

    # Ensure items are in the response
    lightspeed_items = lightspeed_data.get("items", [])
    if not lightspeed_items:
        logger.error("No items found in Lightspeed response.")
        return JsonResponse({"error": "No items found in Lightspeed response."}, status=400)

    # Fetch all Zoho items
    try:
        zoho_items = get_all_zoho_items()
    except Exception as e:
        logger.error(f"Failed to fetch items from Zoho: {e}")
        return JsonResponse({"error": "Failed to fetch items from Zoho."}, status=500)

    if not zoho_items:
        logger.error("No items fetched from Zoho.")
        return JsonResponse({"error": "No items found in Zoho."}, status=400)

    # Map Zoho items by SKU
    zoho_dict = {item['sku']: item for item in zoho_items}

    logger.info(f"Preparing to update {len(lightspeed_items)} items in Zoho.")

    items_to_update = []  # Store update payloads
    successful_updates = 0
    failed_updates = 0

    try:
        # Get Zoho API headers
        headers = get_zoho_headers()
    except Exception as e:
        logger.error(f"Failed to retrieve Zoho headers: {e}")
        return JsonResponse({"error": "Failed to retrieve Zoho headers."}, status=500)

    # Process Lightspeed items
    for item in lightspeed_items:
        sku = item.get("manufacturerSku")
        zoho_item = zoho_dict.get(sku)

        if not zoho_item:
            logger.warning(f"Item with SKU {sku} not found in Zoho. Skipping.")
            continue

        # Calculate total quantity across all shops
        total_quantity = sum(q.get('quantity_on_hand', 0) for q in item.get('quantities', []))

        # Handle negative quantities
        if total_quantity < 0:
            logger.warning(f"Negative quantity for item with SKU {sku}. Total quantity: {total_quantity}. Skipping update.")
            continue  # Skip updating this item

        # Prepare fields for update
        fields_to_update = {}

        if normalize_value(item.get('description')) != normalize_value(zoho_item.get('name')):
            fields_to_update["name"] = item["description"]

        if float(item.get('defaultCost', 0)) != float(zoho_item.get('purchase_rate', 0)):
            fields_to_update["purchase_rate"] = float(item.get('defaultCost', 0))

        if float(item.get('sellPrice', 0)) != float(zoho_item.get('rate', 0)):
            fields_to_update["rate"] = float(item.get('sellPrice', 0))

        if total_quantity != zoho_item.get('quantity', 0):
            fields_to_update["quantity"] = total_quantity

        if fields_to_update:
            logger.info(f"Preparing update for item with SKU: {sku}, Fields: {fields_to_update}")
            items_to_update.append({
                "item_id": zoho_item["item_id"],
                "fields": fields_to_update
            })
        else:
            logger.info(f"No updates required for item with SKU: {sku}")

    # Update items in Zoho
    for idx, item in enumerate(items_to_update):
        logger.info(f"Updating item in Zoho: {item}")
        try:
            success = update_item_in_zoho(item["item_id"], item["fields"])
            if success:
                successful_updates += 1
                logger.info(f"Successfully updated item with ID: {item['item_id']}")
            else:
                failed_updates += 1
                logger.error(f"Failed to update item with ID: {item['item_id']}")
        except Exception as e:
            failed_updates += 1
            logger.error(f"Error updating item {item['item_id']}: {e}")

        # Log progress for large updates
        if (idx + 1) % 100 == 0:
            logger.info(f"Processed {idx + 1} items: {successful_updates} successful, {failed_updates} failed.")

    logger.info(f"Update process complete: {successful_updates} successful updates, {failed_updates} failures.")
    return JsonResponse({
        "message": "Update process completed.",
        "successful_updates": successful_updates,
        "failed_updates": failed_updates
    })










