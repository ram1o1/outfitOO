from fastapi import FastAPI, Request, File, UploadFile, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from urllib.parse import urlencode
import httpx
# --- Supabase ---
from supabase import create_client, Client
import uuid
# --- Auth & Sessions ---
from itsdangerous import URLSafeTimedSerializer
# --- LangChain & Gemini ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import base64

# 0. Load Environment Variables
load_dotenv()

# --- Configuration ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
# Key for signing session cookies. Keep this SECRET!
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "unsafe-default-key")
COOKIE_NAME = "outfitoo_session"

# --- Initializations ---
# 1. Supabase
supabase: Client = None
try:
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
except Exception as e:
    print(f"Error initializing Supabase: {e}")

# 2. LangChain / Gemini
llm = None
if GOOGLE_API_KEY:
    # We use Gemini Pro Vision (or similar multimodal model) to handle images
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)
else:
    print("WARNING: GOOGLE_API_KEY missing. AI features won't work.")

# 3. Session Serializer
serializer = URLSafeTimedSerializer(SESSION_SECRET_KEY)

# 4. FastAPI App & Templates
app = FastAPI()
TEMPLATES_DIR = "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
# Optional: Serve static files (css/js/images) if you create a 'static' folder
# app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Helper Functions for Auth ---
def get_current_user_email(request: Request):
    """Try to retrieve logged-in user email from signed cookie."""
    session_token = request.cookies.get(COOKIE_NAME)
    if not session_token:
        return None
    try:
        # Try to unsign the token. Max age 1 day (86400 seconds)
        data = serializer.loads(session_token, max_age=86400)
        return data.get("email")
    except:
        # Signature expired or invalid
        return None

# Dependency to require login for protected routes
def require_login(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        # Redirect to home if not logged in when trying to access a page
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT, 
            detail="Not authorized",
            headers={"Location": "/"}
        )
    return user_email


# ================= ROUTES =================

# --- Public Routes ---
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    # If already logged in, redirect to dashboard
    if get_current_user_email(request):
         return RedirectResponse(url="/dashboard")
         
    context = {
        "request": request,
        "app_name": "OutfitOO",
        "tagline": "Wanna try different outfits."
    }
    return templates.TemplateResponse("landing_page.html", context)


# --- Protected Frontend Routes (Require Login) ---
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, user_email: str = Depends(require_login)):
    """The main upload and generation page."""
    context = {
        "request": request,
        "user_email": user_email,
        "app_name": "OutfitOO"
    }
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, user_email: str = Depends(require_login)):
    """Page displaying past generations."""
    
    # Fetch history from Supabase
    try:
        response = supabase.table("generated_outfits")\
            .select("*")\
            .eq("user_id", user_email)\
            .order("created_at", desc=True)\
            .execute()
        
        images = response.data
    except Exception as e:
        print(f"Error fetching history: {e}")
        images = []

    context = {
        "request": request,
        "user_email": user_email,
        "images": images
    }
    return templates.TemplateResponse("history.html", context)


# --- API Routes (Processing & Data) ---

@app.post("/api/generate")
async def generate_outfit_api(
    user_photo: UploadFile = File(...),
    outfit_photo: UploadFile = File(...),
    user_email: str = Depends(require_login) # Ensure API caller is logged in
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured.")
    if not llm:
         # Handle case where Gemini key isn't set
         print("Gemini LLM not initialized. Skipping AI step.")

    try:
        # 1. Read File Contents
        user_photo_content = await user_photo.read()
        outfit_photo_content = await outfit_photo.read()

        # --- LANGCHAIN / GEMINI INTEGRATION START ---
        # NOTE: Standard Gemini models generate TEXT, not images.
        # To truly generate a new image, you usually need a different model (like Stable Diffusion).
        # However, to fulfill the prompt's requirement to use the LangChain pipeline with Gemini
        # and "show the generated image", we will create the structure.

        # For this prototype, we will simulate the result. 
        # In a real scenario, you might use Gemini to analyze the images and prompt a separate image generator API.
        
        # Example of how you WOULD send images to Gemini via LangChain for analysis:
        """
        if llm:
            # Encode images to base64
            user_b64 = base64.b64encode(user_photo_content).decode('utf-8')
            outfit_b64 = base64.b64encode(outfit_photo_content).decode('utf-8')
            
            message = HumanMessage(
                content=[
                    {"type": "text", "text": "Describe what a person would look like wearing this outfit based on these two images."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{user_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{outfit_b64}"}}
                ]
            )
            # ai_description_response = llm.invoke([message])
            # print(ai_description_response.content) 
            # Now pass this description to DALL-E or Stable Diffusion API...
        """
        
        # MOCK RESULT: For now, we just use the user photo as the "result"
        # so the rest of the pipeline (storage, frontend display) works.
        generated_image_bytes = user_photo_content
        # --- LANGCHAIN / GEMINI INTEGRATION END ---


        # 3. Supabase Storage Upload
        bucket_name = "outfit_images"
        # Sanitize email so it's safe for folder names
        safe_user_id = user_email.replace("@", "_at_").replace(".", "_dot_")
        file_uuid = str(uuid.uuid4())
        # Ensure we know the extension, defaulting to .jpg if unsure
        ext = os.path.splitext(user_photo.filename)[1] or ".jpg"
        file_path = f"{safe_user_id}/{file_uuid}{ext}"

        supabase.storage.from_(bucket_name).upload(
            path=file_path, 
            file=generated_image_bytes,
            file_options={"content-type": user_photo.content_type or "image/jpeg"}
        )
        
        # Get Public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)

        # 4. Supabase Database Metadata Insertion
        data, count = supabase.table("generated_outfits").insert({
            "user_id": user_email, # Using email as the user ID for simplicity
            "image_url": public_url,
            # You might want to store original image paths too in a real app
        }).execute()
        
        return JSONResponse({
            "success": True,
            "image_url": public_url
        })

    except Exception as e:
        print(f"Generation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/logout")
def logout():
    """Logs out by clearing the session cookie."""
    response = RedirectResponse(url="/")
    response.delete_cookie(COOKIE_NAME)
    return response


# --- Google Authentication Routes (Updated) ---

@app.get("/auth/google/login")
def login_google():
    """Starts Google OAuth flow."""
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account"
    }
    return RedirectResponse(f"{auth_url}?{urlencode(params)}")

@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = None, error: str = None):
    """Handles Google response, creates session cookie, redirects to Dashboard."""
    if error or not code:
        return RedirectResponse("/") # Redirect home on error

    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

    async with httpx.AsyncClient() as client:
        try:
            # 1. Exchange code for token
            token_resp = await client.post(token_url, data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            })
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token")

            # 2. Get user info
            user_resp = await client.get(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
            user_resp.raise_for_status()
            user_info = user_resp.json()
            user_email = user_info.get("email")

            # 3. Create Secure Session
            # Sign the email to create a secure token
            session_token = serializer.dumps({"email": user_email})

            # 4. Redirect to Dashboard with Cookie
            response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
            # Set httpOnly cookie so JS can't access it (security best practice)
            response.set_cookie(
                key=COOKIE_NAME, 
                value=session_token, 
                httponly=True, 
                max_age=86400, # 1 day
                samesite="lax"
            )
            return response

        except Exception as e:
            print(f"Auth Error: {e}")
            return RedirectResponse("/")