# CRM Booking — Project Tracker

## Project overview

| Item | Detail |
| --- | --- |
| Project name | `bookings` |
| Purpose | CRM aur booking management system |
| Framework | Django |
| Database (development) | SQLite |
| Time zone | Asia/Karachi |
| Current stage | Initial project setup complete |

## Current file structure

```text
CRM-Booking/
├── backend/                   # Django backend ka sara code
│   ├── bookings/              # Django project configuration
│   │   ├── __init__.py
│   │   ├── asgi.py            # ASGI deployment entry point
│   │   ├── settings.py        # Project settings
│   │   ├── urls.py            # Main URL routes
│   │   └── wsgi.py            # WSGI deployment entry point
│   ├── manage.py              # Django commands run karne ke liye
│   ├── requirements.txt       # Python packages
│   └── .gitignore             # Backend untracked files ki list
│   ├── accounts/              # Authentication aur user roles
│   ├── clients/               # Client CRM records
│   ├── booking/               # Booking workflows
│   ├── resources/             # Bookable resources
│   ├── payments/              # Invoices aur payments 
│   ├── dashboard/             # Dashboard summary aur stats
│   ├── notifications/         # Email/SMS/in-app alerts
│   ├── reports/               # Reporting aur analytics
│   └── core/                  # Shared backend utilities
├── frontend/                  # Frontend code (React/HTML/CSS/JS)
└── PROJECT_TRACKER.md         # Yeh tracking document
```

## Apps tracker

| App | Responsibility | Status | Notes |
| --- | --- | --- | --- |
| `accounts` | Staff/admin login, JWT aur Google Sign-In | Google auth complete | Custom User, account linking aur token verification added |
| `clients` | Client profiles aur contact details | Setup complete | CRM ka core module |
| `booking` | Booking create, update, cancel aur status | Setup complete | Main business feature |
| `resources` | Rooms, staff, services ya bookable resources | Setup complete | Booking availability ke liye |
| `payments` | Invoices aur payment records | Setup complete | Payment provider later integrate hoga |
| `dashboard` | Dashboard summary cards aur data | Setup complete | Provides key metrics for users |
| `notifications` | Email, SMS aur in-app alerts | Setup complete | Trigger rules later define honge |
| `reports` | Summary, analytics aur exports | Setup complete | Dashboard data yahan se aa sakta hai |
| `core` | Shared utilities aur common functionality | Setup complete | Reusable code ke liye |

## Setup commands

Python install hone ke baad PowerShell mein `backend` folder ke andar ye commands chalayen:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Phir browser mein `http://127.0.0.1:8000/admin/` open karein. Admin user banane ke liye:

```powershell
python manage.py createsuperuser
```

## Working rules

1. Naya Django app `backend` folder mein banega; banne par is file ke **Apps tracker** aur **Current file structure** ko update karein.
2. Har feature ko `Planned`, `In progress`, `Testing`, ya `Complete` status dein.
3. Production se pehle `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` aur database configuration update karein.

## Next recommended task

Google OAuth credentials set karke PostgreSQL par migrations run karein; detailed instructions `backend/GOOGLE_AUTH_SETUP.md` mein hain.
