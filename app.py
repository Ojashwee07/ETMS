from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
from pymongo import MongoClient
from dotenv import load_dotenv
import hashlib, uuid, os, json
from datetime import datetime
from collections import defaultdict
import google.generativeai as genai
#changebyansh

load_dotenv()

app = FastAPI(title="ETMS - Expense Tracker Management System")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client    = MongoClient(MONGO_URI)
db        = client["etms_db"]
users_col   = db["users"]
txns_col    = db["transactions"]
targets_col = db["targets"]

genai.configure(api_key="AIzaSyDKH9WAOyZWcB0Yn-NxryiFuCXtUNGAAcw")
gemini = genai.GenerativeModel("gemini-1.5-flash")

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()
#changebyansh
# ── Models ─────────────────────────────────────────────
class User(BaseModel):
    username: str
    password: str
    @validator("username")
    def u(cls,v):
        v=v.strip()
        if len(v)<3: raise ValueError("Min 3 chars")
        return v
    @validator("password")
    def p(cls,v):
        if len(v)<4: raise ValueError("Min 4 chars")
        return v

class Transaction(BaseModel):
    amount: str
    category: str
    user: str
    @validator("amount")
    def a(cls,v):
        try: val=float(v)
        except: raise ValueError("Invalid amount")
        if val==0: raise ValueError("Cannot be zero")
        return v
    @validator("category")
    def c(cls,v):
        v=v.strip()
        if not v: raise ValueError("Empty category")
        return v


class RegisterUser(BaseModel):
    username: str
    password: str
    fullname: str
    email: str = ""
    phone: str = ""
    monthly_income: float = 0
    income_source: str = ""
    monthly_budget: float = 0
    savings_goal: float = 0
    currency: str = "INR"

class SMSEmailText(BaseModel):
    text: str
    user: str

class AnalyzeRequest(BaseModel):
    user: str

class ReportRequest(BaseModel):
    user: str
    month: int
    year: int

class Target(BaseModel):
    user: str
    target_name: str
    target_type: str   # "savings" | "spending_limit"
    category: str
    amount: float

    @validator("target_name")
    def tn(cls, v):
        v = v.strip()
        if not v: raise ValueError("Target name required")
        if len(v) < 2: raise ValueError("Min 2 characters")
        return v

    @validator("target_type")
    def tt(cls, v):
        if v not in ("savings", "spending_limit"):
            raise ValueError("Type must be savings or spending_limit")
        return v

    @validator("category")
    def cat(cls, v):
        v = v.strip()
        if not v: raise ValueError("Category required")
        return v

    @validator("amount")
    def amt(cls, v):
        if v <= 0: raise ValueError("Amount must be positive")
        return v

# ── POST /login ─────────────────────────────────────────
@app.post("/login")
def login(user: User):
    existing = users_col.find_one({"username": {"$regex": f"^{user.username}$", "$options": "i"}})
    hashed = hash_password(user.password)
    if existing:
        stored = existing["password"]
        if stored == hashed or stored == user.password:
            if stored == user.password:
                users_col.update_one({"_id": existing["_id"]}, {"$set": {"password": hashed}})
            return {"status": "ok", "message": "Login successful"}
        raise HTTPException(status_code=401, detail="Incorrect password")
    users_col.insert_one({"username": user.username, "password": hashed, "created_at": datetime.now().isoformat()})
    return {"status": "ok", "message": "Account created!"}

# ── POST /register ──────────────────────────────────────
@app.post("/register")
def register(u: RegisterUser):
    existing = users_col.find_one({"username": {"$regex": f"^{u.username}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken. Please choose another.")
    if len(u.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(u.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    hashed = hash_password(u.password)
    users_col.insert_one({
        "username": u.username,
        "password": hashed,
        "fullname": u.fullname,
        "email": u.email,
        "phone": u.phone,
        "monthly_income": u.monthly_income,
        "income_source": u.income_source,
        "monthly_budget": u.monthly_budget,
        "savings_goal": u.savings_goal,
        "currency": u.currency,
        "created_at": datetime.now().isoformat()
    })
    # Auto-add first income transaction if monthly income is provided
    if u.monthly_income > 0:
        txns_col.insert_one({
            "id": str(uuid.uuid4()),
            "amount": str(u.monthly_income),
            "category": f"{u.income_source or 'Salary'} — Monthly Income",
            "user": u.username,
            "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
        })
    return {"status": "ok", "message": "Account created successfully!"}

# ── POST /add ───────────────────────────────────────────
@app.post("/add")
def add(t: Transaction):
    txn_id = str(uuid.uuid4())
    txns_col.insert_one({
        "id": txn_id, "amount": t.amount, "category": t.category,
        "user": t.user, "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })
    return {"status": "ok", "id": txn_id}

# ── GET /data ───────────────────────────────────────────
@app.get("/data")
def get_data(user: str):
    if not user: raise HTTPException(status_code=400, detail="User required")
    return list(txns_col.find({"user": user}, {"_id": 0}))

# ── DELETE /delete/{id} ─────────────────────────────────
@app.delete("/delete/{transaction_id}")
def delete_transaction(transaction_id: str, user: str):
    result = txns_col.delete_one({"id": transaction_id, "user": user})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "ok"}

# ── GET /stats ──────────────────────────────────────────
@app.get("/stats")
def get_stats(user: str):
    if not user: raise HTTPException(status_code=400, detail="User required")
    txns    = list(txns_col.find({"user": user}, {"_id": 0}))
    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    return {"income": round(income,2), "expense": round(expense,2), "balance": round(income-expense,2),
            "total_txns": len(txns), "income_txns": sum(1 for t in txns if float(t["amount"])>0),
            "expense_txns": sum(1 for t in txns if float(t["amount"])<0)}

# ── POST /ai/extract ────────────────────────────────────
@app.post("/ai/extract")
def ai_extract(body: SMSEmailText):
    if not body.text.strip(): raise HTTPException(status_code=400, detail="Text empty")
    prompt = f"""Extract transaction from this bank SMS/email:
\"\"\"{body.text}\"\"\"
Return ONLY valid JSON:
{{"found":true/false,"type":"income"/"expense","amount":number,"category":"short name","note":"brief desc","date":"date or empty"}}
Rules: debited/paid=expense, credited/received=income. Amount positive number only. No markdown."""
    try:
        raw = gemini.generate_content(prompt).text.strip()
        if raw.startswith("```"): raw = raw.split("```")[1]; raw = raw[4:] if raw.startswith("json") else raw
        return {"status": "ok", "data": json.loads(raw.strip())}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Could not parse message")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

# ── POST /ai/analyze ────────────────────────────────────
@app.post("/ai/analyze")
def ai_analyze(body: AnalyzeRequest):
    txns = list(txns_col.find({"user": body.user}, {"_id": 0}))
    if not txns: raise HTTPException(status_code=400, detail="No transactions found")
    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            cats[t["category"].split(" — ")[0].strip()] += abs(float(t["amount"]))
    sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    summary = f"Income: Rs.{income:,.0f} | Expense: Rs.{expense:,.0f} | Balance: Rs.{income-expense:,.0f}\nTop expenses: {', '.join([f'{c}: Rs.{a:,.0f}' for c,a in sorted_cats[:5]])}"
    prompt = f"""Personal finance advisor for Indian user.\n{summary}\nGive analysis with:\n1. **Spending Overview**\n2. **Necessary vs Unnecessary**\n3. **Smart Saving Tips** (4-5 tips)\n4. **Financial Health Score /10**\nBe friendly, use emojis, Indian context."""
    try:
        resp = gemini.generate_content(prompt)
        return {"status":"ok","analysis":resp.text.strip(),
                "summary":{"income":income,"expense":expense,"balance":income-expense,"top_categories":sorted_cats[:5]}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

# ── GET /report/data ────────────────────────────────────
@app.get("/report/data")
def report_data(user: str, month: int, year: int):
    if not user: raise HTTPException(status_code=400, detail="User required")
    all_txns = list(txns_col.find({"user": user}, {"_id": 0}))

    # Filter by month & year
    txns = []
    for t in all_txns:
        try:
            dt = datetime.strptime(t["created_at"], "%d %b %Y, %I:%M %p")
            if dt.month == month and dt.year == year:
                txns.append({**t, "_dt": dt})
        except:
            pass

    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)

    # Category breakdown (expenses only)
    cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            cats[t["category"].split(" — ")[0].strip()] += abs(float(t["amount"]))

    # Daily spending (expenses)
    daily = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            day = t["_dt"].strftime("%d")
            daily[day] += abs(float(t["amount"]))

    # Income categories
    income_cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) > 0:
            income_cats[t["category"].split(" — ")[0].strip()] += float(t["amount"])

    sorted_expense_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    sorted_income_cats  = sorted(income_cats.items(), key=lambda x: x[1], reverse=True)
    sorted_daily = sorted(daily.items())

    return {
        "month": month, "year": year,
        "income": round(income, 2), "expense": round(expense, 2),
        "savings": round(income - expense, 2),
        "savings_rate": round((income-expense)/income*100, 1) if income > 0 else 0,
        "total_txns": len(txns),
        "expense_categories": [{"name": k, "amount": round(v, 2)} for k, v in sorted_expense_cats],
        "income_categories":  [{"name": k, "amount": round(v, 2)} for k, v in sorted_income_cats],
        "daily_expense": [{"day": k, "amount": round(v, 2)} for k, v in sorted_daily]
    }

# ── POST /ai/report ─────────────────────────────────────
@app.post("/ai/report")
def ai_report(body: ReportRequest):
    all_txns = list(txns_col.find({"user": body.user}, {"_id": 0}))
    txns = []
    for t in all_txns:
        try:
            dt = datetime.strptime(t["created_at"], "%d %b %Y, %I:%M %p")
            if dt.month == body.month and dt.year == body.year:
                txns.append(t)
        except:
            pass

    if not txns: raise HTTPException(status_code=400, detail="No transactions for this month")

    income  = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    expense = sum(abs(float(t["amount"])) for t in txns if float(t["amount"]) < 0)
    cats = defaultdict(float)
    for t in txns:
        if float(t["amount"]) < 0:
            cats[t["category"].split(" — ")[0].strip()] += abs(float(t["amount"]))
    sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)

    month_name = datetime(body.year, body.month, 1).strftime("%B %Y")
    summary = f"""Month: {month_name}
Total Income:  Rs.{income:,.2f}
Total Expense: Rs.{expense:,.2f}
Savings:       Rs.{income-expense:,.2f} ({round((income-expense)/income*100,1) if income>0 else 0}%)
Transactions:  {len(txns)}
Expense Breakdown:
{chr(10).join([f'  - {c}: Rs.{a:,.2f} ({round(a/expense*100,1) if expense>0 else 0}%)' for c,a in sorted_cats])}"""

    prompt = f"""Generate a detailed monthly expense report for an Indian user.

{summary}

Write a comprehensive report with these sections:
1. **Executive Summary** — Key highlights of the month
2. **Income Analysis** — Income sources and stability
3. **Expense Breakdown** — Detailed analysis of each spending category
4. **Savings Performance** — How well did they save this month?
5. **Unnecessary Expenses** — What could have been avoided?
6. **Budget Recommendations** — Suggested budget for next month
7. **Action Plan** — 3 specific things to do next month

Use Rs. for currency, be specific with numbers, use emojis, friendly tone."""

    try:
        resp = gemini.generate_content(prompt)
        return {
            "status": "ok", "month": month_name, "report": resp.text.strip(),
            "stats": {"income": income, "expense": expense, "savings": income-expense,
                      "savings_rate": round((income-expense)/income*100,1) if income>0 else 0,
                      "top_categories": sorted_cats[:5], "total_txns": len(txns)}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

# ── POST /targets/add ────────────────────────────────────
@app.post("/targets/add")
def add_target(t: Target):
    tid = str(uuid.uuid4())
    targets_col.insert_one({
        "id": tid,
        "user": t.user,
        "target_name": t.target_name,
        "target_type": t.target_type,
        "category": t.category,
        "amount": t.amount,
        "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })
    return {"status": "ok", "id": tid}

# ── GET /targets ──────────────────────────────────────────
@app.get("/targets")
def get_targets(user: str):
    if not user: raise HTTPException(status_code=400, detail="User required")
    docs = list(targets_col.find({"user": user}, {"_id": 0}))

    # Compute progress from current month's transactions
    txns = list(txns_col.find({"user": user}, {"_id": 0}))
    now  = datetime.now()

    for tgt in docs:
        cat = tgt["category"].lower().strip()
        spent  = 0.0
        earned = 0.0
        for tx in txns:
            try:
                dt = datetime.strptime(tx["created_at"], "%d %b %Y, %I:%M %p")
                if dt.month != now.month or dt.year != now.year:
                    continue
            except:
                continue
            tx_cat = tx["category"].split(" — ")[0].lower().strip()
            amt    = float(tx["amount"])
            # Match: "all" matches everything; otherwise match if tx category contains target category
            if cat == "all" or tx_cat == cat or cat in tx_cat or tx_cat in cat:
                if amt < 0:
                    spent  += abs(amt)
                else:
                    earned += amt

        tgt["progress"] = round(spent if tgt["target_type"] == "spending_limit" else earned, 2)
        tgt["pct"]      = min(100, round((tgt["progress"] / tgt["amount"]) * 100, 1)) if tgt["amount"] > 0 else 0

    return docs

# ── DELETE /targets/{id} ──────────────────────────────────
@app.delete("/targets/{target_id}")
def delete_target(target_id: str, user: str):
    result = targets_col.delete_one({"id": target_id, "user": user})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Target not found")
    return {"status": "ok"}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
