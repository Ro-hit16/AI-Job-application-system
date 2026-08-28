# 🚀 AI Job Application System

An AI-powered full-stack job application platform that helps candidates optimize their resumes, discover relevant jobs, and prepare for interviews while enabling recruiters to efficiently manage job postings and applications.

The platform integrates **Ollama** for local Large Language Model (LLM) inference, ensuring privacy without relying on external AI APIs.

---

## 📌 Features

### 👤 Candidate
- User Registration & Login
- Profile Management
- Resume Upload
- AI Resume Analysis
- ATS Score Evaluation
- Resume Improvement Suggestions
- Job Search & Filtering
- Apply for Jobs
- Track Application Status
- AI Interview Question Generation

### 🏢 Recruiter
- Recruiter Authentication
- Company Profile Management
- Create, Update & Delete Job Posts
- View Applicants
- Manage Candidate Applications
- Update Hiring Status

### 🤖 AI Features
- Resume Analysis
- ATS Compatibility Score
- Resume Feedback
- Skill Gap Identification
- Job Matching Assistance
- Interview Preparation
- Local LLM Support using Ollama

---

# 🛠 Tech Stack

## Frontend
- React
- Vite
- Tailwind CSS
- Axios

## Backend
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- Pydantic
- JWT Authentication

## AI
- Ollama
- Local LLMs (Llama, Mistral, Gemma, Qwen)

---

# 📂 Project Structure

```
job-application-system/
│
├── frontend/              # React Application
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── services/
│   │   ├── database/
│   │   ├── schemas/
│   │   ├── utils/
│   │   └── main.py
│   │
│   ├── alembic/
│   ├── uploads/
│   ├── requirements.txt
│   └── run.py
│
└── README.md
```

---

# ⚙️ Installation

## 1. Clone Repository

```bash
git clone https://github.com/yourusername/job-application-system.git

cd job-application-system
```

---

## 2. Backend Setup

```bash
cd backend
```

Create Virtual Environment

```bash
python -m venv venv
```

Activate

### Windows

```powershell
.\venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run Backend

```bash
python -m uvicorn app.main:app --reload
```

Backend runs at

```
http://127.0.0.1:8000
```

---

## 3. Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

Frontend runs at

```
http://localhost:5173
```

---

## 4. Ollama Setup

Install Ollama

https://ollama.com

Pull a model

```bash
ollama pull llama3.2
```

or

```bash
ollama pull mistral
```

or

```bash
ollama pull qwen2.5
```

Start Ollama

```bash
ollama serve
```

Verify

```bash
ollama list
```

---

# 🗄 Database

Apply migrations

```bash
alembic upgrade head
```

Create new migration

```bash
alembic revision --autogenerate -m "migration_name"
```

---

# 🔐 Environment Variables

Create a `.env` file inside `backend`.

Example:

```env
DATABASE_URL=postgresql://username:password@localhost/jobdb

SECRET_KEY=your_secret_key

ALGORITHM=HS256

ACCESS_TOKEN_EXPIRE_MINUTES=30

OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_MODEL=llama3.2
```

---

# 📸 Screenshots

Add screenshots here.

```
Home Page

Candidate Dashboard

Recruiter Dashboard

Resume Analysis

Job Listings

Interview Assistant
```

---

# 🚀 Future Improvements

- Email Notifications
- AI Cover Letter Generation
- Resume Keyword Optimization
- Interview Simulation
- Video Interview Support
- Docker Deployment
- CI/CD Pipeline
- Cloud Deployment
- Multi-language Support

---

# 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature-name
```

3. Commit changes

```bash
git commit -m "Add feature"
```

4. Push

```bash
git push origin feature-name
```

5. Create a Pull Request

---

# 📄 License

This project is licensed under the MIT License.

---

# 👨‍💻 Author

**Rohit Devkar**

- GitHub: https://github.com/Ro-hit16
- LinkedIn: www.linkedin.com/in/rohit-devkar



---

⭐ If you found this project useful, consider giving it a star!
