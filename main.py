from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os

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

# 4. Create a Route with Path Parameters and Query Parameters - Kept
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    # FastAPI automatically validates that item_id is an Integer
    return {"item_id": item_id, "query_param": q}

# 5. Create a POST Route to add data - Kept
@app.post("/items/")
def create_item(item: Item):
    return {"item_name": item.name, "item_price": item.price}