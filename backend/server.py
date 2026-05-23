from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import requests
import secrets

from recommendation_engine import build_recommendations

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
TMDB_API_KEY = os.environ['TMDB_API_KEY']
TMDB_BASE_URL = os.environ['TMDB_BASE_URL']

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=15), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["id"] = str(user["_id"])
        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str = "user"
    watchlist: List[int] = []
    favorites: List[int] = []
    created_at: str

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

class RatingCreate(BaseModel):
    movie_id: int
    rating: float
    review: Optional[str] = None

class RatingResponse(BaseModel):
    id: str
    user_id: str
    user_name: str
    movie_id: int
    rating: float
    review: Optional[str]
    created_at: str

@api_router.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserRegister, response: Response):
    email = user_data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = hash_password(user_data.password)
    new_user = {
        "name": user_data.name,
        "email": email,
        "password_hash": hashed,
        "role": "user",
        "watchlist": [],
        "favorites": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.users.insert_one(new_user)
    user_id = str(result.inserted_id)
    
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return UserResponse(
        id=user_id,
        name=new_user["name"],
        email=new_user["email"],
        role=new_user["role"],
        watchlist=new_user["watchlist"],
        favorites=new_user["favorites"],
        created_at=new_user["created_at"]
    )

@api_router.post("/auth/login", response_model=UserResponse)
async def login(user_data: UserLogin, request: Request, response: Response):
    email = user_data.email.lower()
    identifier = f"{request.client.host}:{email}"
    
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        lockout_time = attempt.get("locked_until")
        if lockout_time and lockout_time > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
    
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": datetime.now(timezone.utc) + timedelta(minutes=15)}},
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    await db.login_attempts.delete_one({"identifier": identifier})
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return UserResponse(
        id=user_id,
        name=user["name"],
        email=user["email"],
        role=user.get("role", "user"),
        watchlist=user.get("watchlist", []),
        favorites=user.get("favorites", []),
        created_at=user["created_at"]
    )

@api_router.post("/auth/logout")
async def logout(response: Response, current_user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload["sub"]
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(user_id, user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
        return {"message": "Token refreshed"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@api_router.get("/movies/trending")
async def get_trending_movies():
    try:
        response = requests.get(f"{TMDB_BASE_URL}/trending/movie/week?api_key={TMDB_API_KEY}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/popular")
async def get_popular_movies():
    try:
        response = requests.get(f"{TMDB_BASE_URL}/movie/popular?api_key={TMDB_API_KEY}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/top-rated")
async def get_top_rated_movies():
    try:
        response = requests.get(f"{TMDB_BASE_URL}/movie/top_rated?api_key={TMDB_API_KEY}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/now-playing")
async def get_now_playing_movies():
    try:
        response = requests.get(f"{TMDB_BASE_URL}/movie/now_playing?api_key={TMDB_API_KEY}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/upcoming")
async def get_upcoming_movies():
    try:
        response = requests.get(f"{TMDB_BASE_URL}/movie/upcoming?api_key={TMDB_API_KEY}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/search")
async def search_movies(query: str, page: int = 1):
    try:
        response = requests.get(f"{TMDB_BASE_URL}/search/movie?api_key={TMDB_API_KEY}&query={query}&page={page}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/discover")
async def discover_movies(
    genre: Optional[str] = None,
    year: Optional[int] = None,
    sort_by: str = "popularity.desc",
    page: int = 1
):
    try:
        params = {"api_key": TMDB_API_KEY, "sort_by": sort_by, "page": page}
        if genre:
            params["with_genres"] = genre
        # TMDB primary_release_year must be a real calendar year
        if year is not None:
            y_max = datetime.now(timezone.utc).year + 8
            if year < 1874 or year > y_max:
                year = None
        if year is not None:
            params["primary_release_year"] = year
        response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/movies/{movie_id}")
async def get_movie_details(movie_id: int):
    try:
        response = requests.get(f"{TMDB_BASE_URL}/movie/{movie_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos,similar")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/genres")
async def get_genres():
    try:
        response = requests.get(f"{TMDB_BASE_URL}/genre/movie/list?api_key={TMDB_API_KEY}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/watchlist/{movie_id}")
async def add_to_watchlist(movie_id: int, current_user: dict = Depends(get_current_user)):
    user_id = ObjectId(current_user["id"])
    await db.users.update_one(
        {"_id": user_id},
        {"$addToSet": {"watchlist": movie_id}}
    )
    return {"message": "Added to watchlist"}

@api_router.delete("/watchlist/{movie_id}")
async def remove_from_watchlist(movie_id: int, current_user: dict = Depends(get_current_user)):
    user_id = ObjectId(current_user["id"])
    await db.users.update_one(
        {"_id": user_id},
        {"$pull": {"watchlist": movie_id}}
    )
    return {"message": "Removed from watchlist"}

@api_router.get("/watchlist")
async def get_watchlist(current_user: dict = Depends(get_current_user)):
    return {"watchlist": current_user.get("watchlist", [])}

@api_router.post("/favorites/{movie_id}")
async def add_to_favorites(movie_id: int, current_user: dict = Depends(get_current_user)):
    user_id = ObjectId(current_user["id"])
    await db.users.update_one(
        {"_id": user_id},
        {"$addToSet": {"favorites": movie_id}}
    )
    return {"message": "Added to favorites"}

@api_router.delete("/favorites/{movie_id}")
async def remove_from_favorites(movie_id: int, current_user: dict = Depends(get_current_user)):
    user_id = ObjectId(current_user["id"])
    await db.users.update_one(
        {"_id": user_id},
        {"$pull": {"favorites": movie_id}}
    )
    return {"message": "Removed from favorites"}

@api_router.post("/ratings", response_model=RatingResponse)
async def create_rating(rating_data: RatingCreate, current_user: dict = Depends(get_current_user)):
    if rating_data.rating < 0 or rating_data.rating > 10:
        raise HTTPException(status_code=400, detail="Rating must be between 0 and 10")
    
    existing = await db.ratings.find_one({"user_id": current_user["id"], "movie_id": rating_data.movie_id})
    if existing:
        await db.ratings.update_one(
            {"_id": existing["_id"]},
            {"$set": {"rating": rating_data.rating, "review": rating_data.review, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        rating_id = str(existing["_id"])
    else:
        new_rating = {
            "user_id": current_user["id"],
            "user_name": current_user["name"],
            "movie_id": rating_data.movie_id,
            "rating": rating_data.rating,
            "review": rating_data.review,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        result = await db.ratings.insert_one(new_rating)
        rating_id = str(result.inserted_id)
    
    return RatingResponse(
        id=rating_id,
        user_id=current_user["id"],
        user_name=current_user["name"],
        movie_id=rating_data.movie_id,
        rating=rating_data.rating,
        review=rating_data.review,
        created_at=datetime.now(timezone.utc).isoformat()
    )

@api_router.get("/ratings/movie/{movie_id}", response_model=List[RatingResponse])
async def get_movie_ratings(movie_id: int):
    ratings = await db.ratings.find({"movie_id": movie_id}, {"_id": 0}).to_list(100)
    return [RatingResponse(id=str(r.get("_id", "")), **r) for r in ratings]

@api_router.get("/recommendations")
async def get_recommendations(
    current_user: dict = Depends(get_current_user),
    type: str = "hybrid",
    mood: Optional[str] = None,
):
    """Hybrid / content (TF-IDF+cosine) / collaborative / mood — query: ?type=&mood="""
    t = (type or "hybrid").lower().strip()
    if t not in ("hybrid", "content", "collaborative", "mood"):
        t = "hybrid"

    raw_ratings = await db.ratings.find({}).to_list(10000)
    ratings_list = []
    for r in raw_ratings:
        uid = r.get("user_id")
        ratings_list.append({
            "user_id": str(uid) if uid is not None else "",
            "movie_id": r.get("movie_id"),
            "rating": r.get("rating"),
        })

    try:
        data = build_recommendations(
            user_id=current_user["id"],
            watchlist=list(current_user.get("watchlist") or []),
            favorites=list(current_user.get("favorites") or []),
            ratings=ratings_list,
            api_key=TMDB_API_KEY,
            base_url=TMDB_BASE_URL,
            rec_type=t,
            mood=mood,
            limit=20,
        )
        if data.get("results"):
            return data
    except Exception as e:
        logger.exception("recommendations engine: %s", e)

    return await get_trending_movies()

app.include_router(api_router)
@app.get("/")
async def health_check():
    return {"status": "ok", "service": "cineverse-backend"}

def _cors_origins() -> List[str]:
    raw = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    parts = [o.strip() for o in raw.split(",") if o.strip()]
    return parts if parts else ["http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.ratings.create_index([("user_id", 1), ("movie_id", 1)], unique=True)
    
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@movieapp.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Admin",
            "role": "admin",
            "watchlist": [],
            "favorites": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
    
    mem_dir = ROOT_DIR / "memory"
    mem_dir.mkdir(exist_ok=True)
    with open(mem_dir / "test_credentials.md", "w") as f:
        f.write(f"# Test Credentials\n\n")
        f.write(f"## Admin Account\n")
        f.write(f"- Email: {admin_email}\n")
        f.write(f"- Password: {admin_password}\n")
        f.write(f"- Role: admin\n\n")
        f.write(f"## Auth Endpoints\n")
        f.write(f"- POST /api/auth/register\n")
        f.write(f"- POST /api/auth/login\n")
        f.write(f"- GET /api/auth/me\n")
        f.write(f"- POST /api/auth/logout\n")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()