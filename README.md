# 🧾 Receipt Extractor

**AI-Powered Receipt Data Extraction System** — Part 1 of the Expense Automation Platform.

An end-to-end system that accepts receipt images/PDFs, extracts structured information using OCR and a Vision LLM, validates the data, stores it in a local database, and displays it through a frontend dashboard.

---

## ✨ Features

- **Multi-format Upload**: Supports PNG, JPG, JPEG, and PDF receipts
- **Hybrid Extraction Engine**: Combines EasyOCR (local) with OpenRouter Vision LLM for accurate data extraction
- **Structured Data Output**: Extracts merchant name, date, line items, subtotal, tax, tip, and total
- **Pydantic Validation**: Schema validation + business logic checks (arithmetic consistency, negative amounts, etc.)
- **SQLite Persistence**: Stores extracted data in structured columns AND complete JSON
- **Dashboard Analytics**: Total receipts, expenses, success rates at a glance
- **Receipt History**: Browse, search, and view previously processed receipts
- **Retry Logic**: Automatic retry with validation feedback for failed extractions
- **Error Handling**: Structured exceptions, controlled retries, no exposed internals

---

## 🏗️ Architecture

```
Streamlit Frontend
        |
        | HTTP REST API (HTTPX)
        v
FastAPI Backend
        |
        v
File Processing Layer (Pillow, PyMuPDF)
        |
        v
Hybrid Extraction Engine
        |
        |---- EasyOCR (Local OCR)
        |
        |---- OpenRouter (Vision LLM)
        |
        v
Structured JSON Extraction
        |
        v
Pydantic Validation + Business Rules
        |
        v
SQLite Database (SQLAlchemy ORM)
        |
        v
Frontend Dashboard + History
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI |
| API Communication | HTTPX |
| OCR | EasyOCR |
| AI Inference | OpenRouter Vision LLM |
| Image Processing | Pillow |
| PDF Processing | PyMuPDF |
| Validation | Pydantic |
| Database | SQLite |
| ORM | SQLAlchemy |
| Configuration | python-dotenv |
| Logging | Python logging |
| Testing | Pytest |

---

## 📁 Project Structure

```
receipt-extractor/
│
├── frontend/
│   ├── app.py                    # Streamlit main application
│   ├── api_client.py             # HTTPX client for backend API
│   └── components/
│       ├── upload.py             # File upload widget
│       ├── receipt_display.py    # Extraction result display
│       └── receipt_history.py    # Receipt history table
│
├── backend/
│   ├── main.py                   # FastAPI application entry point
│   ├── api/
│   │   └── receipt_routes.py     # REST API endpoints
│   ├── services/
│   │   ├── file_service.py       # File validation and saving
│   │   ├── preprocessing_service.py  # Image/PDF preprocessing
│   │   ├── ocr_service.py        # EasyOCR integration
│   │   ├── llm_service.py        # OpenRouter LLM integration
│   │   ├── extraction_service.py # Pipeline orchestrator
│   │   └── validation_service.py # Business validation rules
│   ├── database/
│   │   ├── connection.py         # SQLAlchemy engine and session
│   │   ├── models.py             # ORM models (Receipt, ReceiptItem)
│   │   └── repository.py        # Data access layer (CRUD)
│   ├── schemas/
│   │   └── receipt_schema.py     # Pydantic schemas
│   ├── utils/
│   │   ├── config.py             # Centralized configuration
│   │   ├── logger.py             # Logging setup
│   │   └── exceptions.py        # Custom exception classes
│   └── uploads/                  # Uploaded files (gitignored)
│
├── tests/
│   ├── test_api.py               # API endpoint tests
│   ├── test_extraction.py        # OCR/LLM extraction tests
│   ├── test_validation.py        # Pydantic and business validation tests
│   └── test_database.py          # Database operation tests
│
├── .env.example                  # Environment variable template
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── pytest.ini                    # Pytest configuration
├── run.py                        # Application launcher
└── README.md                     # This file
```

---

## 🚀 Setup Instructions

### Prerequisites

- Python 3.11+ (tested with Python 3.12.10)
- Git
- An OpenRouter API key (free tier available)

### Windows Setup

```powershell
# Clone the repository
git clone <repository-url>
cd receipt-extractor

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
python -m pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your OpenRouter API key
```

### Linux/macOS Setup

```bash
# Clone the repository
git clone <repository-url>
cd receipt-extractor

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
python -m pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your OpenRouter API key
```

---

## ⚙️ Configuration

### OpenRouter Setup

1. Sign up at [https://openrouter.ai](https://openrouter.ai)
2. Get a free API key from the dashboard
3. Set it in your `.env` file:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### Model Configuration

The default model is `google/gemini-2.0-flash-exp:free` — a free Vision model on OpenRouter.

To use a different free Vision model, update:

```env
OPENROUTER_MODEL=your-chosen-model-id
```

**Important**: Verify the model supports image/vision input before configuring it.

### Other Configuration

```env
DATABASE_URL=sqlite:///./receipts.db
MAX_UPLOAD_SIZE_MB=10
MAX_PDF_PAGES=5
OCR_LANGUAGE=en
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=8501
```

---

## ▶️ Running the Application

### Option 1: Using run.py (starts both servers)

```bash
python run.py
```

### Option 2: Manual startup (separate terminals)

**Terminal 1 — Backend:**

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Frontend:**

```bash
streamlit run frontend/app.py
```

### Access Points

| Service | URL |
|---|---|
| Frontend Dashboard | http://127.0.0.1:8501 |
| Backend API | http://127.0.0.1:8000 |
| Swagger Documentation | http://127.0.0.1:8000/docs |
| Health Check | http://127.0.0.1:8000/health |

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/upload` | Upload and process a receipt |
| `GET` | `/receipts` | List all receipts |
| `GET` | `/receipts/{id}` | Get receipt details |
| `DELETE` | `/receipts/{id}` | Delete a receipt |
| `GET` | `/stats` | Dashboard statistics |

### POST /upload

**Request**: Multipart form data with `file` field.

**Response** (200):

```json
{
  "id": 1,
  "filename": "receipt.png",
  "merchant_name": "Target Stores",
  "date": "2026-02-18",
  "line_items": [
    {"item_name": "Wireless Mouse", "price": "24.99"}
  ],
  "subtotal": "24.99",
  "tax": "2.00",
  "tip": null,
  "total_amount": "26.99",
  "status": "COMPLETED",
  "warnings": [],
  "created_at": "2026-02-18T10:30:00"
}
```

---

## 🗄️ Database Design

### receipts table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment ID |
| filename | VARCHAR(255) | Stored filename |
| file_path | VARCHAR(500) | Server file path |
| merchant_name | VARCHAR(255) | Extracted merchant |
| date | DATE | Receipt date |
| subtotal | NUMERIC(10,2) | Subtotal amount |
| tax | NUMERIC(10,2) | Tax amount |
| tip | NUMERIC(10,2) | Tip amount |
| total_amount | NUMERIC(10,2) | Total amount |
| extracted_json | TEXT | Complete extraction JSON |
| raw_ocr_text | TEXT | Raw OCR output |
| status | VARCHAR(50) | Processing status |
| created_at | DATETIME | Record creation time |

### receipt_items table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment ID |
| receipt_id | INTEGER FK | References receipts.id |
| item_name | VARCHAR(500) | Line item name |
| price | NUMERIC(10,2) | Item price |

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test module
python -m pytest tests/test_validation.py -v

# Run with coverage (if installed)
python -m pytest tests/ -v --tb=short
```

All tests mock external dependencies (OpenRouter API, EasyOCR) and use temporary SQLite databases — no API key or inference credits required.

---

## 🔮 Future: Part 2 — Multi-Agent Expense Dispatcher

The architecture is designed for extension. Part 2 will add:

- **Expense Agent**: Categorizes expenses by type
- **Summary Agent**: Generates expense reports
- **Excel Recipient Reader**: Reads recipient lists from Excel
- **Email Dispatcher**: Sends expense reports via Gmail/SMTP

The existing extraction engine, database layer, and API are fully reusable — no architectural changes required.

---

## 📝 Limitations

- EasyOCR model downloads on first run (~100MB)
- OpenRouter free models may have rate limits
- Single receipt processing is synchronous
- PDF processing limited to 5 pages by default
- No authentication on the API (suitable for local use)

---

## 📄 License

This project is built as a technical assessment for an AI Engineer / Full-Stack ML Intern position.

