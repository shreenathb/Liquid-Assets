from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
from pymongo import MongoClient

app = FastAPI(title="Mocktail Stock Exchange")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB setup
client = MongoClient("mongodb://localhost:27017")
db = client["mocktail_exchange"]
drinks_collection = db["drinks"]

# Configuration
alpha = 0.025
WINDOW = 3600  # seconds for price decay

# Models
class Order(BaseModel):
    drink: str
    qty: int = 1



# Initialize drinks in DB
def init_drinks():
    drinks_data = [
        {"name": "Kokam Spritzer", "base": 25, "price": 25, "floor": 20, "ceiling": 30, "demand": 0, "history": []},
        {"name": "Apple Spritzer", "base": 25, "price": 25, "floor": 20, "ceiling": 30, "demand": 0, "history": []},
        {"name": "Guava Spritzer", "base": 25, "price": 25, "floor": 20, "ceiling": 30, "demand": 0, "history": []},
    ]
    for drink in drinks_data:
        if not drinks_collection.find_one({"name": drink["name"]}):
            drinks_collection.insert_one(drink)

def update_prices(cur_demand,cur_drink):
    drinks_list = list(drinks_collection.find())
    
    for drink in drinks_list:

        if drink['name'] == cur_drink:
            total_demand = drink["demand"]
            if drink["demand"] > 0:
                factor = alpha * (cur_demand / total_demand)
                new_price = drink["price"] * (1 + factor)
                new_price = min(max(new_price, drink["floor"]), drink["ceiling"])
                drinks_collection.update_one({"name": drink["name"]}, {"$set": {"price": new_price}})

def cleanup_and_count(drink):
    now = time.time()
    history = [t for t in drink["history"] if now - t < WINDOW]
    drinks_collection.update_one({"name": drink["name"]}, {"$set": {"history": history}})
    return len(history)

def price_decay_task():
    while True:
        time.sleep(WINDOW)
        drinks_list = list(drinks_collection.find())
        demands = {drink["name"]: cleanup_and_count(drink) for drink in drinks_list}
        avg_demand = sum(demands.values()) / len(demands) if demands else 0
        for drink in drinks_list:
            if demands[drink["name"]] < avg_demand and drink["price"] > drink["floor"]:
                new_price = drink["price"] - 1
                drinks_collection.update_one({"name": drink["name"]}, {"$set": {"price": new_price}})
                print(f"Price of {drink['name']} knocked off by 1")

@app.on_event("startup")
def startup_event():
    init_drinks()
    import threading
    t = threading.Thread(target=price_decay_task, daemon=True)
    t.start()

@app.get("/prices")
def get_prices():
    drinks_list = list(drinks_collection.find())
    return {drink["name"]: round(drink["price"], 2) for drink in drinks_list}

@app.post("/order")
def place_order(order: Order):
    drink = drinks_collection.find_one({"name": order.drink})
    if not drink:
        return {"error": "Drink not available"}
    now = time.time()
    history = drink["history"] + [now] * order.qty

    drinks_collection.update_one(
        {"name": order.drink},
        {"$set": {"history": history}, "$inc": {"demand": order.qty}}
    )
    update_prices(order.qty, order.drink)
    return {"message": f"Order placed for {order.qty} {order.drink}(s)"}

# @app.post("/update")
# def manual_update():
#     update_prices()
#     return {"message": "Prices updated", "prices": get_prices()}