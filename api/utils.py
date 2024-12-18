def handle_rate_limit():
    global request_count
    request_count += 1
    if request_count >= ZOHO_RATE_LIMIT:
        logger.info("Rate limit reached. Sleeping for 60 seconds...")
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            logger.warning("Process interrupted during rate limit wait.")
            sys.exit(0)  # Exit gracefully
        request_count = 0

def update_item_in_zoho(item_id, fields, headers):
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            response = make_zoho_request(
                "PUT",
                f"{ZOHO_API_BASE_URL}/items/{item_id}?organization_id={ORGANIZATION_ID}",
                headers,
                fields
            )
        except Exception as e:
            logger.error(f"Exception during update attempt {attempt + 1} for item {item_id}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                logger.error(f"Failed to update item {item_id} after {max_retries} attempts.")
                return False

        if response and response.status_code == 200:
            logger.info(f"Successfully updated item in Zoho: {item_id}")
            return True

        logger.warning(f"Update attempt {attempt + 1} failed for item {item_id}. Status: {response.status_code}")
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
        else:
            logger.error(f"Exhausted all retries for item {item_id}.")
            return False


def refresh_zoho_access_token():
    global zoho_access_token
    if zoho_access_token:
        logger.info("Token is already valid. Skipping refresh.")
        return zoho_access_token  # Skip refresh if token exists

    logger.info("Refreshing Zoho access token.")
    url = "https://accounts.zoho.com/oauth/v2/token"
    payload = {
        "refresh_token": "1000.7d421efc934f671f5d004dcc93c69cfe.cc9d8fb5b418c658fd0af28eb71f9530",
        "client_id": "1000.4EBWLV02KO1UA1L0YRUSYWVNYZYUQF",
        "client_secret": "dd42af92df0b3974f285a6e3b41d83a6891f80fe1b",
        "grant_type": "refresh_token",
        "redirect_uri": "http://localhost:8000/callback/"
    }

    response = requests.post(url, data=payload)
    if response.status_code == 200:
        zoho_access_token = response.json().get('access_token')
        logger.info(f"Successfully refreshed Zoho access token: {zoho_access_token}")
        return zoho_access_token
    else:
        logger.error(f"Failed to refresh Zoho access token: {response.text}")
        return None
