# Google Sign-In backend setup

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/google/` | Google ID token ko application JWTs mein exchange karta hai |
| `POST` | `/api/auth/token/refresh/` | Refresh token se new access token deta hai |

### Request

```json
{
  "id_token": "Google Identity Services se milne wala ID token"
}
```

### Successful response

```json
{
  "access": "application-access-jwt",
  "refresh": "application-refresh-jwt",
  "user": {
    "id": 1,
    "full_name": "Ayesha Khan",
    "email": "ayesha@example.com",
    "profile_picture_url": "https://..."
  },
  "created": true
}
```

`id_token` kabhi persist ya log nahi hota. Backend Google ki signature keys use karke token signature, issuer, audience aur expiry verify karta hai. Sirf verified-email claim ke sath token accept hota hai.

## Local installation

PowerShell mein `backend` folder se:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`.env.example` se required variable names dekhein. Yeh project external dotenv package use nahi karta, is liye local PowerShell session mein environment values set karein ya deployment platform ki environment-variable settings use karein.

```powershell
$env:GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
$env:DB_NAME="crm_booking"
$env:DB_USER="postgres"
$env:DB_PASSWORD="your-password"
$env:DB_HOST="127.0.0.1"
$env:DB_PORT="5432"
python manage.py migrate
python manage.py test accounts
```

## Google Cloud Console configuration

1. Google Cloud Console mein project select/create karein aur **OAuth consent screen** configure karein.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID** mein **Web application** choose karein.
3. Future React app ke production aur local origins ko **Authorized JavaScript origins** mein add karein, for example `http://localhost:3000`.
4. Google se milne wala **Web client ID** `GOOGLE_OAUTH_CLIENT_ID` mein set karein. Client secret is ID-token verification endpoint ko required nahi hai, is liye backend code mein client secret store nahi hota.
5. Frontend Google Sign-In request mein `openid`, `email`, aur `profile` scopes request karega aur returned **ID token** is endpoint ko bhejega.

## Migration note

Yeh initial project hai, is liye `accounts.User` custom user model configured hai. Is setup ko pehli `migrate` command se pehle hi use karein. Agar database mein Django ki existing migrations/users already hain, custom-user migration safely apply karne se pehle data-migration plan zaroor banayein.

## Security notes

- `GOOGLE_OAUTH_CLIENT_ID` required hai; audience mismatch reject hota hai.
- Email address Google ke verified claim se aata hai; client payload se name/email trust nahi kiya jata.
- Email par database-level case-insensitive unique constraint duplicate accounts rokti hai.
- Existing email/password user ko new user create karne ke bajaye Google Subject ID ke sath link kiya jata hai; password/data preserve rehta hai.
- JWT access token 15 minutes aur refresh token 7 days valid hota hai. Refresh rotation aur blacklist enabled hain.
- Valid cryptographically signed Google ID tokens expiry ke baad reject ho jate hain. Google OAuth access/refresh-token revocation ka concept ID tokens par directly query nahi hota; application har sign-in par token ko server-side verify karti hai.
