from fastapi import FastAPI
from pydantic import BaseModel

# 1. Create the App instance
app = FastAPI()

# 2. Define a Pydantic model (for data validation)
class Item(BaseModel):
    name: str
    price: float
    is_offer: bool = None

# 3. Create a Basic GET Route
@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

# 4. Create a Route with Path Parameters and Query Parameters
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    # FastAPI automatically validates that item_id is an Integer
    return {"item_id": item_id, "query_param": q}

# 5. Create a POST Route to add data
@app.post("/items/")
def create_item(item: Item):
    return {"item_name": item.name, "item_price": item.price}