# 💰 ETMS — Expense Tracker Management System

A full-stack personal finance web app built with **FastAPI + MongoDB** and a vanilla JS frontend. ETMS lets you track income and expenses, import bank statements, split group expenses, detect fraudulent SMS/emails, and get AI-powered financial insights using **Google Gemini**.

---

## ✨ Features

### 💳 Core Tracking
- **Auth** — register with profile details (income, budget, savings goal, currency) or log in; passwords are hashed before storage
- **Transactions** — add income/expense entries, delete them, and view live balance, income and expense stats
- **Targets** — set *savings* goals or *spending limits* per category (or `all`) and see monthly progress in real time

### 🤖 AI-Powered
- **Smart Import (SMS/Email)** — paste a bank message and Gemini extracts type, amount, category and date
- **Spending Analysis** — AI breakdown of necessary vs. unnecessary spending, saving tips and a financial health score
- **AOS (AI Financial Assistant)** — chat assistant for budgeting, investing, tax and savings questions, with per-user chat history, saved financial context and typo/Hinglish-tolerant input
- **AI Monthly Report** — executive summary, income/expense analysis, savings performance and next-month action plan

### 📊 Reports
- Month/year report with **doughnut, bar and line charts** (Chart.js) and a ranked category table
- **PDF export** of monthly reports (generated server-side with ReportLab)

### 📥 Statement Import
- Upload **PDF, CSV, XLSX or XLS** bank statements
- Auto-parses rows, categorizes transactions (rule-based + AI), skips duplicates, and applies a minimum-amount filter
- Preview before import, plus an **import history** log

### 🛡️ Fraud Detector
- Paste suspicious SMS/email text (or upload a file) and get a risk score
- Multi-layer analysis: context neutralizers → pattern detection (10 categories) → structural analysis → combination scoring → safe-signal checks
- Optional AI second opinion and **downloadable PDF fraud report**

### 👥 Split Expenses
- Create groups, add shared expenses, choose who paid and who splits
- Automatic net-balance calculation with **simplified debt settlement** suggestions
- Record settle-ups and delete expenses/groups

---

## 🧰 Tech Stack

| Layer     | Technology                                           |
|-----------|------------------------------------------------------|
| Backend   | Python, FastAPI, Pydantic, Uvicorn                   |
| Database  | MongoDB (PyMongo)                                    |
| AI        | Google Gemini 2.0 Flash (`google-genai`)             |
| Parsing   | pdfplumber, pandas, openpyxl, xlrd                   |
| PDF       | ReportLab                                            |
| Frontend  | HTML, CSS, JavaScript, Chart.js                      |

---

## 📁 Project Structure

```
ETMS/
├── app.py                # FastAPI backend (all routes, AI + fraud + import logic)
├── requirements.txt      # Python dependencies
├── ETMS-EXPLANATION.md   # Detailed walkthrough of the project
├── .env                  # Secrets (not committed)
└── static/
    ├── index.html        # UI: login, dashboard, reports, AOS, fraud, splits, targets, upload
    ├── style.css         # Styling
    └── script.js         # Frontend logic and API calls
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- MongoDB running locally (or a MongoDB Atlas URI)
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/Ojashwee07/ETMS.git
cd ETMS

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
MONGO_URI=mongodb://localhost:27017
GEMINI_API_KEY=your_gemini_api_key_here
```

| Variable         | Description                                   | Default                     |
|------------------|-----------------------------------------------|-----------------------------|
| `MONGO_URI`      | MongoDB connection string                     | `mongodb://localhost:27017` |
| `GEMINI_API_KEY` | Google Gemini API key for all AI features     | —                           |

### Run

```bash
# Make sure MongoDB is running, then:
uvicorn app:app --reload
```

Open **http://localhost:8000** in your browser. Interactive API docs are available at **http://localhost:8000/docs**.

---

## 🌐 API Reference

| Method | Endpoint                                | Description                              |
|--------|-----------------------------------------|------------------------------------------|
| POST   | `/register`                             | Create a new account with profile        |
| POST   | `/login`                                | Log in                                   |
| POST   | `/add`                                  | Add a transaction                        |
| GET    | `/data?user=`                           | List a user's transactions               |
| DELETE | `/delete/{id}?user=`                    | Delete a transaction                     |
| GET    | `/stats?user=`                          | Income / expense / balance totals        |
| POST   | `/ai/extract`                           | Extract a transaction from SMS/email     |
| POST   | `/ai/analyze`                           | AI spending analysis                     |
| GET    | `/report/data?user=&month=&year=`       | Monthly chart data                       |
| POST   | `/ai/report`                            | Generate AI monthly report               |
| POST   | `/report/pdf`                           | Download monthly report as PDF           |
| POST   | `/targets/add`                          | Create a savings goal / spending limit   |
| GET    | `/targets?user=`                        | List targets with current progress       |
| DELETE | `/targets/{id}?user=`                   | Delete a target                          |
| POST   | `/fraud/analyze`                        | Analyze text/file for fraud indicators   |
| POST   | `/fraud/pdf`                            | Download fraud analysis report           |
| POST   | `/aos/chat`                             | Chat with the AI financial assistant     |
| GET    | `/aos/history?user=`                    | Get saved chat history                   |
| POST   | `/aos/history/save`                     | Save chat history                        |
| GET    | `/aos/context?user=`                    | Get saved financial context              |
| POST   | `/aos/context/save`                     | Save financial context                   |
| POST   | `/upload-file`                          | Parse an uploaded statement (PDF/CSV/XLS)|
| POST   | `/import-transactions`                  | Import parsed transactions               |
| GET    | `/import-history?user=`                 | View import history                      |
| POST   | `/splits/create`                        | Create a split group                     |
| GET    | `/splits?user=`                         | List a user's groups and balances        |
| POST   | `/splits/add-expense`                   | Add a shared expense                     |
| DELETE | `/splits/expense/{group_id}/{expense_id}` | Delete a shared expense                |
| POST   | `/splits/settle`                        | Record a settlement                      |
| DELETE | `/splits/group/{group_id}`              | Delete a group                           |

---

## 🗄️ Database

**Database:** `etms_db`

| Collection         | Purpose                                   |
|--------------------|-------------------------------------------|
| `users`            | Accounts and profile details              |
| `transactions`     | Income/expense records                    |
| `targets`          | Savings goals and spending limits         |
| `aos_chat_history` | AI assistant conversation history         |
| `aos_user_context` | Saved financial context per user          |
| `aos_learned_qa`   | Stored Q&A pairs for the AI assistant     |
| `import_history`   | Log of statement imports                  |
| `splits_groups`    | Split groups, expenses and settlements    |

> Amounts are stored signed: **income is positive, expense is negative**.

---

## 👤 Author

**Ojashwee**
- GitHub: [@Ojashwee07](https://github.com/Ojashwee07)
- LinkedIn: [ojashweetech](https://www.linkedin.com/in/ojashweetech)
