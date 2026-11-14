import requests


def lookup_indian_pincode(pincode: str, timeout: float = 5.0) -> dict:
    """
    Query the public India Post PIN Code JSON API (FR-44, FR-45).
    Completely isolated from store billing and inventory tables.
    """
    clean_pin = (pincode or "").strip()
    if not clean_pin.isdigit() or len(clean_pin) != 6:
        return {"ok": False, "error": "Please enter a valid 6-digit Indian PIN code.", "offices": []}

    url = f"https://api.postalpincode.in/pincode/{clean_pin}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()

        if not isinstance(payload, list) or not payload:
            return {"ok": False, "error": "Unexpected response format from Postal API.", "offices": []}

        entry = payload[0]
        if entry.get("Status") != "Success" or not entry.get("PostOffice"):
            return {"ok": False, "error": entry.get("Message") or f"No records found for PIN {clean_pin}.", "offices": []}

        offices = [
            {
                "name": po.get("Name", ""),
                "branch_type": po.get("BranchType", ""),
                "district": po.get("District", ""),
                "state": po.get("State", ""),
            }
            for po in entry["PostOffice"]
        ]
        return {"ok": True, "pincode": clean_pin, "offices": offices, "error": None}
    except requests.Timeout:
        return {"ok": False, "error": "Postal API timed out. Check your internet connection.", "offices": []}
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Could not reach Postal API: {exc}", "offices": []}
    except ValueError:
        return {"ok": False, "error": "Invalid JSON received from Postal API.", "offices": []}