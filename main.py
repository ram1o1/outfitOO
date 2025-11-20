from fastapi import FastAPI, Request, File, UploadFile # Modified: Added File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
# --- New Imports for Authentication ---
from dotenv import load_dotenv
from urllib.parse import urlencode
from starlette.responses import RedirectResponse
import httpx
# --- New Imports for Supabase/File Handling ---
from supabase import create_client, Client # New
import uuid # New

# 0. Load Environment Variables from .env
load_dotenv()
# --- Google OAuth Configuration ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
# ------------------------------------

# --- Supabase Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # This is your Anon Key

# Initialize Supabase client
supabase: Client = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        print("WARNING: Supabase configuration (SUPABASE_URL or SUPABASE_KEY) missing.")
except Exception as e:
    print(f"Error initializing Supabase client: {e}")

# --- Configuration for Templating ---
# Create a 'templates' directory in the same folder as main.py
TEMPLATES_DIR = "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
# ------------------------------------

# 1. Create the App instance
app = FastAPI()

# 2. Define a Pydantic model (for data validation) - Kept for future routes
class Item(BaseModel):
    name: str
    price: float
    is_offer: bool = None

# 3. Create the Landing Page Route (Root)
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """
    Renders the OutfitOO landing page template.
    """
    context = {
        "request": request,
        "app_name": "OutfitOO",
        "tagline": "wanna try different outfits."
    }
    # Look for a file named 'landing_page.html' inside the 'templates' directory
    return templates.TemplateResponse("landing_page.html", context)


# 4. Create a Route for Outfit Generation and Storage (New)
@app.post("/api/generate_outfit/{user_id}")
async def generate_and_store_outfit(
    user_id: str,
    user_photo: UploadFile = File(...),
    outfit_photo: UploadFile = File(...),
):
    """
    Handles file upload, mocks image generation (LangChain/Gemini), 
    and stores the resulting image in Supabase Storage and its metadata in the DB.
    """
    if not supabase:
        return {"error": "Supabase client not initialized. Check your environment variables."}

    # 1. Read uploaded photos
    # NOTE: The user_photo content is read here. We will use these bytes later 
    # to mock the 'generated' image bytes, as the actual generation step is outside this scope.
    user_photo_bytes = await user_photo.read()
    await outfit_photo.read() # Read and discard/process outfit photo content

    # --- 2. Image Generation Mock ---
    # In a real app, you would pass user_photo_bytes and outfit_photo_content 
    # to your LangChain/Gemini process. The result is the generated image bytes.
    generated_image_bytes = user_photo_bytes 
    
    # --- 3. Supabase Storage Upload (Generated Image) ---
    bucket_name = "outfit_images"
    file_extension = ".jpg" # Assuming your model generates JPEG
    file_uuid = str(uuid.uuid4())
    file_path = f"{user_id}/{file_uuid}{file_extension}" # e.g., "user123/a1b2c3d4.jpg"
    
    try:
        # Upload the generated image bytes to Supabase Storage
        supabase.storage.from_(bucket_name).upload(file_path, generated_image_bytes)
        
        # Get the public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)

    except Exception as e:
        print(f"Supabase Storage Error: {e}")
        return {"error": f"Failed to upload image to storage: {str(e)}"}

    # --- 4. Supabase Database Insertion (Metadata) ---
    table_name = "generated_outfits"
    
    try:
        # Note: The 'execute()' returns a tuple. We usually care about the second element (data).
        data, count = supabase.table(table_name).insert({
            "user_id": user_id,
            "image_url": public_url,
            "original_user_photo_name": user_photo.filename,
            "original_outfit_photo_name": outfit_photo.filename
        }).execute()
        
        return {
            "message": "Outfit generated and stored successfully!",
            "public_url": public_url,
            "db_response": data[1]
        }
        
    except Exception as e:
        print(f"Supabase DB Error: {e}")
        return {"error": f"Failed to save image metadata: {str(e)}"}


# --- 6. Google Authentication Routes ---

@app.get("/auth/google/login")
def login_google():
    """Starts the Google OAuth flow by redirecting the user to Google's login page."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        # Simple error handling if configuration is missing
        return {"error": "Google OAuth configuration missing."}
        
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        # Request openid, email, and profile scopes
        "scope": "openid email profile", 
        "access_type": "offline",
        "prompt": "select_account"
    }
    
    # Construct and return the redirect response
    return RedirectResponse(f"{AUTHORIZATION_URL}?{urlencode(params)}", status_code=302)

@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = None, error: str = None):
    """Handles the response from Google after authentication."""
    
    if error:
        return {"error": f"Google authentication failed: {error}"}
    
    if not code:
        return {"error": "No authorization code received."}

    # 1. Exchange authorization code for an Access Token
    async with httpx.AsyncClient() as client:
        token_data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        try:
            token_response = await client.post(TOKEN_URL, data=token_data)
            token_response.raise_for_status() # Raise exception for bad status codes
            token_json = token_response.json()
            access_token = token_json.get("access_token")

            if not access_token:
                return {"error": "Failed to get access token from Google."}

            # 2. Use the Access Token to get user information
            user_response = await client.get(
                USERINFO_URL, 
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_response.raise_for_status()
            user_info = user_response.json()
            
            # 3. Authentication complete - Log the user in (Example)
            user_email = user_info.get("email")
            user_name = user_info.get("name")
            
            # --- NEXT STEP: Create a secure session or JWT and redirect to dashboard ---
            # For now, we'll just show the user data:
            # You would replace this return with a RedirectResponse to your app's dashboard
            # after setting a secure authentication token.
            return {
                "message": "Authentication successful!", 
                "email": user_email, 
                "name": user_name
            }

        except httpx.HTTPStatusError as e:
            # Handle specific HTTP errors from Google
            return {"error": f"Google API error: {e.response.text}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


# 4. Create a Route with Path Parameters and Query Parameters - Kept
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    # FastAPI automatically validates that item_id is an Integer
    return {"item_id": item_id, "query_param": q}

# 5. Create a POST Route to add data - Kept
@app.post("/items/")
def create_item(item: Item):
    return {"item_name": item.name, "item_price": item.price}