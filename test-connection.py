import requests
import json

# Azure AD configuration
tenant_id = "80a1c230-4b4a-4858-bc85-9205b3dc5ec5"  # e.g., "contoso.onmicrosoft.com" or "12345678-1234-1234-1234-123456789012"
client_id = "4d55fbd9-74c7-4b19-8dc2-c4519e6988ab"  # Application (client) ID from Azure AD
client_secret = "nvz8Q~HBEWT0nlhwfjbNnFJFDNHqcZp9RILqRbIR"

def get_access_token():
    """Get access token using client credentials flow"""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    
    return response.json()["access_token"]

def get_directory_roles(token):
    """Get directory roles from Microsoft Graph"""
    url = "https://graph.microsoft.com/v1.0/directoryRoles"
    params = {
        "$select": "id,displayName,description,roleTemplateId"
    }
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    return response.json()

# Main execution
try:
    print("Getting access token...")
    access_token = get_access_token()
    print("Token acquired successfully!")
    
    print("\nFetching directory roles...")
    roles = get_directory_roles(access_token)
    
    print("\n" + "="*50)
    print(f"Found {len(roles.get('value', []))} directory roles")
    print("="*50 + "\n")
    
    print(json.dumps(roles, indent=2))
    
except requests.exceptions.HTTPError as e:
    print(f"\nHTTP Error occurred:")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Status Code: {e.response.status_code}")
        print(f"Response Headers: {dict(e.response.headers)}")
        print(f"Response Body: {e.response.text}")
    else:
        print(f"Error: {e}")
        
except Exception as e:
    print(f"\nUnexpected error: {e}")